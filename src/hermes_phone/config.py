"""Runtime settings.

Provider selection follows issue 66963 plus the official ``PHONE_PROVIDER``
variable already read by ``telephony.py``:

1. ``--orchestrator``
2. ``--provider``
3. ``ORCHESTRATOR`` (process environment, then ``$HERMES_HOME/.env``)
4. ``PHONE_PROVIDER`` (same places)
5. ``mock``

``mock`` is the default so a fresh checkout places no vendor calls. When
``ORCHESTRATOR`` is ``mock``, a live ``--provider`` on the command line is
refused rather than sent. Going live means setting ``ORCHESTRATOR`` to
``bland`` or ``vapi``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from hermes_phone.envfile import load_dotenv_values
from hermes_phone.errors import PhoneError
from hermes_phone.numbers import normalize_phone

LIVE_PROVIDERS = {"bland", "vapi"}
KNOWN_ORCHESTRATORS = LIVE_PROVIDERS | {"mock"}

# Variables the official script reads, plus the wrapper's own knobs.
# Documented in ``.env.example``.
SKILL_ENV_KEYS = (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TWILIO_PHONE_NUMBER_SID",
    "BLAND_API_KEY",
    "BLAND_DEFAULT_VOICE",
    "VAPI_API_KEY",
    "VAPI_PHONE_NUMBER_ID",
    "VAPI_VOICE_PROVIDER",
    "VAPI_VOICE_ID",
    "VAPI_MODEL",
    "PHONE_PROVIDER",
)


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def _merged_env(home: Path) -> dict[str, str]:
    """Process environment wins over the Hermes dotenv file."""
    merged = load_dotenv_values(home / ".env")
    for key, value in os.environ.items():
        if value != "":
            merged[key] = value
    return merged


def _decimal(raw: str, name: str) -> Decimal:
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise PhoneError(f"{name} must be a number, got {raw!r}") from exc
    if value < 0:
        raise PhoneError(f"{name} must be zero or greater")
    return value


def _int(raw: str, name: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise PhoneError(f"{name} must be an integer, got {raw!r}") from exc
    if value < 0:
        raise PhoneError(f"{name} must be zero or greater")
    return value


def parse_allowlist(raw: str) -> list[str]:
    numbers: list[str] = []
    for piece in raw.split(","):
        item = piece.strip()
        if item:
            numbers.append(normalize_phone(item))
    return numbers


def load_allowlist_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    numbers: list[str] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            numbers.append(normalize_phone(line))
        except PhoneError as exc:
            raise PhoneError(f"{path}:{line_no}: {exc}") from exc
    return numbers


@dataclass(frozen=True)
class Settings:
    home: Path
    env: dict[str, str]
    orchestrator: str
    phone_provider: str
    allowlist: tuple[str, ...]
    allowlist_file: Path
    max_calls_per_day: int
    max_texts_per_day: int
    max_dollars_per_day: Decimal
    quiet_hours: str
    timezone: ZoneInfo
    log_path: Path
    mock_state_path: Path
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str
    bland_api_key: str
    bland_voice: str
    vapi_api_key: str
    vapi_phone_number_id: str
    vapi_voice_provider: str
    vapi_voice_id: str
    vapi_model: str

    @property
    def mismatch(self) -> str:
        if self.phone_provider and self.orchestrator != self.phone_provider:
            return (
                f"ORCHESTRATOR={self.orchestrator} and PHONE_PROVIDER={self.phone_provider} "
                "differ. Outbound AI calls use ORCHESTRATOR."
            )
        return ""


def resolve_orchestrator(
    env: dict[str, str],
    *,
    cli_orchestrator: str = "",
    cli_provider: str = "",
) -> str:
    cli_orchestrator = (cli_orchestrator or "").strip().lower()
    cli_provider = (cli_provider or "").strip().lower()
    if cli_orchestrator and cli_provider and cli_orchestrator != cli_provider:
        raise PhoneError(
            f"--orchestrator {cli_orchestrator} and --provider {cli_provider} disagree."
        )
    for label, value in (("--orchestrator", cli_orchestrator), ("--provider", cli_provider)):
        if value and value not in KNOWN_ORCHESTRATORS:
            raise PhoneError(
                f"{label} must be mock, bland, or vapi, got {value!r}. "
                "The upstream telephony.py --provider flag accepts only bland or vapi."
            )
    env_orchestrator = env.get("ORCHESTRATOR", "").strip().lower()
    env_provider = env.get("PHONE_PROVIDER", "").strip().lower()
    if env_orchestrator and env_orchestrator not in KNOWN_ORCHESTRATORS:
        raise PhoneError(f"ORCHESTRATOR must be mock, bland, or vapi, got {env_orchestrator!r}.")
    if env_provider and env_provider not in KNOWN_ORCHESTRATORS:
        raise PhoneError(
            f"PHONE_PROVIDER must be mock, bland, or vapi for this wrapper, got {env_provider!r}. "
            "Upstream telephony.py accepts only bland or vapi."
        )

    chosen = cli_orchestrator or cli_provider or env_orchestrator or env_provider or "mock"
    # An explicit ORCHESTRATOR=mock is the dry-run pin. PHONE_PROVIDER and a
    # one-shot --provider do not override it. Unset ORCHESTRATOR still honors
    # PHONE_PROVIDER, which is the variable the official script already uses.
    if env_orchestrator == "mock" and chosen in LIVE_PROVIDERS:
        raise PhoneError(
            "ORCHESTRATOR=mock, so this command will not contact Bland or Vapi. "
            "Set ORCHESTRATOR=bland or ORCHESTRATOR=vapi in the environment when you "
            "intend to spend money. PHONE_PROVIDER alone does not override a mock orchestrator."
        )
    return chosen


def load_settings(
    *,
    cli_orchestrator: str = "",
    cli_provider: str = "",
    home: Path | None = None,
) -> Settings:
    root = home or hermes_home()
    env = _merged_env(root)
    orchestrator = resolve_orchestrator(
        env, cli_orchestrator=cli_orchestrator, cli_provider=cli_provider
    )
    tz_name = env.get("PHONE_TIMEZONE", "America/Los_Angeles").strip() or "America/Los_Angeles"
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise PhoneError(f"PHONE_TIMEZONE is not a known timezone: {tz_name}") from exc

    allow_file = Path(
        env.get("PHONE_ALLOWLIST_FILE", str(root / "phone_allowlist.txt"))
    ).expanduser()
    from_file = load_allowlist_file(allow_file)
    from_env = parse_allowlist(env.get("PHONE_ALLOWLIST", ""))
    # Preserve order, drop duplicates. File first, then env.
    allowlist: list[str] = []
    for number in [*from_file, *from_env]:
        if number not in allowlist:
            allowlist.append(number)

    log_raw = env.get("PHONE_LOG_PATH", "").strip()
    log_path = Path(log_raw).expanduser() if log_raw else root / "phone_audit.jsonl"
    mock_raw = env.get("PHONE_MOCK_STATE_PATH", "").strip()
    mock_state = Path(mock_raw).expanduser() if mock_raw else root / "mock_telephony_state.json"

    return Settings(
        home=root,
        env=env,
        orchestrator=orchestrator,
        phone_provider=env.get("PHONE_PROVIDER", "").strip().lower(),
        allowlist=tuple(allowlist),
        allowlist_file=allow_file,
        max_calls_per_day=_int(env.get("PHONE_MAX_CALLS_PER_DAY", "3"), "PHONE_MAX_CALLS_PER_DAY"),
        max_texts_per_day=_int(env.get("PHONE_MAX_TEXTS_PER_DAY", "10"), "PHONE_MAX_TEXTS_PER_DAY"),
        max_dollars_per_day=_decimal(
            env.get("PHONE_MAX_DOLLARS_PER_DAY", "2.00"), "PHONE_MAX_DOLLARS_PER_DAY"
        ),
        quiet_hours=env.get("PHONE_QUIET_HOURS", "21:00-08:00").strip(),
        timezone=tz,
        log_path=log_path,
        mock_state_path=mock_state,
        twilio_account_sid=env.get("TWILIO_ACCOUNT_SID", "").strip(),
        twilio_auth_token=env.get("TWILIO_AUTH_TOKEN", "").strip(),
        twilio_phone_number=env.get("TWILIO_PHONE_NUMBER", "").strip(),
        bland_api_key=env.get("BLAND_API_KEY", "").strip(),
        bland_voice=env.get("BLAND_DEFAULT_VOICE", "mason").strip() or "mason",
        vapi_api_key=env.get("VAPI_API_KEY", "").strip(),
        vapi_phone_number_id=env.get("VAPI_PHONE_NUMBER_ID", "").strip(),
        vapi_voice_provider=env.get("VAPI_VOICE_PROVIDER", "11labs").strip() or "11labs",
        vapi_voice_id=env.get("VAPI_VOICE_ID", "cjVigY5qzO86Huf0OWal").strip()
        or "cjVigY5qzO86Huf0OWal",
        vapi_model=env.get("VAPI_MODEL", "gpt-4o").strip() or "gpt-4o",
    )
