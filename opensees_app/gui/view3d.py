"""pyvista 3D view embedded in Qt (pyvistaqt)."""
from __future__ import annotations

import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor

from ..core.model.project import Project


class View3D(QtInteractor):
    """3D view of the model with click-to-pick on nodes."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.plotter = self.getPlotter()
        self.plotter.set_background("white")
        self._pick_cb = None

    # ---------- picking ----------
    def enable_pick(self, cb) -> None:
        self._pick_cb = cb
        self.plotter.add_callback("left_click", self._handle_click)

    def _handle_click(self) -> None:
        if self._pick_cb is None:
            return
        pos = self._pick_position()
        if pos is not None:
            self._pick_cb(np.asarray(pos, dtype=float))

    def _pick_position(self):
        try:
            x, y = self.plotter.iren.getEventPosition()
            renderer = self.plotter.renderer
            picker = renderer.picker
            picker.SetPickFromListOn(False)
            return picker.Pick(x, y, 0, renderer)
        except Exception:  # noqa: BLE001  (pick can fail headless; degrade to no-pick)
            return None

    # ---------- rendering ----------
    @staticmethod
    def _sorted_nodes(project: Project):
        return sorted(project.nodes.values(), key=lambda n: n.tag)

    def show_model(self, project: Project, selected: tuple[int, int] = (0, 0)) -> None:
        self.plotter.clear()
        self.plotter.set_background("white")
        self.plotter.add_axes()
        nodes = self._sorted_nodes(project)
        if not nodes:
            return
        pts = np.array([[n.x, n.y, n.z] for n in nodes], dtype=float)
        tag2idx = {n.tag: i for i, n in enumerate(nodes)}
        colors = ["#1f77b4"] * len(nodes)
        if selected[0] in tag2idx:
            colors[tag2idx[selected[0]]] = "#2ca02c"
        if selected[1] in tag2idx:
            colors[tag2idx[selected[1]]] = "#ff7f0e"
        self.plotter.add_points(pv.Points(pts), color=colors, point_size=10,
                                render_points_as_spheres=True)
        if project.elements:
            lines = []
            for e in project.elements.values():
                lines += [tag2idx[e.i_node], tag2idx[e.j_node]]
            self.plotter.add_lines(pv.PolyData(pts, lines), color="#d62728",
                                   line_width=2)
        if project.supports:
            sup = np.array([[n.x, n.y, n.z]
                            for n in (project.nodes[s] for s in project.supports)],
                           dtype=float)
            self.plotter.add_points(pv.Points(sup), color="red", point_size=16,
                                    render_points_as_spheres=True)
        self.plotter.reset_camera()

    def show_deformed(self, project: Project, displacements: dict[int, list[float]],
                      scale: float) -> None:
        self.plotter.clear()
        self.plotter.set_background("white")
        self.plotter.add_axes()
        nodes = self._sorted_nodes(project)
        if not nodes:
            return
        pts0 = np.array([[n.x, n.y, n.z] for n in nodes], dtype=float)
        tag2idx = {n.tag: i for i, n in enumerate(nodes)}
        disp = np.zeros_like(pts0)
        for i, n in enumerate(nodes):
            d = displacements.get(n.tag, [0.0, 0.0, 0.0])
            disp[i] = d[:3]
        pts1 = pts0 + disp * scale
        self.plotter.add_points(pv.Points(pts0), color="lightgray", point_size=6,
                                render_points_as_spheres=True)
        self.plotter.add_points(pv.Points(pts1), color="#d62728", point_size=8,
                                render_points_as_spheres=True)
        lines = []
        for e in project.elements.values():
            lines += [tag2idx[e.i_node], tag2idx[e.j_node]]
        if lines:
            self.plotter.add_lines(pv.PolyData(pts0, lines), color="lightgray",
                                   line_width=2)
            self.plotter.add_lines(pv.PolyData(pts1, lines), color="#d62728",
                                   line_width=2)
        self.plotter.reset_camera()
