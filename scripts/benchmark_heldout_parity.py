"""Portable, preregistered CUDA--Metal held-out parity evidence harness.

The command is intentionally a manual benchmark tool: it validates the committed
fixture before importing accelerator runtimes and writes only the requested
portable evidence bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

FIXTURE_ID = "aukerman-colmap-v1"
SCHEMA_VERSION = 1
POLICY = {
    "iterations": 1250,
    "sh_degree": 1,
    "downscale_factor": 4,
    "max_gaussians": 350_000,
    "refine_start_iter": 300,
    "refine_stop_iter": 625,
    "refine_every": 100,
    "reset_every": 3000,
    "ssim_lambda": 0.2,
    "init_opacity": 0.1,
    "sh_warmup_every": 500,
    "eval_every": 0,
    "benchmark_heldout_split": True,
    "benchmark_test_every": 8,
    "benchmark_keep_crs": True,
    "background_color": [0.0, 0.0, 0.0],
}
PSNR_DELTA_MIN = -1.0
SSIM_DELTA_MIN = -0.030


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha256(path)))
    return digest.hexdigest()


def policy_fingerprint() -> str:
    return hashlib.sha256(_canonical(POLICY).encode("ascii")).hexdigest()


def _fixture_dir(value: Path | None) -> Path:
    return value or Path(__file__).parents[1] / "tests" / "fixtures" / "benchmarks" / "aukerman-v1"


def load_fixture(fixture_dir: Path | None = None) -> tuple[Path, dict[str, Any]]:
    root = _fixture_dir(fixture_dir)
    fixture = json.loads((root / "fixture.json").read_text(encoding="utf-8"))
    if fixture.get("fixture_id") != FIXTURE_ID or fixture.get("schema_version") != 1:
        raise RuntimeError("unsupported held-out fixture schema")
    return root, fixture


def _parse_manifest(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise RuntimeError("invalid image hash manifest") from exc
        if len(digest) != 64 or Path(name).name != name or name in values:
            raise RuntimeError("invalid image hash manifest")
        values[name] = digest
    return values


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract only ordinary relative files/directories from a fixture archive."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            member_path = Path(member.name)
            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or member.issym()
                or member.islnk()
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError(f"unsafe archive member: {member.name}")
        tar.extractall(destination, filter="data")


def _registered_names(model: Any) -> list[str]:
    return sorted(image.name for image in model.images)


def validate_fixture(
    fixture_dir: Path | None,
    source_images: Path,
    staged_root: Path | None = None,
) -> tuple[dict[str, Any], Path]:
    """Check committed sparse/image identities and safely prepare a COLMAP workspace."""
    from backend.services import colmap_io

    root, fixture = load_fixture(fixture_dir)
    archive = root / "aukerman-colmap-sparse.tar.gz"
    manifest_path = root / "aukerman-images.sha256"
    if _sha256(archive) != fixture["sparse_archive_sha256"]:
        raise RuntimeError("fixture sparse archive checksum mismatch")
    if _sha256(manifest_path) != fixture["image_manifest_sha256"]:
        raise RuntimeError("fixture image manifest checksum mismatch")
    manifest = _parse_manifest(manifest_path)
    if len(manifest) != 77:
        raise RuntimeError("fixture image manifest count mismatch")
    for name, expected in manifest.items():
        path = source_images / name
        if not path.is_file() or _sha256(path) != expected:
            raise RuntimeError(f"fixture image checksum mismatch: {name}")
    stage = staged_root or Path(tempfile.mkdtemp(prefix="heldout-parity-"))
    safe_extract(archive, stage)
    sparse = stage / "sparse"
    sparse_model = colmap_io._pick_best_submodel(sparse)
    if _tree_sha256(sparse_model) != fixture["sparse_model_sha256"]:
        raise RuntimeError("fixture sparse model tree checksum mismatch")
    images = stage / "images"
    images.mkdir(parents=True, exist_ok=True)
    for name in manifest:
        target = images / name
        try:
            os.link(source_images / name, target)
        except OSError:
            shutil.copy2(source_images / name, target)
    model = colmap_io.read_model(sparse_model)
    names = _registered_names(model)
    split = fixture["split"]
    heldout = names[:: int(split["test_every"])]
    names_hash = hashlib.sha256(("\n".join(names) + "\n").encode("utf-8")).hexdigest()
    if (
        len(names) != fixture["registered_view_count"]
        or int(model.points_xyz.shape[0]) != fixture["sparse_point_count"]
        or names_hash != split["registered_view_names_sha256"]
        or heldout != split["heldout_view_names"]
        or len(heldout) != split["heldout_view_count"]
        or len(names) - len(heldout) != split["train_view_count"]
    ):
        raise RuntimeError("fixture registered-view split/count mismatch")
    return fixture, stage


def _git_commit(repository: Path) -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()


def _source_images(source: Path, expected_commit: str) -> Path:
    if _git_commit(source) != expected_commit:
        raise RuntimeError("source checkout commit mismatch")
    images = source / "images"
    if not images.is_dir():
        raise RuntimeError("source checkout has no images directory")
    return images


def benchmark_config():
    from backend.services.splat_backends import TrainerConfig

    return TrainerConfig(**{**POLICY, "background_color": tuple(POLICY["background_color"])})


def _sync_target(kind: str) -> None:
    if kind == "cuda":
        import torch

        torch.cuda.synchronize()
    elif kind == "metal":
        import msplat

        msplat.sync()
    else:
        raise ValueError(f"unsupported target: {kind}")


def _runtime_metadata(kind: str) -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for package in ("numpy", "pillow", "torch", "gsplat", "msplat"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    metadata: dict[str, Any] = {
        "kind": kind,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor() or None,
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "packages": versions,
    }
    if kind == "cuda":
        try:
            import torch

            device = torch.cuda.current_device()
            properties = torch.cuda.get_device_properties(device)
            metadata["accelerator"] = {
                "name": torch.cuda.get_device_name(device),
                "capability": list(torch.cuda.get_device_capability(device)),
                "memory_bytes": int(properties.total_memory),
                "torch_cuda": torch.version.cuda,
                "cudnn": torch.backends.cudnn.version(),
                "driver": _command_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=driver_version",
                        "--format=csv,noheader",
                    ]
                ),
            }
        except (ImportError, OSError, RuntimeError) as exc:
            metadata["accelerator"] = {"probe_error": type(exc).__name__}
    elif kind == "metal":
        hardware: dict[str, Any] = {}
        raw = _command_output(["system_profiler", "SPHardwareDataType", "-json"])
        if raw:
            try:
                item = json.loads(raw)["SPHardwareDataType"][0]
                hardware = {
                    "name": item.get("chip_type") or item.get("machine_name"),
                    "machine_model": item.get("machine_model"),
                    "memory": item.get("physical_memory"),
                }
            except (KeyError, IndexError, TypeError, json.JSONDecodeError):
                hardware = {}
        metadata["accelerator"] = hardware
    else:
        raise ValueError(f"unsupported target: {kind}")
    return metadata


def _command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.strip() or None


def _maximum_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def worker(kind: str, colmap_dir: Path, output_dir: Path, result_path: Path) -> int:
    """Fresh-process training entry point; called only by the parent command."""
    from backend.services.splat_backends import get_training_backend

    backend = get_training_backend(kind)
    if not backend.is_available():
        raise RuntimeError(f"requested {kind} benchmark target is unavailable")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "splat.ply"
    started = time.perf_counter()
    result = backend.train(
        colmap_dir,
        output,
        benchmark_config(),
        lambda message, percent: print(f"progress={percent:.3f} {message}", flush=True),
        threading.Event(),
    )
    _sync_target(kind)  # Must occur before the timing endpoint on every target.
    elapsed = time.perf_counter() - started
    if not output.is_file():
        raise RuntimeError("backend completed without exporting splat.ply")
    result_path.write_text(
        _canonical(
            {
                "elapsed_seconds": elapsed,
                "result": result,
                "sync_confirmation": True,
                "maximum_rss_bytes": _maximum_rss_bytes(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


def _environment_text(metadata: dict[str, Any]) -> str:
    distributions = sorted(
        f"{distribution.metadata['Name']}=={distribution.version}"
        for distribution in importlib.metadata.distributions()
        if distribution.metadata.get("Name")
    )
    return _canonical(metadata) + "\n\n" + "\n".join(distributions) + "\n"


def _write_sums(directory: Path, members: list[str]) -> None:
    lines = [f"{_sha256(directory / name)}  {name}" for name in sorted(members)]
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _portable_tar(source: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as tar:
        for path in sorted(item for item in source.iterdir() if item.is_file()):
            info = tar.gettarinfo(str(path), arcname=path.name)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            with path.open("rb") as handle:
                tar.addfile(info, handle)


def run(kind: str, source: Path, output: Path, fixture_dir: Path | None = None) -> Path:
    root, fixture = load_fixture(fixture_dir)
    images = _source_images(source, fixture["source_commit"])
    with tempfile.TemporaryDirectory(prefix="heldout-parity-") as temporary:
        workspace = Path(temporary)
        _, staged = validate_fixture(root, images, workspace / "colmap")
        evidence = workspace / "evidence"
        evidence.mkdir()
        worker_result = workspace / "worker.json"
        log_path = evidence / "backend.log"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--kind",
            kind,
            "--colmap-dir",
            str(staged),
            "--output-dir",
            str(evidence),
            "--result",
            str(worker_result),
        ]
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        runtime = _runtime_metadata(kind)
        if process.returncode != 0 or not worker_result.is_file():
            failure = {
                "schema_version": SCHEMA_VERSION,
                "status": "failed",
                "kind": kind,
                "git_commit": _git_commit(Path(__file__).parents[1]),
                "fixture_id": fixture["fixture_id"],
                "policy_fingerprint": policy_fingerprint(),
                "worker_returncode": process.returncode,
                "runtime": runtime,
                "backend_log_sha256": _sha256(log_path),
            }
            (evidence / "failure.json").write_text(_canonical(failure) + "\n", encoding="utf-8")
            (evidence / "environment.txt").write_text(_environment_text(runtime), encoding="utf-8")
            _write_sums(evidence, ["backend.log", "environment.txt", "failure.json"])
            output.parent.mkdir(parents=True, exist_ok=True)
            _portable_tar(evidence, output)
            raise RuntimeError(f"{kind} benchmark worker failed; evidence bundle: {output}")
        worker_data = json.loads(worker_result.read_text(encoding="utf-8"))
        log = log_path.read_text(encoding="utf-8", errors="replace")
        run_json = {
            "schema_version": SCHEMA_VERSION,
            "kind": kind,
            "git_commit": _git_commit(Path(__file__).parents[1]),
            "fixture": fixture,
            "policy": POLICY,
            "policy_fingerprint": policy_fingerprint(),
            "runtime": runtime,
            "wall_seconds": worker_data["elapsed_seconds"],
            "iterations_per_second": POLICY["iterations"] / worker_data["elapsed_seconds"],
            "gaussian_count": worker_data["result"]["gaussian_count"],
            "splat_sha256": _sha256(evidence / "splat.ply"),
            "sync_confirmation": worker_data["sync_confirmation"],
            "maximum_rss_bytes": worker_data["maximum_rss_bytes"],
            "per_tile_overflow_warnings": log.lower().count("per-tile overflow"),
        }
        (evidence / "run.json").write_text(_canonical(run_json) + "\n", encoding="utf-8")
        (evidence / "environment.txt").write_text(
            _environment_text(run_json["runtime"]), encoding="utf-8"
        )
        _write_sums(evidence, ["backend.log", "environment.txt", "run.json", "splat.ply"])
        output.parent.mkdir(parents=True, exist_ok=True)
        _portable_tar(evidence, output)
    return output


def _read_bundle(bundle: Path) -> tuple[dict[str, Any], Path]:
    extracted = Path(tempfile.mkdtemp(prefix="heldout-bundle-"))
    safe_extract(bundle, extracted)
    required = {"run.json", "splat.ply", "environment.txt", "backend.log", "SHA256SUMS"}
    names = {item.name for item in extracted.iterdir()}
    if names != required:
        raise RuntimeError("bundle member set mismatch")
    sums = _parse_manifest(extracted / "SHA256SUMS")
    if set(sums) != required - {"SHA256SUMS"}:
        raise RuntimeError("bundle checksum schema mismatch")
    for name, digest in sums.items():
        if _sha256(extracted / name) != digest:
            raise RuntimeError(f"bundle checksum mismatch: {name}")
    run_json = json.loads((extracted / "run.json").read_text(encoding="utf-8"))
    if any(Path(value).is_absolute() for value in _walk_strings(run_json)):
        raise RuntimeError("run.json contains an absolute path")
    if run_json.get("splat_sha256") != _sha256(extracted / "splat.ply"):
        raise RuntimeError("run.json splat checksum mismatch")
    return run_json, extracted


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _walk_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_strings(child)


def validate_run_metadata(
    run_json: dict[str, Any], kind: str, fixture: dict[str, Any], commit: str
) -> None:
    if (
        run_json.get("schema_version") != SCHEMA_VERSION
        or run_json.get("kind") != kind
        or run_json.get("fixture") != fixture
        or run_json.get("policy") != POLICY
        or run_json.get("policy_fingerprint") != policy_fingerprint()
        or run_json.get("git_commit") != commit
        or run_json.get("sync_confirmation") is not True
        or int(run_json.get("gaussian_count", 0)) <= 0
        or float(run_json.get("wall_seconds", 0)) <= 0
        or len(str(run_json.get("splat_sha256", ""))) != 64
    ):
        raise RuntimeError(f"invalid {kind} run metadata")


def _render_bundle(
    label: str,
    ply: Path,
    colmap_dir: Path,
    heldout: list[str],
    evidence_dir: Path | None,
) -> list[dict[str, Any]]:
    """Render a bundle with the application-owned CUDA gsplat evaluator only."""
    import numpy as np
    import torch
    from PIL import Image

    from backend.services import accelerator, colmap_io, ply_io
    from backend.services.splat_backends import cuda_gsplat

    torch_runtime, gsplat = cuda_gsplat._import_training_deps()
    device = accelerator.device_str(torch_runtime, allow_metal=False)
    cloud = ply_io.read_3dgs_ply(ply)
    model = colmap_io.read_model(colmap_io._pick_best_submodel(colmap_dir / "sparse"))
    images = {image.name: image for image in model.images}
    rows: list[dict[str, Any]] = []
    for name in heldout:
        image = images[name]
        camera = model.cameras[image.camera_id]
        with Image.open(colmap_dir / "images" / name) as target_image:
            target_image = target_image.convert("RGB")
            size = (max(1, round(target_image.width / 4)), max(1, round(target_image.height / 4)))
            target_image = target_image.resize(size, Image.LANCZOS)
            target_np = np.asarray(target_image, dtype=np.uint8)
        intrinsics = cuda_gsplat._camera_intrinsics(camera, size[0], size[1])
        with torch.no_grad():
            render = cuda_gsplat._rasterize_cloud(
                torch_runtime,
                gsplat,
                cloud,
                colmap_io.world_to_cam_matrix(image),
                size[0],
                size[1],
                device,
                intrinsics=intrinsics,
                background_color=(0.0, 0.0, 0.0),
            )
            target = torch_runtime.from_numpy(target_np).to(device).float() / 255.0
            psnr = cuda_gsplat._psnr(torch_runtime, render, target)
            ssim = float(
                cuda_gsplat._ssim(
                    torch_runtime, render.permute(2, 0, 1)[None], target.permute(2, 0, 1)[None]
                ).item()
            )
            pixels = (render.cpu().numpy() * 255.0).round().clip(0, 255).astype(np.uint8)
        render_bytes = pixels.tobytes()
        png_sha256 = None
        if evidence_dir is not None:
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output = evidence_dir / f"{label}-{name}.png"
            Image.fromarray(pixels).save(output)
            png_sha256 = _sha256(output)
        rows.append(
            {
                "name": name,
                "psnr": psnr,
                "ssim": ssim,
                "render_rgb_sha256": hashlib.sha256(render_bytes).hexdigest(),
                "render_png_sha256": png_sha256,
            }
        )
    return rows


def compare(
    cuda_bundle: Path,
    metal_bundle: Path,
    source: Path,
    output: Path,
    fixture_dir: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict[str, Any]:
    from backend.services.splat_backends import get_training_backend

    if not get_training_backend("cuda").is_available():
        raise RuntimeError("CUDA gsplat evaluator target is unavailable")
    root, fixture = load_fixture(fixture_dir)
    images = _source_images(source, fixture["source_commit"])
    with tempfile.TemporaryDirectory(prefix="heldout-compare-") as temporary:
        workspace = Path(temporary)
        _, staged = validate_fixture(root, images, workspace / "colmap")
        cuda_run, cuda_dir = _read_bundle(cuda_bundle)
        metal_run, metal_dir = _read_bundle(metal_bundle)
        commit = _git_commit(Path(__file__).parents[1])
        validate_run_metadata(cuda_run, "cuda", fixture, commit)
        validate_run_metadata(metal_run, "metal", fixture, commit)
        heldout = fixture["split"]["heldout_view_names"]
        cuda_views = _render_bundle("cuda", cuda_dir / "splat.ply", staged, heldout, evidence_dir)
        metal_views = _render_bundle(
            "metal", metal_dir / "splat.ply", staged, heldout, evidence_dir
        )
        if [row["name"] for row in cuda_views] != heldout or [
            row["name"] for row in metal_views
        ] != heldout:
            raise RuntimeError("evaluator held-out image order mismatch")
        cuda_means = {
            key: sum(float(row[key]) for row in cuda_views) / len(cuda_views)
            for key in ("psnr", "ssim")
        }
        metal_means = {
            key: sum(float(row[key]) for row in metal_views) / len(metal_views)
            for key in ("psnr", "ssim")
        }
        deltas = {key: metal_means[key] - cuda_means[key] for key in cuda_means}
        ratio = metal_run["gaussian_count"] / cuda_run["gaussian_count"]
        verdict = (
            "PASS"
            if deltas["psnr"] >= PSNR_DELTA_MIN and deltas["ssim"] >= SSIM_DELTA_MIN
            else "FAIL"
        )
        result = {
            "schema_version": SCHEMA_VERSION,
            "comparison_git_commit": commit,
            "fixture": fixture,
            "policy_fingerprint": policy_fingerprint(),
            "background_color": [0.0, 0.0, 0.0],
            "evaluator_runtime": _runtime_metadata("cuda"),
            "cuda": {"run": cuda_run, "views": cuda_views, "means": cuda_means},
            "metal": {"run": metal_run, "views": metal_views, "means": metal_means},
            "deltas": deltas,
            "thresholds": {
                "psnr_delta_min": PSNR_DELTA_MIN,
                "ssim_delta_min": SSIM_DELTA_MIN,
            },
            "timing": {
                "cuda_wall_seconds": cuda_run["wall_seconds"],
                "metal_wall_seconds": metal_run["wall_seconds"],
                "metal_to_cuda_wall_ratio": metal_run["wall_seconds"] / cuda_run["wall_seconds"],
                "metal_to_cuda_throughput_ratio": cuda_run["wall_seconds"]
                / metal_run["wall_seconds"],
            },
            "gaussian_count_ratio_metal_to_cuda": ratio,
            "count_alert": ratio < 0.50 or ratio > 2.00,
            "verdict": verdict,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(_canonical(result) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--kind", choices=("cuda", "metal"), required=True)
    run_parser.add_argument("--source", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--fixture-dir", type=Path)
    compare_parser = commands.add_parser("compare")
    compare_parser.add_argument("--cuda-bundle", type=Path, required=True)
    compare_parser.add_argument("--metal-bundle", type=Path, required=True)
    compare_parser.add_argument("--source", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    compare_parser.add_argument("--fixture-dir", type=Path)
    compare_parser.add_argument("--evidence-dir", type=Path)
    worker_parser = commands.add_parser("worker")
    worker_parser.add_argument("--kind", choices=("cuda", "metal"), required=True)
    worker_parser.add_argument("--colmap-dir", type=Path, required=True)
    worker_parser.add_argument("--output-dir", type=Path, required=True)
    worker_parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        run(args.kind, args.source, args.output, args.fixture_dir)
    elif args.command == "compare":
        compare(
            args.cuda_bundle,
            args.metal_bundle,
            args.source,
            args.output,
            args.fixture_dir,
            args.evidence_dir,
        )
    else:
        return worker(args.kind, args.colmap_dir, args.output_dir, args.result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
