"""Solve one load case in the current process. Module-level function so it is
picklable for ProcessPoolExecutor (one OpenSees instance per process)."""
from __future__ import annotations

from ..model.project import Project
from .builder import build_model, dof_layout, setup_analysis


def solve_case(project_dict: dict, case_tag: int) -> dict:
    import openseespy.opensees as ops

    project = Project.from_dict(project_dict)
    case = project.load_cases[case_tag]
    ndf = dof_layout(project)

    build_model(ops, project, case)
    setup_analysis(ops)
    code = ops.analyze(1)
    ok = int(code) == 0

    disp = {n.tag: [float(v) for v in ops.nodeDisp(n.tag)]
            for n in project.nodes.values()}
    forces = {e.tag: [float(v) for v in ops.eleForce(e.tag)]
              for e in project.elements.values()}
    reactions = {s.node_tag: [float(v) for v in ops.nodeReaction(s.node_tag)]
                 for s in project.supports.values()}
    return {
        "case_tag": case_tag,
        "case_name": case.name,
        "ok": ok,
        "ndf": ndf,
        "displacements": disp,
        "element_forces": forces,
        "reactions": reactions,
    }
