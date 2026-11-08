"""Registry keyed on the orchestrator name. See issue 66963."""

from __future__ import annotations

from hermes_phone.config import Settings
from hermes_phone.errors import PhoneError
from hermes_phone.orchestrators.base import Orchestrator
from hermes_phone.orchestrators.bland import BlandOrchestrator
from hermes_phone.orchestrators.mock import MockOrchestrator
from hermes_phone.orchestrators.vapi import VapiOrchestrator

__all__ = [
    "BlandOrchestrator",
    "MockOrchestrator",
    "Orchestrator",
    "VapiOrchestrator",
    "get_orchestrator",
]


def get_orchestrator(name: str, settings: Settings) -> Orchestrator:
    key = name.strip().lower()
    if key == "mock":
        return MockOrchestrator(settings.mock_state_path)
    if key == "bland":
        return BlandOrchestrator(settings.bland_api_key, default_voice=settings.bland_voice)
    if key == "vapi":
        return VapiOrchestrator(
            settings.vapi_api_key,
            phone_number_id=settings.vapi_phone_number_id,
            voice_provider=settings.vapi_voice_provider,
            voice_id=settings.vapi_voice_id,
            model=settings.vapi_model,
        )
    raise PhoneError(
        f"Unsupported orchestrator {name!r}. Use mock, bland, or vapi. "
        "Upstream Hermes telephony.py accepts only bland or vapi."
    )
