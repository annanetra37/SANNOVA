"""
Credential reader for the ingestion worker.

This is the OTHER half of the pair. It runs as a different Azure service
principal holding only get/list on the vault — it can read credentials but
cannot write or delete them. The intake app can write but cannot read.

Neither component can do the other's job, so compromising either one gives
an attacker only half the capability.

Drop this file into your ingestion project (triplei-solar/core/).
"""

from __future__ import annotations

import os
from functools import lru_cache

from azure.identity import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets import SecretClient


def _credential():
    tenant = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_WORKER_CLIENT_ID")
    client_secret = os.getenv("AZURE_WORKER_CLIENT_SECRET")
    if tenant and client_id and client_secret:
        return ClientSecretCredential(tenant, client_id, client_secret)
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def _client() -> SecretClient:
    return SecretClient(
        vault_url=os.environ["AZURE_KEYVAULT_URL"],
        credential=_credential(),
    )


def get(vendor: str, platform: str, field: str) -> str:
    """Fetch one credential. Raises if absent — fail loud, not silent."""
    name = f"{vendor}--{platform}--{field.replace('_', '-')}"
    return _client().get_secret(name).value


def get_platform(vendor: str, platform: str) -> dict[str, str]:
    """
    Fetch every credential stored for one vendor+platform.

    Returns a dict keyed by the original field name with underscores,
    ready to pass into an adapter's constructor.
    """
    prefix = f"{vendor}--{platform}--"
    out: dict[str, str] = {}
    for prop in _client().list_properties_of_secrets():
        if not prop.name.startswith(prefix):
            continue
        field = prop.name[len(prefix):].replace("-", "_")
        out[field] = _client().get_secret(prop.name).value
    return out


def list_vendors() -> set[str]:
    """Every vendor that has submitted anything."""
    return {
        p.name.split("--")[0]
        for p in _client().list_properties_of_secrets()
        if "--" in p.name and not p.name.startswith("healthcheck")
    }


def list_platforms(vendor: str) -> set[str]:
    """Which platforms this vendor has submitted credentials for."""
    return {
        p.name.split("--")[1]
        for p in _client().list_properties_of_secrets()
        if p.name.startswith(f"{vendor}--") and p.name.count("--") >= 2
    }


# ---------------------------------------------------------------------------
# Example wiring into an adapter
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    for vendor in sorted(list_vendors()):
        print(f"\n{vendor}")
        for platform in sorted(list_platforms(vendor)):
            creds = get_platform(vendor, platform)
            # Print field NAMES only. Never values.
            print(f"  {platform}: {', '.join(sorted(creds))}")

    # Typical usage:
    #
    #   from adapters.foxess import FoxESSAdapter
    #   creds = get_platform("sannova", "foxess")
    #   adapter = FoxESSAdapter(api_key=creds["api_key"])
    #
    # Cache the result per run rather than calling per request — Key Vault
    # is rate limited and these values change rarely.
