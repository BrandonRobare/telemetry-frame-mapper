"""Deletes that never leave a row pointing at removed files (#945).

A delete stages its row changes, commits them, and only then removes files. A comparison
belongs to two sessions and two reconstructions, so deleting one of them must not quietly
delete the comparison too. The schema refuses that as well (the comparison FKs have no
ON DELETE action); checking first lets the API answer 409 with the blocking comparisons
before anything is cancelled, deleted or removed from disk.
"""

from __future__ import annotations

import logging
from collections.abc import Collection

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from backend.db.models import SessionComparison

logger = logging.getLogger(__name__)


class DeleteBlocked(Exception):
    """Other records still use what a delete would remove. Nothing has been touched."""

    def __init__(self, message: str, references: list[dict]) -> None:
        super().__init__(message)
        self.message = message
        self.references = references

    def response(self) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": self.message, "blocking_references": self.references},
        )


def refuse_if_compared(
    db: DBSession,
    subject: str,
    *,
    session_ids: Collection[int] = (),
    reconstruction_ids: Collection[int] = (),
) -> None:
    """Raise :class:`DeleteBlocked` if a comparison uses any of these sessions or runs."""
    comparisons = (
        db.query(SessionComparison)
        .filter(
            or_(
                SessionComparison.session_a_id.in_(session_ids),
                SessionComparison.session_b_id.in_(session_ids),
                SessionComparison.reconstruction_a_id.in_(reconstruction_ids),
                SessionComparison.reconstruction_b_id.in_(reconstruction_ids),
            )
        )
        .order_by(SessionComparison.id)
        .all()
    )
    if not comparisons:
        return
    noun = "comparison" if len(comparisons) == 1 else "comparisons"
    ids = ", ".join(str(comparison.id) for comparison in comparisons)
    raise DeleteBlocked(
        f"{subject} is used by {noun} {ids}. Delete the {noun} first "
        "(DELETE /comparisons/{id}); nothing was deleted.",
        [
            {
                "type": "comparison",
                "id": comparison.id,
                "session_a_id": comparison.session_a_id,
                "session_b_id": comparison.session_b_id,
                "reconstruction_a_id": comparison.reconstruction_a_id,
                "reconstruction_b_id": comparison.reconstruction_b_id,
            }
            for comparison in comparisons
        ],
    )


def commit_delete(db: DBSession, subject: str) -> None:
    """Commit staged deletes, before any file is removed.

    A foreign key the pre-checks did not foresee makes SQLite refuse the commit; that
    becomes a 409 with the transaction rolled back, so nothing is deleted and the
    caller never reaches its file cleanup.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.warning("The database refused to delete %s: %s", subject, exc.orig)
        raise HTTPException(
            status_code=409,
            detail=(
                f"{subject} is still referenced by other records, so nothing was deleted "
                "and no files were removed."
            ),
        ) from exc
