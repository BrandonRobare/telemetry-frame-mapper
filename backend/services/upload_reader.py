from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException


class UploadReader(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


async def read_upload_with_limit(
    file: UploadReader,
    max_bytes: int,
    *,
    too_large_detail: str,
) -> bytes:
    """Read one upload with a strict in-memory size bound.

    Requesting one byte beyond the limit detects oversize input without allocating
    the entire upload in this application layer.
    """
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail=too_large_detail)
    return content
