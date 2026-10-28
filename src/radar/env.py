from __future__ import annotations

import os
from pathlib import Path
from typing import MutableMapping


def load_dotenv(path: Path, environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Copy KEY=value lines from a .env file into the environment.

    Variables that are already set win, and empty values are skipped, so the same code runs in
    GitHub Actions (real secrets, no file) and on a laptop. Returns the names it set, never values.
    """
    target = os.environ if environ is None else environ
    try:
        lines = Path(path).read_text().splitlines()
    except FileNotFoundError:
        return []

    loaded: list[str] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        name, sep, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value or name in target:
            continue
        target[name] = value
        loaded.append(name)
    return loaded
