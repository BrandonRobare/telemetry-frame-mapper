#!/usr/bin/env python3
"""Benchmark the current semantic CPU and explicit-MPS paths."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import platform
import statistics
import sys
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np

MODEL_ID = "nvidia/segformer-b0-finetuned-ade-512-512"
MIN_SPEEDUP = 1.20
MIN_LABEL_AGREEMENT = 0.99
MAX_CONFIDENCE_MAE = 0.02


def _fixture_images(count: int = 4, size: int = 512) -> list[np.ndarray]:
    rng = np.random.default_rng(823)
    y, x = np.mgrid[0:size, 0:size]
    images: list[np.ndarray] = []
    for index in range(count):
        noise = rng.integers(-18, 19, size=(size, size, 3))
        image = np.stack((x, y, (x + y) // 2), axis=-1)
        image = np.clip(image + noise + index * 7, 0, 255).astype(np.uint8)
        top = 48 + index * 37
        left = 72 + index * 41
        image[top : top + 96, left : left + 128] = (170, 170, 165)
        image[size - 140 : size - 40, 30 + index * 20 : 180 + index * 20] = (35, 90, 125)
        images.append(image)
    return images


def _sync(torch, device: str) -> None:
    if device == "mps":
        torch.mps.synchronize()


def _run_device(device: str, images: list[np.ndarray], repeats: int):
    import torch  # type: ignore[import-not-found]

    from backend.services import semantic_segmenter

    semantic_segmenter._segmenter_cache.clear()
    segmenter = semantic_segmenter.load_segmenter(MODEL_ID, device=device)
    semantic_segmenter.segment_frame(images[0], segmenter=segmenter, model_id=MODEL_ID)
    _sync(torch, device)
    durations: list[float] = []
    outputs = []
    for _ in range(repeats):
        _sync(torch, device)
        started = time.perf_counter()
        current = [
            semantic_segmenter.segment_frame(image, segmenter=segmenter, model_id=MODEL_ID)
            for image in images
        ]
        _sync(torch, device)
        durations.append(time.perf_counter() - started)
        outputs = current
    del segmenter
    semantic_segmenter._segmenter_cache.clear()
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    return statistics.median(durations), outputs


def _digest(arrays: list[np.ndarray]) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        digest.update(array.tobytes())
    return digest.hexdigest()


def _compare(cpu_outputs, mps_outputs) -> dict[str, float | str]:
    cpu_labels = [labels for labels, _confidence in cpu_outputs]
    mps_labels = [labels for labels, _confidence in mps_outputs]
    cpu_conf = np.stack([confidence.astype(np.float32) for _, confidence in cpu_outputs])
    mps_conf = np.stack([confidence.astype(np.float32) for _, confidence in mps_outputs])
    agreement = float(np.mean(np.stack(cpu_labels) == np.stack(mps_labels)))
    return {
        "label_agreement": agreement,
        "confidence_mae": float(np.mean(np.abs(cpu_conf - mps_conf))),
        "cpu_label_sha256": _digest(cpu_labels),
        "mps_label_sha256": _digest(mps_labels),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("semantic-mps-benchmark.json"))
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()

    import torch  # type: ignore[import-not-found]

    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS is unavailable on this benchmark runner")
    torch.manual_seed(823)
    images = _fixture_images()
    fixture_sha = _digest(images)

    cpu_seconds, cpu_outputs = _run_device("cpu", images, args.repeats)
    mps_seconds, mps_outputs = _run_device("mps", images, args.repeats)
    comparison = _compare(cpu_outputs, mps_outputs)
    speedup = cpu_seconds / mps_seconds
    label_agreement = float(comparison["label_agreement"])
    confidence_mae = float(comparison["confidence_mae"])
    correct = (
        label_agreement >= MIN_LABEL_AGREEMENT
        and confidence_mae <= MAX_CONFIDENCE_MAE
    )
    material_speedup = speedup >= MIN_SPEEDUP
    result = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "model_id": MODEL_ID,
        "fixture": {
            "kind": "deterministic procedural aerial-like RGB",
            "sha256": fixture_sha,
            "images": len(images),
            "shape": list(images[0].shape),
            "seed": 823,
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "torch": str(torch.__version__),
            "transformers": version("transformers"),
            "mps_built": bool(torch.backends.mps.is_built()),
            "mps_available": bool(torch.backends.mps.is_available()),
        },
        "measurement": {
            "order": ["cpu", "mps"],
            "warmup_runs_per_device": 1,
            "timed_repeats": args.repeats,
            "cpu_seconds_per_fixture": cpu_seconds,
            "mps_seconds_per_fixture": mps_seconds,
            "cpu_seconds_per_image": cpu_seconds / len(images),
            "mps_seconds_per_image": mps_seconds / len(images),
            "cpu_over_mps_speedup": speedup,
        },
        "correctness": comparison,
        "criteria": {
            "minimum_speedup": MIN_SPEEDUP,
            "minimum_label_agreement": MIN_LABEL_AGREEMENT,
            "maximum_confidence_mae": MAX_CONFIDENCE_MAE,
        },
        "correct": correct,
        "material_speedup": material_speedup,
        "decision": "enable_mps" if correct and material_speedup else "keep_cpu",
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
