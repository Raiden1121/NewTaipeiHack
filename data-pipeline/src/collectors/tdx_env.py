"""Load local collector configuration from ``collectors/.env``."""

from __future__ import annotations

import os
import re
from pathlib import Path


DEFAULT_ENV_PATH = Path(__file__).with_name(".env")
_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_dotenv(path: str | Path = DEFAULT_ENV_PATH) -> None:
    """Load simple KEY=VALUE entries without overriding environment variables."""

    env_path = Path(path)
    if not env_path.is_file():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()

        key, separator, raw_value = line.partition("=")
        key = key.strip()
        if not separator or not _KEY_PATTERN.fullmatch(key):
            continue
        os.environ.setdefault(key, _parse_value(raw_value.strip()))


def _parse_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
