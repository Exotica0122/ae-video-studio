"""edit plan + design -> ops."""
from .audio import duck_keys, sfx_fade_keys
from .components import REGISTRY
from .context import Context
from .ops import Ops, validate_ops
from .timing import load_transcript, voice_times
from .util import r3


class CompileError(KeyError):
    def __str__(self):
        return str(self.args[0])


def compile_plan(plan, design) -> list:
    f = plan.format
    ops = Ops()
    ops.add("comp", name=plan.name, width=f.width, height=f.height, fps=f.fps, duration=f.duration, bg=[0, 0, 0])
    voices = {v.id: voice_times(v, load_transcript(v.transcript)) for v in plan.voices}
    base_grade = {str(k): v for k, v in plan.grade.get("lumetri", {}).items()}

    for i, s in enumerate(plan.shots):
        lum = dict(base_grade)
        if s.exposure:
            lum["20"] = r3(float(lum.get("20", 0)) + s.exposure)
        ops.add("footage", id=f"SHOT_{i + 1:02d}", file=str(s.clip), start=r3(s.start), end=r3(s.end), src_in=r3(s.src_in),
                zoom=s.zoom if s.zoom != 1 else None, lumetri=lum or None)

    ctx = Context(design, ops, f.width, f.height, f.duration, voices, {"lumetri": base_grade})
    for g in plan.graphics:
        treatment, options = design.treatment(g["type"])
        builder = REGISTRY.get((g["type"], treatment))
        if builder is None:
            raise CompileError(f"no treatment '{treatment}' for '{g['type']}' (design {design.id}); registered: "
                               + ", ".join(sorted(f"{c}/{t}" for c, t in REGISTRY)))
        builder(ctx, g, options)

    for v in plan.voices:
        vt = voices[v.id]
        end = v.at + (v.src_out - v.src_in) if v.src_out is not None else min(vt.offset + 0.5, f.duration)
        ops.add("audio", id=f"VOICE_{v.id}", file=str(v.file), start=r3(v.at), end=r3(end), src_in=r3(v.src_in), gain_db=v.gain_db)

    spans = sorted((vt.onset, vt.offset) for vt in voices.values())
    if plan.music:
        keys = duck_keys(spans, f.duration, **plan.music.duck)
        ops.add("audio", id="MUSIC", file=str(plan.music.file), start=r3(plan.music.start), end=r3(f.duration),
                levels=[[t, round(db + plan.music.gain_db, 3)] for t, db in keys])
    onsets = [on for on, _ in spans]
    for i, sfx in enumerate(plan.sfx):
        keys = sfx_fade_keys(sfx.at, sfx.gain_db, onsets) if sfx.fade_before_voice else None
        ops.add("audio", id=f"SFX_{i + 1:02d}", file=str(sfx.file), start=r3(sfx.at), end=r3(f.duration),
                levels=keys, gain_db=None if keys else sfx.gain_db)

    if plan.fade_out > 0:
        start = r3(f.duration - plan.fade_out)
        ops.add("solid", id="FADE_OUT", color=[0, 0, 0], expr={"opacity": f"100*so((time-{start})/{r3(plan.fade_out - 0.05)})"})
    validate_ops(ops.items)
    return ops.items
