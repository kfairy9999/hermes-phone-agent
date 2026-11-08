"""In-memory stand-in for urllib.request.urlopen."""

from __future__ import annotations

import json
from typing import Any


class FakeResponse:
    def __init__(self, payload: dict[str, Any] | list[Any] | str):
        if isinstance(payload, str):
            self._raw = payload.encode("utf-8")
        else:
            self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


class RecordingOpener:
    def __init__(self, responder):
        self.requests = []
        self._responder = responder

    def __call__(self, req, timeout=30):
        self.requests.append(req)
        payload = self._responder(req)
        return FakeResponse(payload)
