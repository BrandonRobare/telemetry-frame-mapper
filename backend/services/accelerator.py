"""Central accelerator detection and cache management.

Torch is imported lazily so CPU-only backend startup remains supported.  The
module exposes PyTorch device strings while reporting the platform-neutral
accelerator kinds used by capability payloads: ``cuda``, ``metal``, and ``cpu``.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, Literal

AcceleratorKind = Literal["cuda", "metal", "cpu"]

_PRESET_OVERRIDES: dict[AcceleratorKind, dict[str, dict[str, int | float]]] = {
    # Revalidated on the public Aukerman survey for #820. CUDA stays empty so
    # its shipped preset values remain byte-for-byte unchanged.
    "metal": {"quick": {"iterations": 3000}},
    "cuda": {},
    "cpu": {},
}


@dataclass(frozen=True)
class Accelerator:
    """The detected platform accelerator and its PyTorch device string."""

    kind: AcceleratorKind
    device: Literal["cuda", "mps", "cpu"]


def preset_overrides(kind: AcceleratorKind, preset: str) -> dict[str, int | float]:
    """Return a copy of accelerator defaults layered beneath operator values."""
    return dict(_PRESET_OVERRIDES[kind].get(preset, {}))


def _import_torch() -> Any | None:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return None
    return torch


def _native_metal_available() -> bool:
    """Detect Apple-Silicon Metal without requiring the optional PyTorch stack."""
    return platform.system() == "Darwin" and platform.machine().lower() in {
        "arm64",
        "aarch64",
    }


def _is_available(torch: Any, kind: AcceleratorKind) -> bool:
    if kind == "cuda":
        return bool(torch.cuda.is_available())  # type: ignore[attr-defined]
    if kind == "metal":
        mps = getattr(torch.backends, "mps", None)
        return bool(mps and mps.is_available())
    return True


def _normalize_override(override: str | None) -> AcceleratorKind | None:
    if override is None:
        return None
    aliases: dict[str, AcceleratorKind] = {
        "cuda": "cuda",
        "metal": "metal",
        "mps": "metal",
        "cpu": "cpu",
    }
    try:
        return aliases[override.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported accelerator override: {override!r}") from exc


def detect(
    torch: Any | None = None,
    *,
    override: str | None = None,
    allow_metal: bool = True,
) -> Accelerator:
    """Select CUDA, then Metal when supported by the consumer, then CPU.

    An unavailable explicit CUDA or Metal preference safely falls back to CPU;
    it does not silently choose another accelerator.
    """
    requested = _normalize_override(override)
    torch = torch if torch is not None else _import_torch()
    if torch is None:
        if allow_metal and requested in (None, "metal") and _native_metal_available():
            return Accelerator("metal", "mps")
        return Accelerator("cpu", "cpu")

    if requested:
        candidates: tuple[AcceleratorKind, ...] = (requested,)
    elif allow_metal:
        candidates = ("cuda", "metal", "cpu")
    else:
        candidates = ("cuda", "cpu")
    for kind in candidates:
        if (kind != "metal" or allow_metal) and _is_available(torch, kind):
            return Accelerator(kind, "mps" if kind == "metal" else kind)
    return Accelerator("cpu", "cpu")


def device_str(
    torch: Any | None = None,
    *,
    override: str | None = None,
    allow_metal: bool = True,
) -> str:
    """Return a selected PyTorch device string for a compatible consumer."""
    return detect(torch, override=override, allow_metal=allow_metal).device


def empty_cache(torch: Any | None = None, *, allow_metal: bool = True) -> None:
    """Release cache for a compatible accelerator; CPU has no cache."""
    torch = torch if torch is not None else _import_torch()
    if torch is None:
        return
    selected = detect(torch, allow_metal=allow_metal)
    if selected.kind == "cuda":
        torch.cuda.empty_cache()  # type: ignore[attr-defined]
    elif selected.kind == "metal":
        torch.mps.empty_cache()  # type: ignore[attr-defined]


def describe(
    torch: Any | None = None,
    *,
    override: str | None = None,
) -> dict[str, str]:
    """Return the structured capability payload for the machine accelerator."""
    selected = detect(torch, override=override)
    return {"kind": selected.kind, "device": selected.device}
