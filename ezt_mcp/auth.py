"""Simple Bearer API-key authentication for EZT MCP deploy/test."""

from __future__ import annotations

import hmac


class APIKeyAuth:
    """Validate Bearer tokens when keys are configured.

    No configured keys means open access, useful for local development only.
    """

    def __init__(self, api_keys: list[str] | None = None):
        self._api_keys = [key for key in (api_keys or []) if key]

    @property
    def enabled(self) -> bool:
        return bool(self._api_keys)

    def authenticate(self, auth_header: str) -> bool:
        if not self._api_keys:
            return True
        if not auth_header.startswith("Bearer "):
            return False
        key = auth_header[7:]
        return any(hmac.compare_digest(key, valid) for valid in self._api_keys)
