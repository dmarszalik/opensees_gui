"""Application bootstrap: python -m opensees_app gui [project.json]"""
from __future__ import annotations

import sys


def run_gui(project_path: str | None = None) -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()
    if project_path:
        win.open_project(project_path)
    return app.exec()
