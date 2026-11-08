"""End-to-end mock session: text, refuse an unlisted number, confirmed call, status, log."""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from hermes_phone.cli import main
from hermes_phone.config import load_settings
from hermes_phone.service import PhoneService

OWN = "+13105550100"
OTHER = "+12125550199"
LA = ZoneInfo("America/Los_Angeles")


def test_three_beat_session(monkeypatch, capsys):
    monkeypatch.setenv("ORCHESTRATOR", "mock")
    monkeypatch.setenv("PHONE_PROVIDER", "mock")
    monkeypatch.setenv("PHONE_ALLOWLIST", OWN)
    monkeypatch.setenv("PHONE_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("PHONE_QUIET_HOURS", "21:00-08:00")
    phone = PhoneService(load_settings())
    phone._now = lambda: datetime(2026, 11, 8, 16, 30, tzinfo=LA)

    sms = phone.send_sms(OWN, "Reminder: 5pm.", confirmed=True)
    assert sms["message_sid"] == "SM_mock_1"

    code = main(["ai-call", OTHER, "Ask if they are free.", "--confirm"])
    err = capsys.readouterr().err
    assert code == 2
    refused = json.loads(err)
    assert refused["refused"] is True
    assert "not on the allowlist" in refused["error"]

    # The CLI process wrote to the same log. Continue with a fresh service
    # so it sees that refusal and the earlier text.
    phone = PhoneService(load_settings())
    phone._now = lambda: datetime(2026, 11, 8, 16, 31, tzinfo=LA)
    call = phone.ai_call(OWN, "Read the 5pm reminder.", confirmed=True, max_duration=3)
    status = phone.ai_status(call["call_id"], analyze="Did they acknowledge?")
    assert call["provider"] == "mock"
    assert status["status"] == "completed"
    assert "Read the 5pm reminder." in status["transcript"]
    assert status["analysis"]["answers"]

    lines = phone.settings.log_path.read_text(encoding="utf-8").splitlines()
    kinds = [json.loads(line)["kind"] for line in lines]
    decisions = [json.loads(line)["decision"] for line in lines]
    assert kinds == ["sms", "ai-call", "ai-call", "ai-status"]
    assert decisions == ["allowed", "refused", "allowed", "allowed"]
    # Refusals do not spend the call cap. One allowed call remains.
    usage = phone.guard.usage(datetime(2026, 11, 8, 16, 31, tzinfo=LA))
    assert usage.calls == 1
    assert usage.texts == 1


def test_cli_confirm_required_when_stdin_is_not_a_tty(monkeypatch, capsys):
    monkeypatch.setenv("ORCHESTRATOR", "mock")
    monkeypatch.setenv("PHONE_ALLOWLIST", OWN)
    monkeypatch.setenv("PHONE_QUIET_HOURS", "")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code = main(["twilio-send-sms", OWN, "Reminder: 5pm."])
    assert code == 2
    assert "confirm" in capsys.readouterr().err.lower()
