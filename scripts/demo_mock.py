#!/usr/bin/env python3
"""Scripted mock-mode demo.

Three beats:

1. Text an allowlisted number a 5pm reminder, after confirmation.
2. Ask to call a number that is not on the allowlist. The guard refuses it
   even though --confirm is passed.
3. Place a confirmed mock call, then read its status and the audit log.

The demo uses its own HERMES_HOME under /tmp and never reads ~/.hermes.
Exit status is 0 only when all three beats match.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from hermes_phone.guard import in_quiet_hours

OWN = "+13105550100"
OTHER = "+12125550199"
LA = ZoneInfo("America/Los_Angeles")


def demo_home() -> Path:
    raw = os.environ.get("HERMES_PHONE_DEMO_HOME", "/tmp/hermes-phone-demo")
    return Path(raw)


def child_env(home: Path, quiet: str) -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "HERMES_HOME": str(home),
        "ORCHESTRATOR": "mock",
        "PHONE_PROVIDER": "mock",
        "PHONE_ALLOWLIST": OWN,
        "PHONE_TIMEZONE": "America/Los_Angeles",
        "PHONE_QUIET_HOURS": quiet,
        "PHONE_MAX_CALLS_PER_DAY": "3",
        "PHONE_MAX_TEXTS_PER_DAY": "10",
        "PHONE_MAX_DOLLARS_PER_DAY": "2.00",
        "PYTHONPATH": str(root / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }


def run(args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "hermes_phone", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def show(lines: list[str], title: str, command: list[str], code: int, out: str, err: str) -> None:
    lines.append("")
    lines.append(f"── {title}")
    lines.append("$ python -m hermes_phone " + " ".join(shlex.quote(part) for part in command))
    if out.strip():
        lines.append(out.rstrip())
    if err.strip():
        lines.append(err.rstrip())
    lines.append(f"(exit {code})")


def main() -> int:
    home = demo_home()
    if home.exists():
        shutil.rmtree(home)
    home.mkdir(parents=True)

    now = datetime.now(LA)
    quiet = "21:00-08:00"
    quiet_note = "Quiet hours are 21:00-08:00 America/Los_Angeles."
    if in_quiet_hours(now, quiet):
        quiet = ""
        quiet_note = (
            "Quiet hours default to 21:00-08:00 America/Los_Angeles. "
            f"It is {now.strftime('%H:%M')} there, inside that window, so this "
            "recording turns quiet hours off. The guard still enforces them when the window is set."
        )

    env = child_env(home, quiet)
    lines: list[str] = []
    lines.append("hermes-phone-agent")
    lines.append("mock mode · Twilio, Bland, and Vapi are not contacted · vendor spend $0")
    lines.append(f"allowlist: {OWN} (555-0100, a fictional number)")
    lines.append("caps: 3 calls / 10 texts / $2.00 estimated per day")
    lines.append(quiet_note)
    lines.append(f"HERMES_HOME: {home}")

    lines.append("")
    lines.append("You: Text me a reminder at 5pm")
    lines.append("Agent: +1 310 555 0100 is on the allowlist. The text would say \"Reminder: 5pm.\"")
    lines.append("You: yes")
    sms_cmd = ["twilio-send-sms", OWN, "Reminder: 5pm.", "--confirm"]
    code, out, err = run(sms_cmd, env)
    show(lines, "1. Confirmed text", sms_cmd, code, out, err)
    sms = json.loads(out) if code == 0 else {}
    if code != 0 or sms.get("message_sid") != "SM_mock_1":
        lines.append("DEMO FAILED at the SMS step.")
        print("\n".join(lines))
        return 1

    lines.append("")
    lines.append("You: Call +1 212 555 0199 and ask if they are free")
    lines.append("Agent: That number is not on the allowlist. I will not add it, and I will not dial it.")
    call_bad = ["ai-call", OTHER, "Ask if they are free this week.", "--confirm"]
    code, out, err = run(call_bad, env)
    show(lines, "2. Unlisted number, refused even with --confirm", call_bad, code, out, err)
    if code != 2 or "not on the allowlist" not in err:
        lines.append("DEMO FAILED at the refusal step.")
        print("\n".join(lines))
        return 1

    lines.append("")
    lines.append("You: Call me and read the 5pm reminder")
    lines.append("Agent: That is the allowlisted number, still in mock mode. Confirm the call?")
    lines.append("You: yes")
    call_ok = [
        "ai-call",
        OWN,
        "Read the 5pm reminder.",
        "--first-sentence",
        "Hi, this is your reminder line.",
        "--max-duration",
        "3",
        "--confirm",
    ]
    code, out, err = run(call_ok, env)
    show(lines, "3. Confirmed mock call", call_ok, code, out, err)
    if code != 0:
        lines.append("DEMO FAILED at the mock call.")
        print("\n".join(lines))
        return 1
    call = json.loads(out)
    status_cmd = ["ai-status", call["call_id"], "--analyze", "Did they acknowledge?"]
    code, out, err = run(status_cmd, env)
    show(lines, "3b. Mock status and transcript", status_cmd, code, out, err)
    if code != 0:
        lines.append("DEMO FAILED at status.")
        print("\n".join(lines))
        return 1
    status = json.loads(out)
    if status.get("status") != "completed" or "Read the 5pm reminder." not in status.get("transcript", ""):
        lines.append("DEMO FAILED: status payload was not the canned transcript.")
        print("\n".join(lines))
        return 1

    log_path = home / "phone_audit.jsonl"
    log_lines = log_path.read_text(encoding="utf-8").splitlines()
    lines.append("")
    lines.append("── Audit log (append-only JSONL)")
    lines.append(f"$ cat {log_path}")
    lines.extend(log_lines)
    decisions = [json.loads(line)["decision"] for line in log_lines]
    kinds = [json.loads(line)["kind"] for line in log_lines]
    if decisions != ["allowed", "refused", "allowed", "allowed"] or kinds != [
        "sms",
        "ai-call",
        "ai-call",
        "ai-status",
    ]:
        lines.append("DEMO FAILED: audit log shape.")
        print("\n".join(lines))
        return 1
    if any(json.loads(line)["vendor_spend_usd"] != "0" for line in log_lines):
        lines.append("DEMO FAILED: mock log recorded vendor spend.")
        print("\n".join(lines))
        return 1

    lines.append("")
    lines.append("Done. Four log lines: text allowed, unlisted call refused, mock call allowed, status recorded.")
    lines.append("No Twilio, Bland, or Vapi account was required.")
    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)

    if "--cast" in sys.argv:
        cast_path = Path(sys.argv[sys.argv.index("--cast") + 1])
        write_cast(text, cast_path)
        print(f"wrote {cast_path}", file=sys.stderr)
    return 0


def write_cast(text: str, path: Path) -> None:
    header = {
        "version": 2,
        "width": 100,
        "height": 40,
        "timestamp": int(datetime.now().timestamp()),
        "title": "hermes-phone-agent mock demo",
        "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
    }
    events = [json.dumps(header)]
    clock = 0.4
    events.append(json.dumps([0.0, "o", "$ python scripts/demo_mock.py\r\n"]))
    for line in text.splitlines(keepends=True):
        clock += 0.06
        events.append(json.dumps([round(clock, 3), "o", line.replace("\n", "\r\n")]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(events) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
