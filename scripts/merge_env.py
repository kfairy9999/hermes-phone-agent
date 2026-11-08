#!/usr/bin/env python3
"""Add keys that are missing from a Hermes .env file.

Values already present are left alone. The script prints key names only.
"""

from __future__ import annotations

import sys
from pathlib import Path

from hermes_phone.envfile import load_dotenv_values, upsert_env_file


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: merge_env.py DEST.env EXAMPLE.env", file=sys.stderr)
        return 2
    dest = Path(argv[1])
    example = Path(argv[2])
    existing = load_dotenv_values(dest)
    incoming = load_dotenv_values(example)
    missing = {key: value for key, value in incoming.items() if key not in existing}
    if missing:
        dest.parent.mkdir(parents=True, exist_ok=True)
        upsert_env_file(dest, missing)
    print("env keys added:", ", ".join(sorted(missing)) if missing else "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
