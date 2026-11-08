"""Bland.ai adapter.

Request shape copied from ``_bland_call`` and ``_bland_status`` in
``optional-skills/productivity/telephony/scripts/telephony.py`` at Hermes
v0.23.0 (commit 2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19).
"""

from __future__ import annotations

from typing import Any

from hermes_phone.errors import PhoneError
from hermes_phone.http_client import json_request
from hermes_phone.numbers import mask_phone, normalize_phone
from hermes_phone.orchestrators.base import Orchestrator

BLAND_API_BASE = "https://api.bland.ai/v1"
BLAND_DEFAULT_VOICE = "mason"
BLAND_DEFAULT_MODEL = "enhanced"


class BlandOrchestrator(Orchestrator):
    name = "bland"

    def __init__(self, api_key: str, *, default_voice: str = BLAND_DEFAULT_VOICE):
        if not api_key:
            raise PhoneError(
                "Bland.ai is not configured. Use 'save-bland' or set BLAND_API_KEY "
                "in the Hermes .env file."
            )
        self.api_key = api_key
        self.default_voice = default_voice or BLAND_DEFAULT_VOICE

    def place_call(
        self,
        phone_number: str,
        task: str,
        *,
        voice: str | None = None,
        first_sentence: str | None = None,
        max_duration: int = 3,
    ) -> dict[str, Any]:
        normalized = normalize_phone(phone_number)
        chosen = voice or self.default_voice
        body: dict[str, Any] = {
            "phone_number": normalized,
            "task": task,
            "voice": chosen,
            "model": BLAND_DEFAULT_MODEL,
            "max_duration": max_duration,
            "record": True,
            "wait_for_greeting": True,
        }
        if first_sentence:
            body["first_sentence"] = first_sentence
        payload = json_request(
            "POST",
            f"{BLAND_API_BASE}/calls",
            headers={"authorization": self.api_key},
            json_body=body,
        )
        call_id = str(payload.get("call_id") or "")
        if not call_id:
            raise PhoneError(f"Bland.ai returned no call_id: {payload}")
        return {
            "success": True,
            "provider": "bland",
            "call_id": call_id,
            "voice": chosen,
            "max_duration_minutes": max_duration,
            "to_phone_number_masked": mask_phone(normalized),
            "message": "AI call queued with Bland.ai.",
        }

    def call_status(self, call_id: str, *, analyze: str | None = None) -> dict[str, Any]:
        payload = json_request(
            "GET",
            f"{BLAND_API_BASE}/calls/{call_id}",
            headers={"authorization": self.api_key},
        )
        result: dict[str, Any] = {
            "success": True,
            "provider": "bland",
            "call_id": call_id,
            "status": payload.get("status"),
            "answered_by": payload.get("answered_by"),
            "duration_minutes": payload.get("call_length"),
            "transcript": payload.get("concatenated_transcript", ""),
            "recording_url": payload.get("recording_url"),
        }
        if analyze and payload.get("status") == "completed":
            questions = [[q.strip(), "string"] for q in analyze.split(",") if q.strip()]
            if questions:
                analysis = json_request(
                    "POST",
                    f"{BLAND_API_BASE}/calls/{call_id}/analyze",
                    headers={"authorization": self.api_key},
                    json_body={"questions": questions},
                )
                result["analysis"] = analysis
        return result
