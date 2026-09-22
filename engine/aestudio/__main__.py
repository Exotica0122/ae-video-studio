"""ae-video-studio command line: python3 -m aestudio <command> ..."""
import argparse
import json
import sys
import time
from pathlib import Path

from .audiopost import AudioPostError, build as build_audio, merge_into
from .bridge import Bridge, BridgeError
from .compiler import CompileError, compile_plan
from .components.layout import LayoutError
from .design import DesignError, load_design
from .doctor import DoctorError, format_report, run_checks
from .designgen import DesignGenError, Draft, propose, save_design, style_frame_plan
from .footage import log_footage
from .grade import (GradeError, exposure_offsets, grade_plan, load_looks, looks_for,
                     render_look_previews, save_grade)
from .fonts import FontError, installed_files, is_installed, load_catalogue
from .jsx import emit_script, still_script
from .media import MediaError, probe
from .ops import OpsError
from .plan import PlanError, load_plan
from .project import ProjectError, gates, init_project, next_gate, record_decision
from .preview import PreviewError, read_choice, serve, wait_for_choice
from .render import RenderError, render
from .styleframe import render_mockups
from .timing import TimingError
from .videoqa import (QAError, QAReport, decode_check, legibility, mix_loudness,
                      music_before_voice, section_loudness, sfx_audible, share_copy,
                      stills as qa_stills, stream_check, write_report)
from .transcribe import TranscribeError, import_transcript, transcribe as run_transcribe

KNOWN = (PlanError, DesignError, DoctorError, ProjectError, AudioPostError, QAError, GradeError, TimingError, LayoutError, OpsError, CompileError, BridgeError, RenderError, MediaError, TranscribeError, DesignGenError, PreviewError, FontError, json.JSONDecodeError, OSError)


def _compile(a) -> Path:
    plan = load_plan(a.plan)
    if a.name:
        plan.name = a.name
    design = load_design(a.design)
    ops = compile_plan(plan, design)
    if a.project:
        project = Path(a.project).resolve()
    else:
        project = plan.project or (plan.root / "build" / f"{plan.name}.aep").resolve()
    project.parent.mkdir(parents=True, exist_ok=True)
    out = Path(a.out).resolve() if a.out else plan.root / "build" / f"{plan.name}.jsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(emit_script(ops, project=str(project)), encoding="utf-8")
    print(json.dumps({"jsx": str(out), "ops": len(ops), "fonts": sorted(design.fonts())}, ensure_ascii=False))
    return out


def _report_ok(result) -> bool:
    return isinstance(result, dict) and result.get("ok") is True and not result.get("error")


def cmd_validate(a):
    plan, design = load_plan(a.plan), load_design(a.design)
    print(json.dumps({"name": plan.name, "duration": plan.format.duration, "shots": len(plan.shots), "voices": len(plan.voices),
                      "graphics": len(plan.graphics), "design": design.id, "fonts": sorted(design.fonts())}, ensure_ascii=False))
    return 0


def cmd_compile(a):
    _compile(a)
    return 0


def cmd_run(a):
    result = Bridge().run(Path(a.jsx).read_text(encoding="utf-8"), timeout=a.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if _report_ok(result) else 1


def cmd_build(a):
    a.jsx = str(_compile(a))
    return cmd_run(a)


def cmd_still(a):
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    result = Bridge().run(still_script(a.comp, a.time, str(out)), timeout=a.timeout)
    if not _report_ok(result):
        print(json.dumps(result), file=sys.stderr)
        return 1
    deadline, last = time.monotonic() + 60, -1
    while time.monotonic() < deadline:            # saveFrameToPng returns before the file is written
        size = out.stat().st_size if out.exists() else -1
        if size > 0 and size == last:
            print(str(out))
            return 0
        last = size
        time.sleep(1)
    print(f"error: frame was not written to {out}", file=sys.stderr)
    return 1


def cmd_render(a):
    print(str(render(a.project, a.comp, a.out, rs=a.rs, om=a.om, allow_running_ae=a.allow_running_ae)))
    return 0


def cmd_log_footage(a):
    log = log_footage(a.sources, a.out, every=a.every, max_frames=a.max_frames)
    print(json.dumps({"clips": len(log["clips"]), "audio": len(log["audio"]), "images": len(log["images"]),
                      "errors": len(log["errors"]), "out": str(Path(a.out).resolve())}, ensure_ascii=False))
    return 0


def _print_transcript(out, result):
    print(json.dumps({"out": str(Path(out).resolve()), "words": len(result["words"]),
                      "onset": result["onset"], "offset": result["offset"]}, ensure_ascii=False))
    return 0


def cmd_transcribe(a):
    return _print_transcript(a.out, run_transcribe(a.audio, a.out, template=a.cmd))


def cmd_import_transcript(a):
    return _print_transcript(a.out, import_transcript(a.src, a.out))


def _load_log(analysis):
    analysis = Path(analysis).resolve()
    log = json.loads((analysis / "footage.json").read_text(encoding="utf-8"))
    log["root"] = str(analysis)
    return log


def _script_lines(path):
    """--lines: a JSON array of caption lines (docs/components.md), e.g. [["작은 "], [{"hl": "한 걸음"}]]."""
    if not path:
        return None
    lines = json.loads(Path(path).read_text(encoding="utf-8"))
    ok = isinstance(lines, list) and lines and all(
        isinstance(line, list) and line and all(isinstance(seg, str) or
                                                (isinstance(seg, dict) and isinstance(seg.get("hl"), str))
                                                for seg in line)
        for line in lines)
    if not ok:
        raise DesignGenError(f'{path}: expected a JSON array of caption lines, '
                             'e.g. [["작은 "], [{"hl": "한 걸음"}, "에서"]]')
    return lines


def _drafts_from_dir(directory):
    recipes = json.loads((Path(directory) / "drafts.json").read_text(encoding="utf-8"))
    drafts = []
    for raw in recipes:
        recipe = dict(raw)
        notes = recipe.pop("_notes", [])
        drafts.append(Draft(id=recipe["id"], name=recipe.get("name", recipe["id"]), mood=recipe.get("mood", []),
                            recipe=recipe,
                            fonts=_fonts_of(recipe, directory),
                            notes=list(notes)))
    return drafts


def _font_warnings(design) -> dict:
    """{family: warning} for every font the design needs and this machine does not have.
    After Effects substitutes a missing font silently, so say so before anything is built."""
    catalogue, files, out = load_catalogue(), installed_files(), {}
    for name in sorted(design.fonts()):
        font = next((f for f in catalogue if name in f.postscript.values()), None)
        if font is None:
            out[name] = f"{name} is not in the font catalogue — check it is installed before building"
        elif not is_installed(font, files):
            out[font.family] = f"install {font.family} first ({name}): {font.licence} — {font.url}"
    return out


def _pick(directory, draft_id):
    drafts = _drafts_from_dir(directory)
    choice = read_choice(directory) or {}
    wanted = draft_id or choice.get("id")
    if not wanted:
        raise DesignGenError(f"no design chosen yet — run `design-preview --dir {directory}` and click one, "
                             "or pass --id")
    for draft in drafts:
        if draft.id == wanted:
            return draft, choice.get("note")
    raise DesignGenError(f"draft '{wanted}' is not in {Path(directory) / 'drafts.json'}")


def cmd_design_propose(a):
    log = _load_log(a.analysis)
    drafts = propose(a.mood, log=log, scripts=tuple(a.scripts), installed_only=not a.allow_uninstalled_fonts,
                     limit=a.limit, pairings=a.pairings)
    index = render_mockups(drafts, log, a.out, script_lines=_script_lines(a.lines))
    print(json.dumps({"drafts": [d.id for d in drafts], "index": str(index),
                      "notes": [n for d in drafts for n in d.notes]}, ensure_ascii=False))
    return 0


def cmd_design_preview(a):
    server, url = serve(a.dir, port=a.port)
    (Path(a.dir) / "url.json").write_text(json.dumps({"url": url}), encoding="utf-8")
    print(json.dumps({"url": url, "waiting": not a.no_wait}, ensure_ascii=False), flush=True)
    if a.no_wait:
        return 0
    choice = wait_for_choice(server, a.dir, timeout=a.timeout, poll=a.poll)
    print(json.dumps({"chosen": (choice or {}).get("id"), "note": (choice or {}).get("note"), "url": url},
                     ensure_ascii=False))
    return 0 if choice else 1


def _fonts_of(recipe: dict, where) -> dict:
    """Read the type tokens of a saved draft, blaming the file rather than the traceback.

    drafts.json is written by design-propose but users do hand-edit it, and a role missing
    its 'font' used to surface as a bare KeyError.
    """
    roles = recipe.get("tokens", {}).get("type", {})
    missing = [role for role, spec in roles.items() if not isinstance(spec, dict) or not spec.get("font")]
    if missing:
        raise DesignGenError(f"{Path(where) / 'drafts.json'}: draft '{recipe.get('id', '?')}' has no font "
                             f"for {', '.join(sorted(missing))}")
    return {role: spec["font"] for role, spec in roles.items()}


def cmd_design_choose(a):
    draft, note = _pick(a.dir, a.id)
    path = save_design(draft, a.out)
    warnings = list(dict.fromkeys(draft.notes))
    for family, warning in _font_warnings(load_design(path)).items():
        if not any(f"install {family} first" in note for note in warnings):
            warnings.append(warning)                # the draft's own note already covers this font
    for line in warnings:
        print(f"warning: {line}", file=sys.stderr)
    print(json.dumps({"design": str(path), "id": draft.id, "note": note, "warnings": warnings},
                     ensure_ascii=False))
    return 0


def cmd_design_styleplan(a):
    draft, _ = _pick(a.dir, a.id)
    plan_path = style_frame_plan(draft, _load_log(a.analysis), a.out, script_lines=_script_lines(a.lines))
    print(json.dumps({"plan": str(plan_path),
                      "name": json.loads(Path(plan_path).read_text(encoding="utf-8"))["name"]}, ensure_ascii=False))
    return 0


def cmd_doctor(a):
    fonts = None
    if a.design:
        fonts = sorted(load_design(a.design).fonts())
    report = run_checks(bridge_root=a.bridge_dir, design=fonts, ping=a.ping)
    if a.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(report))
    return 1 if report.failures else 0


def cmd_init(a):
    created = init_project(a.dir)
    nxt = next_gate(a.dir)
    print(json.dumps({"root": str(Path(a.dir).expanduser().resolve()), "created": created,
                      "next_gate": None if nxt is None else {"gate": nxt.number, "label": nxt.label}},
                     ensure_ascii=False))
    return 0


def cmd_status(a):
    rows = gates(a.dir)
    if a.json:
        print(json.dumps({"gates": [{"gate": g.number, "label": g.label, "artifact": g.artifact,
                                     "done": g.done, "state": g.state} for g in rows]},
                         ensure_ascii=False, indent=2))
        return 0
    mark = {"done": "x", "recorded": "~", "todo": " "}
    for g in rows:
        note = "  (decided, artifact not written yet)" if g.state == "recorded" else ""
        print(f"[{mark[g.state]}] gate {g.number} {g.label:<14} {g.artifact}{note}")
    nxt = next_gate(a.dir)
    print(f"\nNext: gate {nxt.number} ({nxt.label})" if nxt else "\nAll gates done.")
    return 0


def cmd_decide(a):
    print(str(record_decision(a.dir, a.gate, a.what, a.detail or "")))
    return 0


def cmd_audio_plan(a):
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    root = a.root or Path(a.spec).parent
    audio = build_audio(spec, root, start=a.start, target=a.target)
    if a.merge:
        plan_path = Path(a.merge)
        merged = merge_into(json.loads(plan_path.read_text(encoding="utf-8")), audio)
        plan_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        out = plan_path
    else:
        out = Path(a.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(audio, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "voices": len(audio["voices"]),
                      "duration": audio["duration"],
                      "gains": {v["id"]: v["gain_db"] for v in audio["voices"]}}, ensure_ascii=False))
    return 0


def _voice_spans(plan: dict) -> list:
    """Where each voice actually speaks, preferring the span audio-post measured."""
    out = []
    for v in plan.get("voices") or []:
        if isinstance(v.get("speech"), list) and len(v["speech"]) == 2:
            out.append((float(v["speech"][0]), float(v["speech"][1])))
        elif v.get("at") is not None:
            out.append((float(v["at"]), float(v["at"]) + 2.0))
    return sorted(out)


def cmd_qa(a):
    export = Path(a.export)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8")) if a.plan else {}
    report = QAReport(export=str(export))
    report.findings.append(decode_check(export))
    report.findings += stream_check(export)
    report.findings += mix_loudness(export, target=a.target)
    if a.sections:
        report.findings += section_loudness(export, json.loads(Path(a.sections).read_text(encoding="utf-8")),
                                            target=a.target)
    spans = _voice_spans(plan)
    if spans:
        report.findings += music_before_voice(export, spans, probe(export).duration)
    if plan.get("sfx"):
        report.findings += sfx_audible(export, plan["sfx"], spans=spans)
    if a.design:
        report.findings += legibility(load_design(a.design))
    extras = {}
    qa_dir = Path(a.out)
    if a.stills:
        times = [float(t) for t in a.stills.split(",") if t.strip()]
        made = qa_stills(export, times, qa_dir / "stills")
        extras["Stills"] = ", ".join(f"`{p.name}`" for p in made)
    if a.share:
        copy = share_copy(export, Path(a.share))
        extras["Share copy"] = f"`{copy}` ({copy.stat().st_size / 1e6:.1f} MB)"
    out = write_report(qa_dir, report, extras)
    print(json.dumps({"report": str(out), "failed": len(report.failures),
                      "warnings": len(report.warnings), "checks": len(report.findings)},
                     ensure_ascii=False))
    return 1 if report.failures else 0


def cmd_grade_propose(a):
    log = _load_log(a.analysis)
    looks = looks_for(a.mood, limit=a.limit)
    index = render_look_previews(looks, log, a.out)
    match = exposure_offsets(log)
    print(json.dumps({"looks": [l.id for l in looks], "index": str(index),
                      "target_luma": match["target_luma"],
                      "beyond_match": [b["name"] for b in match["beyond_match"]]}, ensure_ascii=False))
    return 0


def cmd_grade_choose(a):
    choice = read_choice(a.dir) or {}
    look_id = a.id or choice.get("id")
    if not look_id:
        raise GradeError(f"no look chosen yet in {a.dir} — run grade-preview and click one, or pass --id")
    look = next((l for l in load_looks() if l.id == look_id), None)
    if look is None:
        raise GradeError(f"unknown look '{look_id}'")
    log = _load_log(a.analysis)
    match = exposure_offsets(log, target=a.target_luma)
    path = save_grade(grade_plan(look, match, design_hint=a.design_hint or ""), a.out)
    for clip in match["beyond_match"]:
        print(f"warning: {clip['name']} is {clip['stops']:+.2f} stops from the match target "
              f"(luma {clip['luma']:.3f}) — clamped; consider excluding or relighting it", file=sys.stderr)
    print(json.dumps({"grade": str(path), "look": look.id, "note": choice.get("note"),
                      "matched": len(match["offsets"]), "beyond_match": len(match["beyond_match"])},
                     ensure_ascii=False))
    return 0


def parser():
    p = argparse.ArgumentParser(prog="aestudio")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("plan")
    v.add_argument("--design", required=True)
    v.set_defaults(fn=cmd_validate)
    for name, fn in (("compile", cmd_compile), ("build", cmd_build)):
        c = sub.add_parser(name)
        c.add_argument("plan")
        c.add_argument("--design", required=True)
        c.add_argument("--name")
        c.add_argument("--project")
        c.add_argument("--out")
        c.add_argument("--timeout", type=float, default=900)
        c.set_defaults(fn=fn)
    r = sub.add_parser("run")
    r.add_argument("jsx")
    r.add_argument("--timeout", type=float, default=900)
    r.set_defaults(fn=cmd_run)
    s = sub.add_parser("still")
    s.add_argument("--comp", required=True)
    s.add_argument("--time", type=float, required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--timeout", type=float, default=120)
    s.set_defaults(fn=cmd_still)
    e = sub.add_parser("render")
    e.add_argument("--project", required=True)
    e.add_argument("--comp", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--rs", default="Best Settings")
    e.add_argument("--om", default="High Quality")
    e.add_argument("--allow-running-ae", action="store_true")
    e.set_defaults(fn=cmd_render)
    lf = sub.add_parser("log-footage")
    lf.add_argument("sources", nargs="+")
    lf.add_argument("--out", required=True)
    lf.add_argument("--every", type=float, default=4.0)
    lf.add_argument("--max-frames", type=int, default=6, dest="max_frames")
    lf.set_defaults(fn=cmd_log_footage)
    tr = sub.add_parser("transcribe")
    tr.add_argument("audio")
    tr.add_argument("--out", required=True)
    tr.add_argument("--cmd")
    tr.set_defaults(fn=cmd_transcribe)
    it = sub.add_parser("import-transcript")
    it.add_argument("src")
    it.add_argument("--out", required=True)
    it.set_defaults(fn=cmd_import_transcript)
    dp = sub.add_parser("design-propose")
    dp.add_argument("--analysis", required=True)
    dp.add_argument("--out", required=True)
    dp.add_argument("--mood", action="append", default=[])
    dp.add_argument("--scripts", nargs="+", default=["ko"])
    dp.add_argument("--allow-uninstalled-fonts", action="store_true", dest="allow_uninstalled_fonts")
    dp.add_argument("--limit", type=int, default=3, help="how many design directions")
    dp.add_argument("--pairings", type=int, default=2,
                    help="typefaces offered per direction (spec: 2-3)")
    dp.add_argument("--lines", help="JSON array of real caption lines to typeset in the mockups")
    dp.set_defaults(fn=cmd_design_propose)
    dv = sub.add_parser("design-preview")
    dv.add_argument("--dir", required=True)
    dv.add_argument("--timeout", type=float, default=1800)
    dv.add_argument("--poll", type=float, default=0.5)
    dv.add_argument("--port", type=int, default=0)
    dv.add_argument("--no-wait", action="store_true", dest="no_wait")
    dv.set_defaults(fn=cmd_design_preview)
    dc = sub.add_parser("design-choose")
    dc.add_argument("--dir", required=True)
    dc.add_argument("--out", required=True)
    dc.add_argument("--id")
    dc.set_defaults(fn=cmd_design_choose)
    ds = sub.add_parser("design-styleplan")
    ds.add_argument("--dir", required=True)
    ds.add_argument("--analysis", required=True)
    ds.add_argument("--out", required=True)
    ds.add_argument("--id")
    ds.add_argument("--lines", help="JSON array of real caption lines to typeset in the style frame")
    ds.set_defaults(fn=cmd_design_styleplan)
    dr = sub.add_parser("doctor")
    dr.add_argument("--design", help="also check the fonts this design needs (plan/design.json)")
    dr.add_argument("--bridge-dir")
    dr.add_argument("--ping", action="store_true", help="prove the bridge by running a tiny script in After Effects")
    dr.add_argument("--json", action="store_true")
    dr.set_defaults(fn=cmd_doctor)
    ip = sub.add_parser("init")
    ip.add_argument("dir")
    ip.set_defaults(fn=cmd_init)
    st = sub.add_parser("status")
    st.add_argument("--dir", required=True)
    st.add_argument("--json", action="store_true")
    st.set_defaults(fn=cmd_status)
    dc2 = sub.add_parser("decide")
    dc2.add_argument("--dir", required=True)
    dc2.add_argument("--gate", type=int, required=True)
    dc2.add_argument("--what", required=True)
    dc2.add_argument("--detail")
    dc2.set_defaults(fn=cmd_decide)
    ap = sub.add_parser("audio-plan")
    ap.add_argument("spec", help="JSON with a 'takes' list, optional 'music' and 'duration'")
    ap.add_argument("--out", default="plan/audio.json")
    ap.add_argument("--merge", help="splice voices/music into this existing edit.json instead")
    ap.add_argument("--root", help="resolve take files against this folder (default: the spec's folder)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--target", type=float, default=-16.0)
    ap.set_defaults(fn=cmd_audio_plan)
    qa = sub.add_parser("qa")
    qa.add_argument("export")
    qa.add_argument("--plan", help="plan/edit.json — gives voice onsets and SFX to check")
    qa.add_argument("--design", help="plan/design.json — adds the contrast checks")
    qa.add_argument("--sections", help="JSON list of {id,start,end} to measure separately")
    qa.add_argument("--out", default="qa", help="folder for report-vNN.md (default: qa)")
    qa.add_argument("--stills", help="comma-separated times to grab stills at")
    qa.add_argument("--share", help="also write a 1080p share copy to this path")
    qa.add_argument("--target", type=float, default=-16.0)
    qa.set_defaults(fn=cmd_qa)
    gp = sub.add_parser("grade-propose")
    gp.add_argument("--analysis", required=True)
    gp.add_argument("--out", required=True)
    gp.add_argument("--mood", nargs="*", default=[])
    gp.add_argument("--limit", type=int, default=3)
    gp.set_defaults(fn=cmd_grade_propose)
    gc = sub.add_parser("grade-choose")
    gc.add_argument("--dir", required=True)
    gc.add_argument("--analysis", required=True)
    gc.add_argument("--out", required=True)
    gc.add_argument("--id")
    gc.add_argument("--target-luma", type=float, dest="target_luma")
    gc.add_argument("--design-hint", dest="design_hint")
    gc.set_defaults(fn=cmd_grade_choose)
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        return args.fn(args)
    except KNOWN as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
