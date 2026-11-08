"""CLI for the guard.

Outbound commands use the same names as the official telephony script
(``twilio-send-sms``, ``twilio-call``, ``ai-call``, ``ai-status``,
``vapi-import-twilio``). ``--confirm`` is this wrapper's flag. The upstream
script has no confirm flag; its safety rule is an instruction to the agent.
``--orchestrator`` is the selector from Hermes issue 66963, extended with
``mock``.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable

from hermes_phone.config import load_settings
from hermes_phone.errors import GuardRefusal, PhoneError
from hermes_phone.numbers import mask_phone
from hermes_phone.service import PhoneService


def confirmation_granted(
    *,
    flag: bool,
    stdin_is_tty: bool,
    read_line: Callable[[], str],
    prompt: str,
) -> bool:
    if flag:
        return True
    if not stdin_is_tty:
        return False
    print(prompt, file=sys.stderr)
    try:
        answer = read_line()
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


def _print(payload: dict[str, Any], *, stream: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str), file=stream)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-phone",
        description="Guarded outbound SMS and AI calls for the Hermes telephony skill.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("diagnose", help="Show guard state. Does not contact a provider.")

    sub.add_parser("allow-list", help="Print the allowlist")

    add = sub.add_parser("allow-add", help="Add one E.164 number to the allowlist file")
    add.add_argument("number")

    sms = sub.add_parser("twilio-send-sms", help="Send an SMS or MMS through the guard")
    sms.add_argument("to_number")
    sms.add_argument("body")
    sms.add_argument("--media-url", action="append", default=[])
    sms.add_argument("--from-number", default="")
    sms.add_argument(
        "--confirm",
        action="store_true",
        help="Record that a person confirmed this exact outbound action",
    )

    call = sub.add_parser("twilio-call", help="Place a direct Twilio call through the guard")
    call.add_argument("to_number")
    call.add_argument("--message", default="")
    call.add_argument("--audio-url", default="")
    call.add_argument("--voice", default="Polly.Joanna")
    call.add_argument("--send-digits", default="")
    call.add_argument("--from-number", default="")
    call.add_argument("--record", action="store_true")
    call.add_argument("--confirm", action="store_true")

    ai = sub.add_parser("ai-call", help="Place an outbound AI call through the guard")
    ai.add_argument("to_number")
    ai.add_argument("task")
    ai.add_argument("--provider", choices=["mock", "bland", "vapi"], default="")
    ai.add_argument("--orchestrator", choices=["mock", "bland", "vapi"], default="")
    ai.add_argument("--voice", default="")
    ai.add_argument("--first-sentence", default="")
    ai.add_argument("--max-duration", type=int, default=3)
    ai.add_argument("--confirm", action="store_true")

    status = sub.add_parser("ai-status", help="Check an AI call. Read-only.")
    status.add_argument("call_id")
    status.add_argument("--provider", choices=["mock", "bland", "vapi"], default="")
    status.add_argument("--orchestrator", choices=["mock", "bland", "vapi"], default="")
    status.add_argument("--analyze", default="")

    imported = sub.add_parser("vapi-import-twilio", help="Import an owned Twilio number into Vapi")
    imported.add_argument("--phone-number", default="")
    imported.add_argument("--save-env", action="store_true")
    imported.add_argument("--confirm", action="store_true")
    imported.add_argument("--orchestrator", choices=["mock", "vapi"], default="")

    return parser


def _service_from(args: argparse.Namespace) -> PhoneService:
    return PhoneService(
        load_settings(
            cli_orchestrator=getattr(args, "orchestrator", "") or "",
            cli_provider=getattr(args, "provider", "") or "",
        )
    )


def _confirm(args: argparse.Namespace, to_number: str, kind: str) -> bool:
    masked = mask_phone(to_number) if to_number else "the configured number"
    return confirmation_granted(
        flag=bool(getattr(args, "confirm", False)),
        stdin_is_tty=sys.stdin.isatty(),
        read_line=input,
        prompt=f"Type yes to confirm this {kind} to {masked}.",
    )


def dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "allow-add":
        # allow-add does not select a provider. Load with defaults.
        return PhoneService(load_settings()).allow_add(args.number)

    service = _service_from(args)
    if args.command == "diagnose":
        return service.diagnose()
    if args.command == "allow-list":
        return service.allow_list()
    if args.command == "twilio-send-sms":
        return service.send_sms(
            args.to_number,
            args.body,
            confirmed=_confirm(args, args.to_number, "SMS"),
            media_urls=args.media_url or None,
            from_number=args.from_number,
        )
    if args.command == "twilio-call":
        return service.direct_call(
            args.to_number,
            confirmed=_confirm(args, args.to_number, "call"),
            message=args.message,
            audio_url=args.audio_url,
            voice=args.voice,
            send_digits=args.send_digits,
            from_number=args.from_number,
            record=args.record,
        )
    if args.command == "ai-call":
        return service.ai_call(
            args.to_number,
            args.task,
            confirmed=_confirm(args, args.to_number, "AI call"),
            voice=args.voice,
            first_sentence=args.first_sentence,
            max_duration=args.max_duration,
        )
    if args.command == "ai-status":
        return service.ai_status(args.call_id, analyze=args.analyze)
    if args.command == "vapi-import-twilio":
        number = args.phone_number
        return service.import_twilio(
            confirmed=_confirm(args, number, "Vapi import"),
            phone_number=number,
            save_env=args.save_env,
        )
    raise PhoneError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = dispatch(args)
    except GuardRefusal as exc:
        _print(
            {
                "success": False,
                "refused": True,
                "error": str(exc),
                "action": exc.action,
                "to_phone_number_masked": exc.masked,
            },
            stream=sys.stderr,
        )
        return 2
    except PhoneError as exc:
        _print({"success": False, "error": str(exc)}, stream=sys.stderr)
        return 1
    _print(result, stream=sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
