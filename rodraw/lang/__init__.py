"""Per-language string tables.

One module per language keeps each file small enough to read and correct.
Anything a language leaves out falls back to English, so a partial
translation is safe to ship.
"""
from __future__ import annotations

import importlib

CODES = ['bg', 'de', 'es', 'fr', 'it', 'pt', 'ru', 'tr', 'uk']


def load() -> dict[str, dict[str, str]]:
    tables: dict[str, dict[str, str]] = {}
    for code in CODES:
        try:
            module = importlib.import_module(f"rodraw.lang.{code}")
        except ImportError:
            continue
        table = getattr(module, "STRINGS", None)
        if table:
            tables[code] = table
    return tables
