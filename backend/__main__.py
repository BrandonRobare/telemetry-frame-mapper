from __future__ import annotations

import uvicorn

from backend.core.config import get_deployment_config


def main() -> None:
    deployment = get_deployment_config()
    uvicorn.run("backend.main:app", host=deployment["host"], port=deployment["port"])


if __name__ == "__main__":
    main()
