"""Credential Service — secure API key storage via OS credential manager.

Uses ``keyring`` which on Windows delegates to Windows Credential Manager
(WinVaultKeyring).  API keys are NEVER stored as plaintext in settings.json.

Usage::

    from services.credential_service import credential_service

    # Save
    credential_service.save_api_key("OpenAI", "sk-xxx")

    # Load
    key = credential_service.get_api_key("OpenAI")  # -> "sk-xxx" or None

    # Delete
    credential_service.delete_api_key("OpenAI")

Migration
---------
On first load, if ``settings.json`` still contains plaintext ``api_key``
fields, they are automatically migrated to the credential store and
removed from the JSON file on the next save.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_APP_NAME = "AI Market Analyst"


class CredentialService:
    """Thin wrapper around OS credential manager via ``keyring``.

    Service name (the ``service_name`` parameter in keyring) is always
    ``"AI Market Analyst"``.  Each provider is stored as a separate
    entry keyed by provider display name.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def save_api_key(provider: str, api_key: str) -> None:
        """Store *api_key* for *provider* in the OS credential manager.

        Silently ignores empty keys.
        """
        if not provider or not api_key:
            return
        try:
            import keyring
            keyring.set_password(_APP_NAME, provider, api_key)
        except Exception as exc:
            logger.warning("Không lưu được API Key cho %s vào Credential Manager: %s", provider, exc)

    @staticmethod
    def get_api_key(provider: str) -> str | None:
        """Return the stored API key for *provider*, or ``None``."""
        if not provider:
            return None
        try:
            import keyring
            return keyring.get_password(_APP_NAME, provider)
        except Exception as exc:
            logger.warning("Không đọc được API Key cho %s từ Credential Manager: %s", provider, exc)
            return None

    @staticmethod
    def delete_api_key(provider: str) -> None:
        """Remove the stored API key for *provider*."""
        if not provider:
            return
        try:
            import keyring
            keyring.delete_password(_APP_NAME, provider)
        except Exception:
            pass  # Already deleted or credential manager unavailable

    @staticmethod
    def has_api_key(provider: str) -> bool:
        """Return ``True`` if an API key is stored for *provider*."""
        return CredentialService.get_api_key(provider) is not None


# Module-level singleton for convenience
credential_service = CredentialService()
