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


def test_process_srt_rejects_oversized_file(client, monkeypatch):
    import backend.routers.srt as srt_mod

    monkeypatch.setattr(
        srt_mod,
        "get_upload_limits_config",
        lambda: {"srt_max_bytes": len(SRT_SAMPLE) - 1},
    )

    resp = client.post(
        "/srt/process",
        files={"file": ("test.srt", SRT_SAMPLE, "text/plain")},
    )

    assert resp.status_code == 413
    assert "SRT upload exceeds" in resp.json()["detail"]
