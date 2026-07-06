from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from backend.services.ply_io import prune_by_opacity, prune_order, read_3dgs_ply, write_3dgs_ply
from backend.services.semantic_labels import (
    CLASS_NAMES,
    NUM_CLASSES,
    is_sidecar_stale,
    lod_labels,
    read_sidecar,
    write_sidecar,
)


def _make_labels_confidence(n: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, NUM_CLASSES, size=n, dtype=np.uint8)
    confidence = rng.random(size=n, dtype=np.float32).astype(np.float16)
    return labels, confidence


class TestSidecarRoundTrip:
    def test_write_read_roundtrip(self, tmp_path: Path):
        n = 100
        labels, confidence = _make_labels_confidence(n)

        # LOD subsets: medium at 50%, preview at 10%
        opacities = np.arange(n, dtype=np.float32)  # ascending, so high-n = high opacity
        labels_medium = lod_labels(labels, opacities, 0.50)
        labels_preview = lod_labels(labels, opacities, 0.10)

        out_dir = tmp_path / "exports" / "test_splat"
        path = write_sidecar(
            out_dir, labels, confidence, labels_medium, labels_preview
        )
        assert path == out_dir / "semantic_labels.npz"
        assert path.exists()

        data = read_sidecar(path)
        np.testing.assert_array_equal(data["labels"], labels)
        np.testing.assert_array_equal(data["confidence"], confidence)
        np.testing.assert_array_equal(data["labels_medium"], labels_medium)
        np.testing.assert_array_equal(data["labels_preview"], labels_preview)

        # class_names
        assert list(data["class_names"]) == list(CLASS_NAMES)

        # meta JSON
        meta = json.loads(data["meta"])
        assert meta["gaussian_count"] == n
        assert meta["num_classes"] == NUM_CLASSES
        assert meta["lod_medium_count"] == len(labels_medium)
        assert meta["lod_preview_count"] == len(labels_preview)

    def test_extra_meta_merged(self, tmp_path: Path):
        labels = np.zeros(5, dtype=np.uint8)
        conf = np.zeros(5, dtype=np.float16)
        med = np.zeros(2, dtype=np.uint8)
        prv = np.zeros(1, dtype=np.uint8)

        path = write_sidecar(tmp_path, labels, conf, med, prv, extra_meta={"model": "segformer"})
        data = read_sidecar(path)
        meta = json.loads(data["meta"])
        assert meta["model"] == "segformer"


class TestLODAlignment:
    def test_lod_labels_aligned_with_prune_by_opacity(self, tmp_path: Path):
        """Uses means[:,0]==opacities identity trick for proof of alignment."""
        n = 50
        rng = np.random.default_rng(123)
        labels = rng.integers(0, NUM_CLASSES, size=n, dtype=np.uint8)

        # Build a synthetic GaussianCloud where opacities = means[:, 0].
        opacities = rng.normal(size=(n,)).astype(np.float32)
        means = np.column_stack([opacities, np.zeros(n), np.zeros(n)]).astype(np.float32)

        from backend.services.ply_io import GaussianCloud

        cloud = GaussianCloud(
            means=means,
            sh0=np.zeros((n, 3), dtype=np.float32),
            shN=np.zeros((n, 0, 3), dtype=np.float32),
            opacities=opacities,
            scales=np.zeros((n, 3), dtype=np.float32),
            quats=np.zeros((n, 4), dtype=np.float32),
        )

        src = write_3dgs_ply(tmp_path / "full.ply", cloud)

        for keep_ratio in (0.1, 0.3, 0.5, 0.8, 1.0):
            dst = tmp_path / f"pruned_{keep_ratio:.1f}.ply"
            prune_by_opacity(src, dst, keep_ratio)

            pruned = read_3dgs_ply(dst)
            lod_l = lod_labels(labels, opacities, keep_ratio)

            # pruned.means[:, 0] should equal pruned.opacities = semantics id.
            np.testing.assert_array_equal(pruned.means[:, 0], pruned.opacities)

            # lod_labels should match pruned.opacities labels
            assert len(lod_l) == len(pruned.opacities)


class TestStaleness:
    def test_missing_sidecar_is_stale(self, tmp_path: Path):
        assert is_sidecar_stale(tmp_path / "nonexistent.npz", 100) is True

    def test_count_mismatch_is_stale(self, tmp_path: Path):
        labels = np.zeros(5, dtype=np.uint8)
        conf = np.zeros(5, dtype=np.float16)
        med = np.zeros(2, dtype=np.uint8)
        prv = np.zeros(1, dtype=np.uint8)

        path = write_sidecar(tmp_path, labels, conf, med, prv)
        assert is_sidecar_stale(path, 5) is False
        assert is_sidecar_stale(path, 10) is True

    def test_corrupted_sidecar_is_stale(self, tmp_path: Path):
        bad = tmp_path / "semantic_labels.npz"
        bad.write_bytes(b"this is not an npz file")
        assert is_sidecar_stale(bad, 100) is True


class TestPruneOrder:
    def test_prune_order_limits(self):
        opacities = np.array([-2.0, 3.0, 0.5, -1.0, 1.0], dtype=np.float32)
        order = prune_order(opacities, keep_ratio=0.0)
        assert len(order) == 1
        assert opacities[order[0]] == 3.0  # highest

        order_full = prune_order(opacities, keep_ratio=1.0)
        assert len(order_full) == 5

    def test_prune_order_stable(self):
        opacities = np.array([0.5, 0.5, 0.5, 0.5, 0.5], dtype=np.float32)
        order = prune_order(opacities, keep_ratio=0.4)
        assert len(order) == 2
        # stable sort: indices in ascending order for equal values.
        assert order[0] == 0
        assert order[1] == 1