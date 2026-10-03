"""Write the canonical OpenAPI snapshot, or check it without changing files."""

import argparse
import json
from pathlib import Path

from backend.main import app

SNAPSHOT = Path(__file__).resolve().parents[1] / "frontend" / "openapi.json"


def rendered_schema() -> str:
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rendered = rendered_schema()
    if args.check:
        if SNAPSHOT.read_text(encoding="utf-8") != rendered:
            parser.exit(1, "OpenAPI snapshot drift: run python -m tools.openapi_snapshot\n")
    else:
        SNAPSHOT.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
