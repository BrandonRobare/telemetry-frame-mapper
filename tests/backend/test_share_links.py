"""Tests for the share links service and public viewer router."""

import time

import pytest

from backend.services.share_links import (
    SHARE_LINK_PREFIX,
    ShareToken,
    build_public_viewer_payload,
    create_share_token,
    parse_share_token,
)


class TestShareTokenCreateAndParse:
    def test_roundtrip(self):
        token = create_share_token(42, session_id=7)
        assert token.startswith("")
        parsed = parse_share_token(token)
        assert parsed.reconstruction_id == 42
        assert parsed.session_id == 7
        assert not parsed.expired
        assert parsed.expires_at > time.time()
        assert parsed.expires_at <= time.time() + 7 * 24 * 3600 + 5

    def test_custom_expiry(self):
        token = create_share_token(1, expiry_s=60)
        parsed = parse_share_token(token)
        assert parsed.reconstruction_id == 1
        assert parsed.expires_at <= time.time() + 60 + 5

    def test_expired_token(self):
        token = create_share_token(1, expiry_s=-1)
        time.sleep(0.05)  # ensure we're past expiry
        with pytest.raises(ValueError, match="expired"):
            parse_share_token(token)

    def test_invalid_signature(self):
        token = create_share_token(1)
        # Tamper with the last byte
        prefix, sig = token.rsplit(".", 1)
        tampered = prefix + "." + sig[:-1] + ("1" if sig[-1] != "1" else "0")
        with pytest.raises(ValueError, match="signature"):
            parse_share_token(tampered)

    def test_malformed_token(self):
        with pytest.raises(ValueError, match="Malformed"):
            parse_share_token("not_a_valid_token")

    def test_empty_token(self):
        with pytest.raises(ValueError, match="Malformed"):
            parse_share_token("")

    def test_token_uniqueness(self):
        t1 = create_share_token(1)
        # Force different issued-at by sleeping past the second boundary,
        # or by using different reconstruction IDs.
        t2 = create_share_token(2)
        assert t1 != t2, "Different reconstruction IDs should produce different tokens"

    def test_share_token_dataclass(self):
        st = ShareToken(reconstruction_id=1, session_id=None, issued_at=0.0, expires_at=1.0)
        assert st.reconstruction_id == 1
        assert st.expired  # 1.0 is in the past


class TestTokenWithPrefix:
    def test_parse_with_prefix(self):
        raw = create_share_token(5)
        token_with_prefix = SHARE_LINK_PREFIX + raw
        # parse_share_token expects no prefix — router strips it
        parsed = parse_share_token(token_with_prefix[len(SHARE_LINK_PREFIX):])
        assert parsed.reconstruction_id == 5


class TestPublicViewerPayload:
    class FakeReconstruction:
        def __init__(self):
            self.id = 10
            self.session_id = 20
            self.status = "complete"
            self.frames_used = 100
            self.frames_registered = 90
            self.gaussian_count = 50000
            self.psnr = 32.5
            self.ssim = 0.95
            self.mesh_glb_path = "/path/to/mesh.glb"
            self.mesh_obj_path = None

    def test_build_payload(self):
        rec = self.FakeReconstruction()
        payload = build_public_viewer_payload(rec)
        assert payload["reconstruction_id"] == 10
        assert payload["session_id"] == 20
        assert payload["artifacts"]["mesh_glb"] == "/share/10/mesh?format=glb"
        assert payload["artifacts"]["mesh_obj"] is None
        assert payload["artifacts"]["pointcloud"] == "/share/10/pointcloud"
        assert "generated_at" in payload


class TestShareLinkCreateEndpoint:
    """Integration tests against the FastAPI test client."""

    def test_create_share_link_complete(self, client):
        # Setup: create a session with a completed reconstruction
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="ShareTest", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id,
            status="complete",
            frames_used=10,
            mesh_glb_path="/tmp/test.glb",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        # Create share link
        resp = client.post(f"/export/reconstructions/{rec.id}/share-link")
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "share_token" in body
        assert body["reconstruction_id"] == rec.id
        assert body["session_id"] == session.id
        assert body["share_token"].startswith(SHARE_LINK_PREFIX)

    def test_create_share_link_not_found(self, client):
        resp = client.post("/export/reconstructions/99999/share-link")
        assert resp.status_code == 404

    def test_create_share_link_not_complete(self, client):
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="PendingTest", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id, status="pending", frames_used=0
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        resp = client.post(f"/export/reconstructions/{rec.id}/share-link")
        assert resp.status_code == 422


class TestPublicViewerEndpoint:
    def test_viewer_metadata_valid(self, client):
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="ViewTest", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id,
            status="complete",
            frames_used=5,
            frames_registered=5,
            gaussian_count=1000,
            psnr=30.0,
            ssim=0.9,
            mesh_glb_path="/tmp/glb",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        token = create_share_token(rec.id, rec.session_id)
        resp = client.get(f"/share/token/{SHARE_LINK_PREFIX}{token}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["reconstruction_id"] == rec.id
        assert body["session_id"] == rec.session_id
        assert body["frames_used"] == 5

    def test_viewer_invalid_token(self, client):
        resp = client.get("/share/token/bad_token")
        assert resp.status_code == 403

    def test_viewer_not_complete(self, client):
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="NotReady", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id, status="failed", frames_used=0
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        token = create_share_token(rec.id, rec.session_id)
        resp = client.get(f"/share/token/{SHARE_LINK_PREFIX}{token}")
        assert resp.status_code == 410

    def test_viewer_reconstruction_not_found(self, client):
        token = create_share_token(99999)
        resp = client.get(f"/share/token/{SHARE_LINK_PREFIX}{token}")
        assert resp.status_code == 404


class TestPublicDownloadEndpoints:
    def test_pointcloud_download_token_required(self, client):
        resp = client.get("/share/1/pointcloud?token=bad_token")
        assert resp.status_code == 403

    def test_splat_download_token_required(self, client):
        resp = client.get("/share/1/splat?token=bad_token")
        assert resp.status_code == 403

    def test_mesh_download_token_required(self, client):
        resp = client.get("/share/1/mesh?token=bad_token")
        assert resp.status_code == 403

    def test_pointcloud_token_mismatch(self, client):
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="Mismatch", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id, status="complete", frames_used=1
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        # Token for reconstruction 1, request reconstruction 2
        token = create_share_token(rec.id)
        resp = client.get(f"/share/{rec.id + 1}/pointcloud?token={SHARE_LINK_PREFIX}{token}")
        assert resp.status_code == 403


class TestSecurityConstraints:
    """Verify no path traversal or arbitrary file exposure."""

    def test_token_no_filesystem_paths(self, client):
        """The public viewer payload must not expose filesystem paths."""
        from backend.db.models import Reconstruction
        from backend.db.models import Session as SessionModel

        db = _db(client)
        session = SessionModel(name="SecTest", folder_path="/tmp")
        db.add(session)
        db.commit()
        db.refresh(session)
        rec = Reconstruction(
            session_id=session.id,
            status="complete",
            frames_used=1,
            splat_path="/etc/passwd",
            mesh_glb_path="/etc/shadow",
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)

        token = create_share_token(rec.id, rec.session_id)
        resp = client.get(f"/share/token/{SHARE_LINK_PREFIX}{token}")
        assert resp.status_code == 200
        body = resp.json()
        # Artifact URLs must be relative endpoints, not raw paths
        for url in body["artifacts"].values():
            if url is not None:
                assert "/etc/" not in url
                assert url.startswith("/share/")

    def test_no_arbitrary_dir_access(self):
        """_safe_artifact_access rejects paths outside exports/processed."""
        from fastapi import HTTPException

        from backend.routers.share_links import _safe_artifact_access

        with pytest.raises(HTTPException) as exc_info:
            _safe_artifact_access("/etc/passwd")
        assert exc_info.value.status_code == 403


def _db(client):
    from backend.db.database import get_db
    from backend.main import app

    return next(app.dependency_overrides[get_db]())