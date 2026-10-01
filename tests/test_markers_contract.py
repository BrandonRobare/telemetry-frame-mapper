"""Collection selectors and database isolation are contracts with the CI lanes."""

from pathlib import Path

import pytest

from tests.classification import AREA_BY_FILE, AREA_FILES, LEVELS

REPO_ROOT = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.contract, pytest.mark.area_platform_ops]


def test_every_collected_test_has_one_level_and_area(request):
    for item in request.session.items:
        names = [marker.name for marker in item.iter_markers()]
        assert sum(name in LEVELS for name in names) == 1, item.nodeid
        assert sum(name.startswith("area_") for name in names) == 1, item.nodeid


def test_file_map_covers_the_current_layout():
    files = {
        path.relative_to(REPO_ROOT / "tests").as_posix()
        for path in (REPO_ROOT / "tests").rglob("test_*.py")
    }
    assert files == AREA_BY_FILE.keys()
    assert all(area in AREA_FILES for area in AREA_BY_FILE.values())


@pytest.fixture
def suite(pytester, monkeypatch):
    # Subprocesses must never inherit the outer suite's database or clean its rows.
    monkeypatch.delenv("PYTEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    pytester.makeconftest((REPO_ROOT / "tests" / "conftest.py").read_text())
    pytester.makepyprojecttoml(
        (REPO_ROOT / "pyproject.toml").read_text().replace(
            'pythonpath = [".", "src"]',
            f'pythonpath = ["{REPO_ROOT}", "{REPO_ROOT / "src"}"]',
        )
    )
    backend = pytester.path / "tests" / "backend"
    backend.mkdir(parents=True)
    return pytester, backend


def test_area_and_level_selection_reports_deselection(suite):
    pytester, backend = suite
    (backend / "test_quality.py").write_text(
        "def test_unit(): pass\n"
        "def test_db(db_session): pass\n"
    )
    (backend / "test_geometry.py").write_text("def test_other_area(): pass\n")
    result = pytester.runpytest_subprocess("-m", "unit", "--area", "ingest-import", "-q")
    result.assert_outcomes(passed=1, deselected=2)
    result = pytester.runpytest_subprocess("--area", "ingest-import,coverage-planning", "-q")
    result.assert_outcomes(passed=3)


@pytest.mark.parametrize(
    ("filename", "source", "args", "message"),
    [
        ("test_unmapped.py", "def test_new(): pass", [], "Unmapped test file"),
        ("test_quality.py", "def test_new(): pass", ["--area", "ingest_import"], "Unknown --area"),
        (
            "test_quality.py",
            "import pytest\n@pytest.mark.unit\n@pytest.mark.integration\ndef test_new(): pass",
            [], "multiple level markers",
        ),
        (
            "test_quality.py",
            "import pytest\n@pytest.mark.unit\ndef test_new(client): pass",
            [], "unit marker conflicts with integration fixtures: client",
        ),
        (
            "test_quality.py",
            "import pytest\n@pytest.fixture\ndef nested(db_session): return db_session\n"
            "@pytest.mark.unit\ndef test_new(nested): pass",
            [], "unit marker conflicts with integration fixtures: db_session, setup_test_db",
        ),
        (
            "test_quality.py",
            "import pytest\n@pytest.mark.area_ingest_import\n"
            "@pytest.mark.area_platform_ops\ndef test_new(): pass",
            [], "multiple area markers",
        ),
        (
            "test_quality.py", "import pytest\n@pytest.mark.typo\ndef test_new(): pass",
            [], "'typo' not found in",
        ),
        (
            "test_unmapped.py",
            "import pytest\n@pytest.mark.unit\n"
            "@pytest.mark.area_platform_ops\ndef test_new(): pass",
            [], "Unmapped test file",
        ),
    ],
)
def test_invalid_classification_fails_clearly(suite, filename, source, args, message):
    pytester, backend = suite
    (backend / filename).write_text(source)
    result = pytester.runpytest_subprocess("--collect-only", "-q", *args)
    assert result.ret != 0
    assert message in result.stdout.str() + result.stderr.str()


def test_explicit_markers_override_inference(suite):
    pytester, backend = suite
    (backend / "test_quality.py").write_text(
        "import pytest\n"
        "@pytest.mark.contract\n@pytest.mark.area_platform_ops\n"
        "def test_contract(db_session): pass\n"
    )
    result = pytester.runpytest_subprocess("-m", "contract", "--area", "platform-ops", "-q")
    result.assert_outcomes(passed=1)


def test_units_avoid_db_and_transitive_db_fixtures_keep_isolation_and_logs(suite):
    pytester, backend = suite
    (backend / "test_quality.py").write_text('''
import pytest
from sqlalchemy import event
from backend.db.models import Session
from backend.services.reconstruction import _log_rec, get_rec_log

@pytest.fixture(autouse=True)
def watch_database(request):
    from conftest import test_engine
    connections = []
    def connected(*args):
        connections.append(True)
    event.listen(test_engine, "connect", connected)
    yield
    event.remove(test_engine, "connect", connected)
    if request.node.get_closest_marker("unit"):
        assert not connections, "unit test opened the shared database"

@pytest.fixture
def nested_db(db_session):
    return db_session

def test_01_unit_before_db(request):
    assert "db_session" not in request.fixturenames
    from conftest import TEST_DB_PATH
    assert not TEST_DB_PATH.exists()
    assert get_rec_log(958) == []
    _log_rec(958, "unit log")

def test_02_transitive_db(nested_db):
    assert get_rec_log(958) == []
    assert nested_db.query(Session).count() == 0
    nested_db.add(Session(name="isolated", folder_path="/tmp"))
    nested_db.commit()
    _log_rec(958, "integration log")

@pytest.mark.contract
def test_03_contract_db(nested_db):
    assert nested_db.query(Session).count() == 0
    assert get_rec_log(958) == []

def test_04_unit_after_db(request):
    assert "db_session" not in request.fixturenames
    assert get_rec_log(958) == []
''')
    contracts = pytester.path / "tests" / "contract"
    contracts.mkdir()
    (contracts / "test_frontend_api_contract.py").write_text('''
from backend.db.models import Session

def test_01_contract_inserts(db_session):
    assert db_session.query(Session).count() == 0
    db_session.add(Session(name="contract", folder_path="/tmp"))
    db_session.commit()

def test_02_contract_starts_clean(db_session):
    assert db_session.query(Session).count() == 0
''')
    result = pytester.runpytest_subprocess("-q")
    result.assert_outcomes(passed=6)
