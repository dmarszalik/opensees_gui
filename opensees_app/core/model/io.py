"""CSV import/export: one row per entity, `type` column selects the meaning
of the other columns. Load cases are not stored in CSV (v0)."""
from __future__ import annotations

import csv
from pathlib import Path

from .entities import Element, Material, Node, Section, Support
from .project import Project

CSV_FIELDS = [
    "type", "tag", "x", "y", "z", "i_node", "j_node", "section", "material",
    "name", "kind", "E", "nu", "rho", "fy",
    "A", "Iy", "Iz", "J", "h", "b", "tf", "tw",
    "fix_x", "fix_y", "fix_z", "fix_rx", "fix_ry", "fix_rz",
]

_BOOL_TRUE = {"1", "true", "yes", "x", "t"}


def _f(row: dict, col: str) -> float:
    v = (row.get(col) or "").strip()
    return float(v) if v else 0.0


def _b(row: dict, col: str) -> bool:
    return (row.get(col) or "").strip().lower() in _BOOL_TRUE


def _row(**kw) -> dict:
    r = {c: "" for c in CSV_FIELDS}
    r.update(kw)
    return r


def export_csv(project: Project, path) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerow(_row(type="meta", name=project.dim))
        for n in project.nodes.values():
            w.writerow(_row(type="node", tag=n.tag, x=n.x, y=n.y, z=n.z))
        for e in project.elements.values():
            w.writerow(_row(type=e.kind, tag=e.tag, i_node=e.i_node, j_node=e.j_node,
                            section=e.section_tag, material=e.material_tag))
        for s in project.supports.values():
            w.writerow(_row(type="support", tag=s.node_tag,
                            fix_x=int(s.fix_x), fix_y=int(s.fix_y),
                            fix_z=int(s.fix_z), fix_rx=int(s.fix_rx),
                            fix_ry=int(s.fix_ry), fix_rz=int(s.fix_rz)))
        for m in project.materials.values():
            w.writerow(_row(type="material", tag=m.tag, name=m.name, E=m.E, nu=m.nu,
                            rho=m.rho, fy="" if m.fy is None else m.fy))
        for s in project.sections.values():
            w.writerow(_row(type="section", tag=s.tag, name=s.name, kind=s.kind,
                            A=s.A, Iy=s.Iy, Iz=s.Iz, J=s.J,
                            h=s.h, b=s.b, tf=s.tf, tw=s.tw))


def import_csv(path) -> Project:
    project = Project(name=Path(path).stem)
    saw_dim = False
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            t = (row.get("type") or "").strip()
            if t == "meta":
                dim = (row.get("name") or "").strip()
                if dim in ("2d", "3d"):
                    project.dim = dim
                    saw_dim = True
            elif t == "node":
                tag = int(row["tag"])
                project.nodes[tag] = Node(tag, _f(row, "x"), _f(row, "y"), _f(row, "z"))
            elif t in ("truss", "frame"):
                tag = int(row["tag"])
                project.elements[tag] = Element(
                    tag, t, int(row["i_node"]), int(row["j_node"]),
                    int(row["section"]), int(row["material"]))
            elif t == "support":
                tag = int(row["tag"])
                project.supports[tag] = Support(
                    tag, _b(row, "fix_x"), _b(row, "fix_y"), _b(row, "fix_z"),
                    _b(row, "fix_rx"), _b(row, "fix_ry"), _b(row, "fix_rz"))
            elif t == "material":
                tag = int(row["tag"])
                fy_raw = (row.get("fy") or "").strip()
                nu_raw = (row.get("nu") or "").strip()
                rho_raw = (row.get("rho") or "").strip()
                project.materials[tag] = Material(
                    tag, row.get("name") or f"mat{tag}", _f(row, "E"),
                    float(nu_raw) if nu_raw else 0.3,
                    float(rho_raw) if rho_raw else 7850.0,
                    float(fy_raw) if fy_raw else None)
            elif t == "section":
                tag = int(row["tag"])
                project.sections[tag] = Section(
                    tag, row.get("name") or f"sec{tag}", row.get("kind") or "i",
                    _f(row, "A"), _f(row, "Iy"), _f(row, "Iz"), _f(row, "J"),
                    _f(row, "h"), _f(row, "b"), _f(row, "tf"), _f(row, "tw"))
    if not saw_dim:
        project.dim = "3d" if any(n.z != 0.0 for n in project.nodes.values()) else "2d"
    return project
