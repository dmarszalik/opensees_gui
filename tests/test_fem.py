"""Golden tests: FEM results vs analytic / documented reference values.

References:
- Cantilever axial:  dx = P*L/(E*A)
- Cantilever tip load:  dy = P*L^3/(3*E*I),  rot = P*L^2/(2*E*I)
- 3D beam in the XY plane (45 deg): in-plane bending (about Z) -> Iy,
  out-of-plane bending (about Y) -> Iz (empirically pinned, 2026-10-08)
- Truss: OpenSeesPy doc example (ElasticTruss.py)
"""
import math

from opensees_app.core.fem.parallel import combine, solve_all
from opensees_app.core.fem.runner import solve_case

E = 210e9
A = 1e-4
I = 1e-8
P = 1e4
L = 1.0
S = math.sqrt(0.5)
U = (S, S, 0.0)      # 3D beam axis (XY plane, 45 deg)
W = (-S, S, 0.0)     # in-plane transverse direction
IY3 = 2e-8           # cantilever3d section Iy
IZ3 = 1e-8           # cantilever3d section Iz


def test_cantilever_2d_axial(cantilever2d):
    r = solve_case(cantilever2d, 1)
    assert r["ok"]
    dx = r["displacements"][2][0]
    assert math.isclose(dx, P * L / (E * A), rel_tol=1e-8)


def test_cantilever_2d_bending(cantilever2d):
    r = solve_case(cantilever2d, 2)
    assert r["ok"]
    dy = r["displacements"][2][1]
    rot = r["displacements"][2][2]
    assert math.isclose(dy, P * L**3 / (3 * E * I), rel_tol=1e-8)
    assert math.isclose(rot, P * L**2 / (2 * E * I), rel_tol=1e-8)


def test_cantilever_3d_axial(cantilever3d):
    r = solve_case(cantilever3d, 1)
    assert r["ok"]
    d = r["displacements"][2]
    ax = d[0] * U[0] + d[1] * U[1] + d[2] * U[2]
    assert math.isclose(ax, P * L / (E * A), rel_tol=1e-8)


def test_cantilever_3d_inplane_bending(cantilever3d):
    """In-plane bending (about global Z) is governed by Iy."""
    r = solve_case(cantilever3d, 2)
    assert r["ok"]
    d = r["displacements"][2]
    along_w = d[0] * W[0] + d[1] * W[1] + d[2] * W[2]
    assert math.isclose(along_w, P * L**3 / (3 * E * IY3), rel_tol=1e-8)


def test_cantilever_3d_outofplane_bending(cantilever3d):
    """Out-of-plane bending (about global Y) is governed by Iz."""
    r = solve_case(cantilever3d, 3)
    assert r["ok"]
    dz = r["displacements"][2][2]
    assert math.isclose(dz, P * L**3 / (3 * E * IZ3), rel_tol=1e-8)


def test_truss_doc_example(truss_doc):
    r = solve_case(truss_doc, 1)
    assert r["ok"]
    ux = r["displacements"][4][0]
    uy = r["displacements"][4][1]
    assert math.isclose(ux, 0.53009277713228375450, rel_tol=1e-10)
    assert math.isclose(uy, -0.17789363846931768864, rel_tol=1e-10)


def test_element_force_axial(cantilever2d):
    r = solve_case(cantilever2d, 1)
    f = r["element_forces"][1]
    assert len(f) == 6
    assert math.isclose(abs(f[0]), P, rel_tol=1e-8)   # axial at i
    assert math.isclose(abs(f[3]), P, rel_tol=1e-8)   # axial at j


def test_parallel_matches_serial(cantilever2d):
    serial = solve_all(cantilever2d, [1, 2], workers=1)
    par = solve_all(cantilever2d, [1, 2], workers=2)
    for ct in (1, 2):
        for node, d in serial[ct]["displacements"].items():
            assert d == par[ct]["displacements"][node]


def test_superposition(cantilever2d):
    res = solve_all(cantilever2d, [1, 2], workers=1)
    comb = combine(res, {1: 1.35, 2: 1.5})
    u1 = res[1]["displacements"][2]
    u2 = res[2]["displacements"][2]
    for k in range(3):
        assert math.isclose(comb["displacements"][2][k],
                            1.35 * u1[k] + 1.5 * u2[k], rel_tol=1e-10)
    # element end forces carry 2*ndf entries (i-end + j-end) — all must
    # superpose, not just the first ndf
    f1 = res[1]["element_forces"][1]
    f2 = res[2]["element_forces"][1]
    fc = comb["element_forces"][1]
    assert len(fc) == len(f1) == 6
    for k in range(len(f1)):
        assert math.isclose(fc[k], 1.35 * f1[k] + 1.5 * f2[k],
                            rel_tol=1e-10, abs_tol=1e-12)


def test_ref_axis_well_conditioned():
    """The 3D geomTransf reference vector is well-conditioned for all
    orientations. The wheel's LinearCrdTransf3d aborts the process when the
    reference vector is (nearly) parallel to the element axis; _ref_axis
    picks the global axis least aligned with the beam (ties: Z, Y, X), so
    the reference is perpendicular to the axis and >= 45 deg from it."""
    from opensees_app.core.fem.builder import _ref_axis

    def dot(a, b):
        return sum(x * y for x, y in zip(a, b))

    def cross(a, b):
        return (a[1] * b[2] - a[2] * b[1],
                a[2] * b[0] - a[0] * b[2],
                a[0] * b[1] - a[1] * b[0])

    dirs = [(1, 0, 0), (0, 1, 0), (0, 0, 1),
            (S, S, 0.0), (1.0, 0.0, 1.0), (0.0, S, S),
            (1.0, 1.0, 1.0), (1.0, 2.0, 3.0)]
    for d in dirs:
        n = math.sqrt(sum(c * c for c in d))
        u = (d[0] / n, d[1] / n, d[2] / n)
        v = _ref_axis(d)
        assert abs(dot(v, u)) < 1e-12              # perpendicular to the axis
        assert math.sqrt(sum(c * c for c in v)) > 0.8  # >= sin(54.7 deg)
    # in-plane beam (XY): local y-axis is the plane normal (+- global Z),
    # so in-plane bending is governed by Iy (consistent with the 2D builder)
    v = _ref_axis((1.0, 1.0, 0.0))
    y = cross(v, (S, S, 0.0))
    ny = math.sqrt(sum(c * c for c in y))
    y = tuple(c / ny for c in y)
    assert abs(abs(y[2]) - 1.0) < 1e-12


def test_cantilever_3d_axis_parallel():
    """Axis-parallel 3D beam — previously aborted the process in the wheel."""
    from opensees_app.core.model.entities import Material, Section
    from opensees_app.core.model.project import Project

    p = Project(name="axis", dim="3d")
    p.add_node(0, 0, 0)
    p.add_node(0, 0, 1.0)  # column along global Z
    p.materials[1] = Material(1, "m", E)
    p.sections[1] = Section(1, "s", "i", A, IY3, IZ3, 1e-9)
    p.add_element("frame", 1, 2, 1, 1)
    p.add_support(1, fix_x=True, fix_y=True, fix_z=True,
                 fix_rx=True, fix_ry=True, fix_rz=True)
    c = p.add_load_case("tip")
    # global X is the local z-axis of a Z-column -> bending uses Iy
    p.add_load(c.tag, 2, fx=P)
    r = solve_case(p.to_dict(), c.tag)
    assert r["ok"]
    dx = r["displacements"][2][0]
    assert math.isclose(dx, P * 1.0**3 / (3 * E * IY3), rel_tol=1e-8)
