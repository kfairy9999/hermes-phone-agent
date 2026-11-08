"""Errors raised by the wrapper."""

from __future__ import annotations


class PhoneError(RuntimeError):
    """Invalid input, missing credentials, or a provider failure."""


class GuardRefusal(PhoneError):
    """The guard rejected an outbound action before any provider was contacted."""

    def __init__(self, message: str, *, reason: str, action: str, masked: str = ""):
        super().__init__(message)
        self.reason = reason
        self.action = action
        self.masked = masked
