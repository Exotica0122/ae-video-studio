"""Paper Notebook treatments: paper cards with marker highlights, paper-tab lower third,
notebook-page title and polaroid end card."""
from ..util import js, r3
from . import register
from .layout import STATIC, T_END, fade_ref, highlighter, paper_card, parse_line, place_block, schedule_times, segment_times, span, text_block


@register("caption", "paper-card")
@register("quote", "paper-card")
def caption_paper_card(ctx, g, opts):
    d, ops = ctx.design, ctx.ops
    quote = g["type"] == "quote"
    vt = ctx.voices.get(g["voice"]) if g.get("voice") else None
    t_in = r3(g["in"]) if g.get("in") is not None else r3(vt.onset - 0.3)
    t_out = r3(g["out"]) if g.get("out") is not None else r3(vt.offset + 0.5)
    lead, emph = ("quote", "quote") if quote else ("body", "emphasis")
    lines = [parse_line(line, ctx.size(lead, 0.28)) for line in g["lines"]]
    roles = [emph if any(s.hl for s in segs) else lead for segs in lines]
    gap = r3(max(ctx.size(r) for r in roles) * 1.3)
    x, y0, _ = place_block(g.get("place", "top-right" if quote else "bottom-left"), len(lines), gap, ctx.width, ctx.height)
    cid = ops.uid("QUOTE" if quote else "CAPTION")
    ops.add("group", id=cid, anchor=[x, y0], position=[x, y0],
            fade=f"100*so((time-{t_in})/0.35)*(1-si((time-{r3(t_out - 0.4)})/0.4))",
            expr={"position": f"var a=bo((time-{t_in})/{d.motion['in']});var b=si((time-{r3(t_out - 0.45)})/0.45);"
                              f"value+[0,{-ctx.px(40)}*(1-a)+{ctx.px(60)}*b]",
                  "rotation": f"-1.0+1.2*(1-bo((time-{t_in})/{d.motion['in']}))"})
    fade = fade_ref(cid)
    out = r3(t_out + 0.1)
    ink = d.color("ink")
    times = segment_times(lines, vt.words) if vt else schedule_times(lines, t_in + 0.35, 0.12, 0.3)
    block = text_block(ctx, prefix=cid, parent=cid, lines=lines, times=times, x=x, y_first=y0, gap=gap,
                       style=lambda i, s: {"font": d.font(roles[i]), "size": ctx.size(roles[i]), "color": ink}, align="left",
                       reveal={"dur": d.motion["word"], "rise": ctx.px(d.motion["rise"]), "blur": 6, "by": "words"},
                       opacity=fade, t_in=t_in, t_out=out)
    below = list(block.ids)
    if quote:
        mark = f"{cid}_MARK"
        ops.add("text", id=mark, parent=cid, text="“", font=d.font("scripture"), size=ctx.px(220), color=d.color("accent2"),
                position=[r3(x - ctx.px(150)), r3(y0 + ctx.px(90))], expr={"opacity": fade}, **span(t_in, out))
        below.append(mark)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=cid, target=sid, size=ctx.size(roles[i]), t0=times[i][k][0] + 0.05, dur=0.5,
                            color=d.color("accent"), opacity=fade_ref(cid, 88), pad=ctx.px(12), t_in=t_in, t_out=out)
                below.append(f"{sid}_HL")
    paper_card(ctx, id=f"{cid}_CARD", parent=cid, members=block.ids, below=below, pad=(ctx.px(90 if quote else 100), ctx.px(60)),
               color=d.color("paper"), radius=ctx.px(18), opacity=fade, noise=d.texture.get("noise", 0), t_in=t_in, t_out=out)


@register("lower-third", "paper-tab")
def lower_third_paper_tab(ctx, g, opts):
    d, ops, px = ctx.design, ctx.ops, ctx.px
    t_in = r3(g["at"])
    t_out = r3(t_in + g.get("dur", 4.25))
    x, y = r3(0.06 * ctx.width), r3(0.6 * ctx.height)
    lid = ops.uid("LOWER_THIRD")
    sp = span(t_in, t_out + 0.05)
    ops.add("group", id=lid, anchor=[x, y], position=[x, y],
            fade=f"100*so((time-{t_in})/0.3)*(1-si((time-{r3(t_out - 0.45)})/0.45))",
            expr={"position": f"var a=bo((time-{t_in})/0.65);var b=si((time-{r3(t_out - 0.5)})/0.5);value+[{-px(1100)}*(1-a)-{px(700)}*b,0]",
                  "rotation": f"-1.0-1.5*(1-bo((time-{t_in})/0.65))"})
    fade = fade_ref(lid)
    name, role, pill = f"{lid}_NAME", f"{lid}_ROLE", f"{lid}_PILL"
    name_size = ctx.size("headline", 0.9)
    ops.add("text", id=name, parent=lid, text=g["name"], font=d.font("headline"), size=name_size, color=d.color("ink"),
            position=[x, y], expr={"opacity": fade}, **sp)
    ops.add("text", id=role, parent=lid, text=g["role"], font=d.font("label"), size=ctx.size("label", 0.875), color=d.color("paper"),
            tracking=20, position=[r3(x + px(34)), r3(y - px(170))],
            expr={"opacity": f"100*so((time-{r3(t_in + 0.45)})/0.3)*{fade}/100"}, **sp)
    geo = (STATIC + f"var L=thisComp.layer({js(role)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           f"var x0=p[0]+r.left-{px(34)},x1=p[0]+r.left+r.width+{px(34)},y0=p[1]+r.top-{px(18)},y1=p[1]+r.top+r.height+{px(18)};")
    center = geo + "[(x0+x1)/2,(y0+y1)/2]"
    ops.add("rect", id=pill, parent=lid, color=d.color("ink"), roundness=px(40), rect_expr={"size": geo + "[x1-x0,y1-y0]", "center": center},
            expr={"anchor": center, "position": center, "scale": f"var k=bo((time-{r3(t_in + 0.35)})/0.45);[100*k,100*k]", "opacity": fade}, **sp)
    ops.add("order", layer=pill, below=[role])
    highlighter(ctx, id=f"{name}_HL", parent=lid, target=name, size=name_size, t0=t_in + 0.6, dur=0.55, color=d.color("accent"),
                opacity=fade_ref(lid, 88), pad=px(14), t_in=t_in, t_out=t_out + 0.05)
    paper_card(ctx, id=f"{lid}_CARD", parent=lid, members=[name, role], below=[name, role, pill, f"{name}_HL"],
               pad=(px(80), px(60)), color=d.color("paper"), radius=px(18), opacity=fade, noise=d.texture.get("noise", 0),
               t_in=t_in, t_out=t_out + 0.05)


def _page(ctx, pid, t_in, t_out, draw_at):
    """Full-frame paper with texture, soft shadow, ruled lines and a margin line drawn on from the left."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    paper = f"{pid}_PAPER"
    ops.add("rect", id=paper, parent=pid, color=d.color("paper"), size=[W, r3(H + px(40))], center=[r3(W / 2), r3(H / 2 - px(20))],
            **span(t_in, t_out))
    if d.texture.get("noise"):
        ops.add("effect", layer=paper, match="ADBE Noise", props={"1": d.texture["noise"], "2": 0})
    ops.add("effect", layer=paper, match="ADBE Drop Shadow", props={"2": 120, "3": 180, "4": px(14), "5": px(140)})
    spacing, y0 = px(90), px(135)
    ops.add("rules", id=f"{pid}_RULES", parent=pid, count=int((H - y0) // spacing) + 1, spacing=spacing, y0=y0,
            color=d.color("rule"), stroke=px(3), margin_x=r3(0.2 * W), margin_color=d.color("accent2"),
            expr={"scale": f"var k=so((time-{r3(draw_at)})/0.9);[100*k,100]"}, **span(t_in, t_out))


@register("title-page", "notebook-page")
def title_notebook_page(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.75)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, expr={"position": f"var k=si((time-{t_out})/0.7);value+[0,{-r3(H + px(140))}*k]"})
    _page(ctx, tid, t_in, end, t_in + 0.2)
    size = ctx.size("scripture")
    lines = [parse_line(line, ctx.size("scripture", 0.28)) for line in g["lines"]]
    gap = r3(size * 1.4)
    x, y_first = r3(0.263 * W), r3(0.45 * H - (len(lines) - 1) * gap / 2)
    times = schedule_times(lines, start=t_in + 1.0, step=0.09, line_pause=0.35)
    ink = d.color("ink")
    block = text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("scripture"), "size": size, "color": ink}, align="left",
                       reveal={"dur": 0.45, "rise": px(10), "blur": 6, "by": "words"}, t_in=t_in, t_out=end)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=tid, target=sid, size=size, t0=times[i][k][-1] + 0.45, dur=0.6,
                            color=d.color("accent"), pad=px(14), t_in=t_in, t_out=end)
    if g.get("ref"):
        start = times[-1][-1][-1] + 0.8
        ops.add("text", id=f"{tid}_REF", parent=tid, text=g["ref"], font=d.font("label"), size=ctx.size("label", 1.1),
                color=d.color("accent2"), tracking=40, position=[x, r3(y_first + len(lines) * gap)],
                reveal={"times": [r3(start + 0.04 * i) for i in range(len(g["ref"]))], "dur": 0.35, "rise": px(8), "blur": 4, "by": "chars"},
                **span(t_in, end))


@register("end-card", "notebook-page")
def end_card_notebook_page(ctx, g, opts):
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    E = r3(g["in"])
    eid = ops.uid("END")
    sp = span(E)
    ops.add("group", id=eid, expr={"position": f"var k=so((time-{E})/0.75);value+[0,{-r3(H + px(140))}*(1-k)]"})
    _page(ctx, eid, E, None, E + 0.55)

    # polaroid: white frame + moving photo, dropped in with a settle
    PX, PY, PW, PH = r3(0.294 * W), r3(0.5 * H), px(1560), px(1180)
    pol = f"{eid}_POLAROID"
    drop = r3(E + 0.75)
    ops.add("group", id=pol, parent=eid, anchor=[PX, PY], position=[PX, PY],
            expr={"position": f"var k=bo((time-{drop})/0.8);value+[0,{-px(260)}*(1-k)]",
                  "rotation": f"var k=bo((time-{drop})/0.8);3+5*(1-k)"})
    pop = f"100*so((time-{drop})/0.35)"
    ops.add("rect", id=f"{pol}_FRAME", parent=pol, color=[1, 1, 1], size=[PW, PH], center=[PX, PY], roundness=px(6),
            expr={"opacity": pop}, **sp)
    ops.add("effect", layer=f"{pol}_FRAME", match="ADBE Drop Shadow", props={"2": 95, "3": 180, "4": px(26), "5": px(90)})
    photo = g.get("photo")
    if photo:
        ops.add("footage", id=f"{pol}_PHOTO", parent=pol, file=photo["clip"], start=E, end=r3(ctx.duration),
                src_in=photo.get("src_in", 0), stretch=photo.get("stretch"), width=r3(PW - px(70)),
                position=[PX, r3(PY - px(60))], mask=[r3(PW - px(70)), r3(PH - px(200))],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None, expr={"opacity": pop})

    RX = r3(0.542 * W)
    ink = d.color("ink")
    if g.get("year") is not None:
        year = f"{eid}_YEAR"
        ops.add("text", id=year, parent=eid, text=str(g["year"]), font=d.font("label"), size=px(70), color=d.color("paper"), tracking=60,
                position=[r3(RX + px(44)), r3(0.241 * H)], expr={"opacity": f"100*so((time-{r3(E + 1.2)})/0.3)"}, **sp)
        geo = (STATIC + f"var L=thisComp.layer({js(year)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
               f"var x0=p[0]+r.left-{px(44)},x1=p[0]+r.left+r.width+{px(44)},y0=p[1]+r.top-{px(20)},y1=p[1]+r.top+r.height+{px(20)};")
        c = geo + "[(x0+x1)/2,(y0+y1)/2]"
        ops.add("rect", id=f"{year}_PILL", parent=eid, color=ink, roundness=px(46), rect_expr={"size": geo + "[x1-x0,y1-y0]", "center": c},
                expr={"anchor": c, "position": c, "scale": f"var k=bo((time-{r3(E + 1.1)})/0.45);[100*k,100*k]"}, **sp)
        ops.add("order", layer=f"{year}_PILL", below=[year])
    title = f"{eid}_TITLE"
    tsize = ctx.size("headline", 1.93)
    ops.add("text", id=title, parent=eid, text=g["title"], font=d.font("headline"), size=tsize, color=ink, position=[RX, r3(0.421 * H)],
            reveal={"times": [r3(E + 1.25 + 0.09 * i) for i in range(len(g["title"]))], "dur": 0.5, "rise": px(30), "blur": 6, "by": "chars"}, **sp)
    highlighter(ctx, id=f"{title}_HL", parent=eid, target=title, size=tsize, t0=E + 1.8, dur=0.6, color=d.color("accent"), pad=px(18), t_in=E)
    if g.get("tagline"):
        ops.add("text", id=f"{eid}_TAGLINE", parent=eid, text=g["tagline"], font=d.font("body"), size=ctx.size("body", 0.82), color=ink,
                position=[r3(RX + px(6)), r3(0.502 * H)],
                reveal={"times": [r3(E + 2.2 + 0.12 * i) for i in range(len(g["tagline"].split()))], "dur": 0.4, "rise": px(14), "blur": 6, "by": "words"}, **sp)
    y = 0.597 * H
    for r_i, row in enumerate(g.get("rows", [])):
        t0 = E + 2.8 + r_i * 0.3
        ops.add("text", id=f"{eid}_ROW{r_i + 1}_LABEL", parent=eid, text=row["label"], font=d.font("label"), size=ctx.size("label"),
                color=d.color("accent2"), position=[r3(RX + px(6)), r3(y)],
                reveal={"times": [r3(t0)], "dur": 0.35, "rise": px(10), "blur": 3, "by": "words"}, **sp)
        for v_i, value in enumerate(row["values"]):
            ops.add("text", id=f"{eid}_ROW{r_i + 1}_VALUE{v_i + 1}", parent=eid, text=value, font=d.font("body"), size=ctx.size("body", 0.64),
                    color=ink, position=[r3(RX + px(390)), r3(y)],
                    reveal={"times": [r3(t0 + 0.12 + 0.06 * k) for k in range(len(value.split()))], "dur": 0.35, "rise": px(10), "blur": 3, "by": "words"}, **sp)
            y += px(92)
        y += px(40)
    logo = g.get("logo")
    if logo:
        t = r3(E + 3.9)
        ops.add("image", id=f"{eid}_LOGO", parent=eid, file=logo["file"], width=px(logo.get("width", 560)),
                position=[r3(W - px(430)), px(250)], tint=ink if logo.get("tint", True) else None,
                expr={"opacity": f"100*so((time-{t})/0.5)", "anchor": f"value+[0,-40*(1-so((time-{t})/0.6))]"}, **sp)
