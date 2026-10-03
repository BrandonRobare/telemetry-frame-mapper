"""Python checks the schema snapshot; frontend CI checks its generated TypeScript."""

import sys

import pytest
from fastapi.routing import APIRoute

from tools.openapi_snapshot import SNAPSHOT, rendered_schema

pytestmark = [pytest.mark.contract, pytest.mark.area_platform_ops]


def test_openapi_snapshot_matches_backend():
    assert SNAPSHOT.read_text(encoding="utf-8") == rendered_schema(), (
        "OpenAPI snapshot drift: run python -m tools.openapi_snapshot, "
        "then npm run api:generate in frontend"
    )


def test_snapshot_check_rejects_drift_without_writing(monkeypatch, tmp_path):
    from tools import openapi_snapshot

    snapshot = tmp_path / "openapi.json"
    snapshot.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(openapi_snapshot, "SNAPSHOT", snapshot)
    monkeypatch.setattr(sys, "argv", ["openapi_snapshot", "--check"])
    with pytest.raises(SystemExit, match="1"):
        openapi_snapshot.main()
    assert snapshot.read_text(encoding="utf-8") == "{}\n"


def test_public_dict_responses_have_documentation_without_runtime_filtering():
    from backend.routers import (
        comparisons,
        export,
        georeferencing,
        jobs,
        reconstruction,
        storage,
        system,
    )

    paths = {
        "/jobs/",
        "/storage/files",
        "/storage/summary",
        "/storage/apply-policy",
        "/storage/backup-schedule",
        "/system/resources",
        "/export/survey-report",
        "/reconstruction/{reconstruction_id}/semantic-labels",
        "/reconstruction/{reconstruction_id}/geo-transform",
        "/reconstruction/{reconstruction_id}/ortho/status",
        "/reconstruction/{reconstruction_id}/coverage-gaps",
        "/reconstruction/{reconstruction_id}/quality-scorecard",
        "/reconstruction/{reconstruction_id}/validate-checkpoints",
        "/comparisons/{comparison_id}/diff",
        "/georeferencing/sessions/{session_id}/accuracy-report",
    }
    seen = set()
    for route in [
        route
        for module in (jobs, storage, system, export, reconstruction, comparisons, georeferencing)
        for route in module.router.routes
    ]:
        if isinstance(route, APIRoute) and route.path in paths and 200 in route.response_fields:
            assert route.response_model is None, route.path
            assert 200 in route.response_fields, route.path
            seen.add(route.path)
    assert seen == paths


def test_ci_runs_both_drift_checks():
    workflow = (SNAPSHOT.parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "run: npm run api:check" in workflow
    assert "run: uv run --frozen --no-sync pytest" in workflow


def test_documented_models_preserve_real_json_responses_and_sparse_reports(
    client, monkeypatch, tmp_path
):
    from pydantic import TypeAdapter

    from backend.db.models import Image, Reconstruction
    from backend.db.models import Session as SessionModel
    from backend.main import app
    from backend.response_schemas import (
        AppSettings,
        Job,
        OrthoStatus,
        QualityScorecard,
        StorageFileList,
        StorageStats,
        SurveyReport,
        SurveyReportCoverage,
        SurveyReportQualityAssessment,
    )
    from backend.routers import settings
    from backend.routers.reconstruction import PreflightReportContract, ReconstructionContract
    from backend.services.survey_report import _coverage_section, _quality_section

    monkeypatch.setattr(settings, "CONFIG_PATH", str(tmp_path / "settings.yaml"))
    db = app.state.test_db_session
    session = SessionModel(
        name="response contract", folder_path=None, photo_count=1, usable_count=1
    )
    db.add(session)
    db.flush()
    db.add(Image(session_id=session.id, filename="frame.jpg", filepath="/tmp/frame.jpg"))
    rec = Reconstruction(
        session_id=session.id,
        status="complete",
        preset="quick",
        frames_used=1,
        effective_splat_settings="""{"preset":"quick","accelerator_kind":"metal","device":"mps","splat_backend":"metal_msplat","iterations":1250,"max_gaussians":350000}""",
        training_metrics='[{"iter":1,"psnr":28,"ssim":0.8},{"iter":2,"psnr":29,"ssim":0.9}]',
    )
    db.add(rec)
    db.commit()
    documented = {
        "/jobs/": list[Job],
        f"/reconstruction/{rec.id}/status": ReconstructionContract,
        f"/reconstruction/preflight/{session.id}": PreflightReportContract,
        f"/reconstruction/{rec.id}/quality-scorecard": QualityScorecard,
        f"/reconstruction/{rec.id}/ortho/status": OrthoStatus,
        "/storage/files": StorageFileList,
        "/storage/summary": StorageStats,
        "/settings": AppSettings,
        f"/export/survey-report?session_id={session.id}": SurveyReport,
    }
    for url, model in documented.items():
        response = client.get(url)
        assert response.status_code == 200, response.text
        payload = response.json()
        adapter = TypeAdapter(model)
        value = adapter.validate_python(payload)
        assert adapter.dump_python(value, mode="json", by_alias=True, exclude_unset=True) == payload
    for producer, model in (
        (_coverage_section, SurveyReportCoverage),
        (_quality_section, SurveyReportQualityAssessment),
    ):
        sparse = producer(None)
        assert model.model_validate(sparse).model_dump(exclude_unset=True) == sparse
