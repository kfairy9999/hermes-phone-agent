"""Bland, Vapi, and Twilio HTTP adapters. urllib is mocked."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import pytest

from hermes_phone.orchestrators.bland import BLAND_API_BASE, BlandOrchestrator
from hermes_phone.orchestrators.vapi import VAPI_API_BASE, VapiOrchestrator
from hermes_phone.twilio import TwilioClient
from tests.http_util import RecordingOpener


@pytest.fixture
def http(monkeypatch):
    opener = RecordingOpener(lambda req: {})
    monkeypatch.setattr("urllib.request.urlopen", opener)
    return opener


def _header(req, name: str) -> str:
    return req.get_header(name) or ""


def test_bland_place_call_matches_skill_body(http):
    http._responder = lambda req: {"call_id": "call_123", "status": "queued"}
    result = BlandOrchestrator("bland-key", default_voice="mason").place_call(
        "+13105550100",
        "Ask for Tuesday.",
        voice="evelyn",
        first_sentence="Hi, this is the office line.",
        max_duration=3,
    )
    assert result["call_id"] == "call_123"
    assert result["provider"] == "bland"
    req = http.requests[0]
    assert req.get_method() == "POST"
    assert req.full_url == f"{BLAND_API_BASE}/calls"
    assert _header(req, "Authorization") == "bland-key"
    body = json.loads(req.data.decode())
    assert body == {
        "phone_number": "+13105550100",
        "task": "Ask for Tuesday.",
        "voice": "evelyn",
        "model": "enhanced",
        "max_duration": 3,
        "record": True,
        "wait_for_greeting": True,
        "first_sentence": "Hi, this is the office line.",
    }


def test_bland_analyze_only_after_completed(http):
    calls = {"n": 0}

    def responder(req):
        calls["n"] += 1
        if req.get_method() == "GET":
            return {"status": "queued", "concatenated_transcript": ""}
        return {"answers": ["yes"]}

    http._responder = responder
    BlandOrchestrator("bland-key").call_status("call_123", analyze="Was it confirmed?")
    assert len(http.requests) == 1

    http.requests.clear()

    def completed(req):
        if req.get_method() == "GET":
            return {"status": "completed", "concatenated_transcript": "hello", "call_length": 1.2}
        return {"Was it confirmed?": "yes"}

    http._responder = completed
    result = BlandOrchestrator("bland-key").call_status("call_123", analyze="Was it confirmed?, What time?")
    assert len(http.requests) == 2
    analyze_req = http.requests[1]
    assert analyze_req.full_url == f"{BLAND_API_BASE}/calls/call_123/analyze"
    assert json.loads(analyze_req.data.decode()) == {
        "questions": [["Was it confirmed?", "string"], ["What time?", "string"]]
    }
    assert result["transcript"] == "hello"
    assert "analysis" in result


def test_vapi_place_call_and_import(http):
    http._responder = lambda req: {"id": "call_vapi_1", "status": "queued"}
    adapter = VapiOrchestrator(
        "vapi-key",
        phone_number_id="pn_123",
        voice_provider="11labs",
        voice_id="cjVigY5qzO86Huf0OWal",
        model="gpt-4o",
    )
    result = adapter.place_call("+13105550100", "Book a table for two.", max_duration=4)
    assert result["provider"] == "vapi"
    assert result["call_id"] == "call_vapi_1"
    req = http.requests[0]
    assert req.full_url == f"{VAPI_API_BASE}/call"
    assert _header(req, "Authorization") == "Bearer vapi-key"
    body = json.loads(req.data.decode())
    assert body["phoneNumberId"] == "pn_123"
    assert body["customer"] == {"number": "+13105550100"}
    assert body["assistant"]["maxDurationSeconds"] == 240
    assert body["assistant"]["model"]["messages"] == [
        {"role": "system", "content": "Book a table for two."}
    ]
    assert body["assistant"]["voice"] == {"provider": "11labs", "voiceId": "cjVigY5qzO86Huf0OWal"}

    http.requests.clear()
    http._responder = lambda req: {"id": "vapi_phone_9"}
    imported = adapter.import_twilio_number(
        phone_number="+13105550000",
        account_sid="AC123",
        auth_token="token-secret",
    )
    assert imported["phone_number_id"] == "vapi_phone_9"
    sent = json.loads(http.requests[0].data.decode())
    assert sent == {
        "provider": "twilio",
        "number": "+13105550000",
        "twilioAccountSid": "AC123",
        "twilioAuthToken": "token-secret",
    }


def test_vapi_status_ignores_analyze(http):
    http._responder = lambda req: {
        "status": "ended",
        "transcript": "done",
        "duration": 12,
        "endedReason": "customer-ended-call",
        "cost": 0.04,
    }
    result = VapiOrchestrator("vapi-key", phone_number_id="pn").call_status(
        "call_vapi_1", analyze="Should be ignored"
    )
    assert len(http.requests) == 1
    assert http.requests[0].get_method() == "GET"
    assert http.requests[0].full_url == f"{VAPI_API_BASE}/call/call_vapi_1"
    assert result["transcript"] == "done"
    assert "analysis" not in result


def test_twilio_sms_and_call_forms(http):
    http._responder = lambda req: {"sid": "SM123", "status": "queued"}
    client = TwilioClient("AC123", "auth-token", "+13105550000")
    client.send_sms(
        "+13105550100",
        "Here is the chart.",
        media_urls=["https://example.com/chart.png"],
    )
    req = http.requests[0]
    assert req.full_url == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert _header(req, "Authorization").startswith("Basic ")
    form = parse_qs(req.data.decode())
    assert form["To"] == ["+13105550100"]
    assert form["From"] == ["+13105550000"]
    assert form["Body"] == ["Here is the chart."]
    assert form["MediaUrl"] == ["https://example.com/chart.png"]

    http.requests.clear()
    http._responder = lambda req: {"sid": "CA123", "status": "queued"}
    client.call("+13105550100", message="Hello from Hermes.", voice="Polly.Joanna", send_digits="ww1")
    call = http.requests[0]
    assert call.full_url.endswith("/Calls.json")
    call_form = parse_qs(call.data.decode())
    assert call_form["To"] == ["+13105550100"]
    assert "Polly.Joanna" in call_form["Twiml"][0]
    assert "Hello from Hermes." in call_form["Twiml"][0]
    assert call_form["SendDigits"] == ["ww1"]


def test_twilio_call_requires_exactly_one_prompt():
    client = TwilioClient("AC123", "auth-token", "+13105550000")
    with pytest.raises(Exception, match="exactly one"):
        client.call("+13105550100")
