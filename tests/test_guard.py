"""Guard policy: allowlist, confirmation, caps, quiet hours, append-only log."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from hermes_phone.config import load_settings
from hermes_phone.errors import GuardRefusal, PhoneError
from hermes_phone.guard import in_quiet_hours
from hermes_phone.service import PhoneService

LA = ZoneInfo("America/Los_Angeles")
OWN = "+13105550100"
OTHER = "+12125550199"
AFTERNOON = datetime(2026, 11, 8, 15, 0, tzinfo=LA)
NIGHT = datetime(2026, 11, 8, 22, 30, tzinfo=LA)
MORNING_EDGE = datetime(2026, 11, 8, 8, 0, tzinfo=LA)
QUIET_START = datetime(2026, 11, 8, 21, 0, tzinfo=LA)


def service(monkeypatch, **env) -> PhoneService:
    monkeypatch.setenv("PHONE_ALLOWLIST", OWN)
    monkeypatch.setenv("PHONE_TIMEZONE", "America/Los_Angeles")
    monkeypatch.setenv("PHONE_QUIET_HOURS", "21:00-08:00")
    monkeypatch.setenv("ORCHESTRATOR", "mock")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return PhoneService(load_settings())


def test_empty_allowlist_refuses_even_when_confirmed(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR", "mock")
    phone = PhoneService(load_settings())
    with pytest.raises(GuardRefusal, match="not on the allowlist"):
        phone.send_sms(OWN, "hi", confirmed=True)


def test_unlisted_number_is_refused_and_logged(monkeypatch):
    phone = service(monkeypatch)
    with pytest.raises(GuardRefusal, match="not on the allowlist"):
        phone.ai_call(OTHER, "Ask if they are free.", confirmed=True)
    log = phone.settings.log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(log) == 1
    entry = __import__("json").loads(log[0])
    assert entry["decision"] == "refused"
    assert entry["to"] == OTHER
    assert entry["counts_as_call"] is False


def test_missing_confirmation_refuses(monkeypatch):
    phone = service(monkeypatch)
    phone._now = lambda: AFTERNOON
    with pytest.raises(GuardRefusal, match="confirm"):
        phone.send_sms(OWN, "Reminder: 5pm.", confirmed=False)
    entry = __import__("json").loads(phone.settings.log_path.read_text(encoding="utf-8"))
    assert entry["decision"] == "refused"
    assert entry["confirmed"] is False


def test_confirmed_sms_is_allowed_in_mock(monkeypatch):
    phone = service(monkeypatch)
    phone._now = lambda: AFTERNOON
    result = phone.send_sms(OWN, "Reminder: 5pm.", confirmed=True)
    assert result["success"] is True
    assert result["mock"] is True
    assert result["status"] == "queued"
    assert result["to_phone_number_masked"] == "***-***-0100"
    assert result["guard"]["vendor_spend_usd"] == "0"


def test_emergency_numbers_are_refused(monkeypatch):
    phone = service(monkeypatch)
    with pytest.raises(GuardRefusal, match="emergency"):
        phone.ai_call("911", "no", confirmed=True)
    with pytest.raises(GuardRefusal, match="emergency"):
        phone.ai_call("+1988", "no", confirmed=True)


def test_quiet_hours_block_and_edges_do_not(monkeypatch):
    assert in_quiet_hours(NIGHT, "21:00-08:00") is True
    assert in_quiet_hours(QUIET_START, "21:00-08:00") is True
    assert in_quiet_hours(MORNING_EDGE, "21:00-08:00") is False
    assert in_quiet_hours(AFTERNOON, "21:00-08:00") is False
    assert in_quiet_hours(AFTERNOON, "") is False

    phone = service(monkeypatch)
    real_now = phone._now
    phone._now = lambda: NIGHT
    with pytest.raises(GuardRefusal, match="Quiet hours"):
        phone.send_sms(OWN, "late", confirmed=True)
    phone._now = real_now


def test_daytime_window(monkeypatch):
    phone = service(monkeypatch, PHONE_QUIET_HOURS="09:00-17:00")
    phone._now = lambda: AFTERNOON
    with pytest.raises(GuardRefusal, match="Quiet hours"):
        phone.send_sms(OWN, "workday", confirmed=True)


def test_call_cap(monkeypatch):
    phone = service(monkeypatch, PHONE_MAX_CALLS_PER_DAY="1")
    phone._now = lambda: AFTERNOON
    first = phone.ai_call(OWN, "Read the reminder.", confirmed=True)
    assert first["call_id"] == "mock-call-1"
    with pytest.raises(GuardRefusal, match="Daily call cap"):
        phone.ai_call(OWN, "Again.", confirmed=True)


def test_text_cap_does_not_count_calls(monkeypatch):
    phone = service(monkeypatch, PHONE_MAX_TEXTS_PER_DAY="1")
    phone._now = lambda: AFTERNOON
    phone.ai_call(OWN, "A call is not a text.", confirmed=True)
    phone.send_sms(OWN, "one", confirmed=True)
    with pytest.raises(GuardRefusal, match="Daily text cap"):
        phone.send_sms(OWN, "two", confirmed=True)


def test_dollar_cap(monkeypatch):
    phone = service(monkeypatch, PHONE_MAX_DOLLARS_PER_DAY="0.01", PHONE_MAX_TEXTS_PER_DAY="10")
    phone._now = lambda: AFTERNOON
    phone.send_sms(OWN, "fits under one cent? no, 0.0083 does", confirmed=True)
    with pytest.raises(GuardRefusal, match="Daily dollar cap"):
        phone.send_sms(OWN, "second segment pushes the estimate over", confirmed=True)


def test_log_is_append_only(monkeypatch):
    phone = service(monkeypatch)
    phone._now = lambda: AFTERNOON
    path = phone.settings.log_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"ts":"2026-11-08T15:00:00-08:00","kind":"note","decision":"refused"}\n', encoding="utf-8")
    phone.send_sms(OWN, "after the seed", confirmed=True)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith('{"ts":"2026-11-08T15:00:00-08:00"')
    assert len(lines) == 2
    assert "after the seed" in lines[1]


def test_bad_log_line_fails_closed(monkeypatch):
    phone = service(monkeypatch)
    phone.settings.log_path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(PhoneError, match="not valid JSON"):
        phone.send_sms(OWN, "nope", confirmed=True)


def test_mock_does_not_open_network(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("network was contacted")

    monkeypatch.setattr("urllib.request.urlopen", explode)
    phone = service(monkeypatch, BLAND_API_KEY="secret-key", VAPI_API_KEY="secret-key")
    phone._now = lambda: AFTERNOON
    result = phone.ai_call(OWN, "Stay local.", confirmed=True, max_duration=3)
    status = phone.ai_status(result["call_id"])
    assert "Stay local." in status["transcript"]
    text = phone.settings.log_path.read_text(encoding="utf-8")
    assert "secret-key" not in text


def test_live_sms_without_credentials_does_not_consume_cap(monkeypatch):
    phone = service(monkeypatch, ORCHESTRATOR="bland", PHONE_PROVIDER="bland")
    phone._now = lambda: AFTERNOON
    with pytest.raises(PhoneError, match="Twilio credentials"):
        phone.send_sms(OWN, "hello", confirmed=True)
    usage = phone.guard.usage(AFTERNOON)
    assert usage.texts == 0


def test_confirmation_helper_requires_yes():
    from hermes_phone.cli import confirmation_granted

    assert confirmation_granted(flag=True, stdin_is_tty=False, read_line=lambda: "", prompt="") is True
    assert confirmation_granted(flag=False, stdin_is_tty=False, read_line=lambda: "yes", prompt="") is False
    answers = iter(["YES\n"])
    assert (
        confirmation_granted(
            flag=False,
            stdin_is_tty=True,
            read_line=lambda: next(answers),
            prompt="confirm?",
        )
        is True
    )
    assert (
        confirmation_granted(
            flag=False,
            stdin_is_tty=True,
            read_line=lambda: "y\n",
            prompt="confirm?",
        )
        is False
    )


def test_mock_pin_blocks_live_provider_flag(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR", "mock")
    with pytest.raises(PhoneError, match="will not contact Bland"):
        load_settings(cli_provider="bland")


def test_phone_provider_selects_when_orchestrator_unset(monkeypatch):
    monkeypatch.setenv("PHONE_PROVIDER", "vapi")
    settings = load_settings()
    assert settings.orchestrator == "vapi"
