"""Helpers for Telegram referral deep-link payloads."""

import re

REFERRAL_PREFIX = "ref_"
_REFERRAL_CODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")


def normalize_referral_code(value: str) -> str | None:
    """Return a valid stored referral code or None."""
    code = value.strip()
    if code.startswith(REFERRAL_PREFIX):
        code = code[len(REFERRAL_PREFIX):]
    if not _REFERRAL_CODE_RE.fullmatch(code) or code.lower() == "ref":
        return None
    return code


def referral_payload(code: str) -> str:
    """Build the Telegram /start payload for a stored referral code."""
    normalized = normalize_referral_code(code)
    if normalized is None:
        raise ValueError("Invalid referral code")
    return f"{REFERRAL_PREFIX}{normalized}"


def referral_code_from_payload(payload: str) -> str | None:
    """Extract a stored referral code from a Telegram deep-link payload."""
    if not payload.startswith(REFERRAL_PREFIX):
        return None
    return normalize_referral_code(payload[len(REFERRAL_PREFIX):])
