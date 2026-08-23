from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.services.upload_reader import read_upload_with_limit


class RecordingUpload:
    def __init__(self, content: bytes):
        self.content = content
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self.content if size < 0 else self.content[:size]


@pytest.mark.asyncio
async def test_read_upload_with_limit_requests_only_limit_plus_one_byte():
    upload = RecordingUpload(b"abcd")

    content = await read_upload_with_limit(upload, max_bytes=4, too_large_detail="Too large")

    assert content == b"abcd"
    assert upload.read_sizes == [5]


@pytest.mark.asyncio
async def test_read_upload_with_limit_rejects_content_over_limit():
    upload = RecordingUpload(b"abcde")

    with pytest.raises(HTTPException, match="Too large") as exc_info:
        await read_upload_with_limit(upload, max_bytes=3, too_large_detail="Too large")

    assert exc_info.value.status_code == 413
    assert upload.read_sizes == [4]
