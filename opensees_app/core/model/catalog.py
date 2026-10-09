"""Steel section catalog (standard published tables) + default materials.

Catalog units as published: mm, cm^2, cm^4, cm^3. Converted to SI on load.
v0 subset — extend from the user's catalog / Eurocode PDFs before design use.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .entities import Material, Section

_MM = 1e-3
_CM2 = 1e-4
_CM4 = 1e-8
_CM3 = 1e-6

_DATA = Path(__file__).resolve().parent.parent.parent / "data" / "sections" / "profiles.json"


def _torsion_i(h: float, b: float, tf: float, tw: float) -> float:
    """St. Venant torsion constant of an I/H section (rectangular limbs)."""
    return (2.0 * b * tf**3 + (h - 2.0 * tf) * tw**3) / 3.0


def _torsion_pipe(d_outer: float, t: float) -> float:
    r_o = d_outer / 2.0
    r_i = r_o - t
    return math.pi / 2.0 * (r_o**4 - r_i**4)


def load_profiles() -> list[Section]:
    d = json.loads(_DATA.read_text())
    out: list[Section] = []
    for i, p in enumerate(d["profiles"], start=1):
        kind = p["kind"]
        if kind == "pipe":
            d_m = p["d"] * _MM
            t = p["t"] * _MM
            J = _torsion_pipe(d_m, t)
            h = b = d_m
            tf = tw = t
        else:
            h = p["h"] * _MM
            b = p["b"] * _MM
            tf = p["tf"] * _MM
            tw = p["tw"] * _MM
            J = _torsion_i(h, b, tf, tw)
        out.append(Section(
            tag=i, name=p["name"], kind=kind,
            A=p["A"] * _CM2, Iy=p["Iy"] * _CM4, Iz=p["Iz"] * _CM4, J=J,
            h=h, b=b, tf=tf, tw=tw,
            wel_y=p.get("wel_y", 0.0) * _CM3, wpl_y=p.get("wpl_y", 0.0) * _CM3,
            wel_z=p.get("wel_z", p.get("wel_y", 0.0)) * _CM3,
            wpl_z=p.get("wpl_z", p.get("wpl_y", 0.0)) * _CM3,
        ))
    return out


def default_materials() -> list[Material]:
    return [
        Material(1, "S235", 210e9, 0.3, 7850.0, 235e6),
        Material(2, "S355", 210e9, 0.3, 7850.0, 355e6),
        Material(3, "C20/25", 28.6e9, 0.2, 2500.0, None),
    ]
