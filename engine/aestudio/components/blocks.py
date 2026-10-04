"""Positioned editorial blocks and the treatments built around them: kicker/rule/rows blocks, divided word chips,
whole-line subtitles, a fade up from black, a labelled scrim caption, light-ray title pages, a date-row end card and
CRT / split variants of the layout. Every colour is a design palette token.

Scrim PNGs ship beside the design.json: scrim-left.png, scrim-right.png, scrim-caption.png, scrim-split.png and
crt-vignette.png, each only when a graphic asks for it.
"""
from ..util import hex_rgb, r3
from . import register
from .cinematic import _shadow, caption_line_fade
from .editorial import SCRIM_CAPTION, _photo_grade, layout_editorial
from .layout import fade_ref, parse_line, place_block, schedule_times, scrim, segment_times, span, text_block

SCRIMS = {"left": "scrim-left.png", "right": "scrim-right.png", "bottom": SCRIM_CAPTION}
# (x as a fraction of the frame, width in 4K px, opacity %)
RAYS = [(0.22, 300, 13), (0.38, 150, 9), (0.55, 420, 11), (0.74, 200, 8)]
LITERAL = {"white": [1, 1, 1], "black": [0, 0, 0]}


def _color(ctx, name):
    """A palette token, "white"/"black", or "#RRGGBB"."""
    if name in LITERAL:
        return list(LITERAL[name])
    return hex_rgb(name) if name.startswith("#") else ctx.design.color(name)


def _window(g, vt, lead=0.4, tail=0.6):
    t_in = r3(g["in"]) if g.get("in") is not None else r3(vt.onset - lead)
    t_out = r3(g["out"]) if g.get("out") is not None else r3(vt.offset + tail)
    return t_in, t_out


def _voice(ctx, g):
    return ctx.voices.get(g["voice"]) if g.get("voice") else None


def _group(ctx, prefix, t_in, t_out, ramp=0.5):
    gid = ctx.ops.uid(prefix)
    ctx.ops.add("group", id=gid, fade=f"100*so((time-{t_in})/{ramp})*(1-so((time-{r3(t_out - ramp)})/{ramp}))")
    return gid, fade_ref(gid), span(t_in, r3(t_out + 0.1))


def _text(ctx, id, parent, text, role, mult, colour, x, y, t0, fade, sp, tracking=0, justify="center", by="chars", step=0.03):
    n = len(text) if by == "chars" else len(text.split())
    ctx.ops.add("text", id=id, parent=parent, text=text, font=ctx.design.font(role), size=ctx.size(role, mult),
                color=_color(ctx, colour), tracking=tracking, justify=justify, position=[r3(x), r3(y)],
                reveal={"times": [r3(t0 + step * i) for i in range(n)], "dur": 0.6, "rise": ctx.px(12), "blur": 8, "by": by},
                expr={"opacity": fade}, **sp)
    _shadow(ctx, id)


def _rays(ctx, gid, t_in, fade, sp, colour, strength=1.0, stagger=0.2, ramp=1.4, drift=40):
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    for i, (fx, w, o) in enumerate(RAYS):
        rid = f"{gid}_RAY{i + 1}"
        ops.add("rect", id=rid, parent=gid, color=_color(ctx, colour), size=[px(w), r3(H * 1.9)], center=[0, 0],
                position=[r3(W * fx), r3(H / 2)], rotation=-28,
                expr={"opacity": f"{r3(o * strength)}*so((time-{r3(t_in + stagger * i)})/{ramp})*{fade}/100",
                      "position": f"value+[{px(drift)}*(time-{t_in}),0]"}, **sp)
        ops.add("effect", layer=rid, match="ADBE Gaussian Blur 2", props={"1": px(150)})


def _wipe_rule(ctx, id, parent, colour, t0, width, height, left, y, fade, sp, opacity=100, dur=0.6):
    k = f"var k=eio((time-{r3(t0)})/{dur});"
    ctx.ops.add("rect", id=id, parent=parent, color=_color(ctx, colour),
                rect_expr={"size": k + f"[{r3(width)}*k,{r3(height)}]", "center": k + f"[{r3(left)}+{r3(width)}*k/2,{r3(y)}]"},
                expr={"opacity": fade if opacity == 100 else f"{opacity}*{fade}/100"}, **sp)


@register("block", "positioned", default=True)
def block_positioned(ctx, g, opts):
    """Kicker, accent rule, stacked text items and rows that build over time, anchored at a point in the frame.

    g (or g["block"]): {x, y (0..1), align: left|right, scrim: left|right|bottom, rays, kicker, rule, width,
    items: [{lines, role, mult, gap, after, color}], rows: [{at, key, value, n, key_color}], line_at, ...}
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    b = g.get("block") or g
    vt = _voice(ctx, g)
    t_in, t_out = _window(g, vt)
    right = b.get("align") == "right"
    bid, fade, sp = _group(ctx, "BLOCK", t_in, t_out)
    if b.get("scrim"):
        scrim(ctx, id=f"{bid}_SCRIM", parent=bid, asset=SCRIMS[b["scrim"]], strength=100, opacity=fade, **sp)
    if b.get("rays"):
        _rays(ctx, bid, t_in, fade, sp, b.get("ray_color", "ink"), strength=b["rays"])
    x = r3(W * b["x"])
    width = px(b.get("width", 1300))
    x_left = r3(x - width) if right else x
    just = "right" if right else "left"
    y = H * b["y"]
    if b.get("kicker"):
        _text(ctx, f"{bid}_KICK", bid, b["kicker"].upper(), "label", 1.0, "accent", x, y, t_in + 0.15, fade, sp,
              tracking=380, justify=just, step=0.01)
        y += px(120)
    if b.get("rule"):
        _wipe_rule(ctx, f"{bid}_RULE", bid, "accent", t_in + 0.1, px(150), px(7), x - px(150) if right else x, y, fade, sp)
        y += px(110)
    items = b.get("items", [])
    parsed = [[parse_line(line, ctx.size(it.get("role", "body"), it.get("mult", 1.0) * 0.3)) for line in it["lines"]] for it in items]
    flat = [ln for lines in parsed for ln in lines]
    times = []
    if b.get("line_at"):
        times = [schedule_times([ln], at, b.get("step", 0.1), 0.0)[0] for ln, at in zip(flat, b["line_at"])]
    elif vt and not b.get("schedule"):
        times = segment_times(flat, vt.words)
    elif flat:
        times = schedule_times(flat, t_in + b.get("delay", 0.35), b.get("step", 0.1), b.get("line_pause", 0.25))
    ti = 0
    for ii, (it, lines) in enumerate(zip(items, parsed)):
        role, mult = it.get("role", "body"), it.get("mult", 1.0)
        size = ctx.size(role, mult)
        gap = r3(size * it.get("gap", 1.38))
        y += size * 0.82

        def style(i, sg, role=role, size=size, colour=it.get("color", "ink")):
            return {"font": d.font("emphasis" if (sg.hl and role == "body") else role), "size": size,
                    "color": _color(ctx, "accent" if sg.hl else colour)}

        blk = text_block(ctx, prefix=f"{bid}_I{ii + 1}", parent=bid, lines=lines, times=times[ti:ti + len(lines)], x=x,
                         y_first=r3(y), gap=gap, style=style, align=just,
                         reveal={"dur": 0.6, "rise": px(14), "blur": 10, "by": "words"}, opacity=fade, t_in=t_in, t_out=r3(t_out + 0.1))
        for lid in blk.ids:
            _shadow(ctx, lid)
        ti += len(lines)
        y += (len(lines) - 1) * gap + size * it.get("after", 0.55)
    rows = b.get("rows", [])
    if not rows:
        return
    rh = px(b.get("row_h", 190))
    key_mult = b.get("key_mult", 0.78)
    key_size = ctx.size("headline", key_mult)
    for ri, row in enumerate(rows):
        at = r3(row["at"])
        top = y + ri * rh
        _wipe_rule(ctx, f"{bid}_DIV{ri + 1}", bid, "ink", at - 0.15, width, px(3), x_left, top, fade, sp, opacity=30)
        base = top + rh * 0.5 + key_size * 0.35
        kx = x_left
        if row.get("n"):
            _text(ctx, f"{bid}_N{ri + 1}", bid, row["n"], "label", 1.0, "accent", x_left, base - px(14), at, fade, sp,
                  tracking=200, justify="left", step=0.02)
            kx = x_left + px(150)
        _text(ctx, f"{bid}_K{ri + 1}", bid, row["key"], "headline", key_mult, row.get("key_color", "ink"),
              kx, base, at, fade, sp, justify="left", by="words", step=0.1)
        if row.get("value"):
            _text(ctx, f"{bid}_V{ri + 1}", bid, row["value"], "body", 0.72, "ink", kx + px(b.get("value_x", 330)), base - px(6),
                  at + 0.25, fade, sp, justify="left", by="words", step=0.08)
    _wipe_rule(ctx, f"{bid}_DIVEND", bid, "ink", r3(rows[-1]["at"]) + 0.2, width, px(3), x_left, y + len(rows) * rh,
               fade, sp, opacity=30)


@register("chips", "divided", default=True)
def chips_divided(ctx, g, opts):
    """A centred row of words split by thin accent dividers, revealed one by one.

    g (or g["chips"]): {words, y, cx, cell (4K px), role, mult, hl: [indices], scrim, delay, step}
    """
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    c = g.get("chips") or g
    t_in, t_out = _window(g, None)
    cid, fade, sp = _group(ctx, "CHIPS", t_in, t_out)
    if c.get("scrim"):
        scrim(ctx, id=f"{cid}_SCRIM", parent=cid, asset=SCRIMS[c["scrim"]], strength=100, opacity=fade, **sp)
    words = c["words"]
    role, mult = c.get("role", "quote"), c.get("mult", 0.8)
    cell = px(c.get("cell", 520))
    x0 = W * c.get("cx", 0.5) - cell * len(words) / 2
    y = H * c["y"]
    size = ctx.size(role, mult)
    for i, w in enumerate(words):
        t0 = r3(t_in + c.get("delay", 0.3) + i * c.get("step", 0.22))
        _text(ctx, f"{cid}_W{i + 1}", cid, w, role, mult, "accent" if i in c.get("hl", []) else "ink",
              x0 + cell * (i + 0.5), y, t0, fade, sp, step=0.05)
        if i:
            k = f"var k=eio((time-{r3(t0 - 0.1)})/0.5);"
            ops.add("rect", id=f"{cid}_DIV{i}", parent=cid, color=_color(ctx, "accent"),
                    rect_expr={"size": k + f"[{px(3)},{r3(size * 1.1)}*k]", "center": f"[{r3(x0 + cell * i)},{r3(y - size * 0.35)}]"},
                    expr={"opacity": f"70*{fade}/100"}, **sp)


@register("subtitle", "whole-line", default=True)
def subtitle_whole_line(ctx, g, opts):
    """Interview subtitles: each line appears whole and fades, or follows the voice word by word with whole: false.

    g (or g["sub"]): {cx, y (0..1, last line), scale, fade, whole}
    """
    d, W, H = ctx.design, ctx.width, ctx.height
    s = g.get("sub") or g
    vt = _voice(ctx, g)
    t_in, t_out = _window(g, vt)
    f = s.get("fade", 0.4)
    sid, fade, _ = _group(ctx, "SUB", t_in, t_out, ramp=f)
    size = ctx.size("body", s.get("scale", 0.62))
    lines = [parse_line(line, ctx.size("body", 0.2)) for line in g["lines"]]
    gap = r3(size * 1.5)
    y_first = r3(H * s.get("y", 0.9) - (len(lines) - 1) * gap)
    if s.get("whole", vt is None):
        times = schedule_times(lines, t_in + 0.02, 0.0, 0.0)
    elif vt:
        times = segment_times(lines, vt.words)
    else:
        times = schedule_times(lines, t_in + 0.3, 0.1, 0.25)
    block = text_block(ctx, prefix=sid, parent=sid, lines=lines, times=times, x=r3(W * s.get("cx", 0.5)), y_first=y_first, gap=gap,
                       style=lambda i, seg: {"font": d.font("body"), "size": size, "color": _color(ctx, "accent" if seg.hl else "ink")},
                       align="center", reveal={"dur": 0.45, "rise": 0, "blur": 6, "by": "words"},
                       opacity=fade, t_in=t_in, t_out=r3(t_out + 0.1))
    for lid in block.ids:
        _shadow(ctx, lid)


@register("fade-in", "solid", default=True)
def fade_in_solid(ctx, g, opts):
    """A full-frame solid (black unless `color` names a token) that clears between in and out."""
    t_in, t_out = r3(g["in"]), r3(g["out"])
    ctx.ops.add("solid", id=ctx.ops.uid("BLACK_IN"), color=_color(ctx, g.get("color", "black")),
                expr={"opacity": f"100*(1-so((time-{t_in})/{r3(t_out - t_in)}))"}, **span(0, r3(t_out + 0.05)))


LEGACY = {"black_in": fade_in_solid, "sub": subtitle_whole_line, "block": block_positioned, "chips": chips_divided}


@register("caption", "label-scrim")
@register("quote", "label-scrim")
def caption_label_scrim(ctx, g, opts):
    """Line-fade text over a bottom scrim, with an optional spaced `label` above and `by` below.

    A caption carrying `black_in`, `sub`, `block` or `chips` renders as that graphic instead.
    """
    for key, builder in LEGACY.items():
        if g.get(key):
            return builder(ctx, g, opts)
    W, H, px = ctx.width, ctx.height, ctx.px
    t_in, t_out = _window(g, _voice(ctx, g))
    sid = ctx.ops.uid("SCRIM")
    ctx.ops.add("group", id=sid, fade=f"100*so((time-{t_in})/0.6)*(1-so((time-{r3(t_out - 0.5)})/0.5))")
    fade, sp = fade_ref(sid), span(t_in, r3(t_out + 0.1))
    if g.get("tint"):
        ctx.ops.add("rect", id=f"{sid}_TINT", parent=sid, color=_color(ctx, "paper"), size=[r3(W + px(20)), r3(H + px(20))],
                    center=[r3(W / 2), r3(H / 2)], expr={"opacity": f"{g['tint']}*{fade}/100"}, **sp)
    scrim(ctx, id=f"{sid}_IMG", parent=sid, asset=SCRIM_CAPTION, strength=100, opacity=fade, **sp)
    place = g.get("place", "lower-center")
    caption_line_fade(ctx, dict(g, place=place), opts)
    base = "quote" if g["type"] == "quote" else "body"
    gap = r3(ctx.size(base) * 1.45)
    _, y0, _ = place_block(place, len(g["lines"]), gap, W, H)
    if g.get("label"):
        _text(ctx, f"{sid}_LABEL", sid, g["label"].upper(), "label", 1.05, "ink", W / 2, y0 - ctx.size(base) - px(70),
              t_in + 0.2, fade, sp, tracking=140, step=0.01)
    if g.get("by"):
        _text(ctx, f"{sid}_BY", sid, g["by"].upper(), "label", 1.0, "accent", W / 2, y0 + (len(g["lines"]) - 1) * gap + px(130),
              t_in + 1.6, fade, sp, tracking=380)


@register("title-page", "light-rays")
def title_light_rays(ctx, g, opts):
    """Lines fading up one by one over a tinted plate crossed by slow diagonal light rays."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.95)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, fade=f"100*so((time-{t_in})/0.8)*(1-so((time-{t_out})/0.6))")
    fade, sp = fade_ref(tid), span(t_in, end)
    photo = g.get("photo")
    if photo:
        ops.add("footage", id=f"{tid}_BG", parent=tid, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), zoom=photo.get("zoom", 1.04), position=[r3(W / 2), r3(H / 2)],
                lumetri=_photo_grade(ctx, photo), expr={"opacity": fade})
    ops.add("rect", id=f"{tid}_TINT", parent=tid, color=_color(ctx, "paper"), size=[r3(W + px(20)), r3(H + px(20))],
            center=[r3(W / 2), r3(H / 2)], expr={"opacity": f"{g.get('tint', 62)}*{fade}/100"}, **sp)
    _rays(ctx, tid, t_in, fade, sp, g.get("ray_color", "ink"), stagger=0.3, ramp=1.6, drift=28)
    size = ctx.size("scripture")
    lines = [parse_line(line, ctx.size("scripture", 0.3)) for line in g["lines"]]
    gap = r3(size * 1.75)
    y_first = r3(0.44 * H - (len(lines) - 1) * gap / 2)
    vt = _voice(ctx, g)
    times = segment_times(lines, vt.words) if vt else schedule_times(lines, start=t_in + 0.5, step=0.0, line_pause=0.3)
    block = text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=r3(W / 2), y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("scripture"), "size": size, "color": _color(ctx, "accent" if s.hl else "ink")},
                       align="center", reveal={"dur": 1.1, "rise": px(10), "blur": 14, "by": "words"}, opacity=fade, t_in=t_in, t_out=end)
    for lid in block.ids:
        _shadow(ctx, lid)
    if g.get("ref"):
        start = times[-1][-1][-1] + 0.8
        y = r3(y_first + len(lines) * gap)
        _text(ctx, f"{tid}_REF", tid, g["ref"], "label", 1.0, "accent", W / 2, y, start, fade, sp, tracking=400)
        k = f"var k=eio((time-{r3(start)})/0.8);"
        for side, sign in (("L", -1), ("R", 1)):
            ops.add("rect", id=f"{tid}_REF_{side}", parent=tid, color=_color(ctx, "accent"),
                    rect_expr={"size": k + f"[{px(160)}*k,{px(3)}]", "center": f"[{r3(W / 2 + sign * px(420))},{r3(y - px(18))}]"},
                    expr={"opacity": fade}, **sp)


def _frac(value, extent):
    """0..1 is a fraction of `extent`; anything larger is already pixels."""
    return extent * value if value <= 1 else value


def _layout_ids(ctx, g):
    gid = f"LAYOUT_{ctx.ops._counters['LAYOUT']:02d}"
    t_in, t_out = r3(g["in"]), r3(g["out"])
    return gid, t_in, t_out, fade_ref(gid), span(t_in, r3(t_out + 0.55))


def _layout_split(ctx, g):
    """Speaker on the left, pull-quotes building on the right; each quote is {in, out, lines: [{text, hl}], note}."""
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    gid, t_in, t_out, gfade, sp = _layout_ids(ctx, g)
    scrim(ctx, id=f"{gid}_SPLIT", parent=gid, asset="scrim-split.png", strength=100, opacity=gfade, **sp)
    x = r3(W * g.get("quote_x", 0.585))
    size = ctx.size("headline", 1.0)
    gap = r3(size * 1.32)
    for qi, q in enumerate(g.get("quotes", [])):
        q_in, q_out = r3(q["in"]), r3(q["out"])
        qid = f"{gid}_Q{qi + 1}"
        ops.add("group", id=qid, parent=gid, fade=f"100*so((time-{q_in})/0.5)*(1-so((time-{r3(q_out - 0.45)})/0.45))")
        fade = f"{fade_ref(qid)}*{gfade}/100"
        qsp = span(q_in, r3(q_out + 0.05))
        n = len(q["lines"])
        y_first = r3(H * 0.5 - (n - 1) * gap / 2 + size * 0.35)
        _wipe_rule(ctx, f"{qid}_RULE", qid, "accent", q_in + 0.1, px(150), px(8), x, y_first - size - px(60), fade, qsp)
        t = q_in + 0.25
        for li, line in enumerate(q["lines"]):
            _text(ctx, f"{qid}_L{li + 1}", qid, line["text"], "headline", 1.0, "accent" if line.get("hl") else "ink",
                  x, y_first + li * gap, t, fade, qsp, justify="left", by="words", step=0.12)
            t += 0.12 * len(line["text"].split()) + 0.15
        if q.get("note"):
            _text(ctx, f"{qid}_NOTE", qid, q["note"], "body", 0.58, "accent2", x, y_first + (n - 1) * gap + px(150),
                  t + 0.2, fade, qsp, justify="left", by="words", step=0.08)


def _layout_crt(ctx, g):
    """The first panel as a black-and-white CRT: grayscale, grain, scanlines, a rounded vignette and optional bars."""
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    gid, t_in, t_out, fade, sp = _layout_ids(ctx, g)
    pid = f"{gid}_01"
    ops.add("effect", layer=pid, match="ADBE Tint")
    ops.add("effect", layer=pid, match="ADBE Brightness & Contrast 2", props={"2": 22})
    ops.add("effect", layer=pid, match="ADBE Noise", props={"1": 9, "2": 0})
    step = max(2.0, px(6))
    ops.add("rules", id=f"{gid}_SCAN", parent=gid, count=int(H / step) + 1, spacing=step, y0=0, color=[0, 0, 0],
            width=W, stroke=max(1.0, px(2)), expr={"opacity": f"12*{fade}/100"}, **sp)
    scrim(ctx, id=f"{gid}_VIG", parent=gid, asset="crt-vignette.png", strength=100, opacity=fade, **sp)
    top, bot = _frac(g.get("bar_top", 0), H), _frac(g.get("bar_bottom", 0), H)
    for key, y0, hgt in (("TOP", 0, top), ("BOT", H - bot, bot)):
        if hgt:
            ops.add("rect", id=f"{gid}_BAR_{key}", parent=gid, color=_color(ctx, "shade"), size=[r3(W + px(20)), r3(hgt)],
                    center=[r3(W / 2), r3(y0 + hgt / 2)], expr={"opacity": fade}, **sp)


@register("layout", "accent-band")
def layout_accent_band(ctx, g, opts):
    """Editorial panels over an accent band with a kicker and title beneath; `crt` or `split` swap the band for those looks.

    band: {y, h} as fractions of the frame, or false for none.
    """
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    layout_editorial(ctx, g, opts)
    if g.get("split"):
        return _layout_split(ctx, g)
    if g.get("crt"):
        return _layout_crt(ctx, g)
    gid, t_in, t_out, fade, sp = _layout_ids(ctx, g)
    band = g.get("band", {"y": 0.30, "h": 0.26})
    if band:
        k = f"var k=eio((time-{r3(t_in + 0.15)})/0.9);"
        ops.add("rect", id=f"{gid}_BAND", parent=gid, color=_color(ctx, "accent"),
                rect_expr={"size": k + f"[{r3(W + px(20))}*k,{r3(H * band['h'])}]",
                           "center": f"[{r3(W / 2)},{r3(H * (band['y'] + band['h'] / 2))}]"},
                expr={"opacity": fade}, **sp)
        ops.add("order", layer=f"{gid}_BAND", below=[f"{gid}_01"])
    for i in range(len(g["panels"])):
        ops.add("effect", layer=f"{gid}_{i + 1:02d}", match="ADBE Drop Shadow", props={"2": 55, "3": 180, "4": px(20), "5": px(60)})
    if g.get("kicker"):
        _text(ctx, f"{gid}_KICKER", gid, g["kicker"].upper(), "label", 1.0, "accent", W / 2, H * 0.80, t_in + 0.6, fade, sp,
              tracking=420)
    if g.get("title"):
        _text(ctx, f"{gid}_TITLE", gid, g["title"], "headline", 1.39, "ink", W / 2, H * 0.905, t_in + 0.8, fade, sp,
              by="words", step=0.14)


@register("end-card", "date-row")
def end_card_date_row(ctx, g, opts):
    """Logo mark, kicker and title, an optional row of big dates between rules, and a contact line, over blurred footage.

    dates: [{num, label, sub}]; logo: {file, width, tint, color: token | "white"}; contact, contact_label.
    """
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    E = r3(g["in"])
    eid = ops.uid("END")
    ops.add("group", id=eid, fade=f"100*so((time-{E})/0.8)")
    fade, sp, cx = fade_ref(eid), span(E), W / 2
    photo = g.get("photo")
    if photo:
        bg = f"{eid}_BG"
        ops.add("footage", id=bg, parent=eid, file=photo["clip"], start=E, end=r3(ctx.duration), src_in=photo.get("src_in", 0),
                stretch=photo.get("stretch"), zoom=1.06, position=[r3(cx), r3(H / 2)], lumetri=_photo_grade(ctx, photo),
                expr={"opacity": fade})
        ops.add("effect", layer=bg, match="ADBE Gaussian Blur 2", props={"1": px(14)})
    ops.add("rect", id=f"{eid}_SHADE", parent=eid, color=_color(ctx, "paper"), size=[r3(W + px(20)), r3(H + px(20))],
            center=[r3(cx), r3(H / 2)], expr={"opacity": f"{g.get('shade', 70)}*{fade}/100"}, **sp)
    dates = g.get("dates") or []
    logo_y, title_y = (0.25, 0.49) if dates else (0.3, 0.535)
    logo = g.get("logo")
    if logo:
        ops.add("image", id=f"{eid}_MARK", parent=eid, file=logo["file"], width=px(logo.get("width", 460)),
                position=[r3(cx), r3(logo_y * H)], tint=_color(ctx, logo.get("color", "accent")) if logo.get("tint", True) else None,
                expr={"opacity": f"100*so((time-{r3(E + 0.3)})/1.0)*{fade}/100"}, **sp)
    if g.get("kicker"):
        _text(ctx, f"{eid}_KICKER", eid, g["kicker"].upper(), "label", 1.0, "accent", cx, 0.375 * H, E + 0.6, fade, sp,
              tracking=420, step=0.015)
    _text(ctx, f"{eid}_TITLE", eid, g["title"], "headline", 1.53, "ink", cx, title_y * H, E + 0.9, fade, sp, step=0.05)
    rule_top, rule_bot = 0.545 * H, 0.695 * H
    k = f"var k=eio((time-{r3(E + 1.5)})/0.9);"
    if not dates:
        ops.add("rect", id=f"{eid}_RULE", parent=eid, color=_color(ctx, "accent"),
                rect_expr={"size": k + f"[{px(260)}*k,{px(4)}]", "center": f"[{r3(cx)},{r3(0.61 * H)}]"},
                expr={"opacity": fade}, **sp)
    for key, y in ((("TOP", rule_top), ("BOT", rule_bot)) if dates else ()):
        ops.add("rect", id=f"{eid}_RULE_{key}", parent=eid, color=_color(ctx, "ink"),
                rect_expr={"size": k + f"[{px(1900)}*k,{px(3)}]", "center": f"[{r3(cx)},{r3(y)}]"},
                expr={"opacity": f"40*{fade}/100"}, **sp)
    cell = px(940)
    for i, dt in enumerate(dates):
        ccx = cx + (i - (len(dates) - 1) / 2) * cell
        t0 = E + 1.9 + 0.35 * i
        _text(ctx, f"{eid}_D{i + 1}_NUM", eid, dt["num"], "headline", 1.33, "ink", ccx + px(60), 0.655 * H, t0, fade, sp,
              justify="right", step=0.05)
        _text(ctx, f"{eid}_D{i + 1}_LAB", eid, dt["label"], "label", 1.05, "accent", ccx + px(110), 0.605 * H, t0 + 0.3, fade, sp,
              justify="left", by="words", step=0.1)
        if dt.get("sub"):
            _text(ctx, f"{eid}_D{i + 1}_SUB", eid, dt["sub"], "label", 1.05, "ink", ccx + px(110), 0.645 * H, t0 + 0.4, fade, sp,
                  justify="left", by="words", step=0.1)
        if i:
            kv = f"var k=eio((time-{r3(E + 1.8)})/0.7);"
            ops.add("rect", id=f"{eid}_DIV{i}", parent=eid, color=_color(ctx, "ink"),
                    rect_expr={"size": kv + f"[{px(3)},{r3(rule_bot - rule_top)}*k]",
                               "center": f"[{r3(ccx - cell / 2)},{r3((rule_top + rule_bot) / 2)}]"},
                    expr={"opacity": f"40*{fade}/100"}, **sp)
    if g.get("contact"):
        y_lab, y_line, t_lab = (0.775, 0.845, 2.8) if dates else (0.685, 0.755, 1.8)
        if g.get("contact_label"):
            _text(ctx, f"{eid}_CONTACT_LAB", eid, g["contact_label"], "label", 1.0, "accent", cx, y_lab * H, E + t_lab, fade, sp,
                  tracking=400)
        _text(ctx, f"{eid}_CONTACT", eid, g["contact"], "body", 0.72, "ink", cx, y_line * H, E + t_lab + 0.2, fade, sp,
              by="words", step=0.1)
