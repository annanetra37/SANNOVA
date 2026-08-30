"""
Credential intake — Triple i

A small web form the vendor uses to submit monitoring platform credentials.
Values go straight to Azure Key Vault and are never written to disk, never
stored in a database, and never logged.

Access is gated by a signed invite token so the URL cannot be found or
guessed. Tokens expire.

Run locally:
    uvicorn main:app --reload
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from collections import defaultdict

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import vault
from platforms import PLATFORM_BY_SLUG, PLATFORMS, secret_name

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("intake")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set")

TOKEN_MAX_AGE = int(os.getenv("TOKEN_MAX_AGE_SECONDS", 14 * 24 * 3600))
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN")

serializer = URLSafeTimedSerializer(SECRET_KEY, salt="intake-invite")

app = FastAPI(title="Triple i — credential intake", docs_url=None,
              redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------------------------------------------------------------------------
# Security headers and a simple rate limit
# ---------------------------------------------------------------------------

_hits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 30          # requests
RATE_WINDOW = 300        # seconds


def client_ip(request: Request) -> str:
    """
    The caller's address as seen past the platform edge.

    Railway terminates TLS and proxies, so request.client.host is the edge,
    identical for every visitor. Rate limiting on that would bucket the whole
    internet together. The first hop of X-Forwarded-For is the real client.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def over_limit(ip: str) -> bool:
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(_hits[ip]) >= RATE_LIMIT:
        return True
    _hits[ip].append(now)
    return False


@app.middleware("http")
async def guard(request: Request, call_next):
    # The platform health check polls constantly and must never be throttled.
    if request.url.path == "/healthz":
        response = await call_next(request)
    elif over_limit(client_ip(request)):
        # Returned, not raised: an HTTPException raised inside middleware runs
        # outside the handler that would turn it into a 429, and surfaces to
        # the caller as a 500 instead.
        response = JSONResponse({"detail": "Too many requests"},
                                status_code=429)
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self'; script-src 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    # Railway terminates TLS; this tells browsers never to try plain HTTP.
    response.headers["Strict-Transport-Security"] = (
        "max-age=31536000; includeSubDomains"
    )
    return response


# ---------------------------------------------------------------------------
# Invite tokens
# ---------------------------------------------------------------------------

def make_invite(vendor_slug: str, vendor_name: str) -> str:
    return serializer.dumps({"v": vendor_slug, "n": vendor_name})


def read_invite(token: str) -> dict:
    try:
        return serializer.loads(token, max_age=TOKEN_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(410, "This link has expired. Please ask for a "
                                 "fresh one.")
    except BadSignature:
        raise HTTPException(404, "Not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    # No public landing page. Nothing to enumerate.
    raise HTTPException(404, "Not found")


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/admin/invite", response_class=HTMLResponse)
async def admin_invite(request: Request, key: str = "", vendor: str = "",
                       name: str = ""):
    """
    Generate an invite link. Protected by ADMIN_TOKEN.

    Usage:
      /admin/invite?key=<ADMIN_TOKEN>&vendor=sannova&name=SANNOVA+Engineering
    """
    if not ADMIN_TOKEN or not secrets.compare_digest(key, ADMIN_TOKEN):
        raise HTTPException(404, "Not found")
    if not vendor or not vendor.replace("-", "").isalnum():
        raise HTTPException(400, "vendor must be alphanumeric/dashes")

    token = make_invite(vendor, name or vendor)
    base = str(request.base_url).rstrip("/")
    return templates.TemplateResponse(
        request, "invite.html",
        {"url": f"{base}/s/{token}",
         "vendor": vendor, "days": TOKEN_MAX_AGE // 86400},
    )


@app.get("/s/{token}", response_class=HTMLResponse)
async def index(request: Request, token: str):
    data = read_invite(token)
    return templates.TemplateResponse(
        request, "index.html",
        {"token": token, "platforms": PLATFORMS,
         "vendor_name": data["n"]},
    )


@app.get("/s/{token}/{platform_slug}", response_class=HTMLResponse)
async def form(request: Request, token: str, platform_slug: str):
    data = read_invite(token)
    platform = PLATFORM_BY_SLUG.get(platform_slug)
    if not platform:
        raise HTTPException(404, "Unknown platform")
    return templates.TemplateResponse(
        request, "form.html",
        {"token": token, "platform": platform,
         "vendor_name": data["n"]},
    )


@app.post("/s/{token}/{platform_slug}")
async def submit(request: Request, token: str, platform_slug: str):
    data = read_invite(token)
    vendor_slug = data["v"]
    platform = PLATFORM_BY_SLUG.get(platform_slug)
    if not platform:
        raise HTTPException(404, "Unknown platform")

    form_data = await request.form()

    items: list[tuple[str, str]] = []
    missing: list[str] = []

    for f in platform.fields:
        raw = (form_data.get(f.key) or "").strip()
        if not raw:
            if f.required:
                missing.append(f.label)
            continue
        items.append((secret_name(vendor_slug, platform.slug, f.key), raw))

    if missing:
        return templates.TemplateResponse(
            request, "form.html",
            {"token": token, "platform": platform,
             "vendor_name": data["n"],
             "error": "Please complete: " + ", ".join(missing)},
            status_code=400,
        )

    if not items:
        return templates.TemplateResponse(
            request, "form.html",
            {"token": token, "platform": platform,
             "vendor_name": data["n"],
             "error": "Nothing was entered."},
            status_code=400,
        )

    try:
        written = vault.store_many(
            items,
            tags={"vendor": vendor_slug, "platform": platform.slug},
        )
    except vault.VaultError:
        # Honest failure. Never show success for a write that didn't happen.
        return templates.TemplateResponse(
            request, "form.html",
            {"token": token, "platform": platform,
             "vendor_name": data["n"],
             "error": "We couldn't save these securely just now. Nothing was "
                      "stored. Please try again, or contact us."},
            status_code=503,
        )

    log.info("vendor=%s platform=%s stored=%d fields",
             vendor_slug, platform.slug, len(written))

    return RedirectResponse(
        f"/s/{token}/{platform_slug}/done?n={len(written)}", status_code=303
    )


@app.get("/s/{token}/{platform_slug}/done", response_class=HTMLResponse)
async def done(request: Request, token: str, platform_slug: str, n: int = 0):
    data = read_invite(token)
    platform = PLATFORM_BY_SLUG.get(platform_slug)
    if not platform:
        raise HTTPException(404, "Unknown platform")
    return templates.TemplateResponse(
        request, "done.html",
        {"token": token, "platform": platform,
         "count": n, "vendor_name": data["n"]},
    )
