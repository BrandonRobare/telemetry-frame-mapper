"""Benchmark script import/`resource` guards (#878)."""

from __future__ import annotations

import sys


def test_benchmark_module_imports_and_rss_probe_is_platform_safe() -> None:
    from scripts.benchmark_metal_presets import _maximum_rss_bytes

    value = _maximum_rss_bytes()
    if sys.platform == "win32":
        assert value == 0  # ru_maxrss is Unix-only; guarded, not fatal (#878)
    else:
        assert value > 0