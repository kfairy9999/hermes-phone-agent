"""Orchestrator interface from Nous Research issue 66963.

The proposed upstream shape is an abstract orchestrator with one adapter per
voice-AI backend. ``ai-call``, ``ai-status``, and ``vapi-import-twilio`` keep
their existing flags. This repo adds ``mock`` beside ``bland`` and ``vapi``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hermes_phone.errors import PhoneError


class Orchestrator(ABC):
    name: str

    @abstractmethod
    def place_call(
        self,
        phone_number: str,
        task: str,
        *,
        voice: str | None = None,
        first_sentence: str | None = None,
        max_duration: int = 3,
    ) -> dict[str, Any]:
        """Place an outbound AI call. ``max_duration`` is minutes, as in the skill."""

    @abstractmethod
    def call_status(self, call_id: str, *, analyze: str | None = None) -> dict[str, Any]:
        """Return status, and Bland analysis when ``analyze`` is set."""

    def import_twilio_number(
        self,
        *,
        phone_number: str,
        account_sid: str,
        auth_token: str,
    ) -> dict[str, Any]:
        raise PhoneError(
            f"{self.name} does not import Twilio numbers. "
            "vapi-import-twilio is a Vapi operation in the telephony skill."
        )
