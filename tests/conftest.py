"""Keep tests off the developer Hermes home and any real credentials."""

from __future__ import annotations

import pytest

CLEARED = (
    "ORCHESTRATOR",
    "PHONE_PROVIDER",
    "PHONE_ALLOWLIST",
    "PHONE_ALLOWLIST_FILE",
    "PHONE_MAX_CALLS_PER_DAY",
    "PHONE_MAX_TEXTS_PER_DAY",
    "PHONE_MAX_DOLLARS_PER_DAY",
    "PHONE_QUIET_HOURS",
    "PHONE_TIMEZONE",
    "PHONE_LOG_PATH",
    "PHONE_MOCK_STATE_PATH",
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TWILIO_PHONE_NUMBER_SID",
    "BLAND_API_KEY",
    "BLAND_DEFAULT_VOICE",
    "VAPI_API_KEY",
    "VAPI_PHONE_NUMBER_ID",
    "VAPI_VOICE_PROVIDER",
    "VAPI_VOICE_ID",
    "VAPI_MODEL",
    "GROQ_API_KEY",
)


@pytest.fixture(autouse=True)
def isolated_hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    for key in CLEARED:
        monkeypatch.delenv(key, raising=False)
    return home
