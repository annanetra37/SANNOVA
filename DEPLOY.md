# Deploying — where every environment variable comes from

Follow this once. It takes about 20 minutes, most of it in the Azure portal.

At the end you will have seven values to paste into Railway:

    SECRET_KEY
    ADMIN_TOKEN
    AZURE_KEYVAULT_URL
    AZURE_TENANT_ID
    AZURE_CLIENT_ID
    AZURE_CLIENT_SECRET
    TOKEN_MAX_AGE_SECONDS   (optional)

Only `SECRET_KEY` is needed to boot. The rest are needed before the app is
actually usable — see the table at the bottom.

---

## Before you start

You need an Azure subscription, and an account allowed to (a) create
resources and (b) register applications in Microsoft Entra ID. Many
organisations restrict (b) to administrators. If "New registration" is
greyed out in step 2, that is what happened — someone with the Application
Administrator or Cloud Application Administrator role has to do steps 2
and 4 for you and hand you back the three `AZURE_*` identifiers.

---

## 1. The two locally generated values

These are not Azure values. Generate them yourself, on any machine with
Python:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

Run it **twice** and keep the two outputs separate:

- The first becomes `SECRET_KEY`. It signs invite links. Changing it later
  invalidates every link already sent.
- The second becomes `ADMIN_TOKEN`. It is the password on `/admin/invite`.
  It must be a different value from `SECRET_KEY` — anyone who has the admin
  token can mint invite links, and you do not want that to also be the
  signing key.

Never reuse these between environments.

---

## 2. Create the Key Vault  →  `AZURE_KEYVAULT_URL`

1. Sign in at <https://portal.azure.com>.
2. Search **Key vaults** in the top bar → **Create**.
3. **Basics** tab:
   - *Subscription* — yours.
   - *Resource group* — **Create new**, e.g. `triplei-credentials`.
   - *Key vault name* — globally unique across all of Azure, 3–24
     characters, letters/numbers/hyphens, e.g. `triplei-creds`. If the name
     is taken you must pick another; the URL follows from it.
   - *Region* — wherever your data should live (e.g. UK South).
   - *Pricing tier* — **Standard**.
   - *Soft-delete* — on (it is mandatory now). Retention 90 days.
   - *Purge protection* — **enable it**. Without it, someone with delete
     rights can permanently destroy submitted credentials.
4. **Access configuration** tab — this choice matters, see step 3:
   - **Vault access policy** is the simpler path and the one that can
     express "write-only" exactly.
   - **Azure role-based access control (RBAC)** is Microsoft's recommended
     path but needs a custom role for write-only.
5. **Networking** tab: leave *Public access — all networks* enabled.
   Railway does not give you a fixed outbound IP on most plans, so a vault
   firewall restricted to selected networks will block the app.
6. **Review + create** → **Create**.

Then open the vault → **Overview** → copy the **Vault URI**. That is your
value, including the trailing slash:

    AZURE_KEYVAULT_URL=https://triplei-creds.vault.azure.net/

---

## 3. Register the intake app  →  tenant, client, secret

1. Search **Microsoft Entra ID** (this is the service formerly called Azure
   Active Directory — older guides use that name).
2. Left menu → **App registrations** → **New registration**.
3. Fill in:
   - *Name* — `triplei-credential-intake`.
   - *Supported account types* — **Accounts in this organizational
     directory only (single tenant)**.
   - *Redirect URI* — leave empty. This app never logs a human in through
     Azure; it authenticates as itself.
4. **Register**.
5. You land on the **Overview** page. Two of your values are here:

       AZURE_CLIENT_ID   =  "Application (client) ID"
       AZURE_TENANT_ID   =  "Directory (tenant) ID"

   Both are GUIDs like `3f2b9c1a-....`. Copy them now.
6. Left menu → **Certificates & secrets** → **Client secrets** tab →
   **New client secret**.
   - *Description* — `railway-intake`.
   - *Expires* — 12 or 24 months. **Write the expiry date in your
     calendar.** When it lapses the app stops being able to write and every
     submission fails with the "couldn't save securely" page.
7. After clicking Add, copy the **Value** column immediately:

       AZURE_CLIENT_SECRET = the "Value" column

   It is shown once. Navigate away and it is gone forever and you must
   create another. **Do not copy the "Secret ID" column** — that is an
   identifier, not the secret, and is the single most common mistake here.

---

## 4. Grant the app write-only access

This is the security design of the whole project: the app can write
credentials but cannot read any back, including its own. Which screen you
use depends on the choice you made in step 2.4.

### If you chose "Vault access policy"

1. Vault → **Access policies** → **Create**.
2. **Permissions** tab: under *Secret permissions*, tick **Set** and
   nothing else. Leave Get, List, Delete, Purge all unticked.
3. **Principal** tab: search `triplei-credential-intake`, select it.
4. Skip *Application*, then **Create**.

That is a genuine write-only grant, which is why this path is worth the
slightly older-fashioned screen.

### If you chose "Azure RBAC"

The built-in roles cannot express write-only, and it is worth knowing why
before you pick one:

| Built-in role | What it actually allows |
|---|---|
| Key Vault Secrets Officer | read **and** write **and** delete — too much |
| Key Vault Secrets User | read only — cannot write, so the app breaks |

So you need a custom role. Subscription → **Access control (IAM)** →
**Add** → **Add custom role** → start from scratch, then on the **JSON**
tab set the permissions to exactly:

    "actions": [],
    "notActions": [],
    "dataActions": [
      "Microsoft.KeyVault/vaults/secrets/setSecret/action"
    ],
    "notDataActions": []

Name it `Key Vault Secrets Writer`, create it, then assign it to
`triplei-credential-intake` scoped to the vault (Vault → Access control
(IAM) → Add role assignment).

---

## 5. Register the ingestion worker (separate principal)

The worker that later reads these credentials must be a **different** app
registration, holding only read. Two principals is the point: compromising
either one gives an attacker half the capability.

Repeat step 3 with the name `triplei-ingestion-worker`, then grant it:

- *Vault access policy mode* — secret permissions **Get** and **List**
  only.
- *RBAC mode* — the built-in **Key Vault Secrets User** role, which is
  exactly get/list.

Its client ID and secret go into your ingestion project, alongside
`worker_credentials.py`. They do **not** go into Railway.

---

## 6. Put the values into Railway

1. <https://railway.app> → your project → click the service.
2. **Variables** tab → **Raw Editor** is fastest for a first setup.
3. Paste all of them at once:

       SECRET_KEY=...
       ADMIN_TOKEN=...
       AZURE_KEYVAULT_URL=https://triplei-creds.vault.azure.net/
       AZURE_TENANT_ID=...
       AZURE_CLIENT_ID=...
       AZURE_CLIENT_SECRET=...

4. Save. Railway redeploys automatically.

**Do not set `PORT`.** Railway injects it and overriding it breaks the
bind. `TOKEN_MAX_AGE_SECONDS` is optional and defaults to 14 days.

---

## 7. Check it worked

- `https://<your-app>.up.railway.app/healthz` → `{"ok": true}`.
- `https://<your-app>.up.railway.app/` → **404 is correct.** There is no
  public landing page by design; that is not a fault.
- Mint a link:

      /admin/invite?key=<ADMIN_TOKEN>&vendor=sannova&name=SANNOVA+Engineering

  A 404 here means `ADMIN_TOKEN` is unset or does not match.
- Open the invite link, submit one throwaway value, then confirm it landed:
  Azure portal → vault → **Secrets**. You should see
  `sannova--foxess--api-key`. Delete the test value afterwards.

---

## Which variable blocks what

| Variable | Read at | If it is missing |
|---|---|---|
| `SECRET_KEY` | import | **Container crashes on boot** |
| `ADMIN_TOKEN` | import | Boots, but `/admin/invite` 404s — no invite links |
| `AZURE_KEYVAULT_URL` | first write | Boots, submissions fail with 503 |
| `AZURE_TENANT_ID` | first write | Boots, submissions fail with 503 |
| `AZURE_CLIENT_ID` | first write | Boots, submissions fail with 503 |
| `AZURE_CLIENT_SECRET` | first write | Boots, submissions fail with 503 |
| `TOKEN_MAX_AGE_SECONDS` | import | Defaults to 14 days |

The Azure four fail late, at the moment a vendor submits, rather than at
boot. Do a real test submission after any change to them.

---

## When something fails

Submissions return the generic 503 page on any vault failure, and
`vault.py` logs the exception *type* but never the value. Check the Railway
deploy logs for a `keyvault write failed` line:

| Logged type | Almost always means |
|---|---|
| `ClientAuthenticationError` | wrong tenant/client ID, bad secret, or the secret expired |
| `HttpResponseError` with 403 | the principal authenticated but lacks **Set** — redo step 4 |
| `ServiceRequestError` | vault firewall is blocking Railway — see step 2.5 |
| `ResourceNotFoundError` | `AZURE_KEYVAULT_URL` typo |

## Rotating a credential later

Client secrets expire. To rotate without downtime: add a *second* client
secret in step 3.6, paste the new value into Railway, let it redeploy,
confirm a test submission works, then delete the old secret in Azure.
