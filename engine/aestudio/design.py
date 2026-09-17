"""Design recipes: tokens plus one treatment per component (docs/design.md §7)."""
import json
from dataclasses import dataclass
from pathlib import Path

from .util import hex_rgb

ROLES = ("headline", "body", "emphasis", "quote", "label", "scripture")
COMPONENTS = ("caption", "quote", "lower-third", "title-page", "end-card")
PALETTE_KEYS = ("paper", "ink", "accent", "accent2", "rule", "shade")
DESIGNS_DIR = Path(__file__).resolve().parents[2] / "designs"
MOTION_DEFAULTS = {"in": 0.6, "out": 0.45, "word": 0.35, "rise": 14}


class DesignError(ValueError):
    pass


@dataclass
class Design:
    id: str
    name: str
    palette: dict
    type: dict
    motion: dict
    texture: dict
    components: dict
    path: Path

    def font(self, role: str) -> str:
        return self.type[role]["font"]

    def size(self, role: str) -> float:
        return float(self.type[role]["size"])

    def color(self, name: str) -> list:
        return list(self.palette[name])

    def treatment(self, component: str) -> tuple:
        opts = dict(self.components[component])
        return opts.pop("treatment"), opts

    def fonts(self) -> set:
        return {spec["font"] for spec in self.type.values()}


def _resolve(ref) -> Path:
    p = Path(ref).expanduser()
    if p.suffix == ".json" and p.is_file():
        return p
    if (p / "design.json").is_file():
        return p / "design.json"
    if (DESIGNS_DIR / str(ref) / "design.json").is_file():
        return DESIGNS_DIR / str(ref) / "design.json"
    raise DesignError(f"design not found: {ref} (looked for a .json file, <dir>/design.json and {DESIGNS_DIR}/<id>/design.json)")


def load_design(ref) -> Design:
    path = _resolve(ref).resolve()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise DesignError(f"cannot read {path}: {e}") from e
    errors = []
    tokens = raw.get("tokens", {})
    palette = {}
    for key in PALETTE_KEYS:
        try:
            palette[key] = hex_rgb(tokens.get("palette", {}).get(key))
        except ValueError:
            errors.append(f"palette '{key}' must be a #RRGGBB colour")
    types = tokens.get("type", {})
    for role in ROLES:
        spec = types.get(role)
        if not isinstance(spec, dict) or not isinstance(spec.get("font"), str) or not isinstance(spec.get("size"), (int, float)):
            errors.append(f"type role '{role}' needs {{\"font\": PostScript name, \"size\": 4K px}}")
    components = raw.get("components", {})
    for comp in COMPONENTS:
        if not isinstance(components.get(comp), dict) or not isinstance(components[comp].get("treatment"), str):
            errors.append(f"component '{comp}' needs {{\"treatment\": name}}")
    if not isinstance(raw.get("id"), str):
        errors.append("'id' is required")
    if errors:
        raise DesignError(f"{path}:\n  " + "\n  ".join(errors))
    return Design(raw["id"], raw.get("name", raw["id"]), palette, types, {**MOTION_DEFAULTS, **tokens.get("motion", {})},
                  dict(tokens.get("texture", {})), components, path)
