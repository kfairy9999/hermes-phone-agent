"""Compare adapter HTTP with the pinned Hermes telephony.py, when that file is present.

Set UPSTREAM_TELEPHONY_PY to the script from tag v0.23.0. CI downloads it.
The test is skipped locally when the file is absent, and the adapter tests
still lock the request shape.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermes_phone.orchestrators.bland import BlandOrchestrator
from hermes_phone.orchestrators.vapi import VapiOrchestrator
from hermes_phone.twilio import TwilioClient
from tests.http_util import RecordingOpener

PIN = json.loads(Path(__file__).resolve().parents[1].joinpath("UPSTREAM.json").read_text(encoding="utf-8"))


def load_upstream():
    raw = os.environ.get("UPSTREAM_TELEPHONY_PY", "")
    if not raw:
        pytest.skip("UPSTREAM_TELEPHONY_PY is not set")
    path = Path(raw)
    if not path.is_file():
        pytest.skip(f"UPSTREAM_TELEPHONY_PY does not exist: {path}")
    spec = importlib.util.spec_from_file_location("upstream_telephony_v023", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec so dataclass string annotations can resolve the module.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_pin_is_the_release_commit():
    assert PIN["tag"] == "v0.23.0"
    assert PIN["commit"] == "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"
    assert PIN["groq_api"] == "https://api.groq.com/openai/v1"
    assert PIN["groq_model"] == "qwen/qwen3.8-27b"


def test_upstream_ai_call_choices_exclude_mock():
    module = load_upstream()
    parser = module._build_parser()
    args = parser.parse_args(["ai-call", "+13105550100", "task", "--provider", "bland"])
    assert args.provider == "bland"
    with pytest.raises(SystemExit):
        parser.parse_args(["ai-call", "+13105550100", "task", "--provider", "mock"])
    commands = set(parser._subparsers._group_actions[0].choices)
    assert "ai-call" in commands
    assert "ai-status" in commands
    assert "vapi-import-twilio" in commands
    assert "twilio-send-sms" in commands
    assert module.BLAND_API_BASE == "https://api.bland.ai/v1"
    assert module.VAPI_API_BASE == "https://api.vapi.ai"
    assert module.TWILIO_API_BASE == "https://api.twilio.com/2010-04-01/Accounts"
    assert module.BLAND_DEFAULT_VOICE == "mason"
    assert module.VAPI_DEFAULT_MODEL == "gpt-4o"


def _view(req):
    headers = {key.lower(): value for key, value in req.header_items()}
    headers.pop("user-agent", None)
    return {
        "method": req.get_method(),
        "url": req.full_url,
        "headers": headers,
        "body": req.data,
    }


def test_bland_request_matches_upstream(monkeypatch):
    module = load_upstream()
    monkeypatch.setenv("BLAND_API_KEY", "bland-key")
    monkeypatch.setenv("BLAND_DEFAULT_VOICE", "mason")
    opener = RecordingOpener(lambda req: {"call_id": "call_123"})
    monkeypatch.setattr("urllib.request.urlopen", opener)

    BlandOrchestrator("bland-key", default_voice="mason").place_call(
        "+13105550100",
        "Ask for Tuesday.",
        voice="mason",
        first_sentence="Hello.",
        max_duration=3,
    )
    module._bland_call(
        "+13105550100",
        "Ask for Tuesday.",
        voice="mason",
        first_sentence="Hello.",
        max_duration=3,
    )
    assert _view(opener.requests[0]) == _view(opener.requests[1])


def test_vapi_request_matches_upstream(monkeypatch):
    module = load_upstream()
    monkeypatch.setenv("VAPI_API_KEY", "vapi-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "pn_123")
    monkeypatch.setenv("VAPI_VOICE_PROVIDER", "11labs")
    monkeypatch.setenv("VAPI_VOICE_ID", "cjVigY5qzO86Huf0OWal")
    monkeypatch.setenv("VAPI_MODEL", "gpt-4o")
    opener = RecordingOpener(lambda req: {"id": "call_vapi_1"})
    monkeypatch.setattr("urllib.request.urlopen", opener)
    VapiOrchestrator(
        "vapi-key",
        phone_number_id="pn_123",
        voice_provider="11labs",
        voice_id="cjVigY5qzO86Huf0OWal",
        model="gpt-4o",
    ).place_call("+13105550100", "Book a table.", max_duration=4)
    module._vapi_call("+13105550100", "Book a table.", max_duration=4)
    assert _view(opener.requests[0]) == _view(opener.requests[1])


def test_twilio_sms_request_matches_upstream(monkeypatch):
    module = load_upstream()
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "auth-token")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+13105550000")
    module._resolve_twilio_number = lambda identifier=None: SimpleNamespace(
        sid="PN1", phone_number="+13105550000"
    )
    opener = RecordingOpener(lambda req: {"sid": "SM1", "status": "queued"})
    monkeypatch.setattr("urllib.request.urlopen", opener)
    TwilioClient("AC123", "auth-token", "+13105550000").send_sms("+13105550100", "Deploy finished.")
    module._twilio_send_sms("+13105550100", "Deploy finished.")
    assert _view(opener.requests[0]) == _view(opener.requests[1])
