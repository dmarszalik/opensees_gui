"""QThread worker: run the analysis off the GUI thread.

Receives a plain dict snapshot of the project (picklable, no live Qt
objects) plus the list of case tags; validation happens on the main
thread before the worker starts.
"""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from ..core.fem.parallel import solve_all


class AnalysisWorker(QThread):
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, project_dict: dict, case_tags: list[int],
                 workers: int = 1, parent=None):
        super().__init__(parent)
        self._project_dict = project_dict
        self._case_tags = list(case_tags)
        self._workers = workers

    def run(self) -> None:
        try:
            results = solve_all(self._project_dict, self._case_tags, self._workers)
            self.finished_ok.emit(results)
        except Exception:  # noqa: BLE001  (report any solve failure via traceback)
            self.failed.emit(traceback.format_exc())
