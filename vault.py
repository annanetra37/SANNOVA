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


def describe_failure(exc: Exception) -> str:
    """
    A one-line, loggable reason a vault write failed.

    Azure's error text names the vault, the operation and the reason, but
    never echoes the secret value, so this is safe to log and safe to show
    an authenticated operator. Truncated regardless.
    """
    bits = [type(exc).__name__]

    status = getattr(exc, "status_code", None)
    if status:
        bits.append(f"HTTP {status}")

    message = getattr(exc, "message", None) or str(exc)
    if message:
        bits.append(message.strip().splitlines()[0][:300])

    return " | ".join(bits)


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
        # Log the name and why it failed. Never the value.
        log.error("keyvault write failed for %s: %s", name,
                  describe_failure(exc))
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


def health() -> tuple[bool, str]:
    """
    Cheap check that credentials, permissions and network all work.

    Writes a probe secret rather than reading one, because this principal
    has no read permission by design. Returns (ok, detail) so an operator
    can be told what is actually wrong instead of just "failed".
    """
    url = os.getenv("AZURE_KEYVAULT_URL")
    if not url:
        return False, "AZURE_KEYVAULT_URL is not set"

    missing = [v for v in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                           "AZURE_CLIENT_SECRET") if not os.getenv(v)]
    if missing:
        return False, ("not set: " + ", ".join(missing) +
                       " — falling back to DefaultAzureCredential, which has "
                       "no managed identity to use on Railway")

    try:
        client().set_secret("healthcheck--probe",
                            datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        return False, describe_failure(exc)

    return True, f"wrote healthcheck--probe to {url}"
