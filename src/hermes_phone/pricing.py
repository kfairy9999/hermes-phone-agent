"""Pre-call cost estimates used by the daily dollar cap.

These are published list prices, not invoices. The cap commits the estimate
before the provider is contacted. Carrier fees, telephony pass-through, LLM
tokens, and TTS are extra and can make the real bill higher than the cap.

Sources, checked when this repo was written (November 2026):

- Twilio US SMS long-code outbound: $0.0083 per segment
  https://www.twilio.com/en-us/sms/pricing/us (page dated October 2026)
- Twilio US MMS outbound: $0.022 per message (same page)
- Twilio US outbound local voice: $0.0140 per minute
  https://www.twilio.com/en-us/voice/pricing/us (page dated August 2026)
- Bland Start talk time: $0.14 per minute, telephony billed separately
  https://www.bland.ai/pricing
- Vapi platform fee: $0.05 per minute, before speech, model, and carrier
  https://docs.vapi.ai/ (platform fee published on Vapi's pricing; the
  $0.05 figure is the platform component only)
"""

from __future__ import annotations

from decimal import Decimal

SMS_SEGMENT_USD = Decimal("0.0083")
MMS_OUTBOUND_USD = Decimal("0.0220")
TWILIO_VOICE_PER_MIN_USD = Decimal("0.0140")
BLAND_START_PER_MIN_USD = Decimal("0.1400")
VAPI_PLATFORM_PER_MIN_USD = Decimal("0.0500")

# Local-number monthly rental. Not charged by this wrapper. Listed so the
# README and the code share one figure.
TWILIO_LOCAL_NUMBER_MONTHLY_USD = Decimal("1.15")


def estimate_sms(body: str, *, media: bool) -> Decimal:
    """Estimate one outbound message.

    Segment count is ``ceil(len(body) / 160)`` characters. Twilio's real
    segmenter uses GSM-7 septets and UCS-2, so this can under-count a message
    that is not plain ASCII. MMS uses the flat outbound rate instead.
    """
    if media:
        return MMS_OUTBOUND_USD
    segments = max(1, (len(body) + 159) // 160)
    return SMS_SEGMENT_USD * segments


def estimate_call_minutes(provider: str, minutes: int) -> Decimal:
    """Commit ``minutes`` at the provider's published base rate.

    ``mock`` uses the Bland Start rate so a dry run fills the dollar cap the
    way a Bland call would. Vapi uses the platform fee only.
    """
    billable = max(1, int(minutes))
    rates = {
        "bland": BLAND_START_PER_MIN_USD,
        "vapi": VAPI_PLATFORM_PER_MIN_USD,
        "twilio": TWILIO_VOICE_PER_MIN_USD,
        "mock": BLAND_START_PER_MIN_USD,
    }
    rate = rates.get(provider, BLAND_START_PER_MIN_USD)
    return rate * billable


def money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'))}"
