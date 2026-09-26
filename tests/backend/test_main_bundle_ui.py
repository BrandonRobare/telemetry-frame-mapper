"""Packaged-bundle UI entry point (#833).

The frozen `.app`/`.exe` is a headless uvicorn server; these tests pin the
first-launch browser open, the second-launch focus guard, and the kill switch
the CI smoke uses so a headless runner never spawns a browser.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def fake_frozen(monkeypatch):
    monkeypatch.setattr("backend.__main__.sys.frozen", True, raising=False)


class _FakeResponse:
    def __init__(self, serving: bool):
        self.status = 200 if serving else 503

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_health(monkeypatch, serving: bool):
    monkeypatch.setattr(
        "backend.__main__.urllib.request.urlopen",
        lambda *args, **kwargs: _FakeResponse(serving),
    )


def _patch_home(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.__main__._bundle_lock_dir", lambda: tmp_path / "app-data", raising=False
    )


def test_source_checkout_does_not_open_browser(monkeypatch, tmp_path):
    import backend.__main__ as main

    opened: list[str] = []
    monkeypatch.setattr("backend.__main__.webbrowser.open", lambda url: opened.append(url))
    main._open_bundle_ui({"host": "127.0.0.1", "port": 8000})  # sys.frozen is False
    assert opened == []
    assert not (tmp_path / "app-data").exists()


def test_auto_open_disabled_returns_early(fake_frozen, monkeypatch, tmp_path):
    import backend.__main__ as main

    opened: list[str] = []
    monkeypatch.setattr("backend.__main__.webbrowser.open", lambda url: opened.append(url))
    main._open_bundle_ui({"host": "127.0.0.1", "port": 8000, "auto_open_browser": False})
    assert opened == []


def test_second_launch_focuses_existing_instance(fake_frozen, monkeypatch, tmp_path):
    import backend.__main__ as main

    _patch_home(monkeypatch, tmp_path)
    lock = tmp_path / "app-data" / "instance.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    _patch_health(monkeypatch, serving=True)
    opened: list[str] = []
    monkeypatch.setattr("backend.__main__.webbrowser.open", lambda url: opened.append(url))

    with pytest.raises(SystemExit) as excinfo:
        main._open_bundle_ui({"host": "127.0.0.1", "port": 8000})
    assert excinfo.value.code == 0
    assert opened == ["http://127.0.0.1:8000"]


def test_stale_lock_is_replaced_not_kept(fake_frozen, monkeypatch, tmp_path):
    import backend.__main__ as main

    _patch_home(monkeypatch, tmp_path)
    lock = tmp_path / "app-data" / "instance.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()
    _patch_health(monkeypatch, serving=False)  # first instance is gone

    main._open_bundle_ui({"host": "127.0.0.1", "port": 8000})
    assert lock.exists()  # re-created for the new first instance

    lock.unlink()
    main._open_bundle_ui({"host": "127.0.0.1", "port": 8000})
    assert lock.exists()


# ---------------------------------------------------------------------------
# --check-reconstruction-deps (the packaging smoke's capability probe)
#
# A bare `import rasterio` survives a bundle with no GDAL/PROJ data -- rasterio
# only reads it lazily on first CRS or driver use -- so these exercise the
# same PROJ/GDAL/lazrs calls the reconstruction exports actually make.
# ---------------------------------------------------------------------------


def _require_reconstruction_dependencies() -> None:
    pytest.importorskip("laspy")
    pytest.importorskip("rasterio")


def test_reconstruction_capability_check_passes_with_real_libraries():
    _require_reconstruction_dependencies()
    import backend.__main__ as main

    assert main._check_reconstruction_capabilities() == 0


def test_reconstruction_capability_check_fails_when_proj_data_is_missing(monkeypatch):
    _require_reconstruction_dependencies()
    import backend.__main__ as main

    # rasterio.crs.CRS is an immutable Cython type; swap the module's binding
    # instead of patching the class, to simulate a missing proj.db.
    class _NoProjData:
        @classmethod
        def from_epsg(cls, code):
            raise RuntimeError("PROJ: internal_proj_create_from_database: Cannot find proj.db")

    monkeypatch.setattr("rasterio.crs.CRS", _NoProjData)
    assert main._check_reconstruction_capabilities() == 1


def test_reconstruction_capability_check_fails_when_lazrs_backend_is_missing(monkeypatch):
    _require_reconstruction_dependencies()
    import laspy

    import backend.__main__ as main

    def _no_lazrs_backend(self, destination, do_compress=None, laz_backend=None):
        raise laspy.errors.LaspyException("lazrs backend is not available")

    monkeypatch.setattr(laspy.LasData, "write", _no_lazrs_backend)
    assert main._check_reconstruction_capabilities() == 1
