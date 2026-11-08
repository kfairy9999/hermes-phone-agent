"""E.164 checks aligned with the Hermes telephony script.

The official script normalizes numbers in ``_normalize_phone`` and masks them
in ``_mask_phone``. Those rules are reproduced here so the wrapper accepts the
same numbers the skill accepts. Emergency short codes are refused here even
when they fail the length check, because the skill's safety rules forbid them.
"""

from __future__ import annotations

import re

from hermes_phone.errors import PhoneError

# Short codes the official skill forbids dialing. 1911/1988 catch a leading
# country digit glued onto the US emergency and crisis numbers.
EMERGENCY_DIGITS = {"911", "988", "112", "999", "000", "1911", "1988"}


def digits_only(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def is_emergency(number: str) -> bool:
    return digits_only(number) in EMERGENCY_DIGITS


def normalize_phone(number: str) -> str:
    """Return E.164 or raise ``PhoneError`` with the upstream wording."""
    if is_emergency(number):
        raise PhoneError("Refusing to dial an emergency number.")
    if not number:
        raise PhoneError("Phone number is required")
    trimmed = number.strip()
    if not trimmed.startswith("+"):
        raise PhoneError(
            f"Phone number must be E.164 format (for example +15551234567), got: {number}"
        )
    digits = "+" + re.sub(r"\D", "", trimmed)
    if len(digits) < 8:
        raise PhoneError(f"Phone number looks too short: {number}")
    return digits


def mask_phone(number: str) -> str:
    digits = digits_only(number)
    if len(digits) < 4:
        return "***"
    return f"***-***-{digits[-4:]}"
