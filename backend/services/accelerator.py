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
    torch = torch if torch is not None else _import_torch()
    requested = _normalize_override(override)
    if torch is None:
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
