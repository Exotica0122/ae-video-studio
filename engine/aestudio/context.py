"""What a design treatment receives."""
from dataclasses import dataclass, field


@dataclass
class Context:
    design: object
    ops: object
    width: int
    height: int
    duration: float
    voices: dict
    grade: dict = field(default_factory=dict)

    @property
    def s(self) -> float:
        return self.width / 3840

    def px(self, value) -> float:
        return round(value * self.s, 2)

    def size(self, role: str, mult: float = 1.0) -> float:
        return round(self.design.size(role) * mult * self.s, 2)
