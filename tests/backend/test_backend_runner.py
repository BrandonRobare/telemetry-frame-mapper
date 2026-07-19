from __future__ import annotations

from backend import __main__


def test_runner_uses_deployment_profile(monkeypatch):
    deployment = {"host": "192.168.1.50", "port": 8080, "cors_origins": []}
    monkeypatch.setattr(__main__, "get_deployment_config", lambda: deployment)
    calls = []
    monkeypatch.setattr(
        __main__.uvicorn, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    __main__.main()

    assert calls == [(("backend.main:app",), {"host": "192.168.1.50", "port": 8080})]
