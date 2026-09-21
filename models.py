from dataclasses import dataclass, field
from typing import List

# ============================================================
#  МОДЕЛИ ДАННЫХ
# ============================================================

@dataclass
class Part:
    name: str
    w: int
    h: int
    qty: int


@dataclass
class PlacedPart:
    name: str
    x: int
    y: int
    w: int
    h: int
    rotated: bool


@dataclass
class Sheet:
    w: int
    h: int
    placed: List[PlacedPart] = field(default_factory=list)

    @property
    def used_area(self):
        return sum(p.w * p.h for p in self.placed)

    @property
    def total_area(self):
        return self.w * self.h

    @property
    def fill_percent(self):
        return self.used_area / self.total_area * 100 if self.total_area else 0


@dataclass
class FreeRect:
    x: int
    y: int
    w: int
    h: int

@dataclass
class ManualPart:
    """Деталь в ручном редакторе — со своим уникальным id."""
    id: int
    name: str
    w: int
    h: int
    rotated: bool = False
    x: int = 0
    y: int = 0
    placed: bool = False