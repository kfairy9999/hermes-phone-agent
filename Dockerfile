# Mock-mode image. It does not install Hermes Agent and it does not call
# Twilio, Bland, or Vapi. The full agent install is scripts/setup.sh, which
# runs Nous Research's installer at the pinned commit. That install clones
# the agent and downloads its toolchain, so it is not part of this image.
FROM python:3.12-slim

WORKDIR /opt/hermes-phone-agent

COPY pyproject.toml README.md LICENSE UPSTREAM.json ./
COPY src ./src
COPY scripts/demo_mock.py ./scripts/demo_mock.py
COPY skills ./skills

RUN pip install --no-cache-dir .

ENV ORCHESTRATOR=mock \
    PHONE_PROVIDER=mock \
    PHONE_TIMEZONE=America/Los_Angeles \
    PYTHONDONTWRITEBYTECODE=1 \
    HERMES_PHONE_DEMO_HOME=/tmp/hermes-phone-demo

CMD ["python", "scripts/demo_mock.py"]
