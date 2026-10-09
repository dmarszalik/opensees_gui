"""Parallel load-case solving + linear superposition of results.

Strategy (option A, CPU):
- each load case runs in its own process (own OpenSees instance, own memory);
- for linear elastic models, combinations are computed by linear
  superposition of per-case results (no re-solving: the factorization work
  is done once per case, reused across all combinations).
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

from ..model.project import Project
from .builder import FemError
from .runner import solve_case


def run_project(project: Project, workers: int | None = None) -> dict[int, dict]:
    """Validate and solve all load cases. Raises FemError."""
    problems = project.validate()
    if problems:
        raise FemError("\n".join(problems))
    return solve_all(project.to_dict(), list(project.load_cases), workers)


def solve_all(project_dict: dict, case_tags: list[int],
              workers: int | None = None) -> dict[int, dict]:
    case_tags = list(case_tags)
    if not case_tags:
        return {}
    if workers is None:
        workers = min(4, os.cpu_count() or 1)
    workers = max(1, min(workers, len(case_tags)))
    if workers == 1:
        return {ct: solve_case(project_dict, ct) for ct in case_tags}
    results: dict[int, dict] = {}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futs = {ct: pool.submit(solve_case, project_dict, ct) for ct in case_tags}
        for ct, f in futs.items():
            results[ct] = f.result()
    return results


def combine(results: dict[int, dict], factors: dict[int, float]) -> dict:
    """Linear superposition: result = sum(factor_i * case_i)."""
    if not factors:
        raise ValueError("empty combination")

    def _sum(kind: str) -> dict[int, list[float]]:
        keys: set[int] = set()
        for ct in factors:
            keys.update(results[ct][kind])
        out = {}
        for k in keys:
            # element forces carry 2*ndf entries (frame) or 2 (truss);
            # displacements/reactions carry ndf — use the actual vector length
            n = max(len(results[ct][kind][k]) for ct in factors)
            out[k] = [
                sum(factors[ct] * results[ct][kind][k][i]
                    for ct in factors if i < len(results[ct][kind][k]))
                for i in range(n)
            ]
        return out

    return {
        "displacements": _sum("displacements"),
        "element_forces": _sum("element_forces"),
        "reactions": _sum("reactions"),
    }
