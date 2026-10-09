"""Offscreen GUI smoke tests: build a model via the programmatic API, solve,
and check results against analytic values."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _new_window(qapp):
    from opensees_app.gui.main_window import MainWindow
    return MainWindow()


def test_gui_cantilever_2d(qapp):
    w = _new_window(qapp)
    w.project.dim = "2d"
    w.add_node(0.0, 0.0)
    w.add_node(1.0, 0.0)
    # catalog defaults: material 1 = S235 (E=210 GPa), section 1 = IPE 100
    w.add_element("frame", 1, 2, section_tag=1, material_tag=1)
    w.add_support(1, fx=True, fy=True, rz=True)
    w.add_load_case("tip")
    w.add_load(1, 2, fy_kn=10.0)
    results = w.run_analysis_sync()
    assert 1 in results and results[1]["ok"]
    dy = results[1]["displacements"][2][1]
    expect = 10e3 * 1.0**3 / (3 * 210e9 * 234e-8)
    assert abs(dy - expect) / expect < 1e-6
    assert w.tbl_results.rowCount() == 2


def test_gui_3d_axis_parallel(qapp):
    """Axis-parallel 3D beam solves (wheel bug worked around in the builder)."""
    w = _new_window(qapp)
    w.add_node(0.0, 0.0, 0.0)
    w.add_node(1.0, 0.0, 0.0)
    w.add_element("frame", 1, 2, section_tag=1, material_tag=1)
    w.add_support(1, fx=True, fy=True, fz=True, rx=True, ry=True, rz=True)
    w.add_load_case("c")
    w.add_load(1, 2, fy_kn=1.0)
    results = w.run_analysis_sync()
    assert 1 in results and results[1]["ok"]
    dy = results[1]["displacements"][2][1]
    # X-beam: global Y is the local z-axis -> bending uses Iy (IPE 100: 234e-8)
    expect = 1e3 * 1.0**3 / (3 * 210e9 * 234e-8)
    assert abs(dy - expect) / expect < 1e-6
