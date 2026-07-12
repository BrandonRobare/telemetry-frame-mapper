from __future__ import annotations

SRT_SAMPLE = (
    b"1\n"
    b"00:00:00,000 --> 00:00:01,000\n"
    b"GPS(-80.456,35.123,120) H 10.0m\n"
    b"\n"
    b"2\n"
    b"00:00:01,000 --> 00:00:02,000\n"
    b"GPS(-80.4561,35.1231,121) H 11.0m\n"
    b"\n"
)


def _frozen_srt_sample(blocks: int = 12) -> bytes:
    parts = []
    for index in range(blocks):
        parts.append(
            f"{index + 1}\n"
            f"00:00:{index:02d},000 --> 00:00:{index + 1:02d},000\n"
            "GPS(-80.456,35.123,120) H 10.0m\n\n"
        )
    return "".join(parts).encode()


def test_process_srt(client):
    resp = client.post(
        "/srt/process",
        files={"file": ("test.srt", SRT_SAMPLE, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["points"], list)
    assert len(body["points"]) == 2
    assert body["points"][0]["lat"] == 35.123
    assert body["gps_lock_warnings"] == []


def test_process_srt_warns_on_frozen_gps(client):
    resp = client.post(
        "/srt/process",
        files={"file": ("frozen.srt", _frozen_srt_sample(), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["points"]) == 12
    assert any("frozen" in warning for warning in body["gps_lock_warnings"])


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
