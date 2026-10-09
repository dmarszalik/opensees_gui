"""Translate a Project into OpenSeesPy commands.

See docs/openseespy_api_notes.md for the verified API of this wheel.
"""
from __future__ import annotations

import math

from ..model.project import Project


class FemError(RuntimeError):
    """The model cannot be solved with the OpenSeesPy wheel."""


def dof_layout(project: Project) -> int:
    """DOF count per node: 2 (2D truss), 3 (2D frame or 3D truss), 6 (3D frame)."""
    has_frame = any(e.kind == "frame" for e in project.elements.values())
    if project.dim == "2d":
        return 3 if has_frame else 2
    return 6 if has_frame else 3


def _ref_axis(d: tuple[float, float, float]) -> tuple[float, float, float]:
    """Reference vector v for the 3D 'Linear' geomTransf.

    The wheel's LinearCrdTransf3d builds the local axes as
    x = element axis, y = v x x, z = x x y (v = vector passed to geomTransf)
    and aborts the whole process when v is (nearly) parallel to the element
    axis. We pass v = n x u, where u is the unit element axis and n the
    global axis least aligned with u (ties: Z, Y, X). Then v is exactly
    perpendicular to u for every orientation (well-conditioned, no crash),
    and for beams lying in a coordinate plane the local y-axis is the plane
    normal, so in-plane bending uses Iy — consistent with the 2D builder.
    """
    n = math.sqrt(sum(v * v for v in d))
    if n == 0.0:
        raise ValueError("zero-length element: identical node coordinates")
    u = (d[0] / n, d[1] / n, d[2] / n)
    axes = ((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0))
    best, best_dot = axes[0], abs(axes[0][0] * u[0] + axes[0][1] * u[1] + axes[0][2] * u[2])
    for a in axes[1:]:
        dot = abs(a[0] * u[0] + a[1] * u[1] + a[2] * u[2])
        if dot < best_dot:
            best, best_dot = a, dot
    return (best[1] * u[2] - best[2] * u[1],
            best[2] * u[0] - best[0] * u[2],
            best[0] * u[1] - best[1] * u[0])


def _fix_vectors(project: Project, ndf: int) -> dict[int, list[int]]:
    """Per-node fix vectors (exactly ndf 0/1 values, OpenSeesPy 'fix' contract).

    Nodes connected only by truss elements have no rotational stiffness in a
    frame-capable model; their rotational DOFs are auto-fixed (pin joint) to
    keep the stiffness matrix non-singular.
    """
    vecs: dict[int, list[int]] = {}
    for s in project.supports.values():
        if project.dim == "2d":
            v = [int(s.fix_x), int(s.fix_y)] if ndf == 2 else \
                [int(s.fix_x), int(s.fix_y), int(s.fix_rz)]
        else:
            v = [int(s.fix_x), int(s.fix_y), int(s.fix_z)] if ndf == 3 else \
                [int(s.fix_x), int(s.fix_y), int(s.fix_z),
                 int(s.fix_rx), int(s.fix_ry), int(s.fix_rz)]
        vecs[s.node_tag] = v

    frame_nodes: set[int] = set()
    for e in project.elements.values():
        if e.kind == "frame":
            frame_nodes.update((e.i_node, e.j_node))
    rot_idx = (2,) if project.dim == "2d" else (3, 4, 5)
    for n in project.nodes.values():
        if n.tag in frame_nodes:
            continue
        v = vecs.setdefault(n.tag, [0] * ndf)
        for i in rot_idx:
            if i < len(v):
                v[i] = 1
    return vecs


def build_model(ops, project: Project, case) -> None:
    ndf = dof_layout(project)
    ndm = 2 if project.dim == "2d" else 3
    ops.wipe()
    ops.model('basic', '-ndm', ndm, '-ndf', ndf)

    for n in project.nodes.values():
        if ndm == 2:
            ops.node(n.tag, n.x, n.y)
        else:
            ops.node(n.tag, n.x, n.y, n.z)

    for m in project.materials.values():
        ops.uniaxialMaterial('Elastic', m.tag, m.E)

    per_element_transf: dict[int, int] = {}
    has_frame = any(e.kind == "frame" for e in project.elements.values())
    if ndm == 2:
        # 2D 'Linear' geomTransf is only valid when frame elements exist
        # (a truss-only model with ndf=2 rejects it in OpenSees).
        shared_transf = 1
        if has_frame:
            ops.geomTransf('Linear', 1)
    else:
        shared_transf = None
        t = 1
        for e in project.elements.values():
            if e.kind != "frame":
                continue
            a = project.nodes[e.i_node]
            b = project.nodes[e.j_node]
            ops.geomTransf('Linear', t, *_ref_axis((b.x - a.x, b.y - a.y, b.z - a.z)))
            per_element_transf[e.tag] = t
            t += 1

    for e in project.elements.values():
        sec = project.sections[e.section_tag]
        mat = project.materials[e.material_tag]
        if e.kind == "truss":
            ops.element('Truss', e.tag, e.i_node, e.j_node, sec.A, e.material_tag)
        elif project.dim == "2d":
            ops.element('elasticBeamColumn', e.tag, e.i_node, e.j_node,
                        sec.A, mat.E, sec.Iy, shared_transf)
        else:
            ops.element('elasticBeamColumn', e.tag, e.i_node, e.j_node,
                        sec.A, mat.E, mat.G, sec.J, sec.Iy, sec.Iz,
                        per_element_transf[e.tag])

    for node_tag, v in _fix_vectors(project, ndf).items():
        ops.fix(node_tag, *v)

    if case is not None:
        apply_load_case(ops, project, case, ndf)


def apply_load_case(ops, project: Project, case, ndf: int) -> None:
    ops.timeSeries('Linear', 1)
    ops.pattern('Plain', case.tag, 1)
    for L in case.loads:
        if project.dim == "2d":
            vals = (L.fx, L.fy) if ndf == 2 else (L.fx, L.fy, L.mz)
        else:
            vals = (L.fx, L.fy, L.fz) if ndf == 3 else \
                (L.fx, L.fy, L.fz, L.mx, L.my, L.mz)
        ops.load(L.node_tag, *vals)


def setup_analysis(ops) -> None:
    ops.numberer('RCM')
    ops.algorithm('Linear')
    ops.constraints('Plain')
    ops.integrator('LoadControl', 1.0)
    ops.analysis('Static')
