"""Core data model for structural projects.

All quantities are SI: N, m, Pa, m^2, m^4, kg.
"""
from __future__ import annotations

import dataclasses
from dataclasses import asdict, dataclass, field


def _from_dict(cls, d: dict):
    out = {}
    for f in dataclasses.fields(cls):
        if f.name in d:
            out[f.name] = d[f.name]
        elif f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
    return cls(**out)


@dataclass
class Node:
    tag: int
    x: float
    y: float
    z: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return _from_dict(cls, d)


@dataclass
class Material:
    tag: int
    name: str
    E: float                  # Pa
    nu: float = 0.3
    rho: float = 7850.0       # kg/m^3
    fy: float | None = None   # yield stress, Pa (verification)

    @property
    def G(self) -> float:
        return self.E / (2.0 * (1.0 + self.nu))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Material:
        return _from_dict(cls, d)


@dataclass
class Section:
    tag: int
    name: str
    kind: str                 # "i" | "h" | "pipe" | "rect" | "truss"
    A: float                  # m^2
    Iy: float                 # m^4, strong axis
    Iz: float                 # m^4, weak axis
    J: float                  # m^4, St. Venant torsion constant
    h: float = 0.0            # m
    b: float = 0.0            # m
    tf: float = 0.0           # m
    tw: float = 0.0           # m
    wel_y: float = 0.0        # m^3
    wpl_y: float = 0.0        # m^3
    wel_z: float = 0.0        # m^3
    wpl_z: float = 0.0        # m^3

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Section:
        return _from_dict(cls, d)


@dataclass
class Element:
    tag: int
    kind: str                 # "truss" | "frame"
    i_node: int
    j_node: int
    section_tag: int
    material_tag: int

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Element:
        return _from_dict(cls, d)


@dataclass
class Support:
    node_tag: int
    fix_x: bool = False
    fix_y: bool = False
    fix_z: bool = False
    fix_rx: bool = False
    fix_ry: bool = False
    fix_rz: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Support:
        return _from_dict(cls, d)


@dataclass
class Load:
    node_tag: int
    fx: float = 0.0
    fy: float = 0.0
    fz: float = 0.0
    mx: float = 0.0
    my: float = 0.0
    mz: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Load:
        return _from_dict(cls, d)


@dataclass
class LoadCase:
    tag: int
    name: str
    loads: list[Load] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"tag": self.tag, "name": self.name,
                "loads": [l.to_dict() for l in self.loads]}

    @classmethod
    def from_dict(cls, d: dict) -> LoadCase:
        return cls(tag=d["tag"], name=d.get("name", f"case{d['tag']}"),
                   loads=[Load.from_dict(l) for l in d.get("loads", [])])
