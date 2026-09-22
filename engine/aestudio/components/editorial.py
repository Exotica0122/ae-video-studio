"""Editorial treatments: type set directly on full-bleed footage.

Unlike the paper families, nothing here hides the picture. An alpha-gradient PNG
darkens only the part of the frame the type sits on, so photographs stay
full-bleed and the words stay legible over them. The gradients ship beside the
design.json as scrim-title.png / scrim-caption.png.

Designed for a light-ink palette on dark footage: `ink` is used for the type, so
a design using these treatments wants a pale `ink`, not a paper-dark one.
"""
from ..util import r3
from . import register
from .layout import LayoutError, fade_ref, parse_line, schedule_times, scrim, span, text_block

# alpha-gradient assets that ship beside the design.json
SCRIM_TITLE = "scrim-title.png"
SCRIM_CAPTION = "scrim-caption.png"

# How long a layout's bed and panels take to rise. They share one curve so the
# bed can never be more opaque than the panels sitting on it.
RAMP_IN = 0.35


def _photo_grade(ctx, photo):
    """The project grade, plus this photograph's own exposure trim.

    Lumetri parameter "20" is exposure, matching how a shot's `exposure` is applied
    in the compiler. A single underexposed frame - an indoor group shot that has to
    carry type over it - can be lifted here without touching the global grade.
    """
    lum = dict(ctx.grade.get("lumetri", {}))
    ev = float((photo or {}).get("exposure", 0) or 0)
    if ev:
        lum["20"] = r3(float(lum.get("20", 0)) + ev)
    return lum or None


def _label(ctx, *, id, parent, text, x, y, t0, opacity, **sp):
    """Letterspaced Latin kicker - the English line above a Korean sentence."""
    d, ops = ctx.design, ctx.ops
    ops.add("text", id=id, parent=parent, text=text, font=d.font("label"),
            size=ctx.size("label", 0.78), color=d.color("accent2"), tracking=320, justify="left",
            position=[r3(x), r3(y)],
            reveal={"times": [r3(t0 + 0.02 * i) for i in range(len(text))],
                    "dur": 0.5, "rise": 0, "blur": 6, "by": "chars"},
            expr={"opacity": opacity}, **sp)


@register("title-page", "editorial")
def title_editorial(ctx, g, opts):
    """Full-bleed photo, gradient scrim, left-aligned title stack."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.95)
    tid = ops.uid("TITLE")
    ops.add("group", id=tid, fade=f"100*(1-so((time-{t_out})/0.6))")
    fade = fade_ref(tid)
    sp = span(t_in, end)

    photo = g.get("photo")
    if photo:
        bg = f"{tid}_BG"
        ops.add("footage", id=bg, parent=tid, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), zoom=photo.get("zoom", 1.04),
                position=[r3(W / 2), r3(H / 2)],
                lumetri=_photo_grade(ctx, photo), expr={"opacity": fade})
    scrim(ctx, id=f"{tid}_SCRIM", parent=tid, asset=SCRIM_TITLE, strength=92,
           opacity=fade, **sp)

    x = r3(px(150))
    # A title page is one big line; the same treatment also carries a credit list,
    # which needs much smaller type. `role` picks the type role, `size` scales it.
    role = g.get("role", "scripture")
    mult = float(g.get("size", 0.94))
    size = ctx.size(role, mult)
    lines = [parse_line(line, ctx.size(role, mult * 0.3)) for line in g["lines"]]
    gap = r3(size * (1.32 if len(lines) == 1 else 1.5))
    # the block sits on its last line and grows upward, so a six-name credit list
    # stacks above the same baseline a one-line title uses
    y_first = r3(0.744 * H - (len(lines) - 1) * gap)
    if g.get("ref"):
        # clear of the first line's ascenders, however many lines there are
        _label(ctx, id=f"{tid}_KICKER", parent=tid, text=g["ref"], x=x,
               y=r3(y_first - size - px(50)), t0=t_in + 0.35, opacity=fade, **sp)
    # A one-line title can luxuriate; a six-name list has to be fully on screen
    # long enough to read, so tighten the cadence as lines are added.
    many = len(lines) > 2
    times = schedule_times(lines, start=t_in + (0.45 if many else 0.7),
                           step=0.08 if many else 0.13,
                           line_pause=0.16 if many else 0.35)
    text_block(ctx, prefix=tid, parent=tid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("headline" if not s.hl else "headline"),
                                   "size": size, "color": d.color("accent" if s.hl else "ink")},
               align="left", reveal={"dur": 0.8, "rise": px(14), "blur": 12, "by": "words"},
               opacity=fade, t_in=t_in, t_out=end)

    rule_y = r3(y_first + len(lines) * gap + px(28))
    k = f"var k=eio((time-{r3(t_in + 1.15)})/0.7);"
    ops.add("rect", id=f"{tid}_RULE", parent=tid, color=d.color("accent2"),
            rect_expr={"size": k + f"[{px(252)}*k,{px(2)}]",
                       "center": f"[{r3(x + px(126))},{rule_y}]"},
            expr={"opacity": fade}, **sp)
    if g.get("dates"):
        ops.add("text", id=f"{tid}_DATES", parent=tid, text=g["dates"], font=d.font("body"),
                size=ctx.size("label", 0.92), color=d.color("accent2"), justify="left",
                position=[x, r3(rule_y + px(56))],
                reveal={"times": [r3(t_in + 1.5 + 0.02 * i) for i in range(len(g["dates"]))],
                        "dur": 0.5, "rise": 0, "blur": 6, "by": "chars"},
                expr={"opacity": fade}, **sp)


@register("caption", "editorial")
@register("quote", "editorial")
def caption_editorial(ctx, g, opts):
    """Kicker + one or two lines, bottom-left, over a gradient scrim."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    vt = ctx.voices.get(g["voice"]) if g.get("voice") else None
    t_in = r3(g["in"]) if g.get("in") is not None else r3(vt.onset - 0.35)
    t_out = r3(g["out"]) if g.get("out") is not None else r3(vt.offset + 0.55)
    cid = ops.uid("CAPTION")
    ops.add("group", id=cid,
            fade=f"100*so((time-{t_in})/0.5)*(1-so((time-{r3(t_out - 0.5)})/0.5))")
    fade = fade_ref(cid)
    sp = span(t_in, r3(t_out + 0.1))
    scrim(ctx, id=f"{cid}_SCRIM", parent=cid, asset=SCRIM_CAPTION, strength=96,
           opacity=fade, **sp)

    x = r3(px(150))
    size = ctx.size("quote", 0.62)
    lines = [parse_line(line, ctx.size("quote", 0.2)) for line in g["lines"]]
    gap = r3(size * 1.34)
    # keep the last line clear of the frame edge - the type sits on the picture,
    # so it needs the same bottom margin the title stack uses
    y_first = r3(H - px(300) - (len(lines) - 1) * gap)
    if g.get("label"):
        _label(ctx, id=f"{cid}_KICKER", parent=cid, text=g["label"], x=x,
               y=r3(y_first - (len(lines) - 1) * gap - size - px(46)),
               t0=t_in + 0.2, opacity=fade, **sp)
    times = schedule_times(lines, start=t_in + 0.4, step=0.1, line_pause=0.28)
    text_block(ctx, prefix=cid, parent=cid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("quote"), "size": size,
                                   "color": d.color("accent" if s.hl else "ink")},
               align="left", reveal={"dur": 0.65, "rise": px(10), "blur": 8, "by": "words"},
               opacity=fade, t_in=t_in, t_out=r3(t_out + 0.1))


@register("end-card", "editorial")
def end_card_editorial(ctx, g, opts):
    """Scripture centred over a darkened full-bleed photo."""
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
        ops.add("footage", id=bg, parent=eid, file=photo["clip"], start=E, end=r3(ctx.duration),
                src_in=photo.get("src_in", 0), zoom=photo.get("zoom", 1.06),
                position=[cx, r3(H / 2)],
                lumetri=_photo_grade(ctx, photo), expr={"opacity": fade})
    # How hard the photograph is veiled. The default buries an already-dark frame,
    # so a graphic carrying a dim group shot can ask for less.
    shade = r3(float(g.get("shade", 84)))
    ops.add("rect", id=f"{eid}_SHADE", parent=eid, color=d.color("shade"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[cx, r3(H / 2)],
            expr={"opacity": f"{shade}*{fade}/100"}, **sp)

    e_mult = float(g.get("size", 0.55))
    size = ctx.size("scripture", e_mult)
    if "lines" not in g:
        # This treatment is a closing statement, not the info card that `notebook-page` and
        # `centered-stack` build from title/year/rows. Say so, rather than KeyError-ing on a
        # perfectly valid end-card graphic.
        raise LayoutError(
            "the 'editorial' end-card is a closing statement and needs 'lines'; a title/year/"
            "tagline/rows end card needs a treatment that renders info rows, such as "
            "'notebook-page' or 'centered-stack'")
    lines = [parse_line(line, ctx.size("scripture", e_mult * 0.33)) for line in g["lines"]]
    gap = r3(size * 1.42)
    y_first = r3(0.38 * H)
    times = schedule_times(lines, start=E + 0.7, step=0.11, line_pause=0.4)
    text_block(ctx, prefix=eid, parent=eid, lines=lines, times=times, x=cx, y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("scripture"), "size": size,
                                   "color": d.color("accent" if s.hl else "ink")},
               align="center", reveal={"dur": 0.85, "rise": px(12), "blur": 12, "by": "words"},
               opacity=fade, t_in=E)

    rule_y = r3(y_first + len(lines) * gap + px(40))
    k = f"var k=eio((time-{r3(E + 1.6)})/0.8);"
    ops.add("rect", id=f"{eid}_RULE", parent=eid, color=d.color("accent2"),
            rect_expr={"size": k + f"[{px(184)}*k,{px(2)}]", "center": f"[{cx},{rule_y}]"},
            expr={"opacity": fade}, **sp)
    if g.get("ref"):
        ops.add("text", id=f"{eid}_REF", parent=eid, text=g["ref"], font=d.font("label"),
                size=ctx.size("label", 0.86), color=d.color("accent2"), tracking=340,
                justify="center", position=[cx, r3(rule_y + px(54))],
                reveal={"times": [r3(E + 2.0 + 0.025 * i) for i in range(len(g["ref"]))],
                        "dur": 0.6, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **sp)
    if g.get("tagline"):
        ops.add("text", id=f"{eid}_TAG", parent=eid, text=g["tagline"], font=d.font("body"),
                size=ctx.size("label", 0.8), color=d.color("accent2"), tracking=300,
                justify="center", position=[cx, r3(0.78 * H)],
                reveal={"times": [r3(E + 2.5 + 0.02 * i) for i in range(len(g["tagline"]))],
                        "dur": 0.6, "rise": 0, "blur": 6, "by": "chars"},
                expr={"opacity": fade}, **sp)


# Where an inset sits, as a fraction of the frame. Anchored to a corner so several
# insets in one shot form a deliberate arrangement rather than floating at random.
_SPOTS = {
    "tl": (0.085, 0.150), "tr": (0.915, 0.150),
    "bl": (0.085, 0.850), "br": (0.915, 0.850),
    "cl": (0.085, 0.500), "cr": (0.915, 0.500),
}


@register("inset", "editorial")
def inset_editorial(ctx, g, opts):
    """Small photographs laid over the shot beneath.

    This is how weak material earns its place. A 1280px phone photo shown
    full-bleed at 4K is a 3x upscale; the same photo 900px wide is a 0.7x
    DOWNSCALE, and reads sharp. Portrait frames, which lose ~60% of their height
    to a 16:9 crop, appear whole here instead.

    Each item: {"clip", "at": "tl|tr|bl|br|cl|cr", "width": 900, "rotate": -1.5,
                "delay": 0.0}
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    gid = ops.uid("INSET")
    ops.add("group", id=gid,
            fade=f"100*so((time-{t_in})/0.5)*(1-so((time-{r3(t_out - 0.45)})/0.45))")
    fade = fade_ref(gid)
    sp = span(t_in, r3(t_out + 0.1))

    for i, item in enumerate(g["items"]):
        at = item.get("at", "br")
        fx, fy = _SPOTS.get(at, _SPOTS["br"])
        w = r3(px(float(item.get("width", 900))))
        delay = float(item.get("delay", 0.0))
        t0 = r3(t_in + 0.25 + delay)
        aspect = float(item.get("aspect", 0.75))
        pad_o = px(22)
        card_w = w + pad_o * 2
        card_h = w * aspect + pad_o * 2 + px(18)
        # Pin to the corner, then keep the whole card on screen. A portrait inset is
        # far taller than a landscape one at the same width, so a fixed corner point
        # pushes it off the top or bottom of the frame.
        m = px(70)
        ax = fx * W + (card_w / 2 if fx < 0.5 else -card_w / 2)
        ay = fy * H
        ax = r3(min(W - m - card_w / 2, max(m + card_w / 2, ax)))
        ay = r3(min(H - m - card_h / 2, max(m + card_h / 2, ay)))
        iid = f"{gid}_{i + 1:02d}"
        # Card and photo ride a null placed at the inset's spot, and the null is what
        # scales. Scaling the shape layer directly would scale about the comp origin,
        # not about the card, and fling it across the frame.
        hold = f"{iid}_H"
        ops.add("group", id=hold, parent=gid, position=[ax, ay],
                rotation=item.get("rotate", 0),
                expr={"scale": f"var k=eio((time-{t0})/0.6);var s=92+8*k;[s,s]"})
        # the card matches the photo it holds: a 4:3 card around a 3:4 portrait
        # would leave the print floating in white
        # The card fades on the item's own clock, not the group's. A staggered item
        # whose card arrived first showed as an empty white rectangle until its
        # photograph caught up.
        ops.add("rect", id=f"{iid}_CARD", parent=hold, color=[1, 1, 1],
                size=[r3(card_w), r3(card_h)],
                center=[0, 0],
                expr={"opacity": f"96*so((time-{t0})/0.5)*{fade}/100"}, **sp)
        ops.add("effect", layer=f"{iid}_CARD", match="ADBE Drop Shadow",
                props={"2": 55, "3": 135, "4": r3(px(14)), "5": r3(px(46))})
        ops.add("footage", id=iid, parent=hold, file=item["clip"],
                start=t_in, end=r3(t_out + 0.1), width=w,
                src_in=item.get("src_in", 0),  # an inset can be a moving clip, not just a still
                position=[0, r3(-px(9))],  # sit above the print lip
                lumetri=dict(ctx.grade.get("lumetri", {})) or None,
                expr={"opacity": f"100*so((time-{t0})/0.38)*{fade}/100"})
        # move the CARD under the photo - `order` pushes `layer` below `below`,
        # so naming the photo here would bury it under its own white card
        ops.add("order", layer=f"{iid}_CARD", below=[iid])


@register("layout", "editorial")
def layout_editorial(ctx, g, opts):
    """Several photographs on screen at once, each in its own panel.

    Every panel is cropped to the PANEL's aspect ratio and masked around that
    photograph's own subject, so a portrait frame in a narrow vertical panel keeps
    its subject whole. This is the opposite of a 16:9 full-bleed crop, which throws
    away ~60% of a portrait frame's height and usually the subject with it.

    Each panel: {"clip", "x", "y", "w", "h" (comp px), "cx", "cy" (subject, 0..1),
                 "sw", "sh" (source pixel size), "delay"}
    """
    ops, W, H, px = ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    gid = ops.uid("LAYOUT")
    # The group carries the OUT ramp only. Giving it an in-ramp too made every
    # panel's opacity a product of two rising curves, which held the panels near
    # zero long after the bed had gone opaque - see the bed note below.
    #
    # It holds at full strength right up to t_out and only fades AFTER it. Fading
    # out before t_out uncovered the shot bedded underneath, so the picture the
    # layout was built over flashed back on its own for a beat before the next shot
    # arrived. Now the next shot dissolves over the top of the layout instead.
    ops.add("group", id=gid, fade=f"100*(1-so((time-{t_out})/0.45))")
    fade = fade_ref(gid)
    sp = span(t_in, r3(t_out + 0.55))
    # A dark bed so the seams between panels read as deliberate, not as gaps.
    # It must never outrun the panels. While the bed is opaque and the panels are
    # not yet up it hides the outgoing shot completely and the frame flashes black
    # - which is exactly what a fast bed ramp used to do here. Running it on the
    # LAST panel's clock keeps bed opacity <= every panel's, so the join reads as a
    # cross-dissolve and the seams briefly show the shot underneath, never a hole.
    last_delay = max([float(p.get("delay", 0.0)) for p in g["panels"]] or [0.0])
    ops.add("rect", id=f"{gid}_BED", parent=gid, color=ctx.design.color("shade"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"100*so((time-{r3(t_in + last_delay)})/{RAMP_IN})*{fade}/100"}, **sp)

    for i, p in enumerate(g["panels"]):
        pw, ph = r3(p["w"]), r3(p["h"])
        pcx, pcy = r3(p["x"] + pw / 2), r3(p["y"] + ph / 2)
        sw, sh = float(p["sw"]), float(p["sh"])
        cx, cy = float(p.get("cx", 0.5)), float(p.get("cy", 0.45))
        delay = float(p.get("delay", 0.0))
        t0 = r3(t_in + delay)
        scale = max(pw / sw, ph / sh)            # cover the panel, never letterbox it
        # the mask window sits over the subject, clamped inside the source
        hw, hh = (pw / scale) / 2, (ph / scale) / 2
        mx = min(max(cx * sw, hw), sw - hw) / sw
        my = min(max(cy * sh, hh), sh - hh) / sh
        # position the layer so that masked window lands on the panel
        off_x = (mx - 0.5) * sw * scale
        off_y = (my - 0.5) * sh * scale
        pid = f"{gid}_{i + 1:02d}"
        ops.add("footage", id=pid, parent=gid, file=p["clip"],
                start=t_in, end=r3(t_out + 0.55), src_in=p.get("src_in", 0),
                width=r3(sw * scale),
                position=[r3(pcx - off_x), r3(pcy - off_y)],
                mask=[pw, ph], mask_center=[r3(mx), r3(my)],
                lumetri=_photo_grade(ctx, p),
                # a panel can be a moving clip, and a moving clip may need to be heard
                gain_db=p.get("gain_db"), levels=p.get("levels"), remap=p.get("remap"),
                expr={"opacity": f"100*so((time-{t0})/{RAMP_IN})*{fade}/100",
                      **(p.get("expr") or {})})


@register("opening", "editorial")
def opening_editorial(ctx, g, opts):
    """The title sequence: a travel document that assembles itself over frame one.

    A montage that opens on a caption card asks the room to read before it has been
    given a reason to look. This opens on the photograph instead and builds the
    document over it - route, coordinates, title, dates, crew - so the first thing
    the audience sees is the team, and the type arrives as annotation on top.

    The travel language is deliberate and cheap to read at a distance: letterspaced
    Latin capitals, a hairline route with a marker that flies ICN -> WLG, and real
    coordinates for Wellington.

    g: {"in", "out", "lines", "kicker", "coords", "from", "to", "dates", "names",
        "photo": {"clip", ...}}
    """
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.8)
    oid = ops.uid("OPEN")
    # hold at full strength, then lift off: the first shot is already underneath
    ops.add("group", id=oid, fade=f"100*(1-so((time-{t_out})/0.7))")
    fade = fade_ref(oid)
    sp = span(t_in, end)
    x = r3(px(150))
    # Everything vertical is placed in a fraction of the frame, then remapped into
    # the safe band. A 9:16 delivery has the host's own interface over the top and
    # bottom of the picture, so the type has to live between them; 16:9 leaves the
    # default band of the whole frame and nothing moves.
    top, bot = float(g.get("safe_top", 0.0)), float(g.get("safe_bot", 1.0))

    def Y(f):
        return r3((top + f * (bot - top)) * H)

    photo = g.get("photo")
    if photo:
        # a long settling push: starts well inside the frame and eases out, so the
        # picture is still moving while the type lands on it
        z0, z1 = float(photo.get("from", 1.20)), float(photo.get("to", 1.05))
        cover = ("var b=Math.max(thisComp.width/thisLayer.source.width,"
                 "thisComp.height/thisLayer.source.height);")
        k = f"var k=eio(linear(time,{t_in},{r3(t_out + 0.6)},0,1));"
        z = f"var z=b*({r3(z0)}+({r3(z1 - z0)})*k);"
        ops.add("footage", id=f"{oid}_BG", parent=oid, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), position=[r3(W / 2), r3(H / 2)],
                lumetri=_photo_grade(ctx, photo),
                expr={"scale": cover + k + z + "[z*100,z*100]", "opacity": fade})
    # A veil that starts heavy and lifts as the type settles: the frame reads as a
    # title card first and as a photograph by the time the crew list arrives.
    ops.add("rect", id=f"{oid}_VEIL", parent=oid, color=d.color("shade"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"(68-44*eio((time-{r3(t_in + 0.5)})/1.9))*{fade}/100"}, **sp)
    scrim(ctx, id=f"{oid}_SCRIM", parent=oid, asset=SCRIM_TITLE, strength=64, opacity=fade, **sp)

    # ---- route strip: ICN ---o--- WLG -------------------------------------
    y_r = Y(0.104)
    lab = ctx.size("label", 0.74)
    a_code, b_code = g.get("from", "ICN"), g.get("to", "WLG")
    ops.add("text", id=f"{oid}_FROM", parent=oid, text=a_code, font=d.font("label"),
            size=lab, color=d.color("accent2"), tracking=300, justify="left",
            position=[x, y_r],
            reveal={"times": [r3(t_in + 0.45 + 0.03 * i) for i in range(len(a_code))],
                    "dur": 0.45, "rise": 0, "blur": 6, "by": "chars"},
            expr={"opacity": fade}, **sp)
    ops.add("text", id=f"{oid}_TO", parent=oid, text=b_code, font=d.font("label"),
            size=lab, color=d.color("accent"), tracking=300, justify="left",
            position=[r3(x + px(760)), y_r],
            reveal={"times": [r3(t_in + 1.95 + 0.03 * i) for i in range(len(b_code))],
                    "dur": 0.45, "rise": 0, "blur": 6, "by": "chars"},
            expr={"opacity": fade}, **sp)
    # the hairline draws outward from the departure end
    lx0, lx1 = r3(x + px(170)), r3(x + px(700))
    ly = r3(y_r - px(16))
    grow = f"var k=eio((time-{r3(t_in + 0.5)})/0.95);"
    ops.add("rect", id=f"{oid}_ROUTE", parent=oid, color=d.color("rule"),
            rect_expr={"size": grow + f"[{r3(lx1 - lx0)}*k,{px(2)}]",
                       "center": grow + f"[{lx0}+{r3((lx1 - lx0) / 2)}*k,{ly}]"},
            expr={"opacity": f"70*{fade}/100"}, **sp)
    # and a marker flies along it once the line has drawn
    fly = f"var k=eio(linear(time,{r3(t_in + 1.0)},{r3(t_in + 2.05)},0,1));"
    ops.add("rect", id=f"{oid}_MARK", parent=oid, color=d.color("accent"),
            rect_expr={"size": f"[{px(20)},{px(20)}]",
                       "center": fly + f"[{lx0}+{r3(lx1 - lx0)}*k,{ly}]"},
            expr={"opacity": f"100*so((time-{r3(t_in + 0.95)})/0.25)*{fade}/100"}, **sp)

    # ---- kicker + coordinates ---------------------------------------------
    y_k = Y(0.166)
    kick = "   ·   ".join(t for t in (g.get("kicker"), g.get("coords")) if t)
    if kick:
        _label(ctx, id=f"{oid}_KICK", parent=oid, text=kick, x=x, y=y_k,
               t0=t_in + 0.75, opacity=fade, **sp)

    # ---- the title ---------------------------------------------------------
    mult = float(g.get("size", 1.16))
    size = ctx.size("headline", mult)
    lines = [parse_line(line, ctx.size("headline", mult * 0.30)) for line in g["lines"]]
    gap = r3(size * 1.14)
    # Where the title's last line sits, in safe-band space. The default puts it in
    # the upper third, which suits a wide frame; a vertical frame usually has the
    # people across the middle, so the type belongs lower, under them.
    y_last = Y(float(g.get("title_y", 0.430)))
    y_first = r3(y_last - (len(lines) - 1) * gap)
    times = schedule_times(lines, start=t_in + 1.15, step=0.1, line_pause=0.32)
    text_block(ctx, prefix=oid, parent=oid, lines=lines, times=times, x=x, y_first=y_first, gap=gap,
               style=lambda i, s: {"font": d.font("headline"), "size": size,
                                   "color": d.color("accent" if s.hl else "ink")},
               align="left", reveal={"dur": 0.95, "rise": px(26), "blur": 16, "by": "words"},
               opacity=fade, t_in=t_in, t_out=end)

    # ---- rule + dates ------------------------------------------------------
    y_rule = r3(y_last + px(74))
    k2 = f"var k=eio((time-{r3(t_in + 2.2)})/0.8);"
    ops.add("rect", id=f"{oid}_RULE", parent=oid, color=d.color("accent2"),
            rect_expr={"size": k2 + f"[{px(330)}*k,{px(3)}]",
                       "center": k2 + f"[{r3(x + px(165))}*k+{r3(x)}*(1-k),{y_rule}]"},
            expr={"opacity": fade}, **sp)
    if g.get("dates"):
        dt = g["dates"]
        ops.add("text", id=f"{oid}_DATES", parent=oid, text=dt, font=d.font("body"),
                size=ctx.size("label", 1.0), color=d.color("ink"), tracking=120, justify="left",
                position=[x, r3(y_rule + px(82))],
                reveal={"times": [r3(t_in + 2.5 + 0.022 * i) for i in range(len(dt))],
                        "dur": 0.55, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **sp)

    # ---- the crew ----------------------------------------------------------
    # One letterspaced row rather than a column: it reads as the manifest on a
    # travel document, and it keeps the names clear of the title above them.
    names = g.get("names") or []
    if names:
        row = "   ·   ".join(names)
        ops.add("text", id=f"{oid}_CREW", parent=oid, text=row, font=d.font("body"),
                size=ctx.size("label", 0.92), color=d.color("accent2"), tracking=90,
                justify="left", position=[x, Y(0.905)],
                reveal={"times": [r3(t_in + 2.95 + 0.028 * i) for i in range(len(row))],
                        "dur": 0.6, "rise": px(8), "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **sp)
        ops.add("rect", id=f"{oid}_CREWRULE", parent=oid, color=d.color("rule"),
                rect_expr={"size": ("var k=eio((time-" + str(r3(t_in + 2.8)) + ")/0.7);"
                                    f"[{px(1100)}*k,{px(1)}]"),
                           "center": ("var k=eio((time-" + str(r3(t_in + 2.8)) + ")/0.7);"
                                      f"[{r3(x)}+{px(550)}*k,{r3(Y(0.905) - px(56))}]")},
                expr={"opacity": f"46*{fade}/100"}, **sp)


def _open_common(ctx, g):
    """Shared scaffolding for the opening directions: group, fade, safe band, photo."""
    d, ops, W, H, px = ctx.design, ctx.ops, ctx.width, ctx.height, ctx.px
    t_in, t_out = r3(g["in"]), r3(g["out"])
    end = r3(t_out + 0.8)
    oid = ops.uid("OPEN")
    ops.add("group", id=oid, fade=f"100*(1-so((time-{t_out})/0.7))")
    top, bot = float(g.get("safe_top", 0.0)), float(g.get("safe_bot", 1.0))
    Y = lambda f: r3((top + f * (bot - top)) * H)
    return d, ops, W, H, px, t_in, t_out, end, oid, fade_ref(oid), span(t_in, end), Y


@register("opening", "aperture")
def opening_aperture(ctx, g, opts):
    """The frame opens like a lens: two black bars part from a slit at the centre.

    The picture is withheld for a beat and then given, which is a stronger hook on a
    phone than a picture that is simply there. The bars leave two hairlines behind as
    they go, so the gesture resolves into the design rather than just disappearing.
    """
    d, ops, W, H, px, t_in, t_out, end, oid, fade, sp, Y = _open_common(ctx, g)
    x = r3(px(150))
    photo = g.get("photo")
    if photo:
        cover = ("var b=Math.max(thisComp.width/thisLayer.source.width,"
                 "thisComp.height/thisLayer.source.height);")
        k = f"var k=eio(linear(time,{t_in},{r3(t_out + 0.6)},0,1));var z=b*(1.16+(-0.12)*k);"
        ops.add("footage", id=f"{oid}_BG", parent=oid, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), position=[r3(W / 2), r3(H / 2)],
                lumetri=_photo_grade(ctx, photo),
                expr={"scale": cover + k + "[z*100,z*100]", "opacity": fade})
    ops.add("rect", id=f"{oid}_VEIL", parent=oid, color=d.color("shade"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"(52-30*eio((time-{r3(t_in + 0.8)})/1.6))*{fade}/100"}, **sp)
    scrim(ctx, id=f"{oid}_SCRIM", parent=oid, asset=SCRIM_TITLE, strength=70, opacity=fade, **sp)

    # the aperture: half-height grows from a slit to the whole frame
    o0, od = r3(t_in + 0.12), 1.15
    ap = f"var k=eio((time-{o0})/{od});var a={r3(H * 0.021)}+{r3(H * 0.479)}*k;"
    for name, sgn in (("T", -1), ("B", 1)):
        ops.add("rect", id=f"{oid}_BAR{name}", parent=oid, color=[0, 0, 0],
                rect_expr={"size": ap + f"[{r3(W + px(20))},{r3(H / 2)}-a]",
                           "center": ap + (f"[{r3(W / 2)},({r3(H / 2)}-a)/2]" if sgn < 0
                                           else f"[{r3(W / 2)},{r3(H)}-({r3(H / 2)}-a)/2]")},
                expr={"opacity": fade}, **sp)
        ops.add("rect", id=f"{oid}_EDGE{name}", parent=oid, color=d.color("accent"),
                rect_expr={"size": ap + f"[{r3(W + px(20))},{px(3)}]",
                           "center": ap + f"[{r3(W / 2)},{r3(H / 2)}{'-' if sgn < 0 else '+'}a]"},
                expr={"opacity": f"100*so((time-{o0})/0.3)"
                                 f"*(1-so((time-{r3(o0 + od)})/0.5))*{fade}/100"}, **sp)

    mult = float(g.get("size", 1.16))
    size = ctx.size("headline", mult)
    lines = [parse_line(line, ctx.size("headline", mult * 0.30)) for line in g["lines"]]
    gap = r3(size * 1.14)
    y_last = Y(float(g.get("title_y", 0.430)))
    times = schedule_times(lines, start=t_in + 0.95, step=0.1, line_pause=0.3)
    text_block(ctx, prefix=oid, parent=oid, lines=lines, times=times, x=x,
               y_first=r3(y_last - (len(lines) - 1) * gap), gap=gap,
               style=lambda i, s: {"font": d.font("headline"), "size": size,
                                   "color": d.color("accent" if s.hl else "ink")},
               align="left", reveal={"dur": 0.9, "rise": px(34), "blur": 18, "by": "words"},
               opacity=fade, t_in=t_in, t_out=end)
    if g.get("kicker"):
        _label(ctx, id=f"{oid}_KICK", parent=oid, text=g["kicker"], x=x,
               y=r3(y_last - (len(lines) - 1) * gap - size - px(54)),
               t0=t_in + 1.5, opacity=fade, **sp)
    if g.get("dates"):
        dt = g["dates"]
        ops.add("text", id=f"{oid}_DATES", parent=oid, text=dt, font=d.font("body"),
                size=ctx.size("label", 1.0), color=d.color("accent2"), tracking=140,
                justify="left", position=[x, r3(y_last + px(96))],
                reveal={"times": [r3(t_in + 1.85 + 0.022 * i) for i in range(len(dt))],
                        "dur": 0.5, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **sp)


@register("opening", "impact")
def opening_impact(ctx, g, opts):
    """The picture snaps into focus and the words land like stamps.

    Built for a phone held at arm's length: the photograph starts soft and oversized
    and resolves, each line of the title arrives on its own beat with a scale
    overshoot that settles, and a block of accent wipes in behind the second line so
    the eye has somewhere to land. Loud, but it is the type that is loud, not the
    picture - the photograph is simply allowed to become sharp.
    """
    d, ops, W, H, px, t_in, t_out, end, oid, fade, sp, Y = _open_common(ctx, g)
    x = r3(px(150))
    photo = g.get("photo")
    if photo:
        cover = ("var b=Math.max(thisComp.width/thisLayer.source.width,"
                 "thisComp.height/thisLayer.source.height);")
        k = f"var k=eio(linear(time,{t_in},{r3(t_in + 1.5)},0,1));var z=b*(1.34-0.29*k);"
        ops.add("footage", id=f"{oid}_BG", parent=oid, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), position=[r3(W / 2), r3(H / 2)],
                lumetri=_photo_grade(ctx, photo),
                expr={"scale": cover + k + "[z*100,z*100]", "opacity": fade,
                      # blurriness resolves as the push settles
                      "fx:ADBE Gaussian Blur 2:1":
                          f"var k=eio(linear(time,{t_in},{r3(t_in + 1.35)},0,1));{r3(px(52))}*(1-k)"})
    ops.add("rect", id=f"{oid}_VEIL", parent=oid, color=d.color("shade"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": f"(60-36*eio((time-{r3(t_in + 0.4)})/1.5))*{fade}/100"}, **sp)
    scrim(ctx, id=f"{oid}_SCRIM", parent=oid, asset=SCRIM_TITLE, strength=76, opacity=fade, **sp)

    mult = float(g.get("size", 1.16))
    size = ctx.size("headline", mult)
    lines = [parse_line(line, ctx.size("headline", mult * 0.30)) for line in g["lines"]]
    gap = r3(size * 1.16)
    y_last = Y(float(g.get("title_y", 0.430)))
    y_first = r3(y_last - (len(lines) - 1) * gap)

    # a block of accent wipes in behind the last line before the words land on it
    t_blk = r3(t_in + 0.72 + 0.26 * (len(lines) - 1))
    wipe = f"var k=eio((time-{t_blk})/0.5);"
    ops.add("rect", id=f"{oid}_BLOCK", parent=oid, color=d.color("accent"),
            rect_expr={"size": wipe + f"[{r3(size * 4.4)}*k,{r3(size * 1.16)}]",
                       "center": wipe + f"[{r3(x - px(26))}+{r3(size * 2.2)}*k,{r3(y_last - size * 0.3)}]"},
            expr={"opacity": f"88*{fade}/100"}, **sp)

    # each line rides a null that slams and settles
    for i, segs in enumerate(lines):
        t0 = r3(t_in + 0.55 + 0.26 * i)
        hold = f"{oid}_S{i + 1}"
        slam = (f"var t=time-{t0};if(t<0){{[128,128]}}else{{"
                f"var k=eio(Math.min(t/0.42,1));var s=128+(100-128)*k;"
                f"s+=Math.exp(-7*t)*Math.sin(17*t)*5.5;[s,s]}}")
        ops.add("group", id=hold, parent=oid, position=[x, r3(y_first + i * gap)],
                expr={"scale": slam})
        ops.add("text", id=f"{oid}_L{i + 1}", parent=hold,
                text="".join(s.text for s in segs), font=d.font("headline"), size=size,
                # dark type on the accent block, pale type on the photograph
                color=d.color("paper" if segs[0].hl else "ink"), justify="left",
                position=[0, 0],
                reveal={"times": [r3(t0)], "dur": 0.34, "rise": 0, "blur": 22, "by": "words"},
                expr={"opacity": fade}, **sp)
    ops.add("order", layer=f"{oid}_BLOCK", below=[f"{oid}_S{len(lines)}"])

    if g.get("kicker"):
        _label(ctx, id=f"{oid}_KICK", parent=oid, text=g["kicker"], x=x,
               y=r3(y_first - size - px(58)), t0=t_in + 1.35, opacity=fade, **sp)
    if g.get("dates"):
        dt = g["dates"]
        ops.add("text", id=f"{oid}_DATES", parent=oid, text=dt, font=d.font("body"),
                size=ctx.size("label", 1.0), color=d.color("ink"), tracking=140,
                justify="left", position=[x, r3(y_last + px(104))],
                reveal={"times": [r3(t_in + 1.6 + 0.02 * i) for i in range(len(dt))],
                        "dur": 0.45, "rise": px(10), "blur": 10, "by": "chars"},
                expr={"opacity": fade}, **sp)


@register("opening", "postcard")
def opening_postcard(ctx, g, opts):
    """The trip arrives as a print, then the print becomes the film.

    The photograph enters as a bordered card - the same object the polaroids use
    later - tilted, shadowed, settling up from slightly small. It holds while the
    title sets beneath it, then the card grows past the edges of the frame and its
    border falls away, handing the screen to the footage. The whole opening is one
    continuous idea instead of a caption over a picture.
    """
    d, ops, W, H, px, t_in, t_out, end, oid, fade, sp, Y = _open_common(ctx, g)
    x = r3(px(150))
    ops.add("rect", id=f"{oid}_BED", parent=oid, color=d.color("paper"),
            size=[r3(W + px(20)), r3(H + px(20))], center=[r3(W / 2), r3(H / 2)],
            expr={"opacity": fade}, **sp)

    cw = r3(W * 0.80)
    ch = r3(cw * 1.2)
    cy = Y(0.300)
    t_grow = r3(t_out - 1.25)
    # one null carries the card: settle up, hold, then grow past the frame
    hold = f"{oid}_H"
    grow = (f"var a=eio(linear(time,{r3(t_in + 0.1)},{r3(t_in + 1.05)},0,1));"
            f"var b=eio(linear(time,{t_grow},{r3(t_out + 0.25)},0,1));"
            f"var s=(90+10*a)*(1+{r3(W / cw * 1.18 - 1)}*b);[s,s]")
    ops.add("group", id=hold, parent=oid, position=[r3(W / 2), cy],
            rotation=-2.0,
            expr={"scale": grow,
                  "rotation": f"-2.0*(1-eio(linear(time,{t_grow},{r3(t_out + 0.1)},0,1)))"})
    ops.add("rect", id=f"{oid}_CARD", parent=hold, color=[1, 1, 1],
            size=[r3(cw + px(44)), r3(ch + px(44) + px(74))], center=[0, 0],
            expr={"opacity": f"100*so((time-{r3(t_in + 0.1)})/0.5)"
                             f"*(1-so((time-{t_grow})/0.7))*{fade}/100"}, **sp)
    ops.add("effect", layer=f"{oid}_CARD", match="ADBE Drop Shadow",
            props={"2": 62, "3": 135, "4": r3(px(22)), "5": r3(px(70))})
    photo = g.get("photo")
    if photo:
        ops.add("footage", id=f"{oid}_BG", parent=hold, file=photo["clip"], start=t_in, end=end,
                src_in=photo.get("src_in", 0), width=cw,
                position=[0, r3(-px(37))],
                mask=[cw, ch], mask_center=[0.5, float(photo.get("cy", 0.42))],
                lumetri=_photo_grade(ctx, photo), expr={"opacity": fade})
        ops.add("order", layer=f"{oid}_CARD", below=[f"{oid}_BG"])

    mult = float(g.get("size", 1.16))
    size = ctx.size("headline", mult)
    lines = [parse_line(line, ctx.size("headline", mult * 0.30)) for line in g["lines"]]
    gap = r3(size * 1.14)
    y_last = Y(float(g.get("title_y", 0.78)))
    times = schedule_times(lines, start=t_in + 1.0, step=0.1, line_pause=0.3)
    text_block(ctx, prefix=oid, parent=oid, lines=lines, times=times, x=x,
               y_first=r3(y_last - (len(lines) - 1) * gap), gap=gap,
               style=lambda i, s: {"font": d.font("headline"), "size": size,
                                   "color": d.color("accent" if s.hl else "ink")},
               align="left", reveal={"dur": 0.85, "rise": px(22), "blur": 14, "by": "words"},
               opacity=fade, t_in=t_in, t_out=end)
    if g.get("kicker"):
        _label(ctx, id=f"{oid}_KICK", parent=oid, text=g["kicker"], x=x,
               y=r3(y_last - (len(lines) - 1) * gap - size - px(54)),
               t0=t_in + 1.55, opacity=fade, **sp)
    if g.get("dates"):
        dt = g["dates"]
        ops.add("text", id=f"{oid}_DATES", parent=oid, text=dt, font=d.font("body"),
                size=ctx.size("label", 1.0), color=d.color("accent2"), tracking=140,
                justify="left", position=[x, r3(y_last + px(96))],
                reveal={"times": [r3(t_in + 1.9 + 0.022 * i) for i in range(len(dt))],
                        "dur": 0.5, "rise": 0, "blur": 8, "by": "chars"},
                expr={"opacity": fade}, **sp)
