"""Main window: model editing + 3D view + analysis + results.

GUI units: lengths m, forces kN, moments kNm, results mm.
The core model is SI (N, m, Pa).
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.fem.parallel import run_project
from ..core.model.catalog import default_materials, load_profiles
from ..core.model.entities import Element, Load, LoadCase, Node, Support
from ..core.model.io import export_csv, import_csv
from ..core.model.project import Project
from .view3d import View3D
from .worker import AnalysisWorker

KN = 1e3    # GUI kN  -> N
KNM = 1e3   # GUI kNm -> Nm


def _num(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenSees App — 3D structural analysis")
        self.resize(1400, 800)
        self._syncing = False
        self.results: dict[int, dict] = {}
        self._sel_i = 0
        self._sel_j = 0
        self._worker: AnalysisWorker | None = None
        self.current_path: Path | None = None
        self.project = self._new_project()
        self._build_ui()
        self._sync_all()

    # ----------------------------------------------------------------- project
    def _new_project(self) -> Project:
        p = Project(name="untitled", dim="3d")
        for m in default_materials():
            p.materials[m.tag] = m
        for s in load_profiles():
            p.sections[s.tag] = s
        return p

    def new_project(self):
        self.project = self._new_project()
        self.current_path = None
        self.results = {}
        self._sync_all()

    def open_project(self, path: str):
        self.project = Project.load(path)
        for m in default_materials():
            self.project.materials.setdefault(m.tag, m)
        for s in load_profiles():
            self.project.sections.setdefault(s.tag, s)
        self.current_path = Path(path)
        self.results = {}
        self._sync_all()

    def save_project(self, path):
        self.project.save(path)
        self.current_path = Path(path)
        self.statusBar().showMessage(f"saved: {path}", 5000)

    # --------------------------------------------------------------------- UI
    def _build_ui(self):
        try:
            self.view = View3D()
            self.view.enable_pick(self._on_pick)
        except Exception:  # noqa: BLE001  (VTK/Qt init can fail; fall back to no 3D view)
            self.view = None

        tabs = QTabWidget()
        tabs.addTab(self._build_nodes_tab(), "Nodes")
        tabs.addTab(self._build_elements_tab(), "Elements")
        tabs.addTab(self._build_supports_tab(), "Supports")
        tabs.addTab(self._build_loads_tab(), "Loads")
        tabs.addTab(self._build_results_tab(), "Results")

        splitter = QSplitter(Qt.Horizontal)
        if self.view is not None:
            splitter.addWidget(self.view)
        else:
            splitter.addWidget(QLabel("3D view unavailable (VTK init failed)"))
        splitter.addWidget(tabs)
        splitter.setSizes([700, 700])
        self.setCentralWidget(splitter)

        tb = self.addToolBar("Main")
        tb.addAction("New", self.new_project)
        tb.addAction("Open…", self._open_dialog)
        tb.addAction("Save", self._save_dialog)
        tb.addSeparator()
        self.spin_workers = QSpinBox()
        self.spin_workers.setRange(1, 16)
        self.spin_workers.setValue(1)
        tb.addWidget(self.spin_workers)
        self.act_run = tb.addAction("Run ▶", self.run_analysis)
        self.status = QLabel("ready")
        self.statusBar().addWidget(self.status)

        m_file = self.menuBar().addMenu("&File")
        m_file.addAction("New", self.new_project)
        m_file.addAction("Open…", self._open_dialog)
        m_file.addAction("Save", self._save_dialog)
        m_file.addAction("Save As…", self._save_as_dialog)
        m_file.addSeparator()
        m_file.addAction("Import CSV…", self._import_csv_dialog)
        m_file.addAction("Export CSV…", self._export_csv_dialog)
        m_file.addSeparator()
        m_file.addAction("Exit", self.close)
        m_help = self.menuBar().addMenu("&Help")
        m_help.addAction("About", self._about)

    def _build_nodes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl_nodes = QTableWidget(0, 4)
        self.tbl_nodes.setHorizontalHeaderLabels(["tag", "x [m]", "y [m]", "z [m]"])
        self.tbl_nodes.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_nodes.itemChanged.connect(self._on_table_edited)
        lay.addWidget(self.tbl_nodes)
        row = QHBoxLayout()
        b = QPushButton("Add node")
        b.clicked.connect(lambda: self.add_node(0.0, 0.0, 0.0))
        row.addWidget(b)
        b = QPushButton("Delete")
        b.clicked.connect(self._delete_node)
        row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    def _build_elements_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl_elems = QTableWidget(0, 6)
        self.tbl_elems.setHorizontalHeaderLabels(
            ["tag", "kind", "i node", "j node", "section", "material"])
        self.tbl_elems.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_elems.itemChanged.connect(self._on_table_edited)
        lay.addWidget(self.tbl_elems)
        form = QHBoxLayout()
        form.addWidget(QLabel("kind"))
        self.cmb_e_kind = QComboBox()
        self.cmb_e_kind.addItems(["frame", "truss"])
        form.addWidget(self.cmb_e_kind)
        form.addWidget(QLabel("i"))
        self.cmb_e_i = QComboBox()
        form.addWidget(self.cmb_e_i)
        form.addWidget(QLabel("j"))
        self.cmb_e_j = QComboBox()
        form.addWidget(self.cmb_e_j)
        form.addWidget(QLabel("section"))
        self.cmb_e_sec = QComboBox()
        form.addWidget(self.cmb_e_sec)
        form.addWidget(QLabel("material"))
        self.cmb_e_mat = QComboBox()
        form.addWidget(self.cmb_e_mat)
        b = QPushButton("Add element")
        b.clicked.connect(self._add_element_from_form)
        form.addWidget(b)
        b = QPushButton("Delete")
        b.clicked.connect(self._delete_element)
        form.addWidget(b)
        lay.addLayout(form)
        lay.addWidget(QLabel("Tip: click a node in the 3D view to pick i, then j."))
        return w

    def _build_supports_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl_supports = QTableWidget(0, 7)
        self.tbl_supports.setHorizontalHeaderLabels(
            ["node", "fx", "fy", "fz", "rx", "ry", "rz"])
        self.tbl_supports.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_supports.itemChanged.connect(self._on_table_edited)
        lay.addWidget(self.tbl_supports)
        form = QHBoxLayout()
        form.addWidget(QLabel("node"))
        self.cmb_s_node = QComboBox()
        form.addWidget(self.cmb_s_node)
        self.chk_s: dict[str, QCheckBox] = {}
        for name in ("fx", "fy", "fz", "rx", "ry", "rz"):
            c = QCheckBox(name)
            self.chk_s[name] = c
            form.addWidget(c)
        b = QPushButton("Add support")
        b.clicked.connect(self._add_support_from_form)
        form.addWidget(b)
        b = QPushButton("Delete")
        b.clicked.connect(self._delete_support)
        form.addWidget(b)
        lay.addLayout(form)
        return w

    def _build_loads_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tbl_loads = QTableWidget(0, 8)
        self.tbl_loads.setHorizontalHeaderLabels(
            ["case", "node", "fx [kN]", "fy [kN]", "fz [kN]",
             "mx [kNm]", "my [kNm]", "mz [kNm]"])
        self.tbl_loads.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl_loads.itemChanged.connect(self._on_table_edited)
        lay.addWidget(self.tbl_loads)
        form = QHBoxLayout()
        form.addWidget(QLabel("case"))
        self.cmb_l_case = QComboBox()
        form.addWidget(self.cmb_l_case)
        b = QPushButton("New case")
        b.clicked.connect(self._add_case)
        form.addWidget(b)
        b = QPushButton("Delete case")
        b.clicked.connect(self._delete_case)
        form.addWidget(b)
        form.addWidget(QLabel("node"))
        self.cmb_l_node = QComboBox()
        form.addWidget(self.cmb_l_node)
        self.spin_l: dict[str, QDoubleSpinBox] = {}
        for name in ("fx", "fy", "fz", "mx", "my", "mz"):
            s = QDoubleSpinBox()
            s.setRange(-1e9, 1e9)
            self.spin_l[name] = s
            form.addWidget(QLabel(f"{name} [kN{'m' if name.startswith('m') else ''}]"))
            form.addWidget(s)
        b = QPushButton("Add load")
        b.clicked.connect(self._add_load_from_form)
        form.addWidget(b)
        b = QPushButton("Delete load")
        b.clicked.connect(self._delete_load)
        form.addWidget(b)
        lay.addLayout(form)
        return w

    def _build_results_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        row = QHBoxLayout()
        row.addWidget(QLabel("case"))
        self.cmb_case = QComboBox()
        self.cmb_case.currentIndexChanged.connect(self._sync_results_table)
        row.addWidget(self.cmb_case)
        self.chk_deform = QCheckBox("deformed view")
        self.chk_deform.toggled.connect(self._sync_view3d)
        row.addWidget(self.chk_deform)
        row.addWidget(QLabel("scale"))
        self.slider_scale = QSlider(Qt.Horizontal)
        self.slider_scale.setRange(0, 100)
        self.slider_scale.setValue(20)
        self.slider_scale.valueChanged.connect(self._sync_view3d)
        row.addWidget(self.slider_scale)
        row.addStretch(1)
        lay.addLayout(row)
        self.tbl_results = QTableWidget(0, 7)
        self.tbl_results.setHorizontalHeaderLabels(
            ["node", "ux [mm]", "uy [mm]", "uz [mm]", "rx [rad]", "ry [rad]", "rz [rad]"])
        self.tbl_results.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.tbl_results)
        self.lbl_reactions = QLabel("")
        lay.addWidget(self.lbl_reactions)
        return w

    # ------------------------------------------------------------------- sync
    def _sync_all(self):
        self._syncing = True
        try:
            self._fill_nodes()
            self._fill_elements()
            self._fill_supports()
            self._fill_loads()
            self._fill_results()
        finally:
            self._syncing = False
        self._sync_view3d()

    def _fill_nodes(self):
        self.tbl_nodes.setRowCount(0)
        for combo in (self.cmb_e_i, self.cmb_e_j, self.cmb_s_node, self.cmb_l_node):
            combo.clear()
        for n in sorted(self.project.nodes.values(), key=lambda n: n.tag):
            r = self.tbl_nodes.rowCount()
            self.tbl_nodes.insertRow(r)
            for c, v in enumerate((n.tag, n.x, n.y, n.z)):
                it = QTableWidgetItem(str(v))
                if c == 0:
                    it.setFlags(Qt.NoItemFlags)
                self.tbl_nodes.setItem(r, c, it)
            for combo in (self.cmb_e_i, self.cmb_e_j, self.cmb_s_node, self.cmb_l_node):
                combo.addItem(str(n.tag), n.tag)

    def _fill_elements(self):
        self.tbl_elems.setRowCount(0)
        self.cmb_e_sec.clear()
        for s in sorted(self.project.sections.values(), key=lambda s: s.tag):
            self.cmb_e_sec.addItem(s.name, s.tag)
        self.cmb_e_mat.clear()
        for m in sorted(self.project.materials.values(), key=lambda m: m.tag):
            self.cmb_e_mat.addItem(m.name, m.tag)
        for e in sorted(self.project.elements.values(), key=lambda e: e.tag):
            r = self.tbl_elems.rowCount()
            self.tbl_elems.insertRow(r)
            for c, v in enumerate(
                    (e.tag, e.kind, e.i_node, e.j_node, e.section_tag, e.material_tag)):
                it = QTableWidgetItem(str(v))
                if c == 0:
                    it.setFlags(Qt.NoItemFlags)
                self.tbl_elems.setItem(r, c, it)

    def _fill_supports(self):
        self.tbl_supports.setRowCount(0)
        for s in sorted(self.project.supports.values(), key=lambda s: s.node_tag):
            r = self.tbl_supports.rowCount()
            self.tbl_supports.insertRow(r)
            vals = (s.node_tag, int(s.fix_x), int(s.fix_y), int(s.fix_z),
                    int(s.fix_rx), int(s.fix_ry), int(s.fix_rz))
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c == 0:
                    it.setFlags(Qt.NoItemFlags)
                self.tbl_supports.setItem(r, c, it)

    def _fill_loads(self):
        self.tbl_loads.setRowCount(0)
        self.cmb_l_case.clear()
        for c in sorted(self.project.load_cases.values(), key=lambda c: c.tag):
            self.cmb_l_case.addItem(c.name, c.tag)
        for c in sorted(self.project.load_cases.values(), key=lambda c: c.tag):
            for L in c.loads:
                r = self.tbl_loads.rowCount()
                self.tbl_loads.insertRow(r)
                vals = (c.tag, L.node_tag, L.fx / KN, L.fy / KN, L.fz / KN,
                        L.mx / KNM, L.my / KNM, L.mz / KNM)
                for col, v in enumerate(vals):
                    it = QTableWidgetItem(f"{v:g}")
                    if col < 2:
                        it.setFlags(Qt.NoItemFlags)
                    self.tbl_loads.setItem(r, col, it)

    def _fill_results(self):
        self.cmb_case.clear()
        for ct in sorted(self.results):
            self.cmb_case.addItem(f"{ct}: {self.results[ct]['case_name']}", ct)
        self._sync_results_table()

    def _sync_results_table(self):
        self.tbl_results.setRowCount(0)
        ct = self.cmb_case.currentData()
        if ct is None or ct not in self.results:
            self.lbl_reactions.setText("")
            return
        res = self.results[ct]
        for node, d in sorted(res["displacements"].items()):
            d = list(d) + [0.0] * (6 - len(d))
            r = self.tbl_results.rowCount()
            self.tbl_results.insertRow(r)
            vals = [node] + [x * 1e3 for x in d[:3]] + list(d[3:6])
            for c, v in enumerate(vals):
                self.tbl_results.setItem(r, c, QTableWidgetItem(f"{v:g}"))
        n_sup = len(res.get("reactions", {}))
        self.lbl_reactions.setText(
            f"reactions at {n_sup} support node(s); element end forces in the "
            f"results dict / export JSON")

    def _on_table_edited(self):
        if self._syncing:
            return
        self._read_tables()
        self._sync_view3d()

    def _read_tables(self):
        p = self.project
        p.nodes = {
            int(_num(self.tbl_nodes.item(r, 0).text())): Node(
                int(_num(self.tbl_nodes.item(r, 0).text())),
                _num(self.tbl_nodes.item(r, 1).text()),
                _num(self.tbl_nodes.item(r, 2).text()),
                _num(self.tbl_nodes.item(r, 3).text()),
            )
            for r in range(self.tbl_nodes.rowCount())
        }
        p.elements = {
            int(_num(self.tbl_elems.item(r, 0).text())): Element(
                int(_num(self.tbl_elems.item(r, 0).text())),
                self.tbl_elems.item(r, 1).text().strip(),
                int(_num(self.tbl_elems.item(r, 2).text())),
                int(_num(self.tbl_elems.item(r, 3).text())),
                int(_num(self.tbl_elems.item(r, 4).text())),
                int(_num(self.tbl_elems.item(r, 5).text())),
            )
            for r in range(self.tbl_elems.rowCount())
        }
        p.supports = {
            int(_num(self.tbl_supports.item(r, 0).text())): Support(
                int(_num(self.tbl_supports.item(r, 0).text())),
                *[int(_num(self.tbl_supports.item(r, c).text())) == 1
                  for c in range(1, 7)]
            )
            for r in range(self.tbl_supports.rowCount())
        }
        # keep cases that currently have no loads (they must not vanish)
        cases: dict[int, LoadCase] = {ct: LoadCase(ct, c.name)
                                      for ct, c in p.load_cases.items()}
        for r in range(self.tbl_loads.rowCount()):
            ct = int(_num(self.tbl_loads.item(r, 0).text()))
            if ct not in cases:
                cases[ct] = LoadCase(ct, f"case {ct}")
            cases[ct].loads.append(Load(
                int(_num(self.tbl_loads.item(r, 1).text())),
                _num(self.tbl_loads.item(r, 2).text()) * KN,
                _num(self.tbl_loads.item(r, 3).text()) * KN,
                _num(self.tbl_loads.item(r, 4).text()) * KN,
                _num(self.tbl_loads.item(r, 5).text()) * KNM,
                _num(self.tbl_loads.item(r, 6).text()) * KNM,
                _num(self.tbl_loads.item(r, 7).text()) * KNM,
            ))
        p.load_cases = cases

    def _sync_view3d(self):
        if self.view is None:
            return
        try:
            if self.chk_deform.isChecked() and self.results:
                ct = self.cmb_case.currentData()
                if ct in self.results:
                    self.view.show_deformed(
                        self.project, self.results[ct]["displacements"],
                        self.slider_scale.value() / 10.0)
                    return
            self.view.show_model(self.project, (self._sel_i, self._sel_j))
        except Exception as e:  # noqa: BLE001  (any VTK error -> status bar)
            self.statusBar().showMessage(f"view error: {e}", 5000)

    # ------------------------------------------------- programmatic (tests)
    def add_node(self, x: float, y: float, z: float = 0.0) -> Node:
        n = self.project.add_node(x, y, z)
        self._sync_all()
        return n

    def add_element(self, kind: str, i: int, j: int,
                    section_tag: int, material_tag: int) -> Element:
        e = self.project.add_element(kind, i, j, section_tag, material_tag)
        self._sync_all()
        return e

    def add_support(self, node_tag: int, fx: bool = False, fy: bool = False,
                    fz: bool = False, rx: bool = False, ry: bool = False,
                    rz: bool = False) -> Support:
        s = self.project.add_support(node_tag, fx, fy, fz, rx, ry, rz)
        self._sync_all()
        return s

    def add_load_case(self, name: str) -> LoadCase:
        c = self.project.add_load_case(name)
        self._sync_all()
        return c

    def add_load(self, case_tag: int, node_tag: int, fx_kn: float = 0.0,
                 fy_kn: float = 0.0, fz_kn: float = 0.0, mx_knm: float = 0.0,
                 my_knm: float = 0.0, mz_knm: float = 0.0) -> Load:
        L = self.project.add_load(
            case_tag, node_tag, fx_kn * KN, fy_kn * KN, fz_kn * KN,
            mx_knm * KNM, my_knm * KNM, mz_knm * KNM)
        self._sync_all()
        return L

    # ------------------------------------------------------------- form UI
    def _add_element_from_form(self):
        i = self.cmb_e_i.currentData()
        j = self.cmb_e_j.currentData()
        if i is None or j is None:
            QMessageBox.information(self, "Elements", "Pick i and j nodes first.")
            return
        self.project.add_element(self.cmb_e_kind.currentText(), i, j,
                                 self.cmb_e_sec.currentData(),
                                 self.cmb_e_mat.currentData())
        self._sync_all()

    def _add_support_from_form(self):
        node = self.cmb_s_node.currentData()
        if node is None:
            return
        self.project.add_support(
            node, *[self.chk_s[k].isChecked()
                    for k in ("fx", "fy", "fz", "rx", "ry", "rz")])
        self._sync_all()

    def _add_case(self):
        self.project.add_load_case(
            f"case{Project._next_tag(self.project.load_cases)}")
        self._sync_all()

    def _delete_case(self):
        ct = self.cmb_l_case.currentData()
        if ct is not None:
            self.project.load_cases.pop(ct, None)
            self._sync_all()

    def _add_load_from_form(self):
        ct = self.cmb_l_case.currentData()
        node = self.cmb_l_node.currentData()
        if ct is None or node is None:
            return
        self.project.add_load(
            ct, node,
            self.spin_l["fx"].value() * KN, self.spin_l["fy"].value() * KN,
            self.spin_l["fz"].value() * KN, self.spin_l["mx"].value() * KNM,
            self.spin_l["my"].value() * KNM, self.spin_l["mz"].value() * KNM)
        self._sync_all()

    # -------------------------------------------------------------- delete
    def _delete_node(self):
        r = self.tbl_nodes.currentRow()
        if r < 0:
            return
        tag = int(_num(self.tbl_nodes.item(r, 0).text()))
        used = [e.tag for e in self.project.elements.values()
                if tag in (e.i_node, e.j_node)]
        in_sup = tag in self.project.supports
        in_load = any(L.node_tag == tag
                      for c in self.project.load_cases.values() for L in c.loads)
        if used or in_sup or in_load:
            QMessageBox.warning(self, "Delete node",
                                f"Node {tag} is used by elements, supports or loads.")
            return
        self.project.nodes.pop(tag, None)
        self._sync_all()

    def _delete_element(self):
        r = self.tbl_elems.currentRow()
        if r < 0:
            return
        tag = int(_num(self.tbl_elems.item(r, 0).text()))
        self.project.elements.pop(tag, None)
        self._sync_all()

    def _delete_support(self):
        r = self.tbl_supports.currentRow()
        if r < 0:
            return
        tag = int(_num(self.tbl_supports.item(r, 0).text()))
        self.project.supports.pop(tag, None)
        self._sync_all()

    def _delete_load(self):
        r = self.tbl_loads.currentRow()
        if r < 0:
            return
        ct = int(_num(self.tbl_loads.item(r, 0).text()))
        node = int(_num(self.tbl_loads.item(r, 1).text()))
        c = self.project.load_cases.get(ct)
        if c:
            c.loads = [L for L in c.loads if L.node_tag != node]
        self._sync_all()

    # --------------------------------------------------------------- pick
    def _on_pick(self, pos):
        if not self.project.nodes:
            return
        best, best_d = 0, None
        for n in self.project.nodes.values():
            d = math.sqrt((n.x - pos[0]) ** 2 + (n.y - pos[1]) ** 2
                          + (n.z - pos[2]) ** 2)
            if best_d is None or d < best_d:
                best, best_d = n.tag, d
        if best_d is None or best_d > self._pick_threshold():
            return
        if not self._sel_i or self._sel_j:
            self._sel_i, self._sel_j = best, 0
        else:
            self._sel_j = best
        for combo, tag in ((self.cmb_e_i, self._sel_i), (self.cmb_e_j, self._sel_j)):
            if tag and combo.findData(tag) >= 0:
                combo.setCurrentIndex(combo.findData(tag))
        self._sync_view3d()
        self.statusBar().showMessage(
            f"selected i={self._sel_i or '-'}, j={self._sel_j or '-'}", 5000)

    def _pick_threshold(self) -> float:
        pts = [(n.x, n.y, n.z) for n in self.project.nodes.values()]
        if len(pts) < 2:
            return 1e-6
        diag = max(math.dist(p, q) for p in pts for q in pts if p is not q)
        return max(diag * 0.02, 1e-9)

    # ----------------------------------------------------------------- run
    def run_analysis(self):
        problems = self.project.validate()
        if problems:
            QMessageBox.warning(self, "Model problems", "\n".join(problems))
            return
        if not self.project.load_cases:
            QMessageBox.information(self, "No loads",
                                    "Add a load case with loads first.")
            return
        self.status.setText("solving…")
        self.act_run.setEnabled(False)
        # snapshot on the main thread: the worker must not see live UI edits
        d = self.project.to_dict()
        self._worker = AnalysisWorker(d, list(self.project.load_cases),
                                      self.spin_workers.value(), self)
        self._worker.finished_ok.connect(self._on_results)
        self._worker.failed.connect(self._on_analysis_failed)
        self._worker.start()

    def _on_results(self, results):
        self.results = results
        self._syncing = True
        try:
            self._fill_results()
        finally:
            self._syncing = False
        self._sync_view3d()
        self.act_run.setEnabled(True)
        self.status.setText(f"solved {len(results)} case(s)")

    def _on_analysis_failed(self, msg: str):
        self.act_run.setEnabled(True)
        self.status.setText("analysis failed")
        if "FemError" in msg:
            lines = [l for l in msg.splitlines() if "FemError" in l]
            text = lines[-1].split("FemError:", 1)[-1].strip() if lines else msg
        else:
            text = msg
        QMessageBox.critical(self, "Analysis failed", text)

    def run_analysis_sync(self) -> dict[int, dict]:
        """Run in the calling thread (used by tests)."""
        self.results = run_project(self.project, 1)
        self._sync_all()
        return self.results

    # ----------------------------------------------------------------- file
    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "JSON (*.json)")
        if path:
            self.open_project(path)

    def _save_dialog(self):
        if self.current_path is not None:
            self.save_project(self.current_path)
        else:
            self._save_as_dialog()

    def _save_as_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save project", "", "JSON (*.json)")
        if path:
            self.save_project(path)

    def _import_csv_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import model", "", "CSV (*.csv)")
        if path:
            self.project = import_csv(path)
            self.current_path = None
            self.results = {}
            self._sync_all()

    def _export_csv_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export model", "", "CSV (*.csv)")
        if path:
            export_csv(self.project, path)
            self.statusBar().showMessage(f"exported: {path}", 5000)

    def _about(self):
        QMessageBox.about(
            self, "About",
            "OpenSees App v0.1\n\n"
            "Linear elastic FEM on OpenSeesPy 3.8 (openseespymac wheel).\n"
            "2D/3D truss and frame elements.\n\n"
            "Known wheel limitation: 3D frame members must lie in a coordinate "
            "plane (x=0, y=0 or z=0) and not be parallel to a global axis.\n"
            "Use 2D models for plane frames.")
