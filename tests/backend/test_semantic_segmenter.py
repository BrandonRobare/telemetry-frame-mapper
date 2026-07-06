from __future__ import annotations

import numpy as np
import pytest

from backend.services.semantic_segmenter import ade20k_to_semantic


def test_lut_covers_all_150_ids():
    """Every ADE20K id 0..149 maps to a value < 6."""
    pixel_labels = np.arange(150, dtype=np.uint8)
    result = ade20k_to_semantic(pixel_labels)

    assert result.shape == (150,)
    assert result.dtype == np.uint8
    assert int(result.min()) >= 0
    assert int(result.max()) < 6


def test_lut_known_semantic_ids():
    """Spot-check that key ADE20K ids map to the expected semantic classes."""
    # ground
    assert ade20k_to_semantic(np.array([3], dtype=np.uint8))[0] == 0   # floor
    assert ade20k_to_semantic(np.array([26], dtype=np.uint8))[0] == 0  # road
    # vegetation
    assert ade20k_to_semantic(np.array([4], dtype=np.uint8))[0] == 1   # tree
    # structure
    assert ade20k_to_semantic(np.array([1], dtype=np.uint8))[0] == 2   # building
    # vehicle
    assert ade20k_to_semantic(np.array([39], dtype=np.uint8))[0] == 3  # car
    # water
    assert ade20k_to_semantic(np.array([60], dtype=np.uint8))[0] == 4  # water
    # other
    assert ade20k_to_semantic(np.array([2], dtype=np.uint8))[0] == 5   # sky


def test_segmenter_lazy_import_error():
    """_import_segmentation_deps raises RuntimeError when deps are missing."""
    import importlib

    # Simulate missing deps by temporarily setting the internal cache to None
    # and patching importlib to fail for transformers/safetensors.
    import backend.services.semantic_segmenter as seg
    from backend.services.semantic_segmenter import _import_segmentation_deps

    save = seg._segmentation_deps
    seg._segmentation_deps = None

    try:
        # Force re-import by clearing the cache
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                importlib,
                "import_module",
                lambda name: __import__("nonexistent_module_not_found"),
            )
            with pytest.raises(RuntimeError, match="semantic"):
                _import_segmentation_deps()
    finally:
        seg._segmentation_deps = save