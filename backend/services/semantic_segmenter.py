"""Semantic segmentation wrapper for 2D frame images.

Lazy-imports ``transformers`` and ``safetensors`` at call time so the backend
can start without them.  When they are missing the error message points the
user at ``pip install -e '.[semantic]'`` and ``docs/SETUP.md``.

Model default is ``nvidia/segformer-b0-finetuned-ade-512-512``, configurable via
``semantic.model_id`` in ``config.yaml``.  Set ``semantic.hf_home`` to relocate
the HuggingFace cache (the ``HF_HOME`` env var is set before the first lazy
import if the key is present).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# -- label-string -> 6-class semantic mapping ---------------------------------
#
# The checkpoint reports human-readable label strings (``model.config.id2label``)
# whose *numbering* is checkpoint-specific — it must never be hard-coded.  We
# map each label to one of six semantic super-categories by matching label
# *terms*, then resolve id -> category once at load time via ``id2label``.
# Category ids match ``semantic_labels.CLASS_NAMES`` order:
#   0=ground, 1=vegetation, 2=structure, 3=vehicle, 4=water, 5=other.

SEMANTIC_OTHER = 5

_CATEGORY_TERMS: dict[int, tuple[str, ...]] = {
    0: ("road", "sidewalk", "earth", "ground", "path", "floor",
        "sand", "field", "dirt track", "runway"),
    1: ("tree", "grass", "plant", "palm", "flower", "bush"),
    2: ("building", "house", "wall", "fence", "bridge", "skyscraper",
        "hovel", "tower", "awning"),
    3: ("car", "truck", "bus", "van", "boat", "ship", "airplane",
        "bicycle", "motorbike"),
    4: ("water", "sea", "lake", "river", "pool", "waterfall"),
}

_TERM_TO_CATEGORY: dict[str, int] = {
    term: cat for cat, terms in _CATEGORY_TERMS.items() for term in terms
}


def _label_to_category(label: str) -> int:
    """Map one label string to a semantic category (0..5).

    ADE20K labels are often multi-term (``"tree;wood"``, ``"car, auto, machine"``).
    The label is lower-cased and split on ``;``/``,``; the first term matching a
    known category wins.  Unmatched labels (including ``sky``) map to ``other``.
    """
    for raw in re.split(r"[;,]", label.lower()):
        term = raw.strip()
        if term in _TERM_TO_CATEGORY:
            return _TERM_TO_CATEGORY[term]
    return SEMANTIC_OTHER


def build_id_to_category(id2label: dict[int, str] | None) -> np.ndarray:
    """Build a class-id -> semantic-category LUT from a model's ``id2label``.

    Returns a uint8 array where ``lut[class_id]`` is the semantic category
    (0..5), sized to ``max(id) + 1`` so any predicted id indexes safely.  An
    empty or missing map yields a single-element ``other`` LUT.
    """
    if not id2label:
        return np.full(1, SEMANTIC_OTHER, dtype=np.uint8)
    size = max(int(i) for i in id2label) + 1
    lut = np.full(size, SEMANTIC_OTHER, dtype=np.uint8)
    for cid, label in id2label.items():
        lut[int(cid)] = _label_to_category(str(label))
    return lut


def _pipe_id2label(segmenter: Any) -> dict[int, str]:
    """Best-effort extraction of a segmenter's ``id2label`` map."""
    config = getattr(getattr(segmenter, "model", None), "config", None)
    id2label = getattr(config, "id2label", None)
    return dict(id2label) if id2label else {}


# -- lazy dependency import ---------------------------------------------------

_segmentation_deps: Any = None  # tuple of (transformers, safetensors) or None


def _import_segmentation_deps():
    """Lazily import transformers + safetensors, raising a helpful error on failure."""
    global _segmentation_deps
    if _segmentation_deps is not None:
        return _segmentation_deps

    try:
        import safetensors  # noqa: F401
        import transformers  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Semantic segmentation dependencies (transformers + safetensors) are not "
            "installed — run `pip install -e '.[semantic]'` and see docs/SETUP.md for "
            "the GPU setup. Segmentation will be skipped."
        ) from exc

    _segmentation_deps = (transformers, safetensors)
    return _segmentation_deps


# -- segmenter loader + inference ---------------------------------------------

_segmenter_cache: dict[str, Any] = {}
_id_to_category_cache: dict[str, np.ndarray] = {}


def load_segmenter(
    model_id: str = "nvidia/segformer-b0-finetuned-ade-512-512",
    hf_home: str | None = None,
    device: str = "cuda",
) -> Any:
    """Load (or return cached) the SegFormer semantic segmentation pipeline.

    Parameters
    ----------
    model_id:
        HuggingFace model id.  Defaults to the NVIDIA SegFormer B0 checkpoint
        fine-tuned on ADE20K at 512x512.
    hf_home:
        If set, the ``HF_HOME`` environment variable is set before the first
        import of ``transformers`` so the cache lands in the desired location.
    device:
        PyTorch device string.  ``"cuda"`` for fp16 GPU inference, ``"cpu"``
        for fallback.

    Returns
    -------
        A HuggingFace ``transformers.pipeline`` for image segmentation.
    """
    if model_id in _segmenter_cache:
        return _segmenter_cache[model_id]

    if hf_home is not None:
        os.environ.setdefault("HF_HOME", hf_home)

    transformers, _safetensors = _import_segmentation_deps()

    if device == "cuda":
        try:
            import torch

            if not torch.cuda.is_available():
                logger.warning("CUDA requested but not available; falling back to CPU")
                device = "cpu"
        except Exception:
            device = "cpu"

    pipeline_kwargs: dict[str, Any] = {
        "task": "image-segmentation",
        "model": model_id,
        "device": device if device == "cpu" else 0,
    }

    if device == "cuda":
        # transformers resolves string dtypes via ``getattr(torch, s)`` — must be
        # the bare attribute name, not ``"torch.float16"`` (which raises).
        pipeline_kwargs["torch_dtype"] = "float16"

    pipe = transformers.pipeline(**pipeline_kwargs)
    _segmenter_cache[model_id] = pipe
    # Resolve id -> semantic category once, keyed to *this* checkpoint's ids.
    _id_to_category_cache[model_id] = build_id_to_category(_pipe_id2label(pipe))
    return pipe


def segment_frame(
    image: np.ndarray,
    segmenter: Any | None = None,
    model_id: str = "nvidia/segformer-b0-finetuned-ade-512-512",
    hf_home: str | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Run semantic segmentation on a single RGB frame.

    Parameters
    ----------
    image:
        (H, W, 3) uint8 RGB numpy array.
    segmenter:
        Pre-loaded pipeline from ``load_segmenter``.  If ``None``, one is
        loaded on first call.
    model_id:
        Model id (passed to ``load_segmenter`` if *segmenter* is ``None``).
    hf_home:
        HF cache home (passed to ``load_segmenter`` if *segmenter* is ``None``).

    Returns
    -------
        labels: (H, W) uint8 semantic super-category ids (0..5).
        confidence: (H, W) float16 confidence scores.
    """
    if segmenter is None:
        segmenter = load_segmenter(model_id, hf_home=hf_home)

    from PIL import Image

    pil_image = Image.fromarray(image)
    results = segmenter(pil_image)

    h, w = image.shape[:2]
    label_map = np.full((h, w), 5, dtype=np.uint8)  # default: other
    confidence_map = np.zeros((h, w), dtype=np.float32)

    # Resolve id -> semantic category for this checkpoint (cached at load time;
    # rebuilt here if a segmenter was passed in without going through the cache).
    id_to_category = _id_to_category_cache.get(model_id)
    if id_to_category is None:
        id_to_category = build_id_to_category(_pipe_id2label(segmenter))
    label2id = {label: cid for cid, label in _pipe_id2label(segmenter).items()}

    for entry in results:
        label_str: str = entry["label"]
        score: float = float(entry["score"])
        mask = np.asarray(entry["mask"], dtype=bool)

        ade_id = label2id.get(label_str)
        if ade_id is None or ade_id >= len(id_to_category):
            continue

        sem_id = int(id_to_category[ade_id])

        # Higher confidence wins per-pixel.
        update = mask & (score > confidence_map)
        label_map[update] = sem_id
        confidence_map[update] = score

    return label_map, confidence_map.astype(np.float16)