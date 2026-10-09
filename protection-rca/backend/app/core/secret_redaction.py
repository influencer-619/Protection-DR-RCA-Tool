"""Redact secrets from dict payloads before audit / API / logs (Stage F SEC-012)."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional

# Case-insensitive substring match on keys
_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "auth_key",
    "mms_password",
    "ied_password",
    "hashed_password",
)

_REDACTED = "***REDACTED***"


def _is_secret_key(key: str) -> bool:
    k = str(key or "").lower().replace("-", "_")
    return any(part in k for part in _SECRET_KEY_PARTS)


def redact_secrets(value: Any, *, depth: int = 0, max_depth: int = 12) -> Any:
    """Return a deep copy of ``value`` with secret-like keys replaced.

    Safe for audit ``old_value`` / ``new_value`` / ``metadata``. Does not mutate input.
    """
    if depth > max_depth:
        return "<max_depth>"
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            sk = str(k)
            if _is_secret_key(sk):
                out[sk] = _REDACTED if v not in (None, "", [], {}) else v
            else:
                out[sk] = redact_secrets(v, depth=depth + 1, max_depth=max_depth)
        return out
    if isinstance(value, list):
        return [redact_secrets(v, depth=depth + 1, max_depth=max_depth) for v in value]
    if isinstance(value, tuple):
        return tuple(
            redact_secrets(v, depth=depth + 1, max_depth=max_depth) for v in value
        )
    return value


def redact_inplace(payload: Optional[MutableMapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Convenience: redact a mutable mapping (returns new dict)."""
    if payload is None:
        return None
    return redact_secrets(dict(payload))
