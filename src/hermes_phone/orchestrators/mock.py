"""Dry-run orchestrator. No network, no vendor spend.

State is a JSON file so ``ai-status`` works from a later process. That file is
rewritten. The audit log is a different file and is append-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hermes_phone.errors import PhoneError
from hermes_phone.numbers import mask_phone, normalize_phone
from hermes_phone.orchestrators.base import Orchestrator


class MockOrchestrator(Orchestrator):
    name = "mock"

    def __init__(self, state_path: Path):
        self.state_path = state_path

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"calls": {}, "imports": []}
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"calls": {}, "imports": []}
        data.setdefault("calls", {})
        data.setdefault("imports", [])
        return data

    def _save(self, state: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

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
        state = self._load()
        call_id = f"mock-call-{len(state['calls']) + 1}"
        opening = first_sentence or "Hello, this is a mock call."
        transcript = (
            f"agent: {opening}\n"
            f"agent: {task}\n"
            "user: Okay, thanks.\n"
        )
        state["calls"][call_id] = {
            "to": normalized,
            "task": task,
            "voice": voice or "mock",
            "max_duration": max_duration,
            "status": "completed",
            "transcript": transcript,
            "answered_by": "human",
            "call_length": 1,
        }
        self._save(state)
        return {
            "success": True,
            "provider": "mock",
            "mock": True,
            "call_id": call_id,
            "status": "queued",
            "voice": voice or "mock",
            "max_duration_minutes": max_duration,
            "to_phone_number_masked": mask_phone(normalized),
            "vendor_spend_usd": "0",
            "message": "AI call queued with the mock provider. No account was contacted.",
        }

    def call_status(self, call_id: str, *, analyze: str | None = None) -> dict[str, Any]:
        state = self._load()
        record = state["calls"].get(call_id)
        if not isinstance(record, dict):
            raise PhoneError(f"Mock provider has no call {call_id}.")
        result: dict[str, Any] = {
            "success": True,
            "provider": "mock",
            "mock": True,
            "call_id": call_id,
            "status": record.get("status", "completed"),
            "answered_by": record.get("answered_by"),
            "duration_minutes": record.get("call_length"),
            "transcript": record.get("transcript", ""),
            "recording_url": None,
            "to_phone_number_masked": mask_phone(str(record.get("to") or "")),
            "vendor_spend_usd": "0",
            "message": "Mock status. Nothing was dialed.",
        }
        if analyze and record.get("status") == "completed":
            result["analysis"] = {
                "questions": [[q.strip(), "string"] for q in analyze.split(",") if q.strip()],
                "answers": ["mock: not a real conversation" for q in analyze.split(",") if q.strip()],
            }
        return result

    def import_twilio_number(
        self,
        *,
        phone_number: str,
        account_sid: str,
        auth_token: str,
    ) -> dict[str, Any]:
        del account_sid, auth_token
        normalized = normalize_phone(phone_number)
        state = self._load()
        phone_number_id = f"mock-vapi-phone-{len(state['imports']) + 1}"
        state["imports"].append({"phone_number": normalized, "id": phone_number_id})
        self._save(state)
        return {
            "success": True,
            "provider": "mock",
            "mock": True,
            "phone_number_id": phone_number_id,
            "phone_number": normalized,
            "vendor_spend_usd": "0",
            "message": "Mock Vapi import. Twilio and Vapi were not contacted.",
        }
