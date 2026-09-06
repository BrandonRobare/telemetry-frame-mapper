from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services.semantic_segmenter import build_id_to_category

# A SceneParse150-style id2label slice — ids match the real checkpoint numbering
# (road=6, sidewalk=11, earth=13, car=20, water=21, sea=26) that the old
# hand-maintained id LUT got wrong.
_STUB_ID2LABEL = {
    0: "wall",
    2: "sky",
    4: "tree",
    6: "road, route",
    11: "sidewalk, pavement",
    13: "earth, ground",
    20: "car, auto, automobile, machine, motorcar",
    21: "water",
    26: "sea",
    39: "grandstand, covered stand",
}


def _torch(*, cuda: bool = False, metal: bool = False):
    return SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: cuda),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: metal)),
    )


def test_build_id_to_category_dominant_aerial_classes():
    """The ids the old LUT mislabelled now resolve correctly."""
    lut = build_id_to_category(_STUB_ID2LABEL)
    assert lut[6] == 0    # road -> ground (was structure)
    assert lut[11] == 0   # sidewalk -> ground (was structure)
    assert lut[13] == 0   # earth -> ground (was other)
    assert lut[20] == 3   # car -> vehicle (was structure)
    assert lut[21] == 4   # water -> water (was vegetation)
    assert lut[26] == 4   # sea -> water (was ground)


def test_build_id_to_category_low_ids_and_sky():
    lut = build_id_to_category(_STUB_ID2LABEL)
    assert lut[0] == 2   # wall -> structure
    assert lut[4] == 1   # tree -> vegetation
    assert lut[2] == 5   # sky -> other
    assert lut[39] == 5  # unknown label -> other


def test_build_id_to_category_multiterm_labels():
    """Multi-term labels ("tree;wood") match on the first known term."""
    lut = build_id_to_category({0: "tree;wood", 1: "grass;lawn", 2: "nonsense;thing"})
    assert lut[0] == 1   # tree
    assert lut[1] == 1   # grass
    assert lut[2] == 5   # nothing matches -> other


def test_build_id_to_category_empty():
    assert build_id_to_category({}).tolist() == [5]


def test_load_segmenter_cuda_uses_float16(monkeypatch):
    """The cuda path passes a resolvable string dtype (``"float16"``)."""
    import backend.services.semantic_segmenter as seg

    captured: dict = {}

    class FakeConfig:
        id2label = {0: "wall", 6: "road, route", 20: "car, auto"}

    class FakeModel:
        config = FakeConfig()

    class FakePipe:
        model = FakeModel()

    class FakeTransformers:
        @staticmethod
        def pipeline(**kwargs):
            captured.update(kwargs)
            return FakePipe()

    monkeypatch.setattr(seg, "_segmentation_deps", (FakeTransformers(), object()))
    seg._segmenter_cache.clear()
    seg._id_to_category_cache.clear()

    monkeypatch.setattr(seg.accelerator, "_import_torch", lambda: _torch(cuda=True))

    seg.load_segmenter(model_id="fake-model", device="cuda")

    assert captured["torch_dtype"] == "float16"
    assert captured["device"] == 0
    # id -> category resolved and cached against the checkpoint's ids.
    assert seg._id_to_category_cache["fake-model"][6] == 0   # road -> ground
    assert seg._id_to_category_cache["fake-model"][20] == 3  # car -> vehicle


def test_load_segmenter_defaults_to_cpu_on_metal_only_torch(monkeypatch):
    """MPS remains opt-in until its benchmark establishes a dtype policy."""
    import backend.services.semantic_segmenter as seg

    captured: dict = {}

    class FakeConfig:
        id2label = {0: "wall"}

    class FakeModel:
        config = FakeConfig()

    class FakePipe:
        model = FakeModel()

    class FakeTransformers:
        @staticmethod
        def pipeline(**kwargs):
            captured.update(kwargs)
            return FakePipe()

    monkeypatch.setattr(seg, "_segmentation_deps", (FakeTransformers(), object()))
    monkeypatch.setattr(seg.accelerator, "_import_torch", lambda: _torch(metal=True))
    seg._segmenter_cache.clear()
    seg._id_to_category_cache.clear()

    seg.load_segmenter(model_id="fake-metal-model")

    assert captured["device"] == "cpu"
    assert "torch_dtype" not in captured


@pytest.mark.parametrize(
    ("device", "expected_device"),
    [("cpu", "cpu"), ("mps", "mps")],
)
def test_load_segmenter_honors_explicit_device_on_metal_only_torch(
    monkeypatch, device, expected_device
):
    """CPU stays explicit and MPS remains an opt-in seam on Metal-only hosts."""
    import backend.services.semantic_segmenter as seg

    captured: dict = {}

    class FakeConfig:
        id2label = {0: "wall"}

    class FakeModel:
        config = FakeConfig()

    class FakePipe:
        model = FakeModel()

    class FakeTransformers:
        @staticmethod
        def pipeline(**kwargs):
            captured.update(kwargs)
            return FakePipe()

    monkeypatch.setattr(seg, "_segmentation_deps", (FakeTransformers(), object()))
    monkeypatch.setattr(seg.accelerator, "_import_torch", lambda: _torch(metal=True))
    seg._segmenter_cache.clear()
    seg._id_to_category_cache.clear()

    seg.load_segmenter(model_id=f"fake-{device}-model", device=device)

    assert captured["device"] == expected_device
    assert "torch_dtype" not in captured


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