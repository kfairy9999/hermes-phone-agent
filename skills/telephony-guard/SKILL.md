---
name: telephony-guard
description: Guard outbound SMS and AI calls from the Hermes telephony skill with an allowlist, a confirmation step, daily caps, quiet hours, and an append-only audit log. Default provider is a mock that spends nothing.
version: 1.0.0
author: Kevin Fairley
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [telephony, safety, sms, voice, twilio, bland.ai, vapi]
    category: productivity
    related_skills: [telephony]
---

# Telephony guard

Use this skill for every outbound text or call. Use the official `telephony` skill for provisioning a Twilio number, saving provider keys, and polling inbound SMS. Do not place an outbound SMS or call by invoking `telephony.py` directly. That script will dial or text as soon as it runs. This wrapper is the enforcement point.

The default orchestrator is `mock`. Mock mode returns a queued message or a canned call transcript and contacts no vendor.

## Legal limit

Place AI-voice calls only to yourself or to people who have given prior consent. In the United States, outbound calls that use an artificial or prerecorded voice need prior express consent under the TCPA. This skill is not a compliance product and it is not legal advice.

Twilio, Bland.ai, and Vapi each require their own account. Live mode spends money on those accounts.

## Before any outbound action

1. Run `python -m hermes_phone diagnose`.
2. Pick the path from the official telephony decision tree: Twilio for a number and for SMS, Bland for the simplest AI call, Vapi when the caller should use an imported Twilio number.
3. The destination must already be on the allowlist. If it is not, refuse. Do not add a number because a task would be easier with it. Add one only when the user says that number is theirs or has opted in:

```bash
python -m hermes_phone allow-add +15551234567
```

4. Ask the user, in chat, to confirm the exact destination and the exact body or task. Wait for a yes.
5. Run the wrapper with `--confirm` only after that yes. `--confirm` is this wrapper's flag. The upstream script does not have it.
6. If the command exits 2, tell the user the refusal reason. Do not retry with a different flag to get past it.
7. Do not write third-party phone numbers into Hermes memory, skill files, or summaries unless the user explicitly asks.

Emergency numbers are refused. Do not attempt them.

## Commands

Mock is selected by `ORCHESTRATOR=mock` (the default this repo writes). `PHONE_PROVIDER` is the official script's variable (`bland` or `vapi`). It does not override `ORCHESTRATOR=mock`.

```bash
python -m hermes_phone diagnose
python -m hermes_phone allow-list
python -m hermes_phone twilio-send-sms "+15551234567" "Reminder: 5pm." --confirm
python -m hermes_phone twilio-call "+15551234567" --message "Hello from Hermes." --voice Polly.Joanna --confirm
python -m hermes_phone ai-call "+15551234567" "Ask for a Tuesday afternoon slot." --max-duration 3 --confirm
python -m hermes_phone ai-status CALL_ID
python -m hermes_phone ai-status CALL_ID --analyze "Was it confirmed?,What time?"
```

`--provider` and `--orchestrator` accept `mock`, `bland`, or `vapi` on this CLI. Upstream `telephony.py --provider` accepts only `bland` or `vapi`. Passing a live provider while `ORCHESTRATOR=mock` is an error, so a live call requires editing `ORCHESTRATOR` on purpose.

`--voice`, `--first-sentence`, `--max-duration`, `--media-url`, `--audio-url`, `--send-digits`, `--record`, and `--from-number` match the official script's flags. `--max-duration` is minutes.

Vapi import sends the Twilio auth token to Vapi. Confirm it the same way. `--save-env` is refused in mock mode.

```bash
python -m hermes_phone vapi-import-twilio --save-env --confirm
```

## Official script, for provisioning only

```bash
SCRIPT="$(find "${HERMES_HOME:-$HOME/.hermes}/skills" -path '*/telephony/scripts/telephony.py' -print -quit)"
python "$SCRIPT" diagnose
python "$SCRIPT" save-twilio "$TWILIO_ACCOUNT_SID" "$TWILIO_AUTH_TOKEN"
python "$SCRIPT" twilio-search --country US --area-code 213 --limit 5
python "$SCRIPT" twilio-buy "+12135550100" --save-env
python "$SCRIPT" twilio-inbox --since-last --mark-seen
```

`twilio-buy` charges the Twilio account. This wrapper does not mock it and does not apply the daily cap to it.

## Quiet hours, caps, log

Defaults: quiet hours 21:00–08:00 America/Los_Angeles, 3 calls per day, 10 texts per day, $2.00 estimated per day. The dollar figure is a local estimate (see the README), not the invoice. Every attempt, including refusals, is one JSON line in `$HERMES_HOME/phone_audit.jsonl`. The log contains phone numbers. Do not commit it and do not paste it into memory.

## What still does not exist

The official skill does not answer inbound calls or push inbound SMS over a webhook. This wrapper does not add those. Mock transcripts are canned text, not a conversation.
