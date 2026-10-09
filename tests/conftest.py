import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXAMPLES = ROOT / "examples"


def _load(name: str) -> dict:
    return json.loads((EXAMPLES / name).read_text())


@pytest.fixture(scope="session")
def cantilever2d() -> dict:
    return _load("cantilever2d.json")


@pytest.fixture(scope="session")
def cantilever3d() -> dict:
    return _load("cantilever3d.json")


@pytest.fixture(scope="session")
def truss_doc() -> dict:
    return _load("truss_doc.json")
