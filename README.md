# Triple i — Credential Intake

A small web form vendors use to submit inverter platform credentials.
Values go straight into Azure Key Vault: never to disk, never to a database,
never to a log.

## The security design in one paragraph

Two Azure service principals. This app holds **only `set`** on the vault, so
it can write credentials but cannot read any back — including its own. The
ingestion worker holds **only `get`/`list`**, so it can read but cannot write
or delete. Neither can do the other's job, so compromising either gives an
attacker half the capability. Access is gated by a signed, expiring invite
link; there is no public landing page to find.

## Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, routes, invite tokens, security headers |
| `platforms.py` | Field definitions per platform. Add platforms here only. |
| `vault.py` | Write-only Key Vault client |
| `worker_credentials.py` | Read-only client — copy into your ingestion project |
| `templates/`, `static/` | UI |
| `railway.json`, `Procfile` | Railway deployment |

## Quick start

    pip install -r requirements.txt
    cp .env.example .env    # fill in
    uvicorn main:app --reload

Generate an invite:

    /admin/invite?key=<ADMIN_TOKEN>&vendor=sannova&name=SANNOVA+Engineering

## Deploying on Railway

Railway detects the Python project and uses `railway.json` — Nixpacks build,
`uvicorn` start command, `/healthz` health check. Nothing else to configure
except the variables.

**[DEPLOY.md](DEPLOY.md) walks through where every value below comes from,
click by click.** The short version:

Set these in the service's Variables tab:

| Variable | Value |
|---|---|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_TOKEN` | a second, different value from the same command |
| `AZURE_KEYVAULT_URL` | e.g. `https://triplei-creds.vault.azure.net/` |
| `AZURE_TENANT_ID` | the write-only service principal's tenant |
| `AZURE_CLIENT_ID` | the write-only service principal |
| `AZURE_CLIENT_SECRET` | its secret |
| `TOKEN_MAX_AGE_SECONDS` | optional, defaults to 14 days |

`PORT` is supplied by Railway — do not set it. The app refuses to start
without `SECRET_KEY`, so a missing variable fails the deploy loudly rather
than running unprotected.

Changing `SECRET_KEY` invalidates every invite link already sent.

## Adding a platform

Add a `Platform(...)` entry to `PLATFORMS` in `platforms.py`. The form,
validation and vault naming all derive from it. Nothing else changes.

## Secret naming

    {vendor}--{platform}--{field}
    sannova--foxess--api-key

Resubmitting overwrites; Key Vault keeps the previous version.
