"""
Platform definitions: what credentials each monitoring platform needs.

Adding a new platform means adding an entry here. Nothing else changes —
the form, validation, and Key Vault naming all derive from this.

Secret naming convention in Key Vault:
    {vendor_slug}--{platform}--{field}
e.g.  sannova--foxess--api-key

Key Vault names allow only alphanumerics and dashes, so field names with
underscores are converted automatically.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Field:
    key: str
    label: str
    kind: Literal["text", "password", "textarea", "select"] = "text"
    help: str = ""
    required: bool = True
    options: list[str] = field(default_factory=list)
    placeholder: str = ""


@dataclass
class Platform:
    slug: str
    name: str
    brands: str
    fields: list[Field]
    guidance: str = ""


PLATFORMS: list[Platform] = [
    Platform(
        slug="foxess",
        name="FoxESS (FoxCloud 2.0)",
        brands="FoxESS",
        guidance=(
            "Log into foxesscloud.com → User Profile → API Management → "
            "Generate API Key. Copy it immediately; regenerating invalidates "
            "the previous key."
        ),
        fields=[
            Field("api_key", "API Key", "password",
                  "The key generated in API Management."),
            Field("inverter_serials", "Inverter serial numbers", "textarea",
                  "One per line. From Device → Inverter.", required=False),
            Field("battery_serials", "Battery serial numbers", "textarea",
                  "One per line, if any batteries are installed.",
                  required=False),
        ],
    ),
    Platform(
        slug="solax",
        name="SolaX Cloud",
        brands="SolaX",
        guidance=(
            "Portal → Service → API → 'Obtain TokenID'. Then Device → "
            "Inverter and copy the registration number for every device — "
            "SolaX queries per serial, so a missing serial is a missing site."
        ),
        fields=[
            Field("token_id", "TokenID", "password"),
            Field("serials", "Device registration numbers", "textarea",
                  "One per line. All of them."),
            Field("rate_limit", "Known rate limit", "text",
                  "If you know it, e.g. '1 call per 10 seconds'.",
                  required=False),
        ],
    ),
    Platform(
        slug="huawei",
        name="Huawei FusionSolar",
        brands="Huawei",
        guidance=(
            "System → Company Management → Northbound Management → Add. "
            "The northbound username cannot match your portal login. "
            "Please create TWO accounts (production and development) and set "
            "the expiry date as far in the future as allowed. Scope both to "
            "Company, not to a specific plant list."
        ),
        fields=[
            Field("region_prefix", "Portal prefix", "text",
                  "From your portal URL, e.g. 'intl' or 'eu5'.",
                  placeholder="intl"),
            Field("nb_username_prod", "Northbound username (production)",
                  "text"),
            Field("nb_password_prod", "Northbound password (production)",
                  "password"),
            Field("nb_username_dev", "Northbound username (development)",
                  "text", required=False),
            Field("nb_password_dev", "Northbound password (development)",
                  "password", required=False),
            Field("station_codes", "Station codes", "textarea",
                  "One per line, including the NE= prefix.", required=False),
        ],
    ),
    Platform(
        slug="sungrow",
        name="Sungrow iSolarCloud",
        brands="Sungrow",
        guidance=(
            "Once Sungrow approves your Open API application, the "
            "Applications page shows the App Key, Access Key and RSA public "
            "key. Please also create a read-only user for the API rather than "
            "sharing your admin login."
        ),
        fields=[
            Field("region", "Regional gateway", "select",
                  "Which server your account lives on.",
                  options=[
                      "gateway.isolarcloud.eu (Europe)",
                      "gateway.isolarcloud.com.hk (International)",
                      "gateway.isolarcloud.com (China)",
                      "augateway.isolarcloud.com (Australia)",
                  ]),
            Field("app_key", "App Key", "password"),
            Field("access_key", "Access Key (x-access-key)", "password"),
            Field("username", "API user account", "text",
                  "The read-only user, not your admin login."),
            Field("password", "API user password", "password"),
            Field("rsa_public_key", "RSA public key", "textarea",
                  "Only if your app was issued with encryption enabled.",
                  required=False),
        ],
    ),
    Platform(
        slug="solarman",
        name="SOLARMAN Business",
        brands="Deye, Sofar, and rebadged brands",
        guidance=(
            "Issued by Solarman or your distributor, not self-service. "
            "Please confirm the credentials are for the PRODUCTION "
            "environment — test app IDs will not work against live data."
        ),
        fields=[
            Field("app_id", "APP_ID", "password"),
            Field("app_secret", "APP_SECRET", "password"),
            Field("email", "Business account email", "text"),
            Field("password", "Business account password", "password"),
            Field("org_id", "Organisation / merchant ID", "text",
                  "If you have it. We can retrieve it otherwise.",
                  required=False),
        ],
    ),
    Platform(
        slug="solis",
        name="SolisCloud",
        brands="Solis / Ginlong",
        guidance=(
            "soliscloud.com → Service → API Management → Activate Now → "
            "View Key. A verification code arrives by email with a 60-second "
            "window, so have your inbox open first."
        ),
        fields=[
            Field("key_id", "Key ID", "password",
                  "Long number, usually beginning 1300..."),
            Field("key_secret", "Key Secret", "password"),
        ],
    ),
    Platform(
        slug="goodwe",
        name="GoodWe SEMS Portal",
        brands="GoodWe",
        guidance=(
            "GoodWe's API uses your SEMS account login directly — there is no "
            "separate key. Because that credential grants full account "
            "access, we store it in the same encrypted vault as everything "
            "else and access is logged. Please consider creating a dedicated "
            "sub-account if SEMS allows it."
        ),
        fields=[
            Field("username", "SEMS account email", "text"),
            Field("password", "SEMS account password", "password"),
            Field("org_code", "SEMS Organization Code", "text"),
            Field("region", "Region", "text",
                  "e.g. eu, us, au", required=False),
        ],
    ),
    Platform(
        slug="deye",
        name="Deye Cloud",
        brands="Deye (native platform)",
        guidance=(
            "Only needed if your Deye systems do NOT use Solarman loggers. "
            "If they do, the Solarman credentials above already cover them."
        ),
        fields=[
            Field("app_id", "APP_ID", "password", required=False),
            Field("app_secret", "APP_SECRET", "password", required=False),
            Field("email", "Account email", "text", required=False),
            Field("password", "Account password", "password",
                  required=False),
        ],
    ),
    Platform(
        slug="other",
        name="Other platform",
        brands="Sunways, SmartClient, anything else",
        guidance=(
            "For platforms not listed above. Tell us which manufacturer it "
            "is and paste whatever credentials you have."
        ),
        fields=[
            Field("platform_name", "Which platform / manufacturer", "text"),
            Field("credentials", "Credentials", "textarea",
                  "Paste whatever you have — keys, logins, account IDs."),
        ],
    ),
]

PLATFORM_BY_SLUG = {p.slug: p for p in PLATFORMS}


def secret_name(vendor_slug: str, platform_slug: str, field_key: str) -> str:
    """Key Vault secret names allow only alphanumerics and dashes."""
    parts = [vendor_slug, platform_slug, field_key.replace("_", "-")]
    name = "--".join(parts)
    if not all(c.isalnum() or c == "-" for c in name):
        raise ValueError(f"invalid secret name generated: {name}")
    return name
