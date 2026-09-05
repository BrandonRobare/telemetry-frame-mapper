"""Central accelerator detection and cache management.

Torch is imported lazily so CPU-only backend startup remains supported.  The
module exposes PyTorch device strings while reporting the platform-neutral
accelerator kinds used by capability payloads: ``cuda``, ``metal``, and ``cpu``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AcceleratorKind = Literal["cuda", "metal", "cpu"]


@dataclass(frozen=True)
class Accelerator:
    """The detected platform accelerator and its PyTorch device string."""

    kind: AcceleratorKind
    device: Literal["cuda", "mps", "cpu"]


def _import_torch() -> Any | None:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return None
    return torch


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


def detect(torch: Any | None = None, *, override: str | None = None) -> Accelerator:
    """Select CUDA, then Metal, then CPU, respecting an explicit preference.

    An unavailable explicit CUDA or Metal preference safely falls back to CPU;
    it does not silently choose another accelerator.
    """
    torch = torch if torch is not None else _import_torch()
    requested = _normalize_override(override)
    if torch is None:
        return Accelerator("cpu", "cpu")

    candidates: tuple[AcceleratorKind, ...] = (
        (requested,) if requested else ("cuda", "metal", "cpu")
    )
    for kind in candidates:
        if _is_available(torch, kind):
            return Accelerator(kind, "mps" if kind == "metal" else kind)
    return Accelerator("cpu", "cpu")


def device_str(torch: Any | None = None, *, override: str | None = None) -> str:
    """Return the selected PyTorch device string."""
    return detect(torch, override=override).device


def empty_cache(torch: Any | None = None) -> None:
    """Release cached memory for the active accelerator; CPU has no cache."""
    torch = torch if torch is not None else _import_torch()
    if torch is None:
        return
    selected = detect(torch)
    if selected.kind == "cuda":
        torch.cuda.empty_cache()  # type: ignore[attr-defined]
    elif selected.kind == "metal":
        torch.mps.empty_cache()  # type: ignore[attr-defined]


def describe(torch: Any | None = None, *, override: str | None = None) -> dict[str, str]:
    """Return the structured capability payload for the selected accelerator."""
    selected = detect(torch, override=override)
    return {"kind": selected.kind, "device": selected.device}
