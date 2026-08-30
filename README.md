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

## Applying the brand

Every brand decision lives in the `:root` block at the top of
`static/style.css` — colours, type stack, corner radii. Change those tokens
and the whole UI follows; nothing else needs editing.

Two things sit outside that block because they cannot read CSS variables:

- `static/favicon.svg` — the fill is hardcoded, update it alongside `--brand`.
- `templates/base.html` — swap the `.wordmark` span for
  `<img src="/static/logo.svg" alt="Triple i" class="logo">` once you have
  the real mark. The header sizing already allows for it.

The Content-Security-Policy is `style-src 'self'` and `script-src 'none'`,
so remote stylesheets (Google Fonts) and all JavaScript are blocked
deliberately. To use the brand typeface, put the `.woff2` files in
`static/` and add an `@font-face` rule — self-hosted files are allowed.
Do not loosen the CSP to load a font.

## Adding a platform

Add a `Platform(...)` entry to `PLATFORMS` in `platforms.py`. The form,
validation and vault naming all derive from it. Nothing else changes.

## Secret naming

    {vendor}--{platform}--{field}
    sannova--foxess--api-key

Resubmitting overwrites; Key Vault keeps the previous version.
