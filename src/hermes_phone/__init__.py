"""Safety-guarded telephony wrapper for the Hermes Agent telephony skill.

This package does not fork Hermes. It calls the same provider HTTP APIs the
official ``optional-skills/productivity/telephony/scripts/telephony.py`` script
calls, and it refuses outbound SMS and calls that fail a local guard.
"""

__version__ = "0.1.0"
