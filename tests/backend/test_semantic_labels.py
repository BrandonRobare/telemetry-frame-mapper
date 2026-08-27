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

    def test_missing_schema_version_is_stale(self, tmp_path: Path):
        """Pre-versioning sidecars (matching count, wrong labels) are stale."""
        p = tmp_path / "semantic_labels.npz"
        np.savez(p, meta=json.dumps({"gaussian_count": 5}))
        assert is_sidecar_stale(p, 5) is True

    def test_older_schema_version_is_stale(self, tmp_path: Path):
        p = tmp_path / "semantic_labels.npz"
        np.savez(p, meta=json.dumps({"gaussian_count": 5, "schema_version": 1}))
        assert is_sidecar_stale(p, 5) is True

    def test_current_schema_version_is_fresh(self, tmp_path: Path):
        labels = np.zeros(5, dtype=np.uint8)
        conf = np.zeros(5, dtype=np.float16)
        med = np.zeros(2, dtype=np.uint8)
        prv = np.zeros(1, dtype=np.uint8)
        path = write_sidecar(tmp_path, labels, conf, med, prv)
        assert is_sidecar_stale(path, 5) is False


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

class TestVotingCore:
    def test_project_visibility_and_vote_finalize(self):
        from backend.services.semantic_labels import (
            accumulate_votes,
            finalize_labels,
            project_to_view,
            visibility_mask,
        )

        points = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [0.0, 0.0, 4.0]])
        viewmat = np.eye(4)
        k = np.array([[10.0, 0.0, 5.0], [0.0, 10.0, 5.0], [0.0, 0.0, 1.0]])
        projected = project_to_view(points, viewmat, k)
        np.testing.assert_allclose(projected["u"], [5.0, 10.0, 5.0])
        np.testing.assert_allclose(projected["v"], [5.0, 5.0, 5.0])

        expected_depth = np.zeros((12, 12), dtype=np.float32)
        expected_depth[5, 5] = 2.0
        expected_depth[5, 10] = 2.0
        visible = visibility_mask(projected, expected_depth, tau=0.08)
        assert visible.tolist() == [True, True, False]

        seg_a = np.full((12, 12), 5, dtype=np.uint8)
        seg_a[5, 5] = 2
        seg_a[5, 10] = 1
        votes = np.zeros((3, 6), dtype=np.float32)
        accumulate_votes(votes, seg_a, projected, visible, np.array([0.0, 2.0, 0.0]))
        labels, confidence = finalize_labels(votes)
        assert labels.tolist() == [2, 1, 255]
        assert float(confidence[0]) == 1.0

    def test_three_gaussian_two_view_majority_vote(self):
        from backend.services.semantic_labels import (
            accumulate_votes,
            finalize_labels,
            project_to_view,
        )

        points = np.array([[0.0, 0.0, 2.0], [1.0, 0.0, 2.0], [2.0, 0.0, 2.0]])
        viewmat = np.eye(4)
        k = np.array([[2.0, 0.0, 2.0], [0.0, 2.0, 2.0], [0.0, 0.0, 1.0]])
        projected = project_to_view(points, viewmat, k)
        visible = np.array([True, True, True])
        votes = np.zeros((3, 6), dtype=np.float32)
        seg1 = np.full((6, 6), 5, dtype=np.uint8)
        seg2 = np.full((6, 6), 5, dtype=np.uint8)
        for seg, labels in ((seg1, [0, 1, 1]), (seg2, [0, 2, 1])):
            for idx, cls in enumerate(labels):
                seg[int(round(projected["v"][idx])), int(round(projected["u"][idx]))] = cls
        opacities = np.zeros(3, dtype=np.float32)
        accumulate_votes(votes, seg1, projected, visible, opacities)
        accumulate_votes(votes, seg2, projected, visible, opacities)
        labels, confidence = finalize_labels(votes)
        assert labels.tolist() == [0, 1, 1]
        assert float(confidence[0]) == 1.0
        assert float(confidence[1]) == 0.5

    def test_accumulate_votes_matches_reference_loop(self):
        """Vectorised accumulation must equal the per-gaussian reference loop.

        The fixture deliberately includes out-of-frame projections and
        out-of-range segmentation ids (255 = UNLABELED) — both are skipped
        rather than binned or raising IndexError.
        """
        from backend.services.semantic_labels import accumulate_votes

        rng = np.random.default_rng(634)
        n, h, w = 500, 40, 60
        projected = {
            # Deliberately overshoot the frame so out-of-bounds pixels appear.
            "u": rng.uniform(-10, w + 10, n),
            "v": rng.uniform(-10, h + 10, n),
        }
        visible = rng.random(n) < 0.8
        opacities = rng.normal(0.0, 2.0, n)
        seg = rng.integers(0, 6, size=(h, w)).astype(np.uint8)
        seg[seg == 5] = 255  # unmapped pixels the loop skipped via the range check

        def reference(votes):
            u = np.rint(projected["u"]).astype(np.int64)
            v = np.rint(projected["v"]).astype(np.int64)
            weights = 1.0 / (1.0 + np.exp(-np.asarray(opacities, dtype=np.float64)))
            valid = visible & (u >= 0) & (u < w) & (v >= 0) & (v < h)
            for idx in np.flatnonzero(valid):
                cls = int(seg[v[idx], u[idx]])
                if 0 <= cls < votes.shape[1]:
                    votes[idx, cls] += weights[idx]

        expected = np.zeros((n, 6), dtype=np.float32)
        reference(expected)
        assert expected.any(), "fixture must produce some votes"

        actual = np.zeros((n, 6), dtype=np.float32)
        accumulate_votes(actual, seg, projected, visible, opacities)
        np.testing.assert_allclose(actual, expected, rtol=1e-6)

    def test_accumulate_votes_ignores_empty_selection(self):
        from backend.services.semantic_labels import accumulate_votes

        projected = {"u": np.array([1.0, 2.0]), "v": np.array([1.0, 2.0])}
        votes = np.zeros((2, 6), dtype=np.float32)
        accumulate_votes(
            votes,
            np.zeros((4, 4), dtype=np.uint8),
            projected,
            np.array([False, False]),
            np.zeros(2),
        )
        assert not votes.any()
