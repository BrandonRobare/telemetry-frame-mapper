"""Real-Apple-Silicon release gate for Metal splat training (#852).

``train`` verifies and stages the committed CC0 Aukerman fixture, trains it
through the product ``quick`` preset on the Metal msplat backend, and retains
``splat.ply`` plus ``gate.json``. ``validate`` re-reads that export in a fresh
process with the pipeline's own parser, records the verdict in ``gate.json``,
writes ``SHA256SUMS`` over the evidence directory and exits non-zero on any
invalid row. Run as ``python -m scripts.metal_release_gate`` from the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path

FIXTURE_DIR = Path("tests/fixtures/benchmarks/aukerman-v1")
PRESET = "quick"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_fixture(fixture_dir: Path, source: Path) -> tuple[dict, Path]:
    fixture = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    archive = fixture_dir / "aukerman-colmap-sparse.tar.gz"
    manifest = fixture_dir / "aukerman-images.sha256"
    if _sha256(archive) != fixture["sparse_archive_sha256"]:
        raise SystemExit("sparse archive does not match fixture.json")
    if _sha256(manifest) != fixture["image_manifest_sha256"]:
        raise SystemExit("image manifest does not match fixture.json")
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        if _sha256(source / "images" / name) != digest:
            raise SystemExit(f"source image {name} does not match the manifest")
    return fixture, archive


def _command(*argv: str) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True).stdout.strip()


def train(args: argparse.Namespace) -> int:
    import msplat

    from backend.core.config import resolve_reconstruction_preset
    from backend.services.splat_backends.base import TrainerConfig
    from backend.services.splat_backends.metal_msplat import METAL_MSPLAT_BACKEND

    fixture, archive = _verify_fixture(args.fixture_dir, args.source)
    args.evidence.mkdir(parents=True)
    # Exactly the product path: shipped config.yaml layered over accelerator policy.
    config = TrainerConfig.from_preset(resolve_reconstruction_preset(PRESET, "metal"))
    with tempfile.TemporaryDirectory() as tmp:
        colmap_dir = Path(tmp) / "colmap"
        with tarfile.open(archive) as tar:
            tar.extractall(colmap_dir, filter="data")
        (colmap_dir / "images").symlink_to((args.source / "images").resolve())
        started = time.perf_counter()
        result = METAL_MSPLAT_BACKEND.train(
            colmap_dir,
            args.evidence / "splat.ply",
            config,
            lambda message, percent: print(f"progress={percent:.1f} {message}", flush=True),
            threading.Event(),
        )
        msplat.sync()  # Native work must finish before the clock stops.
        wall = time.perf_counter() - started
    gate = {
        "schema_version": 1,
        "git_commit": _command("git", "rev-parse", "HEAD"),
        "preset": PRESET,
        "trainer_config": asdict(config),
        "fixture": fixture,
        "runtime": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "msplat": msplat.__version__,
            "machine_model": _command("sysctl", "-n", "hw.model"),
            "cpu": _command("sysctl", "-n", "machdep.cpu.brand_string"),
        },
        "gaussian_count": result["gaussian_count"],
        "wall_seconds": wall,
        "sync_confirmation": True,
    }
    (args.evidence / "gate.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    return 0


def validate(args: argparse.Namespace) -> int:
    from backend.services.splat_backends.metal_msplat import validate_exported_ply

    gate_path = args.evidence / "gate.json"
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    try:
        rows = validate_exported_ply(args.evidence / "splat.ply", gate.get("gaussian_count"))
    except (RuntimeError, ValueError, OSError) as exc:
        # The invalid artifact stays on disk for diagnostics (#851).
        gate["validation"] = {"ok": False, "detail": str(exc)}
        code = 1
    else:
        gate["validation"] = {"ok": True, "rows": rows}
        code = 0
    gate_path.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    members = sorted(
        path.name
        for path in args.evidence.iterdir()
        if path.is_file() and path.name != "SHA256SUMS"
    )
    (args.evidence / "SHA256SUMS").write_text(
        "".join(f"{_sha256(args.evidence / name)}  {name}\n" for name in members),
        encoding="utf-8",
    )
    print(json.dumps(gate["validation"]), file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train_parser = commands.add_parser("train")
    train_parser.add_argument("--source", type=Path, required=True, help="Aukerman checkout")
    train_parser.add_argument("--evidence", type=Path, required=True, help="new output directory")
    train_parser.add_argument("--fixture-dir", type=Path, default=FIXTURE_DIR)
    train_parser.set_defaults(func=train)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--evidence", type=Path, required=True)
    validate_parser.set_defaults(func=validate)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
