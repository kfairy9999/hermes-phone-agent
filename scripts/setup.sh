#!/usr/bin/env bash
# Install pinned Hermes Agent, the official telephony skill, the Groq
# OpenAI-compatible provider config, and this repo's guard skill.
#
# Flags passed to install.sh are the ones that script documents:
#   --commit SHA --hermes-home PATH --non-interactive --skip-browser --skip-computer-use
# The installer is downloaded from the same commit as the pin, not from the
# mutable https://hermes-agent.nousresearch.com/install.sh URL.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export HERMES_HOME

PIN_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["tag"])' "$ROOT/UPSTREAM.json")"
PIN_COMMIT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$ROOT/UPSTREAM.json")"

echo "Hermes pin: ${PIN_TAG} ${PIN_COMMIT}"
echo "HERMES_HOME: ${HERMES_HOME}"

INSTALLER="$(mktemp)"
trap 'rm -f "$INSTALLER"' EXIT
curl -fsSL "https://raw.githubusercontent.com/NousResearch/hermes-agent/${PIN_COMMIT}/scripts/install.sh" -o "$INSTALLER"

bash "$INSTALLER" \
  --commit "$PIN_COMMIT" \
  --hermes-home "$HERMES_HOME" \
  --non-interactive \
  --skip-browser \
  --skip-computer-use

export PATH="${HOME}/.local/bin:${PATH}"

if [[ ! -e "${HERMES_HOME}/hermes-agent/.git" ]]; then
  echo "Expected a Hermes checkout at ${HERMES_HOME}/hermes-agent" >&2
  exit 1
fi

GOT="$(git -C "${HERMES_HOME}/hermes-agent" rev-parse HEAD)"
if [[ "$GOT" != "$PIN_COMMIT" ]]; then
  echo "Checkout ${GOT} does not match pin ${PIN_COMMIT}" >&2
  exit 1
fi
echo "Hermes checkout matches ${PIN_TAG}."

if ! command -v hermes >/dev/null 2>&1; then
  echo "hermes is not on PATH after install. Looked in ${HOME}/.local/bin." >&2
  exit 1
fi

hermes skills install official/productivity/telephony --yes

# The hermes executable on v0.23.0 is an isolated interpreter (python -I).
# Skill commands run in the user's shell, so the wrapper is installed for
# that python3, which is what `python3 -m hermes_phone` resolves.
python3 -m pip install -e "$ROOT"
echo "Installed hermes-phone for $(command -v python3)."

# The installer writes a full config.yaml before this point, with
# model.provider auto and model.base_url on OpenRouter (observed on v0.23.0).
# These keys are the ones `hermes config set` accepted on that release.
# providers.groq.api is the cookbook base URL. model.base_url is set to the
# same Groq URL so the installer's OpenRouter value does not remain.
echo "Setting the model to Groq qwen/qwen3.8-27b via hermes config set."
hermes config set providers.groq.api "https://api.groq.com/openai/v1"
hermes config set providers.groq.key_env "GROQ_API_KEY"
hermes config set model.provider "custom:groq"
hermes config set model.default "qwen/qwen3.8-27b"
hermes config set model.base_url "https://api.groq.com/openai/v1"

python3 "$ROOT/scripts/merge_env.py" "${HERMES_HOME}/.env" "$ROOT/.env.example"

DEST="${HERMES_HOME}/skills/productivity/telephony-guard"
mkdir -p "$DEST"
cp -a "$ROOT/skills/telephony-guard/." "$DEST/"
echo "Installed local skill at ${DEST}."

ALLOW="${HERMES_HOME}/phone_allowlist.txt"
if [[ ! -f "$ALLOW" ]]; then
  printf '%s\n' "# E.164 numbers the agent may call or text. One per line." \
    "# Empty file means every outbound number is refused." > "$ALLOW"
  chmod 600 "$ALLOW"
fi

echo
echo "Mock mode is the default (ORCHESTRATOR=mock). No Twilio, Bland, or Vapi call will be placed."
echo "Put API keys in ${HERMES_HOME}/.env when you are ready. Read the README before going live."
echo "Check the wrapper: python3 -m hermes_phone diagnose"
