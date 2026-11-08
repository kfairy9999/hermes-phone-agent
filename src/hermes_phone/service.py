"""Glue the guard to the Twilio client and the voice orchestrators."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from hermes_phone.config import Settings
from hermes_phone.envfile import upsert_env_file
from hermes_phone.errors import PhoneError
from hermes_phone.guard import Action, Guard
from hermes_phone.numbers import mask_phone, normalize_phone
from hermes_phone.orchestrators import get_orchestrator
from hermes_phone.pricing import estimate_call_minutes, estimate_sms
from hermes_phone.twilio import MockTwilio, TwilioClient


class PhoneService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.guard = Guard(settings)

    def _now(self) -> datetime:
        return datetime.now(self.settings.timezone)

    def _sms_client(self) -> MockTwilio | TwilioClient:
        if self.settings.orchestrator == "mock":
            from_number = self.settings.twilio_phone_number or "+13105550000"
            return MockTwilio(self.settings.mock_state_path, from_number=from_number)
        return TwilioClient(
            self.settings.twilio_account_sid,
            self.settings.twilio_auth_token,
            self.settings.twilio_phone_number,
        )

    def diagnose(self) -> dict[str, Any]:
        now = self._now()
        usage = self.guard.usage(now)
        quiet = in_quiet(now, self.settings.quiet_hours)
        return {
            "success": True,
            "wrapper": "hermes-phone-agent",
            "orchestrator": self.settings.orchestrator,
            "phone_provider": self.settings.phone_provider or None,
            "provider_note": self.settings.mismatch or None,
            "mock": self.settings.orchestrator == "mock",
            "spend": (
                "Mock mode places no vendor calls and sends no texts."
                if self.settings.orchestrator == "mock"
                else "Live mode can spend money at the selected provider."
            ),
            "allowlist_count": len(self.settings.allowlist),
            "allowlist_masked": [mask_phone(number) for number in self.settings.allowlist],
            "quiet_hours": self.settings.quiet_hours or None,
            "quiet_hours_active": quiet,
            "timezone": self.settings.timezone.key,
            "local_time": now.isoformat(),
            "caps": {
                "calls_per_day": self.settings.max_calls_per_day,
                "texts_per_day": self.settings.max_texts_per_day,
                "dollars_per_day": str(self.settings.max_dollars_per_day),
            },
            "today": {
                "calls": usage.calls,
                "texts": usage.texts,
                "estimated_usd": str(usage.dollars),
            },
            "providers": {
                "twilio": {
                    "account_sid_configured": bool(self.settings.twilio_account_sid),
                    "auth_token_configured": bool(self.settings.twilio_auth_token),
                    "phone_number_configured": bool(self.settings.twilio_phone_number),
                },
                "bland": {
                    "configured": bool(self.settings.bland_api_key),
                    "default_voice": self.settings.bland_voice,
                },
                "vapi": {
                    "configured": bool(self.settings.vapi_api_key),
                    "phone_number_id_configured": bool(self.settings.vapi_phone_number_id),
                },
            },
            "log_path": str(self.settings.log_path),
            "allowlist_file": str(self.settings.allowlist_file),
            "official_script": (
                "Provisioning, inbox polling, and credential helpers stay on the official "
                "telephony.py. This wrapper is the outbound guard."
            ),
        }

    def allow_list(self) -> dict[str, Any]:
        return {
            "success": True,
            "count": len(self.settings.allowlist),
            "numbers": list(self.settings.allowlist),
            "file": str(self.settings.allowlist_file),
        }

    def allow_add(self, number: str) -> dict[str, Any]:
        normalized = normalize_phone(number)
        path = self.settings.allowlist_file
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else "# E.164 numbers. One per line. Empty denies all outbound.\n"
        lines = [line.strip() for line in existing.splitlines()]
        if normalized not in lines:
            if existing and not existing.endswith("\n"):
                existing += "\n"
            path.write_text(existing + normalized + "\n", encoding="utf-8")
        return {
            "success": True,
            "added": normalized,
            "file": str(path),
            "message": "Allowlist updated. The new number is visible to the next command.",
        }

    def send_sms(
        self,
        to_number: str,
        body: str,
        *,
        confirmed: bool,
        media_urls: list[str] | None = None,
        from_number: str = "",
    ) -> dict[str, Any]:
        provider = "mock" if self.settings.orchestrator == "mock" else "twilio"
        action = Action(
            kind="sms",
            provider=provider,
            to=to_number,
            summary=body,
            estimated_cost=estimate_sms(body, media=bool(media_urls)),
            counts_as_text=True,
            needs_confirmation=True,
            needs_allowlist=True,
        )

        def preflight() -> None:
            if not body.strip():
                raise PhoneError("SMS body cannot be empty")
            if provider == "twilio":
                TwilioClient(
                    self.settings.twilio_account_sid,
                    self.settings.twilio_auth_token,
                    from_number or self.settings.twilio_phone_number,
                )

        def execute() -> dict[str, Any]:
            client = self._sms_client()
            return client.send_sms(
                to_number,
                body,
                media_urls=media_urls,
                from_number=from_number or None,
            )

        return self.guard.run(
            action, confirmed=confirmed, now=self._now(), execute=execute, preflight=preflight
        )

    def direct_call(
        self,
        to_number: str,
        *,
        confirmed: bool,
        message: str = "",
        audio_url: str = "",
        voice: str = "Polly.Joanna",
        send_digits: str = "",
        from_number: str = "",
        record: bool = False,
    ) -> dict[str, Any]:
        provider = "mock" if self.settings.orchestrator == "mock" else "twilio"
        action = Action(
            kind="twilio-call",
            provider=provider,
            to=to_number,
            summary=message or audio_url,
            estimated_cost=estimate_call_minutes("twilio", 1),
            counts_as_call=True,
            needs_confirmation=True,
            needs_allowlist=True,
        )

        def preflight() -> None:
            if provider == "twilio":
                TwilioClient(
                    self.settings.twilio_account_sid,
                    self.settings.twilio_auth_token,
                    from_number or self.settings.twilio_phone_number,
                )
            if bool(message) == bool(audio_url):
                raise PhoneError("Provide exactly one of 'message' or 'audio_url' for twilio-call")

        def execute() -> dict[str, Any]:
            client = self._sms_client()
            return client.call(
                to_number,
                message=message or None,
                audio_url=audio_url or None,
                voice=voice,
                send_digits=send_digits or None,
                from_number=from_number or None,
                record=record,
            )

        return self.guard.run(
            action, confirmed=confirmed, now=self._now(), execute=execute, preflight=preflight
        )

    def ai_call(
        self,
        to_number: str,
        task: str,
        *,
        confirmed: bool,
        voice: str = "",
        first_sentence: str = "",
        max_duration: int = 3,
    ) -> dict[str, Any]:
        if not task.strip():
            raise PhoneError("AI call task cannot be empty")
        if max_duration < 1:
            raise PhoneError("--max-duration is minutes and must be at least 1, matching the skill default of 3.")
        provider = self.settings.orchestrator
        action = Action(
            kind="ai-call",
            provider=provider,
            to=to_number,
            summary=task,
            estimated_cost=estimate_call_minutes(provider, max_duration),
            counts_as_call=True,
            needs_confirmation=True,
            needs_allowlist=True,
        )

        def preflight() -> None:
            # Constructing the adapter checks keys without placing the call.
            get_orchestrator(provider, self.settings)

        def execute() -> dict[str, Any]:
            orchestrator = get_orchestrator(provider, self.settings)
            return orchestrator.place_call(
                to_number,
                task,
                voice=voice or None,
                first_sentence=first_sentence or None,
                max_duration=max_duration,
            )

        return self.guard.run(
            action, confirmed=confirmed, now=self._now(), execute=execute, preflight=preflight
        )

    def ai_status(self, call_id: str, *, analyze: str = "") -> dict[str, Any]:
        provider = self.settings.orchestrator
        action = Action(kind="ai-status", provider=provider, summary=call_id, estimated_cost=Decimal("0"))

        def execute() -> dict[str, Any]:
            orchestrator = get_orchestrator(provider, self.settings)
            return orchestrator.call_status(call_id, analyze=analyze or None)

        return self.guard.run(action, confirmed=True, now=self._now(), execute=execute)

    def import_twilio(self, *, confirmed: bool, phone_number: str = "", save_env: bool = False) -> dict[str, Any]:
        if self.settings.orchestrator == "mock" and save_env:
            raise PhoneError(
                "--save-env would write VAPI_PHONE_NUMBER_ID into the Hermes .env file. "
                "Refusing that in mock mode."
            )
        if self.settings.orchestrator not in {"mock", "vapi"}:
            raise PhoneError(
                "vapi-import-twilio is a Vapi operation. "
                f"The selected orchestrator is {self.settings.orchestrator}."
            )
        number = phone_number or self.settings.twilio_phone_number
        if not number:
            raise PhoneError(
                "No default Twilio phone number is set. Pass the owned E.164 number or set TWILIO_PHONE_NUMBER."
            )
        action = Action(
            kind="vapi-import",
            provider=self.settings.orchestrator,
            to=number,
            summary="import Twilio number into Vapi",
            needs_confirmation=True,
            needs_allowlist=False,
        )

        def execute() -> dict[str, Any]:
            orchestrator = get_orchestrator(self.settings.orchestrator, self.settings)
            result = orchestrator.import_twilio_number(
                phone_number=number,
                account_sid=self.settings.twilio_account_sid,
                auth_token=self.settings.twilio_auth_token,
            )
            if save_env:
                upsert_env_file(
                    self.settings.home / ".env",
                    {"VAPI_PHONE_NUMBER_ID": str(result["phone_number_id"])},
                )
                result["saved_env_keys"] = ["VAPI_PHONE_NUMBER_ID"]
                result["env_path"] = str(self.settings.home / ".env")
            return result

        return self.guard.run(action, confirmed=confirmed, now=self._now(), execute=execute)


def in_quiet(now: datetime, spec: str) -> bool:
    from hermes_phone.guard import in_quiet_hours

    return in_quiet_hours(now, spec)
