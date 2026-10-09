"""Command-line interface: python -m opensees_app <run|gui>."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .core.fem.builder import FemError
from .core.fem.parallel import run_project
from .core.model.project import Project


def _cmd_run(args: argparse.Namespace) -> int:
    project = Project.load(args.project)
    try:
        results = run_project(project, args.workers)
    except FemError as e:
        print("Cannot solve model:")
        print(e)
        return 1
    for r in results.values():
        max_d = max((abs(v) for d in r["displacements"].values() for v in d),
                    default=0.0)
        status = "ok" if r["ok"] else "FAILED"
        print(f"case {r['case_tag']} ({r['case_name']}): {status}, "
              f"max |disp| = {max_d:.6e} m")
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2) + "\n")
        print(f"results -> {out}")
    return 0 if all(r["ok"] for r in results.values()) else 1


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui.app import run_gui
    return run_gui(args.project)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="opensees-app")
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="solve all load cases of a project")
    run.add_argument("project", help="path to project JSON")
    run.add_argument("--workers", type=int, default=4,
                     help="parallel processes for load cases")
    run.add_argument("--out", default=None, help="write results JSON here")
    run.set_defaults(func=_cmd_run)

    gui = sub.add_parser("gui", help="launch the GUI")
    gui.add_argument("project", nargs="?", default=None,
                     help="optional project JSON to open")
    gui.set_defaults(func=_cmd_gui)

    args = ap.parse_args(argv)
    return args.func(args)
