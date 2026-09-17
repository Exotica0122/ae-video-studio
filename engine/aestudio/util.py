"""Small helpers shared by the compiler and treatments."""
import json


def js(value) -> str:
    """Compact JSON that ExtendScript (ES3) accepts as a JavaScript literal; non-ASCII is escaped."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def hex_rgb(value: str) -> list[float]:
    """'#RRGGBB' -> [r, g, b] in 0..1, as After Effects colour properties expect."""
    h = value.lstrip("#") if isinstance(value, str) else ""
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"bad colour {value!r}; expected #RRGGBB")
    return [round(int(h[i:i + 2], 16) / 255, 5) for i in (0, 2, 4)]


def r3(x) -> float:
    return round(float(x), 3)
