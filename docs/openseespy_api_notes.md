# OpenSeesPy 3.8.0.0 — verified API map (openseespymac, macOS arm64)

Live-verified on 2026-10-08 in conda env `opensees`. This wheel is OpenSeesPy
3.x (Minjie Zhu, Oregon State) — a high-level wrapper. Several command names
and signatures DIFFER from classic OpenSees (Tcl). Trust this file, not the
classic OpenSees wiki.

## Import
```python
import openseespy.opensees as ops
# or directly: import openseespymac as ops
```

## Model
```python
ops.model('basic', '-ndm', 2, '-ndf', 3)   # 2D frame (ux, uy, rotz)
ops.model('basic', '-ndm', 3, '-ndf', 6)   # 3D frame
ops.model('basic', '-ndm', 2, '-ndf', 2)   # 2D truss
```
- Only the `basic` builder is available (`unidirectional` etc. rejected).
- `ops.wipe()` clears the model.

## Nodes
```python
ops.node(tag, x, y)        # 2D
ops.node(tag, x, y, z)     # 3D
```

## Materials
```python
ops.uniaxialMaterial('Elastic', tag, E)        # for Truss elements
ops.nDMaterial('ElasticIsotropic', tag, E, nu) # exists (beam takes E/G directly)
```

## Sections
```python
ops.section('ElasticMembranePlateSection', tag, E, nu, h, rho)  # for ShellMITC4
ops.section('Fiber', tag, '-GJ', GJ)
```
NOT registered in this wheel: `Prism`, `Area`, `Membrane`.

## Coordinate transforms
```python
ops.geomTransf('Linear', tag)               # 2D
ops.geomTransf('Linear', tag, zx, zy, zz)   # 3D: local z axis REQUIRED
```
3D without the axis vector fails: "insufficient arguments for LinearCrdTransf3d".

## Elements
```python
ops.element('Truss', tag, i, j, A, matTag)
# A in m^2, matTag -> uniaxialMaterial('Elastic', ...)
ops.element('elasticBeamColumn', tag, i, j, A, E, I, transfTag)
# 2D: I = in-plane bending inertia (verified: exact PL^3/3EI result)
ops.element('elasticBeamColumn', tag, i, j, A, E, G, J, Iy, Iz, transfTag)
# 3D
ops.element('ShellMITC4', tag, n1, n2, n3, n4, secTag)
# 6 DOF per node (ndm=3, ndf=6)
```
NOT registered: `beamColumn`, `TwoNodeLink`, `shell189`, `shell43`, `ShellLayered`.
`dispBeamColumn` / `nonlinearBeamColumn` exist (need section + transf) — not yet verified.

## Supports (PITFALL)
```python
ops.fix(node, v1, v2, ...)  # exactly NDF values, each 0 or 1, 1 = fixed
```
- 2D (3 DOF): `ops.fix(1, 1, 1, 1)`
- 3D (6 DOF): `ops.fix(1, 1, 0, 0, 0, 0, 1)`
- Classic Tcl DOF-list style does NOT work: "invalid # of constraint values".

## Loads
```python
ops.timeSeries('Linear', 1)     # must exist before pattern
ops.pattern('Plain', tag, 1)
ops.load(node, *NDF forces)     # 2D: fx, fy, mz | 3D: fx, fy, fz, mx, my, mz
```

## Analysis
```python
ops.numberer('RCM')
ops.algorithm('Linear')
ops.constraints('Plain')
ops.integrator('LoadControl', 1.0)
ops.analysis('Static')          # NOT 'Analysis'
ops.analyze(1)
```
- Do NOT call `ops.test('NormUnbalanced', ...)` — unknown CTest in this wheel;
  the default convergence test is fine.
- `ops.system('BandSPD')` exists but the default ProfileSPD solver is sufficient.

## Results
```python
ops.nodeDisp(tag)      # [..NDF floats]
ops.nodeReaction(tag)
ops.eleForce(tag)      # frame: [P, Vy, Mz] at i, then at j (local coords)
ops.getEleTags(), ops.getNodeTags()
```

## Threading
```python
ops.setNumThreads(n)
ops.getNumThreads()
```

## Verified reference results (golden tests)
- 2D cantilever L=1, A=1e-4, I=1e-8, E=210e9, axial 1e4 N -> dx = 4.7619047619e-4
- 2D cantilever, vertical 1e4 N -> dy = 1.5873015873e-3 (= PL^3/3EI),
  tip rotation = 2.3809523810e-4 (= PL^2/2EI)
- 3D cantilever, axial 1e4 N -> dx = 4.7619047619e-4
- Doc truss (E=3000, A=10/5/5, load 100/-50 at node 4) ->
  u4x = 0.53009277713228375450, u4y = -0.17789363846931768864

## 3D frame orientation (wheel quirk, worked around, verified 2026-10-08)

`LinearCrdTransf3d` builds the local axes as x = element axis,
y = v x x, z = x x y, where v is the vector passed to `geomTransf`. It
aborts the whole process (rc 255, uncatchable) when v is (nearly) parallel
to the element axis, and gives garbage axes otherwise. Passing the element
axis itself as v (the natural choice) therefore crashes for axis-parallel
beams and is numerically degenerate for all other directions.

**Workaround (implemented in `builder._ref_axis`):** pass v = n x u, where
u is the unit element axis and n the global axis least aligned with u
(ties: Z, Y, X). v is then exactly perpendicular to u and at least 45 deg
away from it for every orientation — all 3D orientations solve
(axis-parallel, in-plane, general 3D; verified against analytic values,
including the previously crashing cases).

Resulting local-axis convention (verified against analytic bending):
- local x = element axis; local y = v x u; local z = u x (v x u);
- transverse displacement along local z -> stiffness E*Iy;
  transverse displacement along local y -> stiffness E*Iz;
- a beam in a coordinate plane gets local y = plane normal, so
  **in-plane bending uses Iy** (consistent with the 2D builder) and
  out-of-plane bending uses Iz.

Notes:
- 2D frames are unaffected (2D `Linear` takes no axis vector).
- `Truss` elements are unaffected (no geomTransf needed).
- `PDelta`/`Corotational` share the base-class behavior; only `Linear` is
  used and verified in this app.
- Draft GitHub issue: `docs/issue_openseespy_3d_transf.md`.

## Other verified behavior
- A failed `setDomain` (bad transformation) ABORTS the whole process
  (rc 255), it is not a catchable Python exception.
- `ops.analyze(1)` returns 0 on success, -3 on solver failure (e.g. singular
  matrix: `ProfileSPDLinDirectSolver::solve() - aii < minDiagTol`).
- A single truss member in 3D is a mechanism in the transverse DOFs —
  3D truss models need out-of-plane stability (extra members or supports).
