"""Project container: single source of truth for a structural model."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .entities import Element, Load, LoadCase, Material, Node, Section, Support

SCHEMA_VERSION = 1


@dataclass
class Project:
    name: str = "project"
    dim: str = "3d"  # "2d" | "3d"
    nodes: dict[int, Node] = field(default_factory=dict)
    elements: dict[int, Element] = field(default_factory=dict)
    supports: dict[int, Support] = field(default_factory=dict)
    materials: dict[int, Material] = field(default_factory=dict)
    sections: dict[int, Section] = field(default_factory=dict)
    load_cases: dict[int, LoadCase] = field(default_factory=dict)

    # ---------- builder helpers ----------
    @staticmethod
    def _next_tag(mapping: dict) -> int:
        return (max(mapping) + 1) if mapping else 1

    def add_node(self, x: float, y: float, z: float = 0.0) -> Node:
        n = Node(self._next_tag(self.nodes), x, y, z)
        self.nodes[n.tag] = n
        return n

    def add_element(self, kind: str, i_node: int, j_node: int,
                    section_tag: int, material_tag: int) -> Element:
        e = Element(self._next_tag(self.elements), kind, i_node, j_node,
                    section_tag, material_tag)
        self.elements[e.tag] = e
        return e

    def add_support(self, node_tag: int, fix_x: bool = False, fix_y: bool = False,
                    fix_z: bool = False, fix_rx: bool = False,
                    fix_ry: bool = False, fix_rz: bool = False) -> Support:
        s = Support(node_tag, fix_x, fix_y, fix_z, fix_rx, fix_ry, fix_rz)
        self.supports[node_tag] = s
        return s

    def add_load_case(self, name: str) -> LoadCase:
        c = LoadCase(self._next_tag(self.load_cases), name)
        self.load_cases[c.tag] = c
        return c

    def add_load(self, case_tag: int, node_tag: int, fx: float = 0.0,
                 fy: float = 0.0, fz: float = 0.0, mx: float = 0.0,
                 my: float = 0.0, mz: float = 0.0) -> Load:
        L = Load(node_tag, fx, fy, fz, mx, my, mz)
        self.load_cases[case_tag].loads.append(L)
        return L

    # ---------- validation ----------
    def validate(self) -> list[str]:
        problems: list[str] = []
        if self.dim not in ("2d", "3d"):
            problems.append(f"unknown dim {self.dim!r}")
        for n in self.nodes.values():
            if self.dim == "2d" and n.z != 0.0:
                problems.append(f"node {n.tag}: z != 0 in 2D model")
        for e in self.elements.values():
            for ref in (e.i_node, e.j_node):
                if ref not in self.nodes:
                    problems.append(f"element {e.tag}: missing node {ref}")
            if e.section_tag not in self.sections:
                problems.append(f"element {e.tag}: missing section {e.section_tag}")
            if e.material_tag not in self.materials:
                problems.append(f"element {e.tag}: missing material {e.material_tag}")
            if e.kind not in ("truss", "frame"):
                problems.append(f"element {e.tag}: unknown kind {e.kind!r}")
            if e.i_node == e.j_node:
                problems.append(f"element {e.tag}: i_node == j_node")
            if e.i_node in self.nodes and e.j_node in self.nodes:
                a = self.nodes[e.i_node]
                b = self.nodes[e.j_node]
                length = ((b.x - a.x) ** 2 + (b.y - a.y) ** 2
                           + (b.z - a.z) ** 2) ** 0.5
                if length < 1e-9:
                    problems.append(f"element {e.tag}: zero length")
        for s in self.supports.values():
            if s.node_tag not in self.nodes:
                problems.append(f"support on missing node {s.node_tag}")
        for c in self.load_cases.values():
            for L in c.loads:
                if L.node_tag not in self.nodes:
                    problems.append(f"load in case {c.tag}: missing node {L.node_tag}")
        if not self.elements:
            problems.append("no elements")
        if not self.supports:
            problems.append("no supports")
        return problems

    # ---------- (de)serialization ----------
    def to_dict(self) -> dict:
        return {
            "schema": SCHEMA_VERSION,
            "name": self.name,
            "dim": self.dim,
            "nodes": {str(t): n.to_dict() for t, n in self.nodes.items()},
            "elements": {str(t): e.to_dict() for t, e in self.elements.items()},
            "supports": {str(t): s.to_dict() for t, s in self.supports.items()},
            "materials": {str(t): m.to_dict() for t, m in self.materials.items()},
            "sections": {str(t): s.to_dict() for t, s in self.sections.items()},
            "load_cases": {str(t): c.to_dict() for t, c in self.load_cases.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        p = cls(name=d.get("name", "project"), dim=d.get("dim", "3d"))
        p.nodes = {int(k): Node.from_dict(v) for k, v in d.get("nodes", {}).items()}
        p.elements = {int(k): Element.from_dict(v) for k, v in d.get("elements", {}).items()}
        p.supports = {int(k): Support.from_dict(v) for k, v in d.get("supports", {}).items()}
        p.materials = {int(k): Material.from_dict(v) for k, v in d.get("materials", {}).items()}
        p.sections = {int(k): Section.from_dict(v) for k, v in d.get("sections", {}).items()}
        p.load_cases = {int(k): LoadCase.from_dict(v) for k, v in d.get("load_cases", {}).items()}
        return p

    def save(self, path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path) -> Project:
        return cls.from_dict(json.loads(Path(path).read_text()))
