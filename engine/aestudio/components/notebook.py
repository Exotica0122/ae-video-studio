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


def _page(ctx, pid, t_in, t_out, draw_at, spacing_px=90):
    """Full-frame paper with texture, soft shadow, ruled lines and a margin line drawn on from the left."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    paper = f"{pid}_PAPER"
    ops.add("rect", id=paper, parent=pid, color=d.color("paper"), size=[W, r3(H + px(40))], center=[r3(W / 2), r3(H / 2 - px(20))],
            **span(t_in, t_out))
    if d.texture.get("noise"):
        ops.add("effect", layer=paper, match="ADBE Noise", props={"1": d.texture["noise"], "2": 0})
    ops.add("effect", layer=paper, match="ADBE Drop Shadow", props={"2": 120, "3": 180, "4": px(14), "5": px(140)})
    spacing, y0 = px(spacing_px), px(135)
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
    _page(ctx, tid, t_in, end, t_in + 0.2, spacing_px=int(g.get("ruling", 90)))
    size = ctx.size("scripture", float(g.get("size", 1.0)))
    lines = [parse_line(line, ctx.size("scripture", 0.28)) for line in g["lines"]]
    gap = r3(size * 1.4)
    # Centre the block in the safe band rather than on 0.45H: in a tall frame a
    # fixed fraction leaves the foot of the page empty and the text riding high.
    # A photograph, if one is given, is taped above the writing and measured in.
    st, sb = float(g.get("safe_top", 0.0)), float(g.get("safe_bot", 1.0))
    ref_h = ctx.size("label", 1.1) * 2.2 if g.get("ref") else 0.0
    ph_ = g.get("photo") or {}
    pw = r3(W * float(g.get("card_w", 0.56))) if ph_.get("clip") else 0.0
    pht = r3(pw * float(g.get("card_ar", 1.18))) if pw else 0.0
    border, lip = px(46), px(88)
    card_h = r3(pht + border * 2 + lip) if pw else 0.0
    g1 = px(150) if pw else 0.0
    stack = card_h + g1 + size + (len(lines) - 1) * gap + ref_h
    x = r3(float(g.get("x", 0.263)) * W)
    ytop = st * H + ((sb - st) * H - stack) / 2
    y_first = r3(ytop + card_h + g1 + size)
    if pw:
        pcx, pcy = r3(W / 2), r3(ytop + card_h / 2)
        pol = f"{tid}_PRINT"
        drop = r3(t_in + 0.5)
        ops.add("group", id=pol, parent=tid, anchor=[pcx, pcy], position=[pcx, pcy],
                expr={"position": f"var k=bo((time-{drop})/0.85);value+[0,{-px(260)}*(1-k)]",
                      "rotation": f"var k=bo((time-{drop})/0.85);2.0-6*(1-k)"})
        pop = f"100*so((time-{drop})/0.3)"
        ops.add("rect", id=f"{pol}_FRAME", parent=pol, color=[1, 1, 1],
                size=[r3(pw + border * 2), card_h], center=[pcx, pcy], roundness=px(4),
                expr={"opacity": pop}, **span(t_in, end))
        ops.add("effect", layer=f"{pol}_FRAME", match="ADBE Drop Shadow",
                props={"2": 92, "3": 168, "4": px(24), "5": px(96)})
        sw, sh = float(ph_.get("sw", 3024)), float(ph_.get("sh", 4032))
        sc = pw / sw
        hh = (pht / sc) / 2
        my = min(max(float(ph_.get("cy", 0.42)) * sh, hh), sh - hh) / sh
        ops.add("footage", id=f"{pol}_PHOTO", parent=pol, file=ph_["clip"],
                start=t_in, end=end, src_in=ph_.get("src_in", 0), width=pw,
                position=[pcx, r3(pcy - lip / 2 - (my - 0.5) * sh * sc)],
                mask=[pw, pht], mask_center=[0.5, r3(my)],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None, expr={"opacity": pop})
        ops.add("order", layer=f"{pol}_FRAME", below=[f"{pol}_PHOTO"])
    times = schedule_times(lines, start=t_in + 1.0, step=0.09, line_pause=0.35)
    ink = d.color("ink")
    block = text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("headline" if s.hl else "scripture"),
                                           "size": size, "color": ink}, align="left",
                       reveal={"dur": 0.45, "rise": px(10), "blur": 6, "by": "words"}, t_in=t_in, t_out=end)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=tid, target=sid, size=size,
                            t0=times[i][k][-1] + 0.45, dur=0.6, color=d.color("accent"),
                            pad=px(10), band=(-0.13, 0.055), rough=False,
                            t_in=t_in, t_out=end)
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


@register("opening", "notebook")
def opening_notebook(ctx, g, opts):
    """The film opens as a page of the field notebook, then the page is lifted away.

    Ruled paper draws itself on, the trip's first photograph drops onto it as a taped
    print and settles, the title is written on the rules with a marker stroke pulled
    through the highlighted words - and then the whole page slides up and off, leaving
    the footage underneath.

    The stack (kicker, print, title, dates) is measured and centred in the safe band
    rather than pinned to fractions of the frame, so the page is evenly filled at any
    aspect instead of crowding the top and leaving the foot of the page empty.
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.9)
    oid = ops.uid("OPEN")
    top, bot = float(g.get("safe_top", 0.0)), float(g.get("safe_bot", 1.0))
    band_t, band_b = top * H, bot * H
    ops.add("group", id=oid,
            expr={"position": f"var k=si((time-{t_out})/0.75);value+[0,{-r3(H + px(200))}*k]"})
    _page(ctx, oid, t_in, end, t_in + 0.15, spacing_px=int(g.get("ruling", 150)))
    sp = span(t_in, end)

    # ---- measure the whole stack, then centre it in the band -------------------
    # The print takes the PICTURE's proportions. A fixed card aspect cropped a
    # landscape photograph to 62% of its width and sat it wrong in the frame.
    photo = g.get("photo") or {}
    sw_, sh_ = float(photo.get("sw", 3024)), float(photo.get("sh", 4032))
    pw = r3(W * float(g.get("card_w", 0.84)))
    ph = r3(pw * sh_ / sw_)
    border, lip = r3(0.022 * W), r3(0.032 * W)
    card_w, card_h = r3(pw + border * 2), r3(ph + border * 2 + lip)
    size = ctx.size("headline", float(g.get("size", 1.68)))
    lines = [parse_line(line, ctx.size("headline", 0.3)) for line in g["lines"]]
    gap = r3(size * 1.30)
    kick_h = ctx.size("label", 1.0) if g.get("kicker") else 0.0
    date_h = ctx.size("label", 1.05) if g.get("dates") else 0.0
    rule_h = r3(0.004 * W)
    # even gaps, stated once: kicker | print | title | rule | dates
    g1, g2, g3, g4 = r3(0.036 * H * 0.5), r3(0.046 * H), r3(0.020 * H), r3(0.024 * H)
    stack = (kick_h + (g1 if kick_h else 0) + card_h + g2 + size + (len(lines) - 1) * gap
             + g3 + rule_h + ((g4 + date_h) if date_h else 0))
    y = band_t + (band_b - band_t - stack) / 2
    x = r3(0.082 * W)

    kick_y = r3(y + kick_h)
    card_top = y + kick_h + (g1 if kick_h else 0)
    pcy = r3(card_top + card_h / 2)
    pcx = r3(W / 2)
    y_first = r3(card_top + card_h + g2 + size)
    y_last = r3(y_first + (len(lines) - 1) * gap)
    rule_y = r3(y_last + g3)
    date_y = r3(rule_y + g4 + date_h)

    # ---- the print, dropped onto the page --------------------------------------
    pol = f"{oid}_PRINT"
    drop = r3(t_in + 0.45)
    ops.add("group", id=pol, parent=oid, anchor=[pcx, pcy], position=[pcx, pcy],
            expr={"position": f"var k=bo((time-{drop})/0.85);value+[0,{-px(300)}*(1-k)]",
                  "rotation": f"var k=bo((time-{drop})/0.85);-2.2+7*(1-k)"})
    pop = f"100*so((time-{drop})/0.3)"
    # the photo sits in the window above the lip, so the white border is even on
    # three sides and deep at the foot - the way a print actually is
    photo_cy = r3(pcy - lip / 2)
    ops.add("rect", id=f"{pol}_FRAME", parent=pol, color=[1, 1, 1],
            size=[card_w, card_h], center=[pcx, pcy], roundness=px(4),
            expr={"opacity": pop}, **sp)
    ops.add("effect", layer=f"{pol}_FRAME", match="ADBE Drop Shadow",
            props={"2": 92, "3": 168, "4": px(24), "5": px(96)})
    if photo.get("clip"):
        sw, sh = float(photo.get("sw", 3024)), float(photo.get("sh", 4032))
        scale = pw / sw                       # width= sets exactly this scale
        hh = (ph / scale) / 2
        my = min(max(float(photo.get("cy", 0.42)) * sh, hh), sh - hh) / sh
        # Compensate the layer for where the mask window sits in the source. Without
        # this the window lands off-centre in the card and the print looks crooked.
        off_y = (my - 0.5) * sh * scale
        ops.add("footage", id=f"{pol}_PHOTO", parent=pol, file=photo["clip"],
                start=t_in, end=end, src_in=photo.get("src_in", 0), width=pw,
                position=[pcx, r3(photo_cy - off_y)],
                mask=[pw, ph], mask_center=[0.5, r3(my)],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None, expr={"opacity": pop})
        ops.add("order", layer=f"{pol}_FRAME", below=[f"{pol}_PHOTO"])
        for k, fx in enumerate((-0.34, 0.34)):
            ops.add("rect", id=f"{pol}_TAPE{k + 1}", parent=pol, color=d.color("accent"),
                    size=[r3(pw * 0.20), r3(0.026 * W)],
                    center=[r3(pcx + fx * pw), r3(pcy - ph / 2 - border * 0.6)],
                    roundness=r3(0.002 * W),
                    expr={"opacity": f"34*so((time-{r3(drop + 0.35)})/0.35)"}, **sp)

    # ---- the writing ------------------------------------------------------------
    times = schedule_times(lines, start=t_in + 1.15, step=0.09, line_pause=0.34)
    ink = d.color("ink")
    block = text_block(ctx, prefix=oid, parent=oid, lines=lines, times=times, x=x,
                       y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("headline"), "size": size, "color": ink},
                       align="left", reveal={"dur": 0.5, "rise": px(12), "blur": 7, "by": "words"},
                       t_in=t_in, t_out=end)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                sid = block.segments[i][k]
                highlighter(ctx, id=f"{sid}_HL", parent=oid, target=sid, size=size,
                            t0=times[i][k][-1] + 0.4, dur=0.62, color=d.color("accent"),
                            pad=px(10), band=(-0.15, 0.06), rough=False,
                            t_in=t_in, t_out=end)
    k4 = f"var k=eio((time-{r3(t_in + 1.95)})/0.7);"
    ops.add("rect", id=f"{oid}_RULE", parent=oid, color=d.color("accent"),
            rect_expr={"size": k4 + f"[{r3(0.26 * W)}*k,{rule_h}]",
                       "center": k4 + f"[{x}+{r3(0.13 * W)}*k,{rule_y}]"},
            expr={"opacity": f"85"}, **sp)
    if g.get("kicker"):
        kk = g["kicker"]
        # a filled square leads the line, the way a note gets bulleted
        ops.add("rect", id=f"{oid}_BULLET", parent=oid, color=d.color("accent"),
                size=[r3(0.014 * W), r3(0.014 * W)],
                center=[r3(x - 0.028 * W), r3(kick_y - 0.005 * W)],
                expr={"opacity": f"100*so((time-{r3(t_in + 0.85)})/0.3)"}, **sp)
        ops.add("text", id=f"{oid}_KICK", parent=oid, text=kk, font=d.font("label"),
                size=ctx.size("label", 1.0), color=d.color("accent2"), tracking=160,
                justify="left", position=[x, kick_y],
                reveal={"times": [r3(t_in + 0.95 + 0.02 * i) for i in range(len(kk))],
                        "dur": 0.4, "rise": px(6), "blur": 5, "by": "chars"}, **sp)
    if g.get("dates"):
        dt = g["dates"]
        ops.add("text", id=f"{oid}_DATES", parent=oid, text=dt, font=d.font("body"),
                size=ctx.size("label", 1.05), color=d.color("ink"), tracking=90,
                justify="left", position=[x, date_y],
                reveal={"times": [r3(t_in + 2.0 + 0.022 * i) for i in range(len(dt))],
                        "dur": 0.45, "rise": px(8), "blur": 5, "by": "chars"}, **sp)


@register("layout", "notebook")
def layout_notebook(ctx, g, opts):
    """Several pictures at once, as prints laid out on a page of the notebook.

    The editorial layout beds its panels on a dark field, which is right on a black
    title sequence and wrong here - it reads as a hole punched in the paper. Each
    panel becomes a bordered print instead, inset from its box, tilted a little and
    dropped in on its own beat, on the same ruled page the opening and the scripture
    use. The film then looks like one book from beginning to end.

    The page rises on the LAST print's clock, never ahead of them, or it would cover
    the outgoing shot while the prints were still arriving and the frame would flash
    blank paper.
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.55)
    gid = ops.uid("LAYOUT")
    ops.add("group", id=gid, fade=f"100*(1-so((time-{t_out})/0.62))")
    fade = fade_ref(gid)
    sp = span(t_in, end)
    panels = g["panels"]
    last = max([float(p.get("delay", 0.0)) for p in panels] or [0.0])

    if g.get("page", True):
        page = f"{gid}_PAGE"
        ops.add("group", id=page, parent=gid,
                expr={"opacity": f"100*so((time-{r3(t_in + last)})/0.35)*{fade}/100"})
        _page(ctx, page, t_in, end, t_in + last + 0.05, spacing_px=int(g.get("ruling", 150)))

    inset = px(float(g.get("inset", 34)))
    border = px(float(g.get("border", 26)))
    for i, p in enumerate(panels):
        pw = r3(float(p["w"]) - inset * 2 - border * 2)
        ph = r3(float(p["h"]) - inset * 2 - border * 2)
        cx = r3(float(p["x"]) + float(p["w"]) / 2)
        cy = r3(float(p["y"]) + float(p["h"]) / 2)
        delay = float(p.get("delay", 0.0))
        t0 = r3(t_in + delay)
        pid = f"{gid}_{i + 1:02d}"
        hold = f"{pid}_H"
        ops.add("group", id=hold, parent=gid, anchor=[cx, cy], position=[cx, cy],
                rotation=(-1.6 if i % 2 == 0 else 1.5),
                expr={"position": f"var k=bo((time-{t0})/0.95);value+[0,{-px(150)}*(1-k)]"})
        pop = f"100*so((time-{t0})/0.45)*{fade}/100"
        ops.add("rect", id=f"{pid}_CARD", parent=hold, color=[1, 1, 1],
                size=[r3(pw + border * 2), r3(ph + border * 2)], center=[cx, cy],
                roundness=px(4), expr={"opacity": pop}, **sp)
        ops.add("effect", layer=f"{pid}_CARD", match="ADBE Drop Shadow",
                props={"2": 84, "3": 168, "4": px(20), "5": px(78)})
        sw, sh = float(p["sw"]), float(p["sh"])
        scale = max(pw / sw, ph / sh)
        hw, hh = (pw / scale) / 2, (ph / scale) / 2
        mx = min(max(float(p.get("cx", 0.5)) * sw, hw), sw - hw) / sw
        my = min(max(float(p.get("cy", 0.45)) * sh, hh), sh - hh) / sh
        ops.add("footage", id=pid, parent=hold, file=p["clip"], start=t_in, end=end,
                src_in=p.get("src_in", 0), width=r3(sw * scale),
                position=[r3(cx - (mx - 0.5) * sw * scale), r3(cy - (my - 0.5) * sh * scale)],
                mask=[pw, ph], mask_center=[r3(mx), r3(my)],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None,
                gain_db=p.get("gain_db"), levels=p.get("levels"), remap=p.get("remap"),
                expr={"opacity": pop, **(p.get("expr") or {})})
        ops.add("order", layer=f"{pid}_CARD", below=[pid])
        if p.get("highpass"):
            # Outdoor recordings carry wind as low rumble. High-Low Pass set to
            # High Pass (option 1) rolls it off and lets the singing come forward.
            ops.add("effect", layer=pid, match="ADBE Aud HiLo",
                    props={"1": 1, "2": float(p["highpass"])})


@register("backdrop", "notebook")
def backdrop_notebook(ctx, g, opts):
    """One page of ruled paper, held for the whole film.

    Every other element - prints, title, scripture - is laid on this. Drawing the
    page once instead of per beat means it never re-draws, never flickers, and the
    reel reads as a single notebook rather than a stack of separate pages.
    """
    t_in = r3(g.get("in", 0))
    t_out = r3(g.get("out", ctx.duration))
    bid = ctx.ops.uid("PAGE")
    ctx.ops.add("group", id=bid)
    _page(ctx, bid, t_in, t_out, t_in + 0.1, spacing_px=int(g.get("ruling", 150)))


@register("scrapbook", "notebook")
def scrapbook_notebook(ctx, g, opts):
    """The closing page: the verse, with prints taped around it and pen marks.

    A page of type alone is a poster, not a notebook. Photographs pinned at the top,
    tape over their corners, a rule and a few dots in the margin - the page reads as
    something someone kept, and the scripture sits in it rather than on it.
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.7)
    sid = ops.uid("SCRAP")
    ops.add("group", id=sid, fade=f"100*so((time-{t_in})/0.5)*(1-so((time-{r3(t_out)})/0.6))")
    fade = fade_ref(sid)
    sp = span(t_in, end)
    st, sb = float(g.get("safe_top", 0.0)), float(g.get("safe_bot", 1.0))
    bt, bb = st * H, sb * H

    # ---- the prints, pinned across the top -----------------------------------
    photos = g.get("photos") or []
    # Prints may start above the TEXT-safe band - a photograph partly under the
    # host's top bar costs little - which buys the room to make them larger.
    pt = float(g.get("prints_top", 0.058)) * H
    slots = [(r3(0.040 * W), r3(pt), r3(0.450 * W), -4.0, 0.0),
             (r3(0.515 * W), r3(pt + 0.034 * H), r3(0.450 * W), 3.6, 0.22)]
    prints_bottom = bt
    for i, ph in enumerate(photos[:2]):
        x, y, w, tilt, delay = slots[i]
        sw, sh = float(ph.get("sw", 3024)), float(ph.get("sh", 4032))
        pw = r3(w); phh = r3(pw * sh / sw)          # the print keeps the picture's shape
        # a long verse needs the room: cap the print's height, keeping its shape
        max_h = float(g.get("print_max_h", 1.0)) * H
        if phh > max_h:
            phh = r3(max_h); pw = r3(phh * sw / sh)
        border, lip = r3(0.022 * W), r3(0.032 * W)
        cx, cy = r3(x + pw / 2), r3(y + phh / 2)
        prints_bottom = max(prints_bottom, y + phh + border * 2 + lip)
        hold = f"{sid}_P{i + 1}"
        t0 = r3(t_in + 0.45 + delay)
        ops.add("group", id=hold, parent=sid, anchor=[cx, cy], position=[cx, cy], rotation=tilt,
                expr={"position": f"var k=bo((time-{t0})/0.8);value+[0,{-px(170)}*(1-k)]"})
        pop = f"100*so((time-{t0})/0.3)*{fade}/100"
        ops.add("rect", id=f"{hold}_CARD", parent=hold, color=[1, 1, 1],
                size=[r3(pw + border * 2), r3(phh + border * 2 + lip)],
                center=[cx, r3(cy + lip / 2)], roundness=px(3),
                expr={"opacity": pop}, **sp)
        ops.add("effect", layer=f"{hold}_CARD", match="ADBE Drop Shadow",
                props={"2": 80, "3": 168, "4": px(16), "5": px(64)})
        ops.add("footage", id=f"{hold}_IMG", parent=hold, file=ph["clip"], start=t_in, end=end,
                width=pw, position=[cx, cy], mask=[pw, phh], mask_center=[0.5, 0.5],
                lumetri=dict(ctx.grade.get("lumetri", {})) or None, expr={"opacity": pop})
        ops.add("order", layer=f"{hold}_CARD", below=[f"{hold}_IMG"])
        # a strip of tape across the top corner
        ops.add("rect", id=f"{hold}_TAPE", parent=hold, color=d.color("accent"),
                size=[r3(pw * 0.42), r3(0.026 * W)],
                center=[r3(cx - pw / 2 + pw * 0.12), r3(cy - phh / 2 - 0.008 * W)],
                roundness=px(2), expr={"opacity": f"38*so((time-{r3(t0 + 0.2)})/0.3)*{fade}/100"}, **sp)

    # ---- the verse -------------------------------------------------------------
    size = ctx.size("scripture", float(g.get("size", 1.15)))
    lines = [parse_line(line, ctx.size("scripture", 0.3)) for line in g["lines"]]
    gap = r3(size * 1.4)
    x = r3(float(g.get("x", 0.075)) * W)

    # Centre the verse in whatever the prints leave, rather than at a fixed drop:
    # the prints are sized from their own pictures, so the space below them is not
    # known until they are placed, and a fixed drop leaves the page bottom-heavy.
    gap = r3(size * float(g.get("leading", 1.4)))
    ref_size = ctx.size("label", float(g.get("ref_size", 1.15)))
    ref_off = r3(0.030 * H + ref_size)           # last verse baseline -> ref baseline
    ref_h = ref_off if g.get("ref") else 0.0
    stack = size + (len(lines) - 1) * gap + ref_h
    room = (bb - prints_bottom) - 0.02 * H
    if stack > room:
        # never let the verse run under the host's interface or into the prints:
        # shrink type and leading together until the block fits
        k = (room - ref_h) / (stack - ref_h)
        size, gap = r3(size * k), r3(gap * k)
        stack = size + (len(lines) - 1) * gap + ref_h
    y_first = r3(prints_bottom + ((bb - prints_bottom) - stack) / 2 + size)
    times = schedule_times(lines, start=t_in + 1.05, step=0.08, line_pause=0.3)
    ink = d.color("ink")
    block = text_block(ctx, prefix=sid, parent=sid, lines=lines, times=times, x=x,
                       y_first=y_first, gap=gap,
                       style=lambda i, s: {"font": d.font("headline" if s.hl else "scripture"),
                                           "size": size, "color": ink},
                       align="left", reveal={"dur": 0.45, "rise": px(10), "blur": 6, "by": "words"},
                       opacity=fade, t_in=t_in, t_out=end)
    for i, segs in enumerate(lines):
        for k, seg in enumerate(segs):
            if seg.hl:
                tid = block.segments[i][k]
                highlighter(ctx, id=f"{tid}_HL", parent=sid, target=tid, size=size,
                            t0=times[i][k][-1] + 0.4, dur=0.6, color=d.color("accent"),
                            pad=px(10), band=(-0.13, 0.055), rough=False,
                            opacity=fade, t_in=t_in, t_out=end)
    y_end = r3(y_first + (len(lines) - 1) * gap)
    if g.get("ref"):
        rt = r3(times[-1][-1][-1] + 0.55)
        ops.add("text", id=f"{sid}_REF", parent=sid, text=g["ref"], font=d.font("label"),
                size=ref_size, color=d.color("ink"), tracking=80,
                justify="left", position=[x, r3(y_end + ref_off)],
                reveal={"times": [r3(rt + 0.03 * i) for i in range(len(g["ref"]))],
                        "dur": 0.35, "rise": px(8), "blur": 4, "by": "chars"},
                expr={"opacity": fade}, **sp)
        # a short rule and three dots, the way a page gets annotated
        kr = f"var k=eio((time-{r3(rt + 0.15)})/0.65);"
        ops.add("rect", id=f"{sid}_RULE", parent=sid, color=d.color("accent"),
                rect_expr={"size": kr + f"[{r3(0.22 * W)}*k,{r3(0.004 * W)}]",
                           "center": kr + f"[{x}+{r3(0.11 * W)}*k,{r3(y_end + 0.020 * H)}]"},
                expr={"opacity": f"85*{fade}/100"}, **sp)
        for n in range(3):
            ops.add("rect", id=f"{sid}_DOT{n + 1}", parent=sid, color=d.color("accent2"),
                    size=[r3(0.011 * W), r3(0.011 * W)],
                    center=[r3(W - 0.16 * W + n * 0.038 * W), r3(y_end + ref_off - ref_size * 0.36)],
                    roundness=r3(0.006 * W),
                    expr={"opacity": f"60*so((time-{r3(rt + 0.5 + n * 0.12)})/0.3)*{fade}/100"}, **sp)
    logo = g.get("logo")
    if logo:
        lw = r3(float(logo.get("width", 0.13)) * W)
        lt = r3(t_in + float(logo.get("at", 2.6)))
        # opacity only: the image op sizes the layer by setting scale from `width`,
        # and an expression on scale would override that and render it at full size
        ops.add("image", id=f"{sid}_LOGO", parent=sid, file=logo["file"], width=lw,
                position=[r3(W / 2), r3(y_end + ref_off - ref_size * 0.36)],   # centred on the page
                tint=d.color("ink") if logo.get("tint") else None,
                expr={"opacity": f"100*so((time-{lt})/0.8)*{fade}/100"}, **sp)
