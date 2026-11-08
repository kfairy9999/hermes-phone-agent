"""The files a recruiter is told to trust exist and name the real pin."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKILL_ENV = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TWILIO_PHONE_NUMBER_SID",
    "BLAND_API_KEY",
    "VAPI_API_KEY",
    "VAPI_PHONE_NUMBER_ID",
    "PHONE_PROVIDER",
]


def test_env_example_lists_skill_variables_and_no_secrets():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for key in SKILL_ENV:
        assert f"{key}=" in text
    assert "ORCHESTRATOR=mock" in text
    assert "gsk_" not in text
    assert "AC" not in text.split("TWILIO_ACCOUNT_SID=", 1)[1].splitlines()[0]


def test_groq_config_matches_the_cookbook_shape():
    text = (ROOT / "config" / "hermes.config.yaml").read_text(encoding="utf-8")
    assert "api: https://api.groq.com/openai/v1" in text
    assert "key_env: GROQ_API_KEY" in text
    assert "default: qwen/qwen3.8-27b" in text
    assert "provider: custom:groq" in text
    assert "base_url: https://api.groq.com/openai/v1" in text


def test_setup_uses_the_documented_installer_flags_and_skill_command():
    text = (ROOT / "scripts" / "setup.sh").read_text(encoding="utf-8")
    pin = json.loads((ROOT / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert "UPSTREAM.json" in text
    assert "--commit" in text
    assert "--non-interactive" in text
    assert "--skip-browser" in text
    assert "--skip-computer-use" in text
    assert "hermes skills install official/productivity/telephony --yes" in text
    assert 'hermes config set model.provider "custom:groq"' in text
    assert 'hermes config set model.default "qwen/qwen3.8-27b"' in text
    assert 'hermes config set providers.groq.api "https://api.groq.com/openai/v1"' in text
    assert 'hermes config set model.base_url "https://api.groq.com/openai/v1"' in text
    assert pin["commit"] == "2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19"
    assert "raw.githubusercontent.com/NousResearch/hermes-agent/${PIN_COMMIT}/scripts/install.sh" in text


def test_readme_covers_the_portfolio_requirements():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in (
        "TCPA",
        "```mermaid",
        "What I learned",
        "How it was built",
        "Kevin Fairley designed and directed",
        "AI coding agents",
        "Twilio, Bland.ai, and Vapi each need their own paid account",
        "https://github.com/NousResearch/hermes-agent",
        "issue 66963",
    ):
        assert phrase in text
    skill = (ROOT / "skills" / "telephony-guard" / "SKILL.md").read_text(encoding="utf-8")
    assert "--confirm" in skill
    assert "TCPA" in skill
    assert "official/productivity/telephony" not in skill or "telephony.py" in skill
