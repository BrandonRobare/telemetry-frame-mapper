from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.services import accelerator


def _torch(*, cuda: bool = False, metal: bool = False):
    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: cuda,
            empty_cache=lambda: None,
        ),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: metal)),
        mps=SimpleNamespace(empty_cache=lambda: None),
    )


@pytest.mark.parametrize(
    ("torch", "kind", "device"),
    [
        (_torch(cuda=True), "cuda", "cuda"),
        (_torch(metal=True), "metal", "mps"),
        (_torch(), "cpu", "cpu"),
    ],
)
def test_detect_selects_available_accelerator(torch, kind, device):
    selected = accelerator.detect(torch)

    assert selected.kind == kind
    assert selected.device == device
    assert accelerator.device_str(torch) == device
    assert accelerator.describe(torch) == {"kind": kind, "device": device}


def test_detect_honors_explicit_device_preference_when_available():
    torch = _torch(cuda=True, metal=True)

    assert accelerator.detect(torch, override="metal").kind == "metal"
    assert accelerator.detect(torch, override="mps").device == "mps"


def test_detect_falls_back_to_cpu_when_explicit_device_is_unavailable():
    assert accelerator.detect(_torch(metal=True), override="cuda").device == "cpu"


def test_detect_rejects_unknown_explicit_device():
    with pytest.raises(ValueError, match="Unsupported accelerator override"):
        accelerator.detect(_torch(), override="opencl")


def test_empty_cache_dispatches_to_selected_backend():
    calls: list[str] = []
    torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: False,
            empty_cache=lambda: calls.append("cuda"),
        ),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)),
        mps=SimpleNamespace(empty_cache=lambda: calls.append("metal")),
    )

    accelerator.empty_cache(torch)

    assert calls == ["metal"]


def test_empty_cache_is_a_noop_on_cpu():
    calls: list[str] = []
    torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: False,
            empty_cache=lambda: calls.append("cuda"),
        ),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
        mps=SimpleNamespace(empty_cache=lambda: calls.append("metal")),
    )

    accelerator.empty_cache(torch)

    assert calls == []
