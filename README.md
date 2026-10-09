# opensees-app

Desktop GUI + CLI for 3D frame (and shell) structural analysis on OpenSeesPy,
with Eurocode (EC0/EC1/EC2/EC3/EC5, Poland) load and verification support.

## Status (v0.1)
- Model + linear FEM pipeline: 2D/3D truss & frame, JSON project file
- Parallel load-case solving (multiprocessing + OpenMP)
- Golden tests (analytic reference values)
- GUI v0: 3D view, node/element/support/load editing, run + results

## Roadmap
- Eurocode loads (EC1: dead, live, wind, snow, temperature) + EC0 combinations
- Verification (EC3 steel, EC2 concrete, EC5 timber) + utilization report
- Shell elements (ShellMITC4) + plate checks
- PDF report / CSV / DXF export

## Requirements
conda env `opensees` (Python 3.11) with:
`openseespy 3.8`, `PySide6`, `pyvista`, `pyvistaqt`, `numpy`, `matplotlib`, `pytest`, `ruff`

## Run CLI
```
conda activate opensees
python -m opensees_app run examples/cantilever2d.json --workers 4
```

## Run GUI
```
conda activate opensees
python -m opensees_app gui
```

## Tests
```
pytest
```

## Units
- Core & project JSON: SI (N, m, Pa, m^2, m^4)
- GUI: forces in kN, moments in kNm, lengths in m (converted internally)
- Section catalog: mm / cm^2 / cm^4 (converted internally)

## Project file
One JSON file per project (see `examples/`). CSV import/export: one row per
entity, `kind` in {node, truss, frame, support, material, section}.

## 3D beam orientation (wheel quirk, worked around)
The wheel's `LinearCrdTransf3d` aborts the process when the vector passed to
`geomTransf` is parallel to the element axis. The builder works around this
with a perpendicular reference vector, so **all 3D orientations work**
(including axis-parallel beams and general 3D directions).

Section orientation convention: for a beam in a coordinate plane the
section's local y-axis is the plane normal, so **in-plane bending uses Iy**
(same as 2D) and out-of-plane bending uses Iz. Details:
`docs/openseespy_api_notes.md`, issue draft: `docs/issue_openseespy_3d_transf.md`.
