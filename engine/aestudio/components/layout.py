"""Layout shared by treatments: segmented lines synced to speech, highlighter, paper card, placement."""
from dataclasses import dataclass

from ..timing import align_words
from ..util import js, r3

STATIC = "posterizeTime(0);"          # layout that never animates: evaluate once
T_END = "thisComp.duration-0.01"      # measure text after every reveal animator has finished
PLACES = ("bottom-left", "top-left", "bottom-right", "top-right", "lower-center", "top-center", "center")


class LayoutError(ValueError):
    pass


@dataclass
class Segment:
    text: str
    hl: bool
    gap: float


@dataclass
class Block:
    segments: list
    lines: list
    ids: list


def span(t_in=None, t_out=None) -> dict:
    out = {}
    if t_in is not None:
        out["in"] = r3(t_in)
    if t_out is not None:
        out["out"] = r3(t_out)
    return out


def parse_line(line, space_px):
    if not isinstance(line, list) or not line:
        raise LayoutError(f"a line must be a non-empty list of segments, got {line!r}")
    segs, pending = [], False
    for item in line:
        if isinstance(item, str):
            raw, hl = item, False
        elif isinstance(item, dict) and list(item) == ["hl"] and isinstance(item["hl"], str):
            raw, hl = item["hl"], True
        else:
            raise LayoutError(f'a segment must be a string or {{"hl": text}}, got {item!r}')
        text = raw.strip()
        if not text:
            pending = pending or bool(raw)
            continue
        gap = space_px if segs and (pending or raw[0].isspace()) else 0.0
        segs.append(Segment(text, hl, round(float(gap), 2)))
        pending = raw[-1].isspace()
    if not segs:
        raise LayoutError(f"line has no visible text: {line!r}")
    return segs


def _word_counts(lines):
    return [[len(s.text.split()) for s in segs] for segs in lines]


def segment_times(lines, words):
    flat = [w for segs in lines for s in segs for w in s.text.split()]
    times = align_words(flat, words)
    out, i = [], 0
    for counts in _word_counts(lines):
        row = []
        for n in counts:
            row.append([r3(t) for t in times[i:i + n]])
            i += n
        out.append(row)
    return out


def schedule_times(lines, start, step, line_pause):
    out, t = [], float(start)
    for counts in _word_counts(lines):
        row = []
        for n in counts:
            row.append([r3(t + k * step) for k in range(n)])
            t += n * step
        out.append(row)
        t += line_pause
    return out


def place_block(place, n_lines, gap, width, height):
    if place not in PLACES:
        raise LayoutError(f"unknown place '{place}' (expected one of {', '.join(PLACES)})")
    extent = (n_lines - 1) * gap
    horiz = "center" if place.endswith("center") else place.split("-")[1]
    vert = "center" if place == "center" else ("top" if place.startswith("top") else "bottom")
    x = {"left": 0.09, "right": 0.55, "center": 0.5}[horiz] * width
    y_first = {"top": 0.17 * height, "bottom": 0.85 * height - extent, "center": 0.5 * height - extent / 2}[vert]
    return round(x, 2), round(y_first, 2), ("center" if horiz == "center" else "left")


def fade_ref(group_id, mult=100):
    return f'thisComp.layer({js(group_id)}).effect("FADE")(1)*{mult}/100'


def text_block(ctx, *, prefix, parent, lines, times, x, y_first, gap, style, align, reveal, opacity=None, t_in=None, t_out=None):
    ops = ctx.ops
    block = Block([], [], [])
    for i, segs in enumerate(lines):
        y = r3(y_first + i * gap)
        seg_parent, origin = parent, [x, y]
        if align == "center":
            line_id = f"{prefix}_L{i + 1}"
            ops.add("group", id=line_id, parent=parent, position=[x, y])
            block.lines.append(line_id)
            seg_parent, origin = line_id, [0, 0]
        row = []
        for k, seg in enumerate(segs):
            sid = f"{prefix}_L{i + 1}S{k + 1}"
            st = style(i, seg)
            expr = {"opacity": opacity} if opacity else {}
            if k:
                expr["position"] = (STATIC + f"var P=thisComp.layer({js(row[-1])});var r=P.sourceRectAtTime({T_END},false);"
                                    f"[P.transform.position[0]+r.left+r.width+{seg.gap},value[1]]")
            ops.add("text", id=sid, parent=seg_parent, text=seg.text, font=st["font"], size=st["size"], color=st["color"],
                    tracking=st.get("tracking"), position=list(origin), reveal=dict(reveal, times=times[i][k]),
                    expr=expr or None, **span(t_in, t_out))
            row.append(sid)
        if align == "center":
            f, z = row[0], row[-1]
            ops.add("expr", layer=block.lines[-1], exprs={"position": (
                STATIC + f"var F=thisComp.layer({js(f)}),Z=thisComp.layer({js(z)});"
                f"var rf=F.sourceRectAtTime({T_END},false),rz=Z.sourceRectAtTime({T_END},false);"
                "var x0=F.transform.position[0]+rf.left,x1=Z.transform.position[0]+rz.left+rz.width;[value[0]-(x0+x1)/2,value[1]]")})
        block.segments.append(row)
        block.ids.extend(row)
    return block


def highlighter(ctx, *, id, parent, target, size, t0, dur, color, opacity=None, pad=14, band=(0.5, 0.46), rough=True, t_in=None, t_out=None):
    geo = (f"var L=thisComp.layer({js(target)});var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           # band[0] may be negative - an underline sits BELOW the baseline - so the
           # offset is added in parentheses rather than subtracted, or the expression
           # emits "p[1]--12.3" and After Effects rejects it
           f"var x0=p[0]+r.left-{pad},w=r.width+{r3(2 * pad)},top=p[1]+({r3(-size * band[0])}),h={r3(size * band[1])};"
           f"var k=eio((time-{r3(t0)})/{dur});")
    ctx.ops.add("rect", id=id, parent=parent, color=color, rect_expr={"size": geo + "[w*k,h]", "center": geo + "[x0+w*k/2,top+h/2]"},
                expr={"opacity": opacity} if opacity else None, **span(t_in, t_out))
    if rough:
        ctx.ops.add("effect", layer=id, match="ADBE Roughen Edges", props={"3": ctx.px(5)})
    ctx.ops.add("order", layer=id, below=[target])


def paper_card(ctx, *, id, parent, members, below, pad, color, radius, opacity=None, noise=0, shadow=True, t_in=None, t_out=None):
    geo = (STATIC + f"var N={js(list(members))};var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;"
           f"for(var i=0;i<N.length;i++){{var L=thisComp.layer(N[i]);var p=L.transform.position;var r=L.sourceRectAtTime({T_END},false);"
           "x0=Math.min(x0,p[0]+r.left);y0=Math.min(y0,p[1]+r.top);x1=Math.max(x1,p[0]+r.left+r.width);y1=Math.max(y1,p[1]+r.top+r.height);}")
    ctx.ops.add("rect", id=id, parent=parent, color=color, roundness=radius,
                rect_expr={"size": geo + f"[x1-x0+{r3(2 * pad[0])},y1-y0+{r3(2 * pad[1])}]", "center": geo + "[(x0+x1)/2,(y0+y1)/2]"},
                expr={"opacity": opacity} if opacity else None, **span(t_in, t_out))
    if noise:
        ctx.ops.add("effect", layer=id, match="ADBE Noise", props={"1": noise, "2": 0})
    if shadow:
        ctx.ops.add("effect", layer=id, match="ADBE Drop Shadow", props={"2": 60, "3": 180, "4": ctx.px(14), "5": ctx.px(40)})
    ctx.ops.add("order", layer=id, below=list(below))
