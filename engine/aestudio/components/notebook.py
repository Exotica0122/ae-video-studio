"""Paper Notebook treatments: paper cards with marker highlights, paper-tab lower third,
notebook-page title and polaroid end card."""
from ..util import js, r3
from . import register
from .layout import STATIC, T_END, fade_ref, highlighter, paper_card, parse_line, place_block, segment_times, span, text_block


@register("caption", "paper-card")
@register("quote", "paper-card")
def caption_paper_card(ctx, g, opts):
    d, ops = ctx.design, ctx.ops
    quote = g["type"] == "quote"
    vt = ctx.voices[g["voice"]]
    t_in = r3(g.get("in", vt.onset - 0.3))
    t_out = r3(g.get("out", vt.offset + 0.5))
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
    times = segment_times(lines, vt.words)
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
