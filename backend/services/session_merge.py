from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from backend.core.config import get_config
from backend.db.models import Image, SessionFrameSelection
from backend.db.models import Session as SessionModel

logger = logging.getLogger(__name__)


class SessionMergeError(ValueError):
    """Raised when session merge validation fails."""


def validate_sessions_for_merge(
    session_ids: list[int],
    db: DBSession,
) -> None:
    """Validate that all sessions exist, have usable images, and cover
    overlapping or compatible geography."""
    if len(session_ids) < 2:
        raise SessionMergeError("At least two session IDs are required for a merge.")

    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.id.in_(session_ids))
        .all()
    )
    found_ids = {s.id for s in sessions}
    missing = set(session_ids) - found_ids
    if missing:
        raise SessionMergeError(
            f"Sessions not found: {sorted(missing)}"
        )

    # Each session must have at least one usable image
    for session in sessions:
        # Check manual frame selection first
        selected = (
            db.query(SessionFrameSelection)
            .filter(SessionFrameSelection.session_id == session.id)
            .first()
        )
        usable_count = 0
        if selected:
            usable_count = (
                db.query(Image)
                .filter(
                    Image.session_id == session.id,
                    Image.usable == True,  # noqa: E712
                    Image.id.in_(
                        db.query(SessionFrameSelection.image_id).filter(
                            SessionFrameSelection.session_id == session.id
                        )
                    ),
                )
                .count()
            )
        else:
            usable_count = (
                db.query(Image)
                .filter(
                    Image.session_id == session.id,
                    Image.usable == True,  # noqa: E712
                )
                .count()
            )
        if usable_count == 0:
            raise SessionMergeError(
                f"Session {session.id} ('{session.name}') has no usable images."
            )

    # Check for geographic overlap: at least one pair of sessions must
    # have images within 500m of each other
    session_centers: dict[int, tuple[float, float]] = {}
    for sid in session_ids:
        center = (
            db.query(
                Image.latitude, Image.longitude
            )
            .filter(
                Image.session_id == sid,
                Image.usable == True,  # noqa: E712
                Image.latitude.isnot(None),
                Image.longitude.isnot(None),
            )
            .order_by(Image.id)
            .first()
        )
        if center and center[0] is not None and center[1] is not None:
            session_centers[sid] = (center[0], center[1])

    if len(session_centers) < 2:
        raise SessionMergeError(
            "At least two sessions must have GPS-tagged images to verify "
            "geographic compatibility."
        )

    # Check pairwise distances
    sids = list(session_centers.keys())
    min_distance_m = float("inf")
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            lat1, lon1 = session_centers[sids[i]]
            lat2, lon2 = session_centers[sids[j]]
            # Approximate distance in meters using equirectangular
            import math
            dlat = (lat2 - lat1) * 111320.0
            dlon = (lon2 - lon1) * 111320.0 * math.cos(
                math.radians((lat1 + lat2) / 2)
            )
            dist = math.sqrt(dlat * dlat + dlon * dlon)
            min_distance_m = min(min_distance_m, dist)

    MAX_OVERLAP_DISTANCE_M = 10_000.0  # 10 km — generous for site-scale work
    if min_distance_m > MAX_OVERLAP_DISTANCE_M:
        raise SessionMergeError(
            f"No geographic overlap between sessions. "
            f"Minimum pairwise distance is {min_distance_m:.0f}m, "
            f"which exceeds the {MAX_OVERLAP_DISTANCE_M:.0f}m threshold."
        )

    logger.info(
        "Session merge validated: %d sessions, min pairwise distance %.0fm",
        len(session_ids),
        min_distance_m,
    )


def merge_session_workspace(
    session_ids: list[int],
    db: DBSession,
) -> tuple[list[Image], Path]:
    """Build a deterministic merged COLMAP workspace.

    Returns:
        (merged_images, colmap_dir): the combined image list and the
        colmap workspace directory path.
    """
    merged_images: list[Image] = []
    for session_id in session_ids:
        images = (
            db.query(Image)
            .filter(
                Image.session_id == session_id,
                Image.usable == True,  # noqa: E712
            )
            .order_by(Image.filename)
            .all()
        )

        # Apply frame selection filter if set
        selected = (
            db.query(SessionFrameSelection)
            .filter(SessionFrameSelection.session_id == session_id)
            .first()
        )
        if selected:
            selected_ids = {
                row.image_id
                for row in db.query(SessionFrameSelection)
                .filter(SessionFrameSelection.session_id == session_id)
                .all()
            }
            images = [img for img in images if img.id in selected_ids]

        merged_images.extend(images)

    if not merged_images:
        raise SessionMergeError(
            "No usable images found across the selected sessions."
        )

    cfg = get_config()
    # Deterministic workspace ID: sorted session IDs
    workspace_id = "_".join(str(sid) for sid in sorted(session_ids))
    colmap_dir = Path(cfg.data_dir) / "colmap" / f"merged_{workspace_id}"

    # Write merge manifest for auditability
    manifest_path = Path(cfg.data_dir) / "colmap" / f"merged_{workspace_id}_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "source_session_ids": sorted(session_ids),
        "image_count": len(merged_images),
        "images": [
            {
                "image_id": img.id,
                "session_id": img.session_id,
                "filename": img.filename,
                "filepath": img.filepath,
            }
            for img in merged_images
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    logger.info(
        "Merged workspace manifest written to %s (%d images from %d sessions)",
        manifest_path,
        len(merged_images),
        len(session_ids),
    )

    return merged_images, colmap_dir