from __future__ import annotations

import os

import uvicorn

from backend.core.config import get_deployment_config


def main() -> None:
    deployment = get_deployment_config()
    # Reload mode uses one API worker; BACKEND_RELOAD=1 is how the dev launchers ask for it.
    uvicorn.run(
        "backend.main:app",
        host=deployment["host"],
        port=deployment["port"],
        workers=1,
        reload=os.environ.get("BACKEND_RELOAD", "").strip() == "1",
    )


if __name__ == "__main__":
    main()
