"""Cinematic Minimal treatments: centred lines that fade up, accent-colour emphasis, rule-wipe lower third,
black-frame title and a centred end card over blurred footage."""
from ..util import r3
from . import register
from .layout import fade_ref, parse_line, place_block, schedule_times, segment_times, span, text_block


def _shadow(ctx, layer_id):
    ctx.ops.add("effect", layer=layer_id, match="ADBE Drop Shadow", props={"2": 90, "3": 180, "4": 0, "5": ctx.px(36)})


@register("caption", "line-fade")
@register("quote", "line-fade")
def caption_line_fade(ctx, g, opts):
    d, ops = ctx.design, ctx.ops
    quote = g["type"] == "quote"
    vt = ctx.voices[g["voice"]]
    t_in = r3(g.get("in", vt.onset - 0.4))
    t_out = r3(g.get("out", vt.offset + 0.6))
    base = "quote" if quote else "body"
    raw = [list(line) for line in g["lines"]]
    if quote:
        raw[0] = ["“"] + raw[0]
        raw[-1] = raw[-1] + ["”"]
    lines = [parse_line(line, ctx.size(base, 0.3)) for line in raw]
    gap = r3(ctx.size(base) * 1.45)
    x, y0, align = place_block(g.get("place", "lower-center"), len(lines), gap, ctx.width, ctx.height)
    cid = ops.uid("QUOTE" if quote else "CAPTION")
    ops.add("group", id=cid, fade=f"100*so((time-{t_in})/0.5)*(1-so((time-{r3(t_out - 0.5)})/0.5))",
            expr={"position": f"value+[0,{ctx.px(24)}*(1-so((time-{t_in})/0.8))]"})

    def style(i, seg):
        return {"font": d.font("emphasis" if seg.hl and not quote else base), "size": ctx.size(base),
                "color": d.color("accent" if seg.hl else "ink")}

    block = text_block(ctx, prefix=cid, parent=cid, lines=lines, times=segment_times(lines, vt.words), x=x, y_first=y0, gap=gap,
                       style=style, align=align, reveal={"dur": d.motion["word"], "rise": ctx.px(d.motion["rise"]), "blur": 10, "by": "words"},
                       opacity=fade_ref(cid), t_in=t_in, t_out=r3(t_out + 0.1))
    for sid in block.ids:
        _shadow(ctx, sid)


@register("lower-third", "rule-wipe")
def lower_third_rule_wipe(ctx, g, opts):
    d, ops, px = ctx.design, ctx.ops, ctx.px
    t_in = r3(g["at"])
    t_out = r3(t_in + g.get("dur", 4.25))
    x, y = r3(0.07 * ctx.width), r3(0.8 * ctx.height)
    lid = ops.uid("LOWER_THIRD")
    sp = span(t_in, t_out + 0.05)
    ops.add("group", id=lid, fade=f"100*(1-so((time-{r3(t_out - 0.6)})/0.6))")
    fade = fade_ref(lid)
    name_size = ctx.size("headline", 0.62)
    rule_w, rule_h, rule_y = px(360), px(4), r3(y - name_size - px(40))
    k = f"var k=eio((time-{r3(t_in + 0.1)})/0.6);"
    ops.add("rect", id=f"{lid}_RULE", parent=lid, color=d.color("accent"),
            rect_expr={"size": k + f"[{rule_w}*k,{rule_h}]", "center": k + f"[{x}+{rule_w}*k/2,{rule_y}]"},
            expr={"opacity": fade}, **sp)
    name, role = f"{lid}_NAME", f"{lid}_ROLE"
    ops.add("text", id=name, parent=lid, text=g["name"], font=d.font("headline"), size=name_size, color=d.color("ink"), position=[x, y],
            reveal={"times": [r3(t_in + 0.35 + 0.03 * i) for i in range(len(g["name"]))], "dur": 0.5, "rise": px(12), "blur": 8, "by": "chars"},
            expr={"opacity": fade}, **sp)
    ops.add("text", id=role, parent=lid, text=g["role"], font=d.font("label"), size=ctx.size("label"), color=d.color("accent"),
            tracking=120, position=[x, r3(y + px(90))],
            reveal={"times": [r3(t_in + 0.7 + 0.08 * i) for i in range(len(g["role"].split()))], "dur": 0.5, "rise": px(8), "blur": 6, "by": "words"},
            expr={"opacity": fade}, **sp)
    _shadow(ctx, name)
    _shadow(ctx, role)


@register("title-page", "black-frame")
def title_black_frame(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.95)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, fade=f"100*(1-so((time-{t_out})/0.6))")
    ops.add("rect", id=f"{tid}_BG", parent=tid, color=d.color("shade"), size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"100*(1-so((time-{r3(t_out + 0.3)})/0.6))"}, **span(t_in, end))
    size = ctx.size("scripture")
    lines = [parse_line(line, ctx.size("scripture", 0.3)) for line in g["lines"]]
    gap = r3(size * 1.5)
    y_first = r3(0.47 * H - (len(lines) - 1) * gap / 2)
    times = schedule_times(lines, start=t_in + 0.8, step=0.14, line_pause=0.4)
    fade = fade_ref(tid)
    text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=r3(W / 2), y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("scripture"), "size": size, "color": d.color("accent" if s.hl else "ink")},
               align="center", reveal={"dur": 0.9, "rise": 0, "blur": 14, "by": "words"}, opacity=fade, t_in=t_in, t_out=end)
    if g.get("ref"):
        start = times[-1][-1][-1] + 0.6
        ops.add("text", id=f"{tid}_REF", parent=tid, text=g["ref"], font=d.font("label"), size=ctx.size("label"), color=d.color("accent"),
                tracking=300, justify="center", position=[r3(W / 2), r3(y_first + len(lines) * gap + px(20))],
                reveal={"times": [r3(start + 0.03 * i) for i in range(len(g["ref"]))], "dur": 0.6, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **span(t_in, end))


@register("end-card", "centered-stack")
def end_card_centered_stack(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    E = r3(g["in"])
    eid = ops.uid("END")
    sp = span(E)
    ops.add("group", id=eid, fade=f"100*so((time-{E})/0.8)")
    fade = fade_ref(eid)
    cx = r3(W / 2)
    photo = g.get("photo")
    if photo:
        bg = f"{eid}_BG"
        ops.add("footage", id=bg, parent=eid, file=photo["clip"], start=E, end=r3(ctx.duration), src_in=photo.get("src_in", 0),
                stretch=photo.get("stretch"), zoom=1.1, position=[cx, r3(H / 2)], lumetri=dict(ctx.grade.get("lumetri", {})) or None,
                expr={"opacity": fade})
        ops.add("effect", layer=bg, match="ADBE Gaussian Blur 2", props={"1": px(60)})
    ops.add("rect", id=f"{eid}_SHADE", parent=eid, color=d.color("shade"), size=[r3(W + px(20)), r3(H + px(20))], center=[cx, r3(H / 2)],
            expr={"opacity": f"72*{fade}/100"}, **sp)

    def ctext(key, text, role, mult, colour, y, times, by, tracking=0, x=cx):
        ops.add("text", id=f"{eid}_{key}", parent=eid, text=text, font=d.font(role), size=ctx.size(role, mult), color=d.color(colour),
                tracking=tracking, justify="center", position=[r3(x), r3(y)],
                reveal={"times": times, "dur": 0.7, "rise": px(16), "blur": 8, "by": by}, expr={"opacity": fade}, **sp)

    logo = g.get("logo")
    if logo:
        ops.add("image", id=f"{eid}_LOGO", parent=eid, file=logo["file"], width=px(logo.get("width", 420)), position=[cx, r3(0.14 * H)],
                tint=d.color("ink") if logo.get("tint", True) else None,
                expr={"opacity": f"100*so((time-{r3(E + 0.4)})/0.8)*{fade}/100"}, **sp)
    if g.get("year") is not None:
        year = str(g["year"])
        ctext("YEAR", year, "label", 1.0, "accent", 0.30 * H, [r3(E + 0.6 + 0.05 * i) for i in range(len(year))], "chars", tracking=300)
    ctext("TITLE", g["title"], "headline", 1.6, "ink", 0.43 * H, [r3(E + 0.9 + 0.06 * i) for i in range(len(g["title"]))], "chars")
    k = f"var k=eio((time-{r3(E + 1.4)})/0.8);"
    ops.add("rect", id=f"{eid}_RULE", parent=eid, color=d.color("accent"),
            rect_expr={"size": k + f"[{px(520)}*k,{px(3)}]", "center": f"[{cx},{r3(0.43 * H + px(70))}]"}, expr={"opacity": fade}, **sp)
    if g.get("tagline"):
        ctext("TAGLINE", g["tagline"], "body", 1.0, "ink", 0.52 * H, [r3(E + 1.8 + 0.12 * i) for i in range(len(g["tagline"].split()))], "words")
    rows = g.get("rows", [])
    for r_i, row in enumerate(rows):
        col_x = W * (r_i + 1) / (len(rows) + 1)
        t0 = E + 2.4 + r_i * 0.25
        ctext(f"ROW{r_i + 1}_LABEL", row["label"], "label", 1.0, "accent", 0.66 * H, [r3(t0)], "words", tracking=120, x=col_x)
        for v_i, value in enumerate(row["values"]):
            ctext(f"ROW{r_i + 1}_VALUE{v_i + 1}", value, "body", 0.9, "ink", 0.66 * H + px(100) + v_i * px(84),
                  [r3(t0 + 0.15 + 0.06 * k2) for k2 in range(len(value.split()))], "words", x=col_x)
