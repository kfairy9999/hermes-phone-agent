"""Vapi adapter.

Request shape copied from ``_vapi_call``, ``_vapi_status``, and
``_vapi_import_twilio_number`` in the pinned telephony script.
"""

from __future__ import annotations

from typing import Any

from hermes_phone.errors import PhoneError
from hermes_phone.http_client import json_request
from hermes_phone.numbers import mask_phone, normalize_phone
from hermes_phone.orchestrators.base import Orchestrator

VAPI_API_BASE = "https://api.vapi.ai"
VAPI_DEFAULT_VOICE_PROVIDER = "11labs"
VAPI_DEFAULT_VOICE_ID = "cjVigY5qzO86Huf0OWal"  # ElevenLabs "Eric" in the skill
VAPI_DEFAULT_MODEL = "gpt-4o"


class VapiOrchestrator(Orchestrator):
    name = "vapi"

    def __init__(
        self,
        api_key: str,
        *,
        phone_number_id: str = "",
        voice_provider: str = VAPI_DEFAULT_VOICE_PROVIDER,
        voice_id: str = VAPI_DEFAULT_VOICE_ID,
        model: str = VAPI_DEFAULT_MODEL,
    ):
        if not api_key:
            raise PhoneError(
                "Vapi is not configured. Use 'save-vapi' or set VAPI_API_KEY "
                "in the Hermes .env file."
            )
        self.api_key = api_key
        self.phone_number_id = phone_number_id
        self.voice_provider = voice_provider or VAPI_DEFAULT_VOICE_PROVIDER
        self.voice_id = voice_id or VAPI_DEFAULT_VOICE_ID
        self.model = model or VAPI_DEFAULT_MODEL

    def place_call(
        self,
        phone_number: str,
        task: str,
        *,
        voice: str | None = None,
        first_sentence: str | None = None,
        max_duration: int = 3,
    ) -> dict[str, Any]:
        if not self.phone_number_id:
            raise PhoneError(
                "No Vapi phone number id is configured. Import an owned Twilio number with "
                "'vapi-import-twilio --save-env' or set VAPI_PHONE_NUMBER_ID in the Hermes .env file."
            )
        normalized = normalize_phone(phone_number)
        voice_id = voice or self.voice_id
        assistant: dict[str, Any] = {
            "model": {
                "provider": "openai",
                "model": self.model,
                "messages": [{"role": "system", "content": task}],
            },
            "voice": {"provider": self.voice_provider, "voiceId": voice_id},
            "maxDurationSeconds": max_duration * 60,
        }
        if first_sentence:
            assistant["firstMessage"] = first_sentence
        payload = json_request(
            "POST",
            f"{VAPI_API_BASE}/call",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "phoneNumberId": self.phone_number_id,
                "customer": {"number": normalized},
                "assistant": assistant,
            },
        )
        call_id = str(payload.get("id") or "")
        if not call_id:
            raise PhoneError(f"Vapi returned no call id: {payload}")
        return {
            "success": True,
            "provider": "vapi",
            "call_id": call_id,
            "voice_provider": self.voice_provider,
            "voice_id": voice_id,
            "max_duration_minutes": max_duration,
            "to_phone_number_masked": mask_phone(normalized),
            "message": "AI call queued with Vapi.",
        }

    def call_status(self, call_id: str, *, analyze: str | None = None) -> dict[str, Any]:
        # The upstream script ignores --analyze for Vapi. Match that.
        del analyze
        payload = json_request(
            "GET",
            f"{VAPI_API_BASE}/call/{call_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return {
            "success": True,
            "provider": "vapi",
            "call_id": call_id,
            "status": payload.get("status"),
            "duration_seconds": payload.get("duration"),
            "ended_reason": payload.get("endedReason"),
            "transcript": payload.get("transcript", ""),
            "recording_url": payload.get("recordingUrl"),
            "summary": payload.get("summary"),
            "cost": payload.get("cost"),
        }

    def import_twilio_number(
        self,
        *,
        phone_number: str,
        account_sid: str,
        auth_token: str,
    ) -> dict[str, Any]:
        normalized = normalize_phone(phone_number)
        if not account_sid or not auth_token:
            raise PhoneError(
                "Twilio credentials are not configured. Use 'save-twilio' or set "
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in the Hermes .env file."
            )
        payload = json_request(
            "POST",
            f"{VAPI_API_BASE}/phone-number",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json_body={
                "provider": "twilio",
                "number": normalized,
                "twilioAccountSid": account_sid,
                "twilioAuthToken": auth_token,
            },
        )
        phone_number_id = str(payload.get("id") or "")
        if not phone_number_id:
            raise PhoneError(f"Vapi did not return a phone number id: {payload}")
        return {
            "success": True,
            "provider": "vapi",
            "phone_number_id": phone_number_id,
            "phone_number": normalized,
            "message": "Twilio number imported into Vapi.",
        }
