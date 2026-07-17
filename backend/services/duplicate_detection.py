from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from ..db.models import Image
from ..db.models import Session as SessionModel

# ponytail: tunable heuristic, not a cryptographic guarantee. Raise if real
# flights legitimately share >70% of filenames (e.g. camera resets its counter
# each battery); lower if near-miss duplicates keep sneaking through.
FILENAME_OVERLAP_THRESHOLD = 0.7


def _normalize_folder(folder_path: str) -> str:
    return os.path.normcase(os.path.normpath(str(Path(folder_path))))


def find_duplicate_matches(
    db: DBSession,
    folder_path: str | None,
    filenames: list[str] | None,
) -> list[dict]:
    """Return existing sessions that likely duplicate the given import candidate.

    Cheap lazy fingerprint only: normalized folder_path equality, and/or
    filename-overlap ratio against each session's known images. No file
    bytes are read.
    """
    matches: list[dict] = []
    incoming_names = set(filenames) if filenames else set()
    normalized_candidate = _normalize_folder(folder_path) if folder_path else None

    for s in db.query(SessionModel).all():
        if normalized_candidate and s.folder_path:
            if _normalize_folder(s.folder_path) == normalized_candidate:
                matches.append({
                    "session_id": s.id,
                    "name": s.name,
                    "reason": "same folder path",
                    "overlap": 1.0,
                })
                continue

        if not incoming_names:
            continue
        existing_names = {
            row[0] for row in db.query(Image.filename).filter(Image.session_id == s.id).all()
        }
        if not existing_names:
            continue
        overlap = len(incoming_names & existing_names) / len(incoming_names)
        if overlap >= FILENAME_OVERLAP_THRESHOLD:
            matches.append({
                "session_id": s.id,
                "name": s.name,
                "reason": f"{overlap:.0%} filename overlap",
                "overlap": round(overlap, 2),
            })

    return matches
