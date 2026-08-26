from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from backend.core.config import AppConfig
from backend.db.models import Session as SessionModel
from backend.services.storage_lifecycle import (
    PolicyRule,
    _configured_roots,
    _disk_usage_pct,
    _is_relative_to_any,
    apply_policy,
)


class TestPolicyRule:
    def test_age_rule(self):
        r = PolicyRule(target="raw_frames", age_days=30)
        assert r.target == "raw_frames"
        assert r.age_days == 30
        assert r.disk_pct is None

    def test_disk_rule(self):
        r = PolicyRule(target="raw_frames", disk_pct=80.0)
        assert r.disk_pct == 80.0
        assert r.age_days is None

    def test_rejects_both(self):
        with pytest.raises(ValueError):
            PolicyRule(target="raw_frames", age_days=30, disk_pct=80.0)

    def test_rejects_neither(self):
        with pytest.raises(ValueError):
            PolicyRule(target="raw_frames")


class TestPathSafety:
    def test_is_relative_to_any(self, tmp_path):
        root = tmp_path / "safe"
        root.mkdir()
        child = root / "child"
        child.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        roots = (root,)
        assert _is_relative_to_any(child, roots) is True
        assert _is_relative_to_any(outside, roots) is False

    def test_configured_roots_are_absolute(self):
        cfg = AppConfig(
            imports_dir="./imports",
            processed_dir="./processed",
            exports_dir="./exports",
            data_dir="./data",
        )
        roots = _configured_roots(cfg)
        for r in roots:
            assert r.is_absolute()


class TestApplyPolicyDryRun:
    def test_dry_run_returns_candidates(self, tmp_path):
        """Dry run with a real temp dir should find candidates or return empty."""
        imports = tmp_path / "imports"
        imports.mkdir()
        session_dir = imports / "old_session"
        session_dir.mkdir()
        (session_dir / "frame.jpg").write_bytes(b"x" * 100)

        (tmp_path / "processed").mkdir()
        (tmp_path / "exports").mkdir()
        (tmp_path / "data").mkdir()

        cfg = AppConfig(
            imports_dir=str(imports),
            processed_dir=str(tmp_path / "processed"),
            exports_dir=str(tmp_path / "exports"),
            data_dir=str(tmp_path / "data"),
        )

        rules = [{"target": "raw_frames", "age_days": 0}]
        result = apply_policy(rules, execute=False, cfg=cfg, db=_FakeDb())
        assert result["mode"] == "dry-run"
        assert isinstance(result["candidates"], list)
        assert len(result["candidates"]) == 1
        assert result["candidates"][0]["action"] == "archive"
        assert isinstance(result["summary"], dict)

    def test_dry_run_rejects_unknown_target(self):
        result = apply_policy([{"target": "nonexistent", "age_days": 30}], execute=False)
        assert "error" in result

    def test_dry_run_rejects_invalid_rule(self):
        result = apply_policy(
            [{"target": "raw_frames", "age_days": 30, "disk_pct": 80}],
            execute=False,
        )
        assert "error" in result


class TestExecuteSafety:
    def test_execute_stays_inside_roots(self, tmp_path):
        imports = tmp_path / "imports"
        imports.mkdir()
        session_dir = imports / "test_session"
        session_dir.mkdir()
        (session_dir / "frame.jpg").write_bytes(b"x" * 100)

        (tmp_path / "processed").mkdir()
        (tmp_path / "exports").mkdir()
        (tmp_path / "data").mkdir()

        cfg = AppConfig(
            imports_dir=str(imports),
            processed_dir=str(tmp_path / "processed"),
            exports_dir=str(tmp_path / "exports"),
            data_dir=str(tmp_path / "data"),
        )

        rules = [{"target": "raw_frames", "age_days": 0}]
        result = apply_policy(rules, execute=False, cfg=cfg, db=_FakeDb())
        for c in result["candidates"]:
            assert any(Path(c["path"]).resolve().is_relative_to(r) for r in _configured_roots(cfg))

    def test_disk_usage_pct_returns_number(self):
        pct = _disk_usage_pct(".")
        assert isinstance(pct, float)
        assert 0.0 <= pct <= 100.0


class TestEndpoint:
    def test_apply_policy_endpoint_dry_run(self, client):
        rules = [{"target": "raw_frames", "age_days": 365 * 10}]
        resp = client.post(
            "/storage/apply-policy",
            json={"rules": rules, "execute": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "dry-run"
        assert "candidates" in data
        assert "summary" in data

    def test_apply_policy_invalid_target(self, client):
        resp = client.post(
            "/storage/apply-policy",
            json={
                "rules": [{"target": "nonexistent", "age_days": 30}],
                "execute": False,
            },
        )
        assert resp.status_code == 422


class _Query:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return SessionModel(
            name="old",
            folder_path="/tmp/old_session",
            imported_at=datetime.now(UTC) - timedelta(days=1),
        )

    def all(self):
        return [self.first()]


class _FakeDb:
    def query(self, _model):
        return _Query()


def test_execute_archives_age_based_raw_frames(tmp_path):
    imports = tmp_path / "imports"
    imports.mkdir()
    session_dir = imports / "old_session"
    session_dir.mkdir()
    (session_dir / "frame.jpg").write_bytes(b"x" * 100)

    (tmp_path / "processed").mkdir()
    exports = tmp_path / "exports"
    exports.mkdir()
    (tmp_path / "data").mkdir()

    cfg = AppConfig(
        imports_dir=str(imports),
        processed_dir=str(tmp_path / "processed"),
        exports_dir=str(exports),
        data_dir=str(tmp_path / "data"),
    )

    result = apply_policy(
        [{"target": "raw_frames", "age_days": 0}],
        execute=True,
        cfg=cfg,
        db=_FakeDb(),
    )

    assert result["summary"]["archived_items"] == 1
    assert result["summary"].get("removed_items", 0) == 0
    archived = Path(result["executed"]["archived"][0]["archive_path"])
    assert archived.exists()
    assert archived.is_dir()
    assert not session_dir.exists()
    assert archived.is_relative_to((exports / "storage_archive").resolve())


def test_execute_does_not_expose_storage_exception(tmp_path, monkeypatch):
    imports = tmp_path / "imports"
    imports.mkdir()
    session_dir = imports / "old_session"
    session_dir.mkdir()
    (session_dir / "frame.jpg").write_bytes(b"x")
    exports = tmp_path / "exports"
    exports.mkdir()
    (tmp_path / "processed").mkdir()
    (tmp_path / "data").mkdir()
    cfg = AppConfig(
        imports_dir=str(imports),
        processed_dir=str(tmp_path / "processed"),
        exports_dir=str(exports),
        data_dir=str(tmp_path / "data"),
    )
    def fail_move(*_):
        raise OSError(r"C:\internal\secret")

    monkeypatch.setattr("backend.services.storage_lifecycle.shutil.move", fail_move)

    result = apply_policy(
        [{"target": "raw_frames", "age_days": 0}], execute=True, cfg=cfg, db=_FakeDb()
    )

    assert result["executed"]["failed"] == [
        {"path": str(session_dir.resolve()), "reason": "operation failed"}
    ]


def test_apply_policy_without_db_dry_run_returns_empty_candidates(tmp_path):
    cfg = AppConfig(
        imports_dir=str(tmp_path / "imports"),
        processed_dir=str(tmp_path / "processed"),
        exports_dir=str(tmp_path / "exports"),
        data_dir=str(tmp_path / "data"),
    )
    result = apply_policy([{"target": "raw_frames", "age_days": 0}], execute=False, cfg=cfg)
    assert result["mode"] == "dry-run"
    assert result["candidates"] == []


def test_apply_policy_uses_session_import_date_for_dry_run(tmp_path):
    class SessionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return SessionModel(
                name="old",
                folder_path="/tmp/old_session",
                imported_at=datetime.now(UTC) - timedelta(days=10),
            )

        def all(self):
            return [self.first()]

    class Db:
        def query(self, _model):
            return SessionQuery()

    imports = tmp_path / "imports"
    imports.mkdir()
    session_dir = imports / "old_session"
    session_dir.mkdir()
    (session_dir / "frame.jpg").write_bytes(b"x" * 100)
    (tmp_path / "processed").mkdir()
    (tmp_path / "exports").mkdir()
    (tmp_path / "data").mkdir()
    cfg = AppConfig(
        imports_dir=str(imports),
        processed_dir=str(tmp_path / "processed"),
        exports_dir=str(tmp_path / "exports"),
        data_dir=str(tmp_path / "data"),
    )

    result = apply_policy(
        [{"target": "raw_frames", "age_days": 5}], execute=False, cfg=cfg, db=Db()
    )

    assert len(result["candidates"]) == 1
    assert "Age 10d" in result["candidates"][0]["reason"]


class TestSessionMatchingIsExact:
    """Regression tests for #643: folder_path lookup must be an exact path
    match, not an unescaped LIKE substring, and must never fall back to an
    arbitrary row when the match is ambiguous or absent (this decides
    whether we delete a user's data).
    """

    @staticmethod
    def _cfg(tmp_path: Path, imports: Path) -> AppConfig:
        (tmp_path / "processed").mkdir(exist_ok=True)
        (tmp_path / "exports").mkdir(exist_ok=True)
        (tmp_path / "data").mkdir(exist_ok=True)
        return AppConfig(
            imports_dir=str(imports),
            processed_dir=str(tmp_path / "processed"),
            exports_dir=str(tmp_path / "exports"),
            data_dir=str(tmp_path / "data"),
        )

    def test_short_name_is_not_matched_by_substring_of_older_session(
        self, tmp_path, db_session
    ):
        """Exact scenario from #643: imports/10 (imported today) sits next to
        imports/2026-01-10 (imported 200 days ago). A substring LIKE match on
        "10" hits both rows; picking .first() can return the 200-day-old row
        for the *fresh* "10" directory and archive today's data.
        """
        imports = tmp_path / "imports"
        imports.mkdir()

        old_dir = imports / "2026-01-10"
        old_dir.mkdir()
        (old_dir / "frame.jpg").write_bytes(b"x" * 100)

        fresh_dir = imports / "10"
        fresh_dir.mkdir()
        (fresh_dir / "frame.jpg").write_bytes(b"x" * 100)

        # Insert the old session first so an order-dependent `.first()` over
        # a substring match is the row most likely returned for both dirs.
        db_session.add(
            SessionModel(
                name="old",
                folder_path=str(old_dir.resolve()),
                imported_at=datetime.now(UTC) - timedelta(days=200),
            )
        )
        db_session.add(
            SessionModel(
                name="fresh",
                folder_path=str(fresh_dir.resolve()),
                imported_at=datetime.now(UTC),
            )
        )
        db_session.commit()

        cfg = self._cfg(tmp_path, imports)
        result = apply_policy(
            [{"target": "raw_frames", "age_days": 90}],
            execute=False,
            cfg=cfg,
            db=db_session,
        )

        candidate_paths = {c["path"] for c in result["candidates"]}
        assert str(old_dir.resolve()) in candidate_paths
        assert str(fresh_dir.resolve()) not in candidate_paths

    def test_wildcard_named_directory_matches_nothing(self, tmp_path, db_session):
        """A directory literally named "%" must not match every row via an
        unescaped LIKE pattern."""
        imports = tmp_path / "imports"
        imports.mkdir()

        wild_dir = imports / "%"
        wild_dir.mkdir()
        (wild_dir / "frame.jpg").write_bytes(b"x" * 100)

        db_session.add(
            SessionModel(
                name="unrelated-old",
                folder_path=str(tmp_path / "somewhere-else"),
                imported_at=datetime.now(UTC) - timedelta(days=200),
            )
        )
        db_session.commit()

        cfg = self._cfg(tmp_path, imports)
        result = apply_policy(
            [{"target": "raw_frames", "age_days": 90}],
            execute=False,
            cfg=cfg,
            db=db_session,
        )

        candidate_paths = {c["path"] for c in result["candidates"]}
        assert str(wild_dir.resolve()) not in candidate_paths

    def test_ambiguous_duplicate_rows_are_skipped_not_first(self, tmp_path, db_session):
        """Two rows sharing the same folder_path is ambiguous; an arbitrary
        `.first()` pick is not safe on a delete path."""
        imports = tmp_path / "imports"
        imports.mkdir()

        session_dir = imports / "dup_session"
        session_dir.mkdir()
        (session_dir / "frame.jpg").write_bytes(b"x" * 100)

        db_session.add(
            SessionModel(
                name="dup-old",
                folder_path=str(session_dir.resolve()),
                imported_at=datetime.now(UTC) - timedelta(days=200),
            )
        )
        db_session.add(
            SessionModel(
                name="dup-fresh",
                folder_path=str(session_dir.resolve()),
                imported_at=datetime.now(UTC),
            )
        )
        db_session.commit()

        cfg = self._cfg(tmp_path, imports)
        result = apply_policy(
            [{"target": "raw_frames", "age_days": 90}],
            execute=False,
            cfg=cfg,
            db=db_session,
        )

        candidate_paths = {c["path"] for c in result["candidates"]}
        assert str(session_dir.resolve()) not in candidate_paths

    def test_unmatched_directory_is_skipped_not_aged_by_mtime(self, tmp_path, db_session):
        """No DB row at all for this directory: must be skipped outright, not
        aged from filesystem mtime as a fallback."""
        imports = tmp_path / "imports"
        imports.mkdir()

        orphan_dir = imports / "orphan_session"
        orphan_dir.mkdir()
        (orphan_dir / "frame.jpg").write_bytes(b"x" * 100)

        old_time = (datetime.now(UTC) - timedelta(days=200)).timestamp()
        os.utime(orphan_dir, (old_time, old_time))

        cfg = self._cfg(tmp_path, imports)
        result = apply_policy(
            [{"target": "raw_frames", "age_days": 90}],
            execute=False,
            cfg=cfg,
            db=db_session,
        )

        candidate_paths = {c["path"] for c in result["candidates"]}
        assert str(orphan_dir.resolve()) not in candidate_paths
