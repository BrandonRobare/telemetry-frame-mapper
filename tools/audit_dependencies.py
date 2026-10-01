"""Audit all resolved groups/platforms without installing their dependencies."""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def requirement_batches(export: str) -> list[dict[str, str]]:
    # pip-audit rejects two versions of a name in one file. Keep all uv variants,
    # stripping markers so Windows/Metal/other-Python dependencies are also audited.
    batches: list[dict[str, str]] = [{}]
    for line in export.splitlines():
        requirement = line.split(";", 1)[0].strip()
        if not requirement or requirement.startswith("#"):
            continue
        if not re.fullmatch(r"[\w.-]+==[\w.+!-]+", requirement):
            raise ValueError(f"Cannot audit an unpinned registry requirement: {requirement}")
        name = requirement.split("==", 1)[0]
        for batch in batches:
            if name not in batch or batch[name] == requirement:
                batch[name] = requirement
                break
        else:
            batches.append({name: requirement})
    if not batches[0]:
        raise ValueError("The dependency export was empty")
    return batches


def main() -> None:
    export = subprocess.check_output(
        [
            "uv",
            "export",
            "--frozen",
            "--all-groups",
            "--no-emit-project",
            "--no-hashes",
            "--no-annotate",
            "--format",
            "requirements-txt",
        ],
        cwd=ROOT,
        text=True,
    )
    with tempfile.TemporaryDirectory(prefix="tfm-dependency-audit-") as directory:
        for index, batch in enumerate(requirement_batches(export)):
            requirements = Path(directory) / f"requirements-{index}.txt"
            requirements.write_text("\n".join(batch.values()) + "\n", encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_audit",
                    "--strict",
                    "--no-deps",
                    "--disable-pip",
                    "-r",
                    str(requirements),
                ],
                cwd=ROOT,
                check=True,
            )


if __name__ == "__main__":
    main()
