"""
Azure Key Vault client — write only.

This module deliberately exposes no read path. The service principal this
app runs as should hold ONLY the 'set' permission on the vault, so even a
full compromise of this application cannot read back any credential that
was previously submitted, including its own.

The ingestion worker runs as a DIFFERENT service principal holding only
get/list. Neither side can do the other's job. That separation is the main
security property of this design and it is worth preserving.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

log = logging.getLogger("vault")


class VaultError(RuntimeError):
    pass


def _credential():
    tenant = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")

    if tenant and client_id and client_secret:
        return ClientSecretCredential(tenant, client_id, client_secret)
    # Falls back to managed identity / az login for local development.
    return DefaultAzureCredential()


_client: SecretClient | None = None


def client() -> SecretClient:
    global _client
    if _client is None:
        url = os.getenv("AZURE_KEYVAULT_URL")
        if not url:
            raise VaultError("AZURE_KEYVAULT_URL is not set")
        _client = SecretClient(vault_url=url, credential=_credential())
    return _client


def store(name: str, value: str, tags: dict[str, str] | None = None) -> None:
    """
    Write one secret. Never logs the value.

    Raises VaultError on failure so the caller can tell the user honestly
    rather than showing a success page for a write that did not happen.
    """
    meta = dict(tags or {})
    meta["submitted_at"] = datetime.now(timezone.utc).isoformat()

    try:
        client().set_secret(name, value, tags=meta)
    except Exception as exc:
        # Log the name and the failure. Never the value.
        log.error("keyvault write failed for %s: %s", name, type(exc).__name__)
        raise VaultError(f"could not store {name}") from exc

    log.info("stored secret %s (%d bytes)", name, len(value))


def store_many(items: list[tuple[str, str]],
               tags: dict[str, str] | None = None) -> list[str]:
    """
    Write several secrets. Returns the names written.

    If any write fails, the exception propagates — the caller must not
    report partial success as success. Already-written secrets stay
    written, which is safe: they are overwritten on resubmission.
    """
    written: list[str] = []
    for name, value in items:
        store(name, value, tags)
        written.append(name)
    return written


def health() -> bool:
    """
    Cheap check that credentials and network are working.

    Uses a write to a known probe secret rather than a read, because this
    principal has no read permission by design.
    """
    try:
        store("healthcheck--probe", datetime.now(timezone.utc).isoformat())
        return True
    except Exception:
        return False
