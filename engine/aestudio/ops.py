"""Ops: the flat instruction list the ExtendScript runtime executes (engine/jsx/runtime.jsx)."""
import re

REQUIRED = {
    "comp": ["name", "width", "height", "fps", "duration"],
    "footage": ["id", "file", "start", "end"],
    "audio": ["id", "file", "start", "end"],
    "group": ["id"],
    "rect": ["id", "color"],
    "text": ["id", "text", "font", "size", "color"],
    "image": ["id", "file"],
    "solid": ["id", "color"],
    "rules": ["id", "count", "spacing", "y0", "color"],
    "effect": ["layer", "match"],
    "order": ["layer", "below"],
    "expr": ["layer", "exprs"],
}
_LAYER_REF = re.compile(r'thisComp\.layer\("([^"]+)"\)')


class OpsError(ValueError):
    pass


class Ops:
    def __init__(self):
        self.items = []
        self._ids = set()
        self._counters = {}

    def uid(self, prefix: str) -> str:
        n = self._counters.get(prefix, 0) + 1
        self._counters[prefix] = n
        return f"{prefix}_{n:02d}"

    def add(self, op: str, **fields):
        item = {"op": op}
        item.update({k: v for k, v in fields.items() if v is not None})
        lid = item.get("id")
        if lid is not None:
            if lid in self._ids:
                raise OpsError(f"duplicate id '{lid}'")
            self._ids.add(lid)
        self.items.append(item)
        return lid


def _expressions(item):
    for key in ("expr", "rect_expr", "exprs"):
        for value in (item.get(key) or {}).values():
            yield value
    if "fade" in item:
        yield item["fade"]
    for value in (item.get("props") or {}).values():
        if isinstance(value, dict) and "expr" in value:
            yield value["expr"]


def validate_ops(items) -> None:
    if not items or items[0].get("op") != "comp":
        raise OpsError("first op must be 'comp'")
    defined = set()
    for i, item in enumerate(items):
        op = item.get("op")
        if op not in REQUIRED:
            raise OpsError(f"op {i}: unknown op '{op}'")
        for key in REQUIRED[op]:
            if key not in item:
                raise OpsError(f"op {i} ({op}): missing '{key}'")
        refs = [("parent", item.get("parent")), ("layer", item.get("layer"))]
        refs += [("below", b) for b in item.get("below", [])]
        refs += [("expression", r) for e in _expressions(item) for r in _LAYER_REF.findall(e)]
        for kind, ref in refs:
            if ref is not None and ref not in defined:
                raise OpsError(f"op {i} ({op} {item.get('id', '')}): {kind} '{ref}' is not defined by an earlier op")
        if "id" in item:
            if item["id"] in defined:
                raise OpsError(f"op {i}: duplicate id '{item['id']}'")
            defined.add(item["id"])
