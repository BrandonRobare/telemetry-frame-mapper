from __future__ import annotations

import numpy as np

from scripts.benchmark_semantic_mps import _compare, _digest, _fixture_images


def test_semantic_mps_fixture_is_deterministic() -> None:
    first = _fixture_images()
    second = _fixture_images()
    assert _digest(first) == _digest(second)
    assert len(first) == 4
    assert first[0].shape == (512, 512, 3)


def test_semantic_mps_comparison_reports_exact_matches() -> None:
    labels = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    confidence = np.array([[0.9, 0.8], [0.7, 0.6]], dtype=np.float16)
    result = _compare([(labels, confidence)], [(labels.copy(), confidence.copy())])

    assert result["label_agreement"] == 1.0
    assert result["confidence_mae"] == 0.0
    assert result["cpu_label_sha256"] == result["mps_label_sha256"]
