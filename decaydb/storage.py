"""TheSNMC RustDB local file storage utilities."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path


def storage_dir() -> Path:
    root = Path(os.getenv("RUSTDB_STORAGE_DIR", "rustdb_storage"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_name(filename: str) -> str:
    base = Path(filename).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", base)


def save_binary(filename: str, data: bytes) -> str:
    safe = _safe_name(filename)
    path = storage_dir() / f"{int(time.time() * 1000)}_{safe}"
    path.write_bytes(data)
    return str(path)
