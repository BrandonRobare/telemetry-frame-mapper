from __future__ import annotations

import pytest

from drone_video_geotagger.gps_quality import (
    FROZEN_MIN_RUN,
    GpsSample,
    assess_gps_lock,
    samples_from_telemetry,
)
from drone_video_geotagger.telemetry import TelemetryPoint


def _track(count: int, *, step_deg: float = 0.0001, start: float = 0.0) -> list[GpsSample]:
    """A healthy straight-line track: ~11 m/s northbound, one fix per second."""
    return [
        GpsSample(lat=41.1 + i * step_deg, lon=-81.1, t_s=start + float(i)) for i in range(count)
    ]


def test_healthy_track_has_no_warnings() -> None:
    report = assess_gps_lock(_track(30))

    assert report.sample_count == 30
    assert report.near_zero_count == 0
    assert report.jump_count == 0
    assert report.warnings == ()


def test_empty_and_single_sample_have_no_warnings() -> None:
    assert assess_gps_lock([]).warnings == ()
    assert assess_gps_lock([GpsSample(lat=41.1, lon=-81.1, t_s=0.0)]).warnings == ()


def test_near_zero_coordinates_warn() -> None:
    samples = [GpsSample(lat=0.0, lon=0.0, t_s=float(i)) for i in range(5)]

    report = assess_gps_lock(samples)

    assert report.near_zero_count == 5
    assert any("(0, 0)" in warning for warning in report.warnings)


def test_near_zero_mixed_with_valid_points_warns_without_jump_noise() -> None:
    # GPS acquires a fix mid-flight: zeros first, then real coordinates.
    samples = [GpsSample(lat=0.0, lon=0.0, t_s=float(i)) for i in range(3)]
    samples += [
        GpsSample(lat=41.1 + i * 0.0001, lon=-81.1, t_s=3.0 + i) for i in range(5)
    ]

    report = assess_gps_lock(samples)

    assert report.near_zero_count == 3
    # The zero->real transition must not be double-reported as a position jump.
    assert report.jump_count == 0
    assert len(report.warnings) == 1


def test_frozen_coordinates_warn() -> None:
    samples = [GpsSample(lat=41.1, lon=-81.1, t_s=float(i)) for i in range(FROZEN_MIN_RUN)]

    report = assess_gps_lock(samples)

    assert report.longest_frozen_run == FROZEN_MIN_RUN
    assert any("frozen" in warning for warning in report.warnings)


def test_short_frozen_run_does_not_warn() -> None:
    frozen = [GpsSample(lat=41.1, lon=-81.1, t_s=float(i)) for i in range(FROZEN_MIN_RUN - 1)]
    moving = [
        GpsSample(lat=41.2 + i * 0.0001, lon=-81.1, t_s=100.0 + i) for i in range(5)
    ]

    report = assess_gps_lock(frozen + moving)

    assert report.longest_frozen_run == FROZEN_MIN_RUN - 1
    assert not any("frozen" in warning for warning in report.warnings)


def test_implausible_speed_jump_warns() -> None:
    samples = _track(5)
    # ~1.1 km in one second (~1113 m/s) between fixes 5 and 6.
    samples.append(GpsSample(lat=samples[-1].lat + 0.01, lon=-81.1, t_s=5.0))

    report = assess_gps_lock(samples)

    assert report.jump_count == 1
    assert report.max_speed_ms is not None
    assert report.max_speed_ms > 1000
    assert any("jump" in warning for warning in report.warnings)


def test_distance_jump_without_timestamps_warns() -> None:
    samples = [
        GpsSample(lat=41.1, lon=-81.1),
        GpsSample(lat=41.1001, lon=-81.1),
        GpsSample(lat=41.2, lon=-81.1),  # ~11 km step with no timing information
    ]

    report = assess_gps_lock(samples)

    assert report.jump_count == 1
    assert report.max_speed_ms is None
    assert any("jump" in warning for warning in report.warnings)


def test_plausible_speed_is_measured_but_not_flagged() -> None:
    report = assess_gps_lock(_track(10))

    assert report.jump_count == 0
    assert report.max_speed_ms == pytest.approx(11.13, abs=0.5)


def test_cli_warn_gps_lock_prints_warnings_to_stream() -> None:
    import io

    from drone_video_geotagger.cli import warn_gps_lock

    frozen = [
        TelemetryPoint(start_s=float(i), end_s=float(i + 1), lat=41.1, lon=-81.1, rel_alt_m=100.0)
        for i in range(FROZEN_MIN_RUN)
    ]
    stream = io.StringIO()

    warn_gps_lock(frozen, stream=stream)

    output = stream.getvalue()
    assert "WARNING" in output
    assert "frozen" in output


def test_cli_warn_gps_lock_silent_for_healthy_track() -> None:
    import io

    from drone_video_geotagger.cli import warn_gps_lock

    healthy = [
        TelemetryPoint(
            start_s=float(i),
            end_s=float(i + 1),
            lat=41.1 + i * 0.0001,
            lon=-81.1,
            rel_alt_m=100.0,
        )
        for i in range(12)
    ]
    stream = io.StringIO()

    warn_gps_lock(healthy, stream=stream)

    assert stream.getvalue() == ""


def test_samples_from_telemetry_uses_start_seconds() -> None:
    points = [
        TelemetryPoint(start_s=0.0, end_s=1.0, lat=41.1, lon=-81.1, rel_alt_m=100.0),
        TelemetryPoint(start_s=1.0, end_s=2.0, lat=41.2, lon=-81.0, rel_alt_m=102.0),
    ]

    samples = samples_from_telemetry(points)

    assert samples == [
        GpsSample(lat=41.1, lon=-81.1, t_s=0.0),
        GpsSample(lat=41.2, lon=-81.0, t_s=1.0),
    ]
