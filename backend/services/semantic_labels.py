"""Atomic NPZ sidecar for semantic segmentation labels on a Gaussian splat.

Sidecar file layout
-------------------
One ``semantic_labels.npz`` per splat in the splat's ``exports`` sub-directory:

    exports/{splat_id}/semantic_labels.npz

Arrays (all keyed by name inside the archive):

    labels           uint8   [N]   per-gaussian semantic class (0..5)
    confidence       float16 [N]   per-gaussian confidence score
    labels_medium    uint8   [M]   LOD-medium subset (top ``lod_medium_ratio``)
    labels_preview   uint8   [P]   LOD-preview subset (top ``lod_preview_ratio``)
    class_names      str     [C]   human-readable class labels
    meta             JSON str      one JSON blob with gaussian_count, class counts, etc.

Atomic write: data is written to a ``.tmp`` file and then ``os.replace``-ed to
the final path so readers never see a partially-written file.

Staleness detection: the ``gaussian_count`` recorded in the ``meta`` JSON is
compared against the number of vertices in the associated ``splat.ply``. A
mismatch signals the sidecar needs recomputation.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np

from backend.services.ply_io import prune_order

# -- public helpers -----------------------------------------------------------

CLASS_NAMES = (
    "ground",
    "vegetation",
    "structure",
    "vehicle",
    "water",
    "other",
)

NUM_CLASSES = len(CLASS_NAMES)


def lod_labels(
    labels: np.ndarray,
    opacities: np.ndarray,
    keep_ratio: float,
) -> np.ndarray:
    """Return *labels* sorted by ``prune_order(opacities, keep_ratio)``.

    This guarantees that for any given ``keep_ratio`` the subset returned here
    is index-aligned with a ``GaussianCloud`` pruned by
    ``prune_by_opacity(..., keep_ratio)`` — the same *order* array drives both.
    """
    order = prune_order(opacities, keep_ratio)
    return labels[order]


def is_sidecar_stale(sidecar_path: Path, gaussian_count: int) -> bool:
    """Return ``True`` when the sidecar was computed for a different point count."""
    if not sidecar_path.exists():
        return True
    try:
        with np.load(sidecar_path) as data:
            meta = json.loads(str(data["meta"]))
    except Exception:
        return True
    return meta.get("gaussian_count", -1) != gaussian_count


# -- atomic NPZ write / read --------------------------------------------------

def _atomic_replace_tmp(src: Path, dst: Path) -> None:
    """Move *src* to *dst* with a fallback for cross-device rename."""

    try:
        os.replace(src, dst)
    except OSError:
        # Cross-device (e.g. /tmp → exports/) — copy + unlink.
        import shutil

        shutil.copy2(src, dst)
        src.unlink(missing_ok=True)


def write_sidecar(
    out_dir: Path,
    labels: np.ndarray,
    confidence: np.ndarray,
    labels_medium: np.ndarray,
    labels_preview: np.ndarray,
    class_names: list[str] | None = None,
    extra_meta: dict | None = None,
) -> Path:
    """Atomically write a ``semantic_labels.npz`` sidecar into *out_dir*.

    Parameters
    ----------
    out_dir:
        The exports directory for one splat (``exports/{splat_id}``).
    labels:
        uint8 [N] per-gaussian class ids.
    confidence:
        float16 [N] per-gaussian confidence.
    labels_medium:
        uint8 [M] LOD-medium subset.
    labels_preview:
        uint8 [P] LOD-preview subset.
    class_names:
        Optional human-readable class names (default: the built-in 6-class list).
    extra_meta:
        Optional dict merged into the ``meta`` JSON blob.
    """
    if class_names is None:
        class_names = list(CLASS_NAMES)

    n = int(labels.shape[0])
    counts = [int(np.count_nonzero(labels == c)) for c in range(NUM_CLASSES)]
    meta: dict = {
        "gaussian_count": n,
        "class_counts": {name: cnt for name, cnt in zip(CLASS_NAMES, counts, strict=False)},
        "num_classes": NUM_CLASSES,
        "lod_medium_count": int(labels_medium.shape[0]),
        "lod_preview_count": int(labels_preview.shape[0]),
    }
    if extra_meta:
        meta.update(extra_meta)

    dest = out_dir / "semantic_labels.npz"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write to a temp file next to the destination so rename stays on-device.
    with tempfile.NamedTemporaryFile(
        dir=out_dir,
        prefix=".semantic_labels_",
        suffix=".npz.tmp",
        delete=False,
    ) as tmp:
        np.savez_compressed(
            tmp,
            labels=np.asarray(labels, dtype=np.uint8),
            confidence=np.asarray(confidence, dtype=np.float16),
            labels_medium=np.asarray(labels_medium, dtype=np.uint8),
            labels_preview=np.asarray(labels_preview, dtype=np.uint8),
            class_names=np.array(class_names, dtype=str),
            meta=json.dumps(meta),
        )
        tmp_path = Path(tmp.name)

    _atomic_replace_tmp(tmp_path, dest)
    return dest


def read_sidecar(sidecar_path: Path) -> dict[str, np.ndarray | str]:
    """Read a ``semantic_labels.npz`` sidecar into a plain dict.

    Returns
    -------
    dict with keys:
        labels       (uint8 [N]),
        confidence   (float16 [N]),
        labels_medium (uint8 [M]),
        labels_preview (uint8 [P]),
        class_names  (list of str),
        meta         (str — JSON blob).
    """
    with np.load(sidecar_path, allow_pickle=False) as data:
        return {
            "labels": data["labels"],
            "confidence": data["confidence"],
            "labels_medium": data["labels_medium"],
            "labels_preview": data["labels_preview"],
            "class_names": list(data["class_names"]),
            "meta": str(data["meta"]),
        }