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
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# -- ADE20K -> 6-class semantic mapping ---------------------------------------

# ADE20K has 150 classes.  Each ADE20K class id maps to one of our six
# semantic super-categories: 0=ground, 1=vegetation, 2=structure, 3=vehicle,
# 4=water, 5=other.
#
# The mapping is a 150-element uint8 LUT where ``lut[ade_id]`` gives the
# semantic category.  Every id maps to a value < 6.

_ADE20K_TO_SEMANTIC: np.ndarray = np.full(150, 5, dtype=np.uint8)  # default: other

# ground (0) — earth, roads, floors, paths, fields
for _cid in {
    3,   # floor
    9,   # grass (lawn)
    14,  # earth, ground
    23,  # sidewalk, pavement
    26,  # road
    27,  # runway
    29,  # path
    30,  # playingfield
    52,  # sand
    53,  # dirt track
    54,  # runway (alt)
    85,  # field
    91,  # hill
    96,  # land
    116,  # runway (another)
}:
    _ADE20K_TO_SEMANTIC[_cid] = 0

# vegetation (1) — trees, plants, bushes, moss
for _cid in {
    4,   # tree
    5,   # plant
    8,   # flower
    17,  # grass
    18,  # plant (other)
    21,  # palm
    22,  # bush
    66,  # moss
    73,  # straw
    84,  # trunk
    110,  # forest / vegetation
    129,  # vegetation (alt)
}:
    _ADE20K_TO_SEMANTIC[_cid] = 1

# structure (2) — buildings, walls, bridges, fences, man-made standing objects
for _cid in {
    0,   # wall
    1,   # building, edifice
    6,   # cabinet
    7,   # door
    10,  # windowpane, window
    11,  # awning
    12,  # blind, screen
    13,  # railing, banister
    15,  # ceiling
    16,  # curtain
    19,  # painting, picture
    20,  # post
    24,  # stairs
    25,  # escalator
    28,  # fence, paling
    31,  # column, pillar
    32,  # signboard, sign
    33,  # streetlight
    34,  # sconce
    35,  # canopy
    36,  # bridge, span
    37,  # booth, stall, kiosk
    40,  # stove, oven
    43,  # toilet
    44,  # towel rail, towel bar
    46,  # bathtub
    47,  # shower
    48,  # fireplace
    56,  # skyscraper
    57,  # hovel, hut, hutch, shack, shanty
    58,  # house
    65,  # arcade machine
    71,  # booth
    74,  # ruins
    77,  # tent
    81,  # net
    83,  # grate
    86,  # barn
    88,  # pier, wharf, wharfage, dock
    89,  # stage
    97,  # chimney
    99,  # fountain
    100,  # pool table, billiard table, snooker table
    101,  # stairs_moving
    103,  # shower_curtain
    105,  # teller machine, cash machine, ATM
    108,  # corridor
    111,  # stairway
    114,  # base, pedestal, stand
    118,  # skylight
    119,  # tower
    120,  # bridge_other
    126,  # aquarium
    135,  # clothes
    144,  # greenhouse, nursery
    148,  # shower_stall
}:
    _ADE20K_TO_SEMANTIC[_cid] = 2

# vehicle (3) — cars, trucks, trains, boats, planes, bikes
for _cid in {
    38,  # bus, autobus, coach
    39,  # car, auto, automobile, machine, motorcar
    41,  # truck, motortruck
    42,  # train
    45,  # boat
    49,  # airplane, aeroplane, plane
    50,  # bike, bicycle, wheel
    51,  # scooter
    69,  # ship
    70,  # van
    72,  # helicopter
    75,  # skateboard
    80,  # motorbike, motorcycle
    104,  # baby carriage, baby buggy, perambulator, pram, pushchair
    113,  # bicycle_wheel
    142,  # tricycle
}:
    _ADE20K_TO_SEMANTIC[_cid] = 3

# water (4) — water, sea, river, lake, waterfall
for _cid in {
    60,  # water
    87,  # waterfall
    128,  # lake
}:
    _ADE20K_TO_SEMANTIC[_cid] = 4

# everything else stays at 5 (other):
#   2=sky, 55=keyboard, 59=floor_mat, 61=blind, 62=coffee_table,
#   63=ottoman, 64=sofa, 67=pillow, 68=box, 76=platform,
#   78=computer, 79=towel, 82=books, 90=case, 92=pot,
#   93=glass, 94=barrel, 95=ottoman_other, 98=kitchen_island,
#   102=basket, 106=printer, 107=flag, 109=conveyor_belt,
#   112=light, 115=bench, 117=sculpture, 121=radiator,
#   122=fan, 123=ceiling_fan, 124=swivel_chair, 125=range_hood,
#   127=stool, 130=escalator_other, 131=microwave, 132=kitchen_counter,
#   133=bag, 134=trash_can, 136=sofa_bed, 137=lamp, 138=nightstand,
#   139=monitor, 140=ottoman_bench, 141=cushion, 143=shelf,
#   145=chest_of_drawers, 146=wardrobe, 147=sofa_chair, 149=armchair


def ade20k_to_semantic(pixel_labels: np.ndarray) -> np.ndarray:
    """Map per-pixel ADE20K class ids (0..149) to semantic super-categories (0..5).

    Parameters
    ----------
    pixel_labels:
        np.ndarray of uint8 (or int), any shape.  ADE20K fine-grained class ids.

    Returns
    -------
        np.ndarray of uint8, same shape as input, values in 0..5.
    """
    return _ADE20K_TO_SEMANTIC[np.asarray(pixel_labels, dtype=np.uint8)]


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
        pipeline_kwargs["torch_dtype"] = "torch.float16"

    pipe = transformers.pipeline(**pipeline_kwargs)
    _segmenter_cache[model_id] = pipe
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

    # Build label2id from the model config.
    label2id: dict[str, int] = {}
    if hasattr(segmenter.model, "config"):
        cfg = segmenter.model.config
        if hasattr(cfg, "label2id") and cfg.label2id is not None:
            label2id = cfg.label2id
        elif hasattr(cfg, "id2label") and cfg.id2label is not None:
            label2id = {v: k for k, v in cfg.id2label.items()}

    for entry in results:
        label_str: str = entry["label"]
        score: float = float(entry["score"])
        mask = np.asarray(entry["mask"], dtype=bool)

        ade_id = label2id.get(label_str)
        if ade_id is None:
            continue

        sem_id = int(_ADE20K_TO_SEMANTIC[ade_id])

        # Higher confidence wins per-pixel.
        update = mask & (score > confidence_map)
        label_map[update] = sem_id
        confidence_map[update] = score

    return label_map, confidence_map.astype(np.float16)