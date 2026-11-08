"""Read and update a Hermes ``.env`` file the way ``telephony.py`` does.

The quote and parse rules match ``_quote_env_value``, ``_load_dotenv_values``,
and ``_upsert_env_file`` in the pinned telephony script. Process environment
variables are applied by the caller and win over the file.
"""

from __future__ import annotations

import re
from pathlib import Path


def quote_env_value(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:+@-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def load_dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = raw_line.partition("=")
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        values[key] = value
    return values


def upsert_env_file(path: Path, updates: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _rest = line.partition("=")
        key = key.strip()
        if key in updates:
            new_lines.append(f"{key}={quote_env_value(str(updates[key]))}")
            seen.add(key)
        else:
            new_lines.append(line)
    if new_lines and new_lines[-1].strip():
        new_lines.append("")
    for key, value in updates.items():
        if key not in seen:
            new_lines.append(f"{key}={quote_env_value(str(value))}")
    path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")
    return path
