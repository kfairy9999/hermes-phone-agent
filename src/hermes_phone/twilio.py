"""Twilio SMS and direct calls.

Live requests match ``_twilio_send_sms`` and ``_twilio_call`` in the pinned
telephony script. The official script can also search owned numbers and fall
back to the only number on the account. This wrapper sends from
``TWILIO_PHONE_NUMBER`` (or ``--from-number``) and does not list the account.
Number search, purchase, and inbox polling stay on the official script.
"""

from __future__ import annotations

import json
from html import escape as xml_escape
from pathlib import Path
from typing import Any

from hermes_phone.errors import PhoneError
from hermes_phone.http_client import json_request
from hermes_phone.numbers import mask_phone, normalize_phone

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"
TWILIO_DEFAULT_TTS_VOICE = "Polly.Joanna"


def twiml_say(message: str, voice: str) -> str:
    return f'<Response><Say voice="{xml_escape(voice)}">{xml_escape(message)}</Say></Response>'


def twiml_play(audio_url: str) -> str:
    return f"<Response><Play>{xml_escape(audio_url)}</Play></Response>"


class TwilioClient:
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        if not account_sid or not auth_token:
            raise PhoneError(
                "Twilio credentials are not configured. Use 'save-twilio' or set "
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in the Hermes .env file."
            )
        if not from_number:
            raise PhoneError(
                "No default Twilio phone number is set. Use 'twilio-buy --save-env', "
                "'twilio-set-default', or set TWILIO_PHONE_NUMBER in the Hermes .env file."
            )
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = normalize_phone(from_number)
        token = f"{account_sid}:{auth_token}".encode()
        import base64

        self._auth = base64.b64encode(token).decode("ascii")

    def _form(self, path: str, form: dict[str, Any]) -> dict[str, Any]:
        return json_request(
            "POST",
            f"{TWILIO_API_BASE}/{self.account_sid}/{path}",
            headers={"Authorization": f"Basic {self._auth}"},
            form=form,
        )

    def send_sms(
        self,
        to_number: str,
        body: str,
        *,
        media_urls: list[str] | None = None,
        from_number: str | None = None,
    ) -> dict[str, Any]:
        destination = normalize_phone(to_number)
        source = normalize_phone(from_number) if from_number else self.from_number
        if not body.strip():
            raise PhoneError("SMS body cannot be empty")
        form: dict[str, Any] = {"To": destination, "From": source, "Body": body}
        if media_urls:
            form["MediaUrl"] = media_urls
        payload = self._form("Messages.json", form)
        return {
            "success": True,
            "provider": "twilio",
            "message_sid": payload.get("sid"),
            "status": payload.get("status"),
            "from_phone_number": source,
            "to_phone_number_masked": mask_phone(destination),
            "media_count": len(media_urls or []),
            "message": "SMS/MMS queued via Twilio.",
        }

    def call(
        self,
        to_number: str,
        *,
        message: str | None = None,
        audio_url: str | None = None,
        voice: str = TWILIO_DEFAULT_TTS_VOICE,
        send_digits: str | None = None,
        from_number: str | None = None,
        record: bool = False,
    ) -> dict[str, Any]:
        destination = normalize_phone(to_number)
        source = normalize_phone(from_number) if from_number else self.from_number
        if bool(message) == bool(audio_url):
            raise PhoneError("Provide exactly one of 'message' or 'audio_url' for twilio-call")
        twiml = twiml_play(audio_url) if audio_url else twiml_say(message or "", voice)
        form: dict[str, Any] = {"To": destination, "From": source, "Twiml": twiml}
        if send_digits:
            form["SendDigits"] = send_digits
        if record:
            form["Record"] = "true"
        payload = self._form("Calls.json", form)
        return {
            "success": True,
            "provider": "twilio",
            "call_sid": payload.get("sid"),
            "status": payload.get("status"),
            "from_phone_number": source,
            "to_phone_number_masked": mask_phone(destination),
            "mode": "play" if audio_url else "say",
            "recording_requested": record,
            "message": "Twilio call initiated.",
        }


class MockTwilio:
    """Simulates Twilio SMS and direct calls. Writes the same mock state file."""

    def __init__(self, state_path: Path, from_number: str = "+13105550000"):
        self.state_path = state_path
        self.from_number = from_number

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"messages": [], "direct_calls": []}
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"messages": [], "direct_calls": []}
        data.setdefault("messages", [])
        data.setdefault("direct_calls", [])
        return data

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def send_sms(
        self,
        to_number: str,
        body: str,
        *,
        media_urls: list[str] | None = None,
        from_number: str | None = None,
    ) -> dict[str, Any]:
        destination = normalize_phone(to_number)
        source = normalize_phone(from_number) if from_number else self.from_number
        if not body.strip():
            raise PhoneError("SMS body cannot be empty")
        state = self._load()
        sid = f"SM_mock_{len(state['messages']) + 1}"
        state["messages"].append(
            {
                "sid": sid,
                "to": destination,
                "from": source,
                "body": body,
                "media": list(media_urls or []),
                "status": "queued",
            }
        )
        self._save(state)
        return {
            "success": True,
            "provider": "mock",
            "mock": True,
            "message_sid": sid,
            "status": "queued",
            "from_phone_number": source,
            "to_phone_number_masked": mask_phone(destination),
            "media_count": len(media_urls or []),
            "vendor_spend_usd": "0",
            "message": "SMS queued with the mock provider. Twilio was not contacted.",
        }

    def call(
        self,
        to_number: str,
        *,
        message: str | None = None,
        audio_url: str | None = None,
        voice: str = TWILIO_DEFAULT_TTS_VOICE,
        send_digits: str | None = None,
        from_number: str | None = None,
        record: bool = False,
    ) -> dict[str, Any]:
        destination = normalize_phone(to_number)
        source = normalize_phone(from_number) if from_number else self.from_number
        if bool(message) == bool(audio_url):
            raise PhoneError("Provide exactly one of 'message' or 'audio_url' for twilio-call")
        state = self._load()
        sid = f"CA_mock_{len(state['direct_calls']) + 1}"
        state["direct_calls"].append(
            {
                "sid": sid,
                "to": destination,
                "from": source,
                "message": message,
                "audio_url": audio_url,
                "voice": voice,
                "send_digits": send_digits,
                "record": record,
                "status": "completed",
            }
        )
        self._save(state)
        return {
            "success": True,
            "provider": "mock",
            "mock": True,
            "call_sid": sid,
            "status": "queued",
            "from_phone_number": source,
            "to_phone_number_masked": mask_phone(destination),
            "mode": "play" if audio_url else "say",
            "recording_requested": record,
            "vendor_spend_usd": "0",
            "message": "Direct call queued with the mock provider. Twilio was not contacted.",
        }
