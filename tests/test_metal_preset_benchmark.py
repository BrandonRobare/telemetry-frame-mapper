from __future__ import annotations

import pytest


def test_selects_smallest_candidate_that_reaches_preregistered_growth() -> None:
    from scripts.benchmark_metal_presets import select_quick_iterations

    runs = [
        {"iterations": 1250, "growth_ratio": 1.04},
        {"iterations": 1500, "growth_ratio": 1.19},
        {"iterations": 2000, "growth_ratio": 1.31},
        {"iterations": 2500, "growth_ratio": 1.72},
    ]

    assert select_quick_iterations(runs, minimum_growth_ratio=1.25) == 2000


def test_selection_fails_when_no_candidate_densifies_enough() -> None:
    from scripts.benchmark_metal_presets import select_quick_iterations

    runs = [
        {"iterations": 1250, "growth_ratio": 1.00},
        {"iterations": 3000, "growth_ratio": 1.24},
    ]

    with pytest.raises(RuntimeError, match="No candidate reached 1.250x"):
        select_quick_iterations(runs, minimum_growth_ratio=1.25)


@pytest.mark.parametrize(
    ("probe_count", "probe_rss", "expected"),
    [
        (165_000, 4_000_000_000, 500_000),
        (150_000, 4_000_000_000, 350_000),
        (165_000, 6_000_000_000, 350_000),
    ],
)
def test_cap_probe_requires_output_gain_and_memory_headroom(
    probe_count: int, probe_rss: int, expected: int
) -> None:
    from scripts.benchmark_metal_presets import select_quick_cap

    assert select_quick_cap(
        base_cap=350_000,
        base_count=150_000,
        probe_cap=500_000,
        probe_count=probe_count,
        probe_rss_bytes=probe_rss,
        memory_bytes=8_000_000_000,
        minimum_count_gain=1.10,
        maximum_memory_fraction=0.70,
    ) == expected
