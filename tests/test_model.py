"""Unit tests: model dataclasses, JSON/CSV round-trips, section catalog."""
from opensees_app.core.model.catalog import default_materials, load_profiles
from opensees_app.core.model.io import export_csv, import_csv
from opensees_app.core.model.project import Project


def test_json_roundtrip(cantilever2d):
    p1 = Project.from_dict(cantilever2d)
    p2 = Project.from_dict(p1.to_dict())
    assert p2.dim == p1.dim == "2d"
    assert set(p2.nodes) == set(p1.nodes)
    assert set(p2.elements) == set(p1.elements)
    assert p2.elements[1].i_node == 1 and p2.elements[1].j_node == 2
    assert p2.elements[1].kind == "frame"
    assert set(p2.load_cases) == {1, 2}
    assert p2.load_cases[1].loads[0].fx == 10000.0


def test_validate_clean(cantilever2d):
    p = Project.from_dict(cantilever2d)
    assert p.validate() == []


def test_validate_detects_missing_node(cantilever2d):
    p = Project.from_dict(cantilever2d)
    del p.nodes[2]
    problems = p.validate()
    assert any("missing node 2" in x for x in problems)


def test_csv_roundtrip(cantilever2d, tmp_path):
    p = Project.from_dict(cantilever2d)
    path = tmp_path / "model.csv"
    export_csv(p, path)
    q = import_csv(path)
    assert set(q.nodes) == set(p.nodes)
    assert set(q.elements) == set(p.elements)
    assert set(q.supports) == set(p.supports)
    assert set(q.materials) == set(p.materials)
    assert set(q.sections) == set(p.sections)
    assert q.dim == p.dim == "2d"
    assert q.elements[1].kind == "frame"
    assert q.supports[1].fix_x and q.supports[1].fix_rz and q.supports[1].fix_y is True


def test_catalog_si_units():
    profiles = load_profiles()
    assert len(profiles) >= 20
    s = next(p for p in profiles if p.name == "IPE 200")
    assert abs(s.A - 28.5e-4) < 1e-9        # 28.5 cm^2 -> m^2
    assert abs(s.Iy - 1943e-8) < 1e-12      # 1943 cm^4 -> m^4
    assert abs(s.h - 0.200) < 1e-9          # 200 mm -> m
    assert 0 < s.J < s.Iy                    # torsion constant plausible
    pipe = next(p for p in profiles if p.kind == "pipe")
    assert pipe.Iy == pipe.Iz                # circular: equal inertias
    assert pipe.J > 0


def test_default_materials():
    mats = default_materials()
    assert len(mats) == 3
    s355 = next(m for m in mats if m.name == "S355")
    assert s355.E == 210e9
    assert s355.fy == 355e6
    assert abs(s355.G - 210e9 / (2 * 1.3)) < 1.0
