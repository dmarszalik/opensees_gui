# OpenSeesPy issue draft: LinearCrdTransf3d broken for 3D beam orientations

> Draft to file at https://github.com/zhuminjie/OpenSeesPy (issues) or the
> OpenSeesPy forum (f=12). Verified on openseespymac 3.8.0.0, macOS arm64,
> Python 3.11.

## Summary

`geomTransf('Linear', ...)` in 3D gives wrong or unusable local axes for many
element orientations. Only members lying exactly in a coordinate plane
(one component of the axis vector == 0) and not parallel to an axis give
correct results.

## Observed behavior (openseespymac 3.8.0.0)

Element: single `elasticBeamColumn`, L=1 m, A=1e-4 m2, E=210e9 Pa,
Iy=2e-8 m4, Iz=1e-8 m4, node 1 fixed (all 6 DOF), axial load 1e4 N along the
element axis. Expected: axial displacement = PL/EA = 4.7619e-4 m, zero
transverse displacement.

| axis (element direction) | result |
|---|---|
| (1,0,0) | **process aborts** (rc 255): `LinearCrdTransf3d::getLocalAxes ... vector v that defines plane xz is parallel to x axis` |
| (0,1,0) | **process aborts** (same message) |
| (0,0,1) | **process aborts** (same message) |
| (1,0.2,0) .. (1,1,0) in-plane | **correct** (axial = PL/EA, transverse ~ 1e-17) |
| (1,0.1,0) in-plane | **process aborts** (same message) |
| (1,1,0.5) general 3D | solves, but **wrong physics**: transverse disp 6.7e-4 m (should be 0) |
| (0.577,0.577,0.577) | **singular matrix**: `ProfileSPDLinDirectSolver::solve() - aii < minDiagTol (i, aii): (2, 8.63777e-26)` |

Notes:
- The crash is a hard process abort (C++), not a Python exception — it kills
  the whole interpreter.
- `PDelta` shows the same behavior (shares the base class).
- `Corotational` does not crash but also gives wrong physics for general
  axes (axial 6.27e-4 vs expected 4.76e-4, transverse 1.5 m).
- 2D `Linear` (no axis vector) is unaffected.
- The `Truss` element (no geomTransf) is unaffected.

## Reproduction

```python
import openseespy.opensees as ops

E, P, L, A, Iy, Iz, J = 210e9, 1e4, 1.0, 1e-4, 2e-8, 1e-8, 1e-9
G = E / (2 * 1.3)
axis = (0.5774, 0.5774, 0.5774)   # or (1,0,0) / (0,1,0) / (0,0,1)

ops.model('basic', '-ndm', 3, '-ndf', 6)
ops.node(1, 0, 0, 0)
ops.node(2, *axis)
ops.uniaxialMaterial('Elastic', 1, E)
ops.geomTransf('Linear', 1, *axis)
ops.element('elasticBeamColumn', 1, 1, 2, A, E, G, J, Iy, Iz, 1)
ops.fix(1, 1, 1, 1, 1, 1, 1)
ops.timeSeries('Linear', 1)
ops.pattern('Plain', 1, 1)
ops.load(2, P * axis[0], P * axis[1], P * axis[2], 0, 0, 0)
ops.numberer('RCM')
ops.algorithm('Linear')
ops.constraints('Plain')
ops.integrator('LoadControl', 1.0)
ops.analysis('Static')
code = ops.analyze(1)
print(code, ops.nodeDisp(2))
# expected: code=0, displacement = 4.7619e-4 along `axis`, 0 elsewhere
```

## Impact

3D frame models with members along global axes (typical buildings: columns
along Z, beams along X/Y) cannot be solved at all.

## Root cause

`LinearCrdTransf3d::getLocalAxes` computes y = v x x (v = vector passed to
`geomTransf`, x = element axis) and returns -3 ("vector v that defines plane
xz is parallel to x axis") when v x x is (numerically) zero. Passing the
element axis itself as v is therefore invalid input: the crash is
deterministic when the two vectors are bit-identical, and the result is
garbage when they differ by rounding.

## Workaround (implemented in this app)

Pass a reference vector perpendicular to the element axis: v = n x u, where
u is the unit element axis and n the global axis least aligned with u
(ties: Z, Y, X). All orientations then solve with correct physics.
