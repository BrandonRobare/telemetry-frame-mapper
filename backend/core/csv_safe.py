"""Spreadsheet-injection guard for CSV exports (#863).

Cell values that begin with ``= + - @`` (or whitespace-prefixed variants) are
interpreted as formulas by Excel/LibreOffice when a CSV is opened. Prefix such
values with a single quote, matching the defensive convention used by
established CSV exporters.
"""

from __future__ import annotations

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: object) -> str:
    """Return a formula-neutral string form of ``value`` for CSV cells."""
    text = "" if value is None else str(value)
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text