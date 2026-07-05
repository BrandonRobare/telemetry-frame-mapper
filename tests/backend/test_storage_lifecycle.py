from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.config import AppConfig
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
        result = apply_policy(rules, execute=False, cfg=cfg)
        assert result["mode"] == "dry-run"
        assert isinstance(result["candidates"], list)
        assert isinstance(result["summary"], dict)

    def test_dry_run_rejects_unknown_target(self):
        result = apply_policy(
            [{"target": "nonexistent", "age_days": 30}], execute=False
        )
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
        result = apply_policy(rules, execute=False, cfg=cfg)
        for c in result["candidates"]:
            assert any(
                Path(c["path"]).resolve().is_relative_to(r)
                for r in _configured_roots(cfg)
            )

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
        resp = client.post("/storage/apply-policy", json={
            "rules": [{"target": "nonexistent", "age_days": 30}],
            "execute": False,
        })
        assert resp.status_code == 422