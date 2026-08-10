"""Regression checks for immutable Python environments and release actions."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
DOCKERFILE = ROOT / "Dockerfile"
DEPENDABOT = ROOT / ".github/dependabot.yml"
PYPROJECT = ROOT / "pyproject.toml"


def test_ci_uses_locked_uv_environment_and_audits_runtime_groups() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    pyproject = PYPROJECT.read_text(encoding="utf-8")

    assert "uv lock --check" in ci
    assert "python tests/test_supply_chain_configuration.py" in ci
    assert (
        "uv sync --frozen --group backend --group reconstruction --group dev --group audit"
        in ci
    )
    assert (
        "uv export --frozen --no-dev --no-emit-project "
        "--group backend --group reconstruction"
    ) in ci
    assert "pip-audit -r /tmp/runtime-requirements.txt" in ci
    assert "pip install" not in ci
    assert '"pip-audit==2.10.1"' in pyproject


def test_docker_uses_locked_uv_runtime_environment_and_ci_smokes_health() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock README.md LICENSE ./" in dockerfile
    assert "uv sync --frozen --no-dev --group backend --group reconstruction" in dockerfile
    assert "pip install" not in dockerfile
    assert "docker run --detach" in ci
    assert "http://127.0.0.1:8000/health" in ci
    assert "docker logs telemetry-frame-mapper-ci" in ci


def test_release_actions_are_immutable_and_write_scope_is_publication_job_only() -> None:
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    action_refs = re.findall(r"^\s*uses:\s+[^@\s]+@([^\s#]+)", release, flags=re.MULTILINE)
    pinned_actions = re.findall(
        r"^\s*uses:\s+[^@\s]+@[0-9a-f]{40}\s+# v\d+", release, flags=re.MULTILINE
    )

    assert action_refs
    assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs)
    assert len(pinned_actions) == len(action_refs)
    assert re.search(r"^permissions:\n\s+contents: read$", release, flags=re.MULTILINE)
    assert re.search(
        r"^  publish-frontend-dist:\n(?:.*\n)*?^    permissions:\n      contents: write$",
        release,
        flags=re.MULTILINE,
    )
    assert len(re.findall(r"contents: write", release)) == 1


def test_dependabot_keeps_github_actions_updates_enabled() -> None:
    dependabot = DEPENDABOT.read_text(encoding="utf-8")

    assert 'package-ecosystem: "github-actions"' in dependabot


if __name__ == "__main__":
    test_ci_uses_locked_uv_environment_and_audits_runtime_groups()
    test_docker_uses_locked_uv_runtime_environment_and_ci_smokes_health()
    test_release_actions_are_immutable_and_write_scope_is_publication_job_only()
    test_dependabot_keeps_github_actions_updates_enabled()
