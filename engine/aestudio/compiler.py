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


def _motion_exprs(shot, width, height):
    """A slow push anchored on a point in the source, as scale + position expressions.

    Both read thisLayer.source at runtime, so the same expression works whatever the
    source's pixel dimensions are. Anchoring on cx/cy keeps the subject where it is
    while the frame closes in; a centre-anchored zoom walks it out of shot whenever
    the subject is not in the middle of the picture.
    """
    m = shot.motion
    if not m:
        return None
    z0, z1 = float(m["from"]), float(m["to"])
    cx, cy = float(m.get("cx", 0.5)), float(m.get("cy", 0.5))
    # the subject sits slightly above centre - where faces sit comfortably
    fy = float(m.get("frame_y", 0.44))
    t0, t1 = r3(shot.start), r3(shot.end)
    cover = ("var b=Math.max(thisComp.width/thisLayer.source.width,"
             "thisComp.height/thisLayer.source.height);")
    k = f"var k=eio(linear(time,{t0},{t1},0,1));var z=b*({r3(z0)}+({r3(z1 - z0)})*k);"
    # Clamp to the layer's own edges: a subject far off-centre cannot be pulled all
    # the way to the middle without dragging empty frame in behind it. Without this
    # the layer slides off and the comp background shows as a black band.
    clamp = ("var hw=thisLayer.source.width*z/2;var hh=thisLayer.source.height*z/2;"
             f"var px={r3(width / 2)}+(0.5-{r3(cx)})*thisLayer.source.width*z;"
             f"var py={r3(height / 2)}+({r3(fy)}-{r3(cy)})*thisLayer.source.height*z;"
             f"px=Math.min(hw,Math.max({r3(width)}-hw,px));"
             f"py=Math.min(hh,Math.max({r3(height)}-hh,py));")
    return {
        "scale": cover + k + "[z*100,z*100]",
        "position": cover + k + clamp + "[px,py]",
    }


def compile_plan(plan, design) -> list:
    f = plan.format
    ops = Ops()
    ops.add("comp", name=plan.name, width=f.width, height=f.height, fps=f.fps, duration=f.duration, bg=[0, 0, 0])
    voices = {v.id: voice_times(v, load_transcript(v.transcript)) for v in plan.voices}
    base_grade = {str(k): v for k, v in plan.grade.get("lumetri", {}).items()}

    # A montage of hard cuts with no transition grammar reads as a slideshow. A short
    # dissolve costs almost nothing and makes the cut feel authored. Each shot holds
    # `dissolve` seconds past its out point and the NEXT one fades up over it.
    default_dis = r3(float(plan.grade.get("dissolve", 0.0) or 0.0))

    sound = []      # spans where a shot's own audio plays, so the music can duck for it

    for i, s in enumerate(plan.shots):
        dis = r3(s.dissolve if s.dissolve is not None else default_dis)
        lum = dict(base_grade)
        if s.exposure:
            lum["20"] = r3(float(lum.get("20", 0)) + s.exposure)
        expr = _motion_exprs(s, f.width, f.height) or {}
        end = r3(s.end)
        # a shot only holds past its out point if the NEXT one dissolves over it
        nxt = plan.shots[i + 1] if i + 1 < len(plan.shots) else None
        nxt_dis = r3(nxt.dissolve if (nxt and nxt.dissolve is not None) else default_dis) if nxt else 0
        if nxt_dis > 0:
            end = r3(min(s.end + nxt_dis, f.duration))
        if dis > 0 and i > 0:  # the first shot has nothing to dissolve from
            expr = dict(expr)
            expr["opacity"] = f"100*so((time-{r3(s.start)})/{dis})"
        # A shot that keeps its own sound fades it in and out on its own edges, not
        # on the layer's extended end - otherwise the audio runs on under the next
        # shot for as long as the dissolve holds this one open.
        levels = None
        if s.gain_db is not None:
            g = r3(s.gain_db)
            a, b = r3(s.start), r3(s.end)
            levels = [[a, -60], [r3(min(a + 0.3, b)), g], [r3(max(b - 0.4, a)), g], [b, -60]]
            sound.append((a, b))
        ops.add("footage", id=f"SHOT_{i + 1:02d}", file=str(s.clip), start=r3(s.start), end=end, src_in=r3(s.src_in),
                zoom=s.zoom if s.zoom != 1 else None, lumetri=lum or None,
                width=r3(f.width * s.zoom) if s.fit == "width" else None,
                levels=levels, expr=expr or None)

    ctx = Context(design, ops, f.width, f.height, f.duration, voices, {"lumetri": base_grade},
                  graphics_from=len(ops.items))
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

    # the music ducks for anything the audience is meant to hear, voice or clip -
    # including clips inside graphics, which the plan declares as music.spans
    extra = [tuple(sp) for sp in (plan.music.spans if plan.music else [])]
    spans = sorted([(vt.onset, vt.offset) for vt in voices.values()] + sound + extra)
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
