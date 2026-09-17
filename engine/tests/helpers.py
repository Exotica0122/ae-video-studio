from aestudio.context import Context
from aestudio.design import load_design
from aestudio.ops import Ops
from aestudio.timing import VoiceTimes


def voice(vid, at, words):
    w = [(t, round(s + at, 3), round(e + at, 3)) for t, s, e in words]
    return VoiceTimes(vid, w[0][1], w[-1][2], w)


def make_ctx(design_id="notebook", voices=None, width=3840, height=2160, duration=40.0):
    ops = Ops()
    ops.add("comp", name="TEST", width=width, height=height, fps=23.976, duration=duration)
    return Context(load_design(design_id), ops, width, height, duration, voices or {}, {})
