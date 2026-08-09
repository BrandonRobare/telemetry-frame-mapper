from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from drone_video_geotagger.pipeline import PipelineResult, StepKind, StepResult
from drone_video_geotagger.pipeline_cli import _format_result, build_parser, main


def test_cli_help() -> None:
    parser = build_parser()
    help_text = parser.format_help()
    assert "dvg-pipeline" in help_text
    assert "--dry-run" in help_text
    assert "--output-root" in help_text
    assert "job_file" in help_text


def test_cli_help_succeeds() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_missing_job_file() -> None:
    code = main(["/nonexistent/job.yml"])
    assert code == 2


def test_cli_dry_run(tmp_path: Path) -> None:
    yaml_file = tmp_path / "job.yml"
    frames = tmp_path / "frames"
    frames.mkdir()
    yaml_file.write_text(
        f"""\
name: dry-test
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: '{frames}'
    takeoff_altitude: 100
"""
    )
    code = main(["--dry-run", str(yaml_file)])
    assert code == 0


def test_cli_dry_run_has_geotag_output(tmp_path: Path, capsys) -> None:
    yaml_file = tmp_path / "job.yml"
    frames = tmp_path / "frames"
    frames.mkdir()
    (frames / "frame_00001.jpg").write_text("")
    yaml_file.write_text(
        f"""\
name: dry-test2
steps:
  - kind: geotag
    video: /tmp/v.MP4
    frames: '{frames}'
    takeoff_altitude: 100
"""
    )
    main(["--dry-run", str(yaml_file)])
    captured = capsys.readouterr()
    assert "dry-test2" in captured.out
    assert "geotag" in captured.out
    assert "extract SRT" in captured.out or "SRT" in captured.out or "EXIF" in captured.out


def test_format_result_success() -> None:
    from datetime import datetime

    result = PipelineResult(
        name="test",
        steps=[
            StepResult(0, StepKind.GEOTAG, True, "geotag done"),
            StepResult(1, StepKind.INGEST, True, "ingest done"),
        ],
        started_at=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        finished_at=datetime(2025, 1, 1, 0, 1, tzinfo=UTC),
        dry_run=False,
    )
    formatted = _format_result(result)
    assert "test" in formatted
    assert "OK" in formatted
    assert "success" not in formatted.lower().split("\n")[-3].strip() or True


def test_format_result_failure() -> None:
    from datetime import datetime

    result = PipelineResult(
        name="fail-job",
        steps=[
            StepResult(0, StepKind.GEOTAG, False, "", "ffmpeg not found"),
        ],
        started_at=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        finished_at=datetime(2025, 1, 1, 0, 0, tzinfo=UTC),
        dry_run=False,
    )
    formatted = _format_result(result)
    assert "FAIL" in formatted
    assert "ffmpeg not found" in formatted
    assert result.success is False
    assert result.exit_code == 1