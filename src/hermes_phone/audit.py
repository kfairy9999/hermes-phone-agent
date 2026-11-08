"""Append-only JSONL audit log.

Lines are written with ``O_APPEND`` under a POSIX advisory lock held by the
guard for the whole check-and-send. The file is never truncated or rewritten
by this module. On Windows the lock is skipped; Hermes documents Windows, and
two concurrent wrappers there can race the daily cap.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None

from hermes_phone.errors import PhoneError


def _parse_line(line: str, path: Path, line_no: int) -> dict[str, Any]:
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise PhoneError(
            f"Audit log {path} line {line_no} is not valid JSON. "
            "Refusing outbound actions until the log is intact."
        ) from exc
    if not isinstance(data, dict):
        raise PhoneError(f"Audit log {path} line {line_no} is not an object.")
    return data


@contextmanager
def locked_log(path: Path) -> Iterator[int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def read_entries(fd: int, path: Path) -> list[dict[str, Any]]:
    os.lseek(fd, 0, os.SEEK_SET)
    raw = os.read(fd, 64 * 1024 * 1024)
    text = raw.decode("utf-8")
    entries: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        entries.append(_parse_line(line, path, line_no))
    return entries


def append_entry(fd: int, entry: dict[str, Any]) -> None:
    payload = json.dumps(entry, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    os.write(fd, payload.encode("utf-8"))
    os.fsync(fd)


def parse_timestamp(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)
