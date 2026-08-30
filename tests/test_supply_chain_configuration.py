"""Regression checks for immutable Python environments and release actions."""

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_WORKFLOW = ROOT / ".github/workflows/ci.yml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release.yml"
DOCKERFILE = ROOT / "Dockerfile"
DEPENDABOT = ROOT / ".github/dependabot.yml"
PYPROJECT = ROOT / "pyproject.toml"
PACKAGE_INIT = ROOT / "src/drone_video_geotagger/__init__.py"
BACKEND_MAIN = ROOT / "backend/main.py"
FRONTEND_PACKAGE = ROOT / "frontend/package.json"
FRONTEND_LOCK = ROOT / "frontend/package-lock.json"
WINDOWS_INSTALLER = ROOT / "packaging/telemetry-frame-mapper.iss"
UV_LOCK = ROOT / "uv.lock"
CHANGELOG = ROOT / "CHANGELOG.md"
RELEASE_NOTES = ROOT / "release-notes/v2.0.4.md"
RELEASE_VERSION = "2.0.4"


def _match_version(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_release_version_declarations_agree() -> None:
    pyproject = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    package_init = PACKAGE_INIT.read_text(encoding="utf-8")
    backend_main = BACKEND_MAIN.read_text(encoding="utf-8")
    frontend_package = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))
    frontend_lock = json.loads(FRONTEND_LOCK.read_text(encoding="utf-8"))
    windows_installer = WINDOWS_INSTALLER.read_text(encoding="utf-8")
    uv_lock = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    changelog = CHANGELOG.read_text(encoding="utf-8")
    release_notes = RELEASE_NOTES.read_text(encoding="utf-8")
    locked_project = next(
        package for package in uv_lock["package"] if package["name"] == pyproject["project"]["name"]
    )

    declarations = {
        "pyproject.toml": pyproject["project"]["version"],
        "src/drone_video_geotagger/__init__.py": _match_version(
            r'^__version__ = "([^"]+)"$', package_init
        ),
        "backend/main.py": _match_version(
            r'FastAPI\([^\n]+version="([^"]+)"', backend_main
        ),
        "frontend/package.json": frontend_package["version"],
        "frontend/package-lock.json root": frontend_lock["version"],
        "frontend/package-lock.json package": frontend_lock["packages"][""]["version"],
        "packaging/telemetry-frame-mapper.iss": _match_version(
            r'^#define AppVersion "([^"]+)"$', windows_installer
        ),
        "uv.lock": locked_project["version"],
        "CHANGELOG.md": _match_version(r"^## \[([^]]+)\]", changelog),
        "release-notes/v2.0.4.md": _match_version(
            r"^# Telemetry Frame Mapper v([^\s]+)$", release_notes
        ),
    }

    assert declarations == dict.fromkeys(declarations, RELEASE_VERSION)


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
    assert not re.search(r"^\s*pip install\b", ci, flags=re.MULTILINE)
    assert '"pip-audit==2.10.1"' in pyproject


def test_windows_ci_runs_documented_path_and_subprocess_sensitive_pytest_suites() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")

    windows_job = re.search(
        r"^  windows-package:\n(?P<body>.*?)(?=^  [a-z][\w-]*:\n|\Z)",
        ci,
        flags=re.MULTILINE | re.DOTALL,
    )

    assert windows_job is not None
    body = windows_job.group("body")
    assert "Test Windows-sensitive Python suites" in body
    assert "tests/cli" in body
    assert "tests/backend/test_settings_router.py" in body
    assert "The Windows job intentionally runs the CLI suite" in body
    assert "path, subprocess, and redirected-stream behavior" in body


def test_reusable_ci_builds_and_smokes_the_wheel_distribution() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r"^\s{2}workflow_call:\s*$", ci, flags=re.MULTILINE)
    assert re.search(r"^  distribution:\n", ci, flags=re.MULTILINE)
    assert "uv build" in ci
    assert "uv venv --clear" in ci
    assert "uv pip install --python" in ci
    assert "dist/*.whl" in ci
    assert re.search(r'wheel-venv/bin/drone-video-geotagger" --help', ci)
    assert re.search(r'wheel-venv/bin/dvg-pipeline" --help', ci)


def test_tag_release_invokes_reusable_full_verification_before_publication() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert re.search(r'^\s{4}tags:\n\s{6}- "v\*"$', release, flags=re.MULTILINE)
    for job in ("test", "frontend", "docker-build", "distribution", "windows-package"):
        assert re.search(rf"^  {job}:\n", ci, flags=re.MULTILINE)
    assert re.search(
        r'^  verification:\n(?:.*\n)*?^    uses: \.\/\.github\/workflows\/ci\.yml$',
        release,
        flags=re.MULTILINE,
    )
    assert re.search(
        r"^  publish-frontend-dist:\n(?:.*\n)*?^    needs: \[verification, frontend-dist\]$",
        release,
        flags=re.MULTILINE,
    )


def test_docker_uses_locked_uv_runtime_environment_and_ci_smokes_health() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    ci = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock README.md LICENSE ./" in dockerfile
    assert "uv sync --frozen --no-dev --group backend --group reconstruction" in dockerfile
    assert "pip install" not in dockerfile
    assert "docker run --detach" in ci
    assert "http://127.0.0.1:8000/health" in ci
    assert "docker logs telemetry-frame-mapper-ci" in ci


def test_ci_and_release_actions_are_immutable_and_write_scope_is_publication_job_only() -> None:
    ci = CI_WORKFLOW.read_text(encoding="utf-8")
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    workflows = ci + "\n" + release
    action_refs = re.findall(r"^\s*uses:\s+[^@\s]+@([^\s#]+)", workflows, flags=re.MULTILINE)
    pinned_actions = re.findall(
        r"^\s*uses:\s+[^@\s]+@[0-9a-f]{40}\s+# v[^\s]+", workflows, flags=re.MULTILINE
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
    test_release_version_declarations_agree()
    test_ci_uses_locked_uv_environment_and_audits_runtime_groups()
    test_windows_ci_runs_documented_path_and_subprocess_sensitive_pytest_suites()
    test_reusable_ci_builds_and_smokes_the_wheel_distribution()
    test_tag_release_invokes_reusable_full_verification_before_publication()
    test_docker_uses_locked_uv_runtime_environment_and_ci_smokes_health()
    test_ci_and_release_actions_are_immutable_and_write_scope_is_publication_job_only()
    test_dependabot_keeps_github_actions_updates_enabled()
