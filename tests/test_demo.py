"""The scripted demo is the end-to-end mock run a recruiter can replay."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_script(tmp_path):
    env = os.environ.copy()
    env["HERMES_PHONE_DEMO_HOME"] = str(tmp_path / "demo")
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo_mock.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Reminder: 5pm." in proc.stdout
    assert "not on the allowlist" in proc.stdout
    assert "completed" in proc.stdout
    assert "vendor spend $0" in proc.stdout
    assert "Read the 5pm reminder." in proc.stdout
