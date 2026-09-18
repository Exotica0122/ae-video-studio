"""ae-video-studio command line: python3 -m aestudio <command> ..."""
import argparse
import json
import sys
import time
from pathlib import Path

from .bridge import Bridge, BridgeError
from .compiler import CompileError, compile_plan
from .components.layout import LayoutError
from .design import DesignError, load_design
from .designgen import DesignGenError, Draft, propose, save_design, style_frame_plan
from .footage import log_footage
from .fonts import FontError, installed_files, is_installed, load_catalogue
from .jsx import emit_script, still_script
from .media import MediaError
from .ops import OpsError
from .plan import PlanError, load_plan
from .preview import PreviewError, read_choice, serve, wait_for_choice
from .render import RenderError, render
from .styleframe import render_mockups
from .timing import TimingError
from .transcribe import TranscribeError, import_transcript, transcribe as run_transcribe

KNOWN = (PlanError, DesignError, TimingError, LayoutError, OpsError, CompileError, BridgeError, RenderError, MediaError, TranscribeError, DesignGenError, PreviewError, FontError, OSError)


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
    print(json.dumps({"clips": len(log["clips"]), "audio": len(log["audio"]), "errors": len(log["errors"]),
                      "out": str(Path(a.out).resolve())}, ensure_ascii=False))
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
                            recipe=recipe, fonts={r: s["font"] for r, s in recipe["tokens"]["type"].items()},
                            notes=list(notes)))
    return drafts


def _font_warnings(design) -> list:
    """After Effects substitutes a missing font silently, so say so before anything is built."""
    catalogue, files, out = load_catalogue(), installed_files(), []
    for name in sorted(design.fonts()):
        font = next((f for f in catalogue if name in f.postscript.values()), None)
        if font is None:
            out.append(f"{name} is not in the font catalogue — check it is installed before building")
        elif not is_installed(font, files):
            out.append(f"install {font.family} first ({name}): {font.licence} — {font.url}")
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
                     limit=a.limit)
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


def cmd_design_choose(a):
    draft, note = _pick(a.dir, a.id)
    path = save_design(draft, a.out)
    warnings = list(dict.fromkeys(list(draft.notes) + _font_warnings(load_design(path))))
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
    dp.add_argument("--limit", type=int, default=3)
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
