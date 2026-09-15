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