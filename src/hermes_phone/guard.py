"""Outbound guard: allowlist, confirmation, daily caps, quiet hours, audit log.

Refusals happen before any provider code runs. Allowed actions are logged
after the provider returns, including provider errors, and those attempts
count toward the daily caps. The cap is fail-closed: a call that errors after
we decided to send still consumes a slot, because the provider may have
accepted it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from hermes_phone.audit import append_entry, locked_log, parse_timestamp, read_entries
from hermes_phone.config import Settings
from hermes_phone.errors import GuardRefusal, PhoneError
from hermes_phone.numbers import is_emergency, mask_phone, normalize_phone
from hermes_phone.pricing import money

_QUIET_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")
OUTBOUND_KINDS = {"sms", "ai-call", "twilio-call"}


@dataclass
class Action:
    kind: str
    provider: str
    to: str | None = None
    summary: str = ""
    estimated_cost: Decimal = Decimal("0")
    counts_as_call: bool = False
    counts_as_text: bool = False
    needs_confirmation: bool = False
    needs_allowlist: bool = False


@dataclass
class Usage:
    calls: int
    texts: int
    dollars: Decimal


def quiet_spec_ok(spec: str) -> None:
    if spec == "":
        return
    if not _QUIET_RE.match(spec):
        raise PhoneError(
            "PHONE_QUIET_HOURS must be HH:MM-HH:MM (24-hour, local to PHONE_TIMEZONE) "
            f"or empty to disable, got {spec!r}."
        )
    match = _QUIET_RE.match(spec)
    assert match is not None
    for hour, minute in ((int(match.group(1)), int(match.group(2))), (int(match.group(3)), int(match.group(4)))):
        if hour > 23 or minute > 59:
            raise PhoneError(f"PHONE_QUIET_HOURS has an impossible clock time: {spec}")


def in_quiet_hours(now: datetime, spec: str) -> bool:
    quiet_spec_ok(spec)
    if spec == "":
        return False
    match = _QUIET_RE.match(spec)
    assert match is not None
    start = int(match.group(1)) * 60 + int(match.group(2))
    end = int(match.group(3)) * 60 + int(match.group(4))
    if start == end:
        return False
    minutes = now.hour * 60 + now.minute
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end


def usage_on(entries: list[dict[str, Any]], day: datetime) -> Usage:
    calls = 0
    texts = 0
    dollars = Decimal("0")
    target = day.date()
    for entry in entries:
        if entry.get("decision") != "allowed":
            continue
        if entry.get("kind") not in OUTBOUND_KINDS:
            continue
        try:
            stamp = parse_timestamp(str(entry.get("ts")))
        except ValueError as exc:
            raise PhoneError(f"Audit log has an unreadable ts: {entry.get('ts')!r}") from exc
        if stamp.tzinfo is None:
            raise PhoneError("Audit log ts values must include a timezone offset.")
        if stamp.astimezone(day.tzinfo).date() != target:
            continue
        if entry.get("counts_as_call"):
            calls += 1
        if entry.get("counts_as_text"):
            texts += 1
        dollars += Decimal(str(entry.get("estimated_cost_usd") or "0"))
    return Usage(calls=calls, texts=texts, dollars=dollars)


class Guard:
    def __init__(self, settings: Settings):
        self.settings = settings
        quiet_spec_ok(settings.quiet_hours)

    def usage(self, now: datetime) -> Usage:
        with locked_log(self.settings.log_path) as fd:
            return usage_on(read_entries(fd, self.settings.log_path), now)

    def run(
        self,
        action: Action,
        *,
        confirmed: bool,
        now: datetime,
        execute: Callable[[], dict[str, Any]],
        preflight: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if now.tzinfo is None:
            raise PhoneError("Guard clock must be timezone-aware.")
        local_now = now.astimezone(self.settings.timezone)
        masked = mask_phone(action.to) if action.to else ""
        normalized = ""
        refusal: str | None = None

        if action.to:
            if is_emergency(action.to):
                refusal = "Refusing to dial an emergency number."
            else:
                try:
                    normalized = normalize_phone(action.to)
                except PhoneError as exc:
                    refusal = str(exc)

        if refusal is None and action.needs_allowlist:
            if not normalized or normalized not in self.settings.allowlist:
                refusal = (
                    f"{masked or action.to} is not on the allowlist. "
                    "The allowlist is empty by default. Add the number only if it is yours "
                    "or the person has opted in."
                )
        if refusal is None and action.needs_allowlist and in_quiet_hours(local_now, self.settings.quiet_hours):
            refusal = (
                f"Quiet hours are {self.settings.quiet_hours} "
                f"({self.settings.timezone.key}). It is {local_now.strftime('%H:%M')} there."
            )

        with locked_log(self.settings.log_path) as fd:
            entries = read_entries(fd, self.settings.log_path)
            usage = usage_on(entries, local_now)
            if refusal is None and action.counts_as_call and usage.calls + 1 > self.settings.max_calls_per_day:
                refusal = (
                    f"Daily call cap is {self.settings.max_calls_per_day}. "
                    f"Already used {usage.calls} today ({self.settings.timezone.key})."
                )
            if refusal is None and action.counts_as_text and usage.texts + 1 > self.settings.max_texts_per_day:
                refusal = (
                    f"Daily text cap is {self.settings.max_texts_per_day}. "
                    f"Already used {usage.texts} today ({self.settings.timezone.key})."
                )
            projected = usage.dollars + action.estimated_cost
            if (
                refusal is None
                and action.kind in OUTBOUND_KINDS
                and projected > self.settings.max_dollars_per_day
            ):
                refusal = (
                    f"Daily dollar cap is ${self.settings.max_dollars_per_day}. "
                    f"Today is already ${money(usage.dollars)} and this action estimates "
                    f"${money(action.estimated_cost)}."
                )
            if refusal is None and action.needs_confirmation and not confirmed:
                refusal = (
                    "A person has to confirm this outbound action. "
                    "At a terminal, type yes. From a script or an agent, pass --confirm "
                    "only after a person has agreed to this exact message or call."
                )

            result: dict[str, Any] | None = None
            error = ""
            config_error = ""
            if refusal is None and preflight is not None:
                try:
                    preflight()
                except PhoneError as exc:
                    config_error = str(exc)
            if refusal is None and not config_error:
                try:
                    result = execute()
                except Exception as exc:
                    error = str(exc)
                    result = {"success": False, "error": error}

            if refusal:
                decision = "refused"
            elif config_error:
                decision = "error"
            else:
                decision = "allowed"
            counted = decision == "allowed"
            entry = {
                "ts": local_now.isoformat(),
                "kind": action.kind,
                "provider": action.provider,
                "decision": decision,
                "reason": refusal or config_error,
                "confirmed": bool(confirmed),
                "to": normalized,
                "to_masked": masked,
                "summary": action.summary[:2000],
                "summary_truncated": len(action.summary) > 2000,
                "estimated_cost_usd": money(action.estimated_cost if counted else Decimal("0")),
                "counts_as_call": bool(action.counts_as_call and counted),
                "counts_as_text": bool(action.counts_as_text and counted),
                "vendor_spend_usd": "0",
                "result": result,
                "error": error,
            }
            append_entry(fd, entry)

        if refusal:
            raise GuardRefusal(refusal, reason=refusal, action=action.kind, masked=masked)
        if config_error:
            raise PhoneError(config_error)
        if error:
            raise PhoneError(error)
        assert result is not None
        result = dict(result)
        result["guard"] = {
            "confirmed": bool(confirmed),
            "estimated_cost_usd": money(action.estimated_cost),
            "vendor_spend_usd": entry["vendor_spend_usd"],
            "log": str(self.settings.log_path),
            "orchestrator": self.settings.orchestrator,
        }
        return result
