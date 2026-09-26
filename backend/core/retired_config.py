"""Config keys removed in past releases.

A key missing from the bundled ``config.yaml`` is not necessarily retired.
Some valid keys are optional (``deployment.auto_open_browser``), and some are
omitted on purpose (``reconstruction.presets.quick.iterations`` is filled by
accelerator policy). Only the paths listed here are dropped from an existing
``config.yaml``.

Both the packaged app's runtime hook and ``backend.core.config`` read this
list. The hook imports this module before the backend starts, so it must not
import anything.
"""

RETIRED_CONFIG_KEYS: tuple[tuple[str, ...], ...] = (
    # v2.0.4, #667: never selected the COLMAP matcher.
    ("reconstruction", "presets", "quick", "exhaustive_matching"),
    ("reconstruction", "presets", "full", "exhaustive_matching"),
    # v2.0.5, #776: consumed by nothing.
    ("reconstruction", "presets", "quick", "max_frames"),
    ("reconstruction", "presets", "full", "max_frames"),
)


def pop_retired_keys(data: object) -> dict[str, object]:
    """Remove retired keys from *data* in place; return them by dotted path."""
    removed: dict[str, object] = {}
    for path in RETIRED_CONFIG_KEYS:
        node = data
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict) and path[-1] in node:
            removed[".".join(path)] = node.pop(path[-1])
    return removed
