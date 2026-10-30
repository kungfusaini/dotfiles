"""FreeAgent provider preset for the reusable OAuth 2.0 connector."""
from __future__ import annotations

from oauth2 import OAuthConfig, login as oauth_login, configure as oauth_configure

PRODUCTION = "https://api.freeagent.com"
SANDBOX = "https://api.sandbox.freeagent.com"
DOCS = "https://dev.freeagent.com/docs/oauth"


def settings(base_url: str) -> OAuthConfig:
    if base_url not in (PRODUCTION, SANDBOX):
        raise ValueError("FreeAgent OAuth only supports official production or sandbox hosts")
    return OAuthConfig(authorization_url=base_url + "/v2/approve_app",
                       token_url=base_url + "/v2/token_endpoint", client_auth="basic")


def login(db, api_id: str, client_id: str, client_secret: str, redirect_uri: str, base_url: str) -> None:
    oauth_login(db, api_id, base_url, DOCS, client_id, client_secret, redirect_uri, settings(base_url))


def migrate_legacy(db) -> None:
    """Keep logins made with the initial FreeAgent-specific implementation usable."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='freeagent_oauth'").fetchone():
        return
    rows = db.execute("SELECT f.api_id, f.client_id, a.base_url FROM freeagent_oauth f JOIN apis a ON a.id=f.api_id").fetchall()
    for api_id, client_id, base_url in rows:
        oauth_configure(db, api_id, base_url, DOCS, client_id, settings(base_url))
    with db:
        db.execute("DROP TABLE freeagent_oauth")
