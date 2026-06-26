from __future__ import annotations

SRT_SAMPLE = (
    b"1\n"
    b"00:00:00,000 --> 00:00:01,000\n"
    b"GPS(-80.456,35.123,120) H 10.0m\n"
    b"\n"
    b"2\n"
    b"00:00:01,000 --> 00:00:02,000\n"
    b"GPS(-80.457,35.124,121) H 11.0m\n"
    b"\n"
)


def test_process_srt(client):
    resp = client.post(
        "/srt/process",
        files={"file": ("test.srt", SRT_SAMPLE, "text/plain")},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_process_srt_file_too_large(client):
    # Test with a file that's too large (we use the default limit of 10MB for flight logs)
    # Create a 15MB SRT file which is larger than the default 10MB limit
    large_data = b"a" * (15 * 1024 * 1024)  # 15 MB to exceed the limit of 10MB
    resp = client.post(
        "/srt/process",
        files={"file": ("large.srt", large_data, "text/plain")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"]
