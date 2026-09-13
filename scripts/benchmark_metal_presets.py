from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, cast

DEFAULT_CANDIDATES = (1250, 1500, 2000, 2500, 3000)
DEFAULT_MINIMUM_GROWTH_RATIO = 1.25


def select_quick_iterations(
    runs: list[dict[str, Any]], *, minimum_growth_ratio: float
) -> int:
    """Return the smallest candidate that passes the preregistered growth gate."""
    passing = [
        int(run["iterations"])
        for run in runs
        if float(run["growth_ratio"]) >= minimum_growth_ratio
    ]
    if not passing:
        raise RuntimeError(f"No candidate reached {minimum_growth_ratio:.3f}x sparse count")
    return min(passing)


def select_quick_cap(
    *,
    base_cap: int,
    base_count: int,
    probe_cap: int,
    probe_count: int,
    probe_rss_bytes: int,
    memory_bytes: int,
    minimum_count_gain: float,
    maximum_memory_fraction: float,
) -> int:
    """Raise the cap only when the probe adds detail within memory headroom."""
    enough_detail = probe_count >= base_count * minimum_count_gain
    enough_memory = memory_bytes > 0 and probe_rss_bytes <= memory_bytes * maximum_memory_fraction
    return probe_cap if enough_detail and enough_memory else base_cap


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def _maximum_rss_bytes() -> int:
    # ru_maxrss is Unix-only; importing resource at module top broke the
    # benchmark entirely on Windows (#878). Report 0 (unknown) there.
    if sys.platform == "win32":
        return 0
    import resource

    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _sysctl(name: str) -> str | None:
    try:
        return subprocess.check_output(["sysctl", "-n", name], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


def _parse_candidates(value: str) -> tuple[int, ...]:
    candidates = tuple(sorted({int(item) for item in value.split(",")}))
    if not candidates or candidates[0] <= 0:
        raise argparse.ArgumentTypeError("candidates must be positive comma-separated integers")
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Metal quick-preset densification")
    parser.add_argument("--colmap-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-commit", required=True)
    parser.add_argument("--image-manifest-sha256", required=True)
    parser.add_argument(
        "--candidates",
        type=_parse_candidates,
        default=DEFAULT_CANDIDATES,
    )
    parser.add_argument(
        "--minimum-growth-ratio",
        type=float,
        default=DEFAULT_MINIMUM_GROWTH_RATIO,
    )
    parser.add_argument("--max-gaussians", type=int, default=350_000)
    parser.add_argument("--probe-max-gaussians", type=int, default=500_000)
    parser.add_argument("--minimum-cap-count-gain", type=float, default=1.10)
    parser.add_argument("--maximum-memory-fraction", type=float, default=0.70)
    args = parser.parse_args()

    from backend.services import colmap_io
    from backend.services.splat_backends import TrainerConfig
    from backend.services.splat_backends.metal_msplat import METAL_MSPLAT_BACKEND

    if not METAL_MSPLAT_BACKEND.is_available():
        raise RuntimeError("native Metal msplat backend is unavailable")
    sparse_model = colmap_io._pick_best_submodel(args.colmap_dir / "sparse")
    model = colmap_io.read_model(sparse_model)
    initial_count = int(model.points_xyz.shape[0])
    if initial_count <= 0:
        raise RuntimeError("fixture sparse model has no points")

    run_root = args.output.parent / "metal-preset-runs"
    run_root.mkdir(parents=True, exist_ok=True)
    runs: list[dict[str, Any]] = []
    for iterations in args.candidates:
        output_path = run_root / str(iterations) / "splat.ply"
        config = TrainerConfig.from_preset(
            {
                "iterations": iterations,
                "max_gaussians": args.max_gaussians,
                "sh_degree": 1,
                "downscale_factor": 4,
            }
        )
        started = time.perf_counter()
        result = METAL_MSPLAT_BACKEND.train(
            args.colmap_dir,
            output_path,
            config,
            lambda message, pct, candidate=iterations: print(
                f"candidate={candidate} progress={pct:.1f} message={message}", flush=True
            ),
            threading.Event(),
        )
        elapsed = time.perf_counter() - started
        gaussian_count = cast(int, result["gaussian_count"])
        runs.append(
            {
                "iterations": iterations,
                "gaussian_count": gaussian_count,
                "growth_ratio": gaussian_count / initial_count,
                "wall_seconds": elapsed,
                "maximum_rss_bytes": _maximum_rss_bytes(),
                "output_sha256": _sha256(output_path),
            }
        )

    selected: int | None = None
    error: str | None = None
    try:
        selected = select_quick_iterations(
            runs, minimum_growth_ratio=args.minimum_growth_ratio
        )
    except RuntimeError as exc:
        error = str(exc)

    memory_bytes = int(_sysctl("hw.memsize") or 0)
    cap_probe: dict[str, Any] | None = None
    selected_max_gaussians = args.max_gaussians
    if selected is not None:
        output_path = run_root / f"{selected}-cap-{args.probe_max_gaussians}" / "splat.ply"
        probe_config = TrainerConfig.from_preset(
            {
                "iterations": selected,
                "max_gaussians": args.probe_max_gaussians,
                "sh_degree": 1,
                "downscale_factor": 4,
            }
        )
        started = time.perf_counter()
        probe_result = METAL_MSPLAT_BACKEND.train(
            args.colmap_dir,
            output_path,
            probe_config,
            lambda message, pct: print(
                f"cap_probe={args.probe_max_gaussians} progress={pct:.1f} message={message}",
                flush=True,
            ),
            threading.Event(),
        )
        probe_count = cast(int, probe_result["gaussian_count"])
        cap_probe = {
            "iterations": selected,
            "max_gaussians": args.probe_max_gaussians,
            "gaussian_count": probe_count,
            "wall_seconds": time.perf_counter() - started,
            "maximum_rss_bytes": _maximum_rss_bytes(),
            "output_sha256": _sha256(output_path),
        }
        base_run = next(run for run in runs if run["iterations"] == selected)
        selected_max_gaussians = select_quick_cap(
            base_cap=args.max_gaussians,
            base_count=int(base_run["gaussian_count"]),
            probe_cap=args.probe_max_gaussians,
            probe_count=probe_count,
            probe_rss_bytes=int(cap_probe["maximum_rss_bytes"]),
            memory_bytes=memory_bytes,
            minimum_count_gain=args.minimum_cap_count_gain,
            maximum_memory_fraction=args.maximum_memory_fraction,
        )

    evidence = {
        "protocol": {
            "candidates": list(args.candidates),
            "minimum_growth_ratio": args.minimum_growth_ratio,
            "selection": "smallest candidate meeting the growth gate",
        },
        "fixture": {
            "name": "OpenDroneMap Aukerman",
            "license": "CC0-1.0",
            "source_commit": args.fixture_commit,
            "image_count": len(model.images),
            "sparse_point_count": initial_count,
            "image_manifest_sha256": args.image_manifest_sha256,
            "sparse_model_sha256": _tree_sha256(sparse_model),
        },
        "hardware": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "memory_bytes": memory_bytes,
        },
        "runtime": {
            "python": platform.python_version(),
            "msplat": importlib.metadata.version("msplat"),
        },
        "settings": {
            "sh_degree": 1,
            "downscale_factor": 4,
            "max_gaussians": args.max_gaussians,
        },
        "runs": runs,
        "cap_protocol": {
            "base_cap": args.max_gaussians,
            "probe_cap": args.probe_max_gaussians,
            "minimum_count_gain": args.minimum_cap_count_gain,
            "maximum_memory_fraction": args.maximum_memory_fraction,
        },
        "cap_probe": cap_probe,
        "selected_iterations": selected,
        "selected_max_gaussians": selected_max_gaussians,
        "passed": error is None,
        "error": error,
    }
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if error is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
