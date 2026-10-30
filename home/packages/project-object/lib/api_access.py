"""Local API catalog and project availability. Credentials live in Secret Service, not SQLite."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sqlite3
import subprocess
from urllib.parse import urlsplit

from project_object import RegistryError, canonical_uuid, ensure_private_directory

API_ID = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
SCHEMA = """
CREATE TABLE IF NOT EXISTS apis (
  id TEXT PRIMARY KEY,
  base_url TEXT NOT NULL,
  docs_url TEXT NOT NULL DEFAULT '',
  auth_type TEXT NOT NULL CHECK (auth_type IN ('bearer', 'header')),
  header_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS access (
  api_id TEXT NOT NULL REFERENCES apis(id) ON DELETE CASCADE,
  project_id TEXT NOT NULL,
  PRIMARY KEY (api_id, project_id)
);
"""
# The empty project ID represents global availability; all other IDs are canonical UUIDs.


def validate_api_id(value: str) -> str:
    if not API_ID.fullmatch(value):
        raise ValueError("API ID must be lowercase letters, digits, or hyphens, starting with a letter")
    return value


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or value.endswith("//")):
        raise ValueError("Base URL must be an HTTPS origin (no path, query, or credentials)")
    try:
        parsed.port
    except ValueError as error:
        raise ValueError("Invalid API port") from error
    return value.rstrip("/")


def validate_header(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", value):
        raise ValueError("Invalid HTTP header name")
    if value.lower() in ("host", "authorization", "cookie", "proxy-authorization"):
        raise ValueError("Use bearer auth for Authorization; reserved header name")
    return value


def open_catalog(data_root: Path) -> sqlite3.Connection:
    ensure_private_directory(data_root)
    path = data_root / "apis.sqlite"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise RegistryError("Unsafe API catalog path")
    connection = sqlite3.connect(path, timeout=5)
    try:
        os.chmod(path, 0o600)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)
        return connection
    except BaseException:
        connection.close()
        raise


def add_api(db: sqlite3.Connection, api_id: str, base_url: str, auth_type: str,
            docs_url: str = "", header_name: str = "") -> None:
    validate_api_id(api_id)
    base_url = validate_base_url(base_url)
    if auth_type not in ("bearer", "header"):
        raise ValueError("Auth type must be bearer or header")
    if auth_type == "header":
        validate_header(header_name)
    elif header_name:
        raise ValueError("Header name only applies to header authentication")
    if docs_url and urlsplit(docs_url).scheme != "https":
        raise ValueError("Docs URL must use HTTPS")
    with db:
        db.execute("INSERT INTO apis VALUES (?, ?, ?, ?, ?)",
                   (api_id, base_url, docs_url, auth_type, header_name))


def grant(db: sqlite3.Connection, api_id: str, project_id: str) -> None:
    validate_api_id(api_id)
    if project_id:
        canonical_uuid(project_id)
    with db:
        if not db.execute("SELECT 1 FROM apis WHERE id = ?", (api_id,)).fetchone():
            raise ValueError("Unknown API")
        db.execute("INSERT OR IGNORE INTO access VALUES (?, ?)", (api_id, project_id))


def available(db: sqlite3.Connection, project_id: str) -> list[tuple]:
    canonical_uuid(project_id)
    return db.execute("""SELECT DISTINCT a.id, a.base_url, a.docs_url, a.auth_type, a.header_name
        FROM apis a JOIN access g ON g.api_id = a.id
        WHERE g.project_id IN ('', ?) ORDER BY a.id""", (project_id,)).fetchall()


def lookup(db: sqlite3.Connection, project_id: str, api_id: str) -> tuple:
    validate_api_id(api_id)
    record = next((row for row in available(db, project_id) if row[0] == api_id), None)
    if record is None:
        raise ValueError("API not available in this project")
    return record


def store_credential(api_id: str, secret: str, *, secret_tool: str = "secret-tool") -> None:
    validate_api_id(api_id)
    if not secret or "\n" in secret or "\r" in secret:
        raise ValueError("Credential must be non-empty and fit on one line")
    subprocess.run([secret_tool, "store", "--label", f"Project Object: {api_id}",
                    "application", "project-object", "api", api_id],
                   input=secret, text=True, check=True, stdout=subprocess.DEVNULL)


def load_credential(api_id: str, *, secret_tool: str = "secret-tool") -> str:
    validate_api_id(api_id)
    result = subprocess.run([secret_tool, "lookup", "application", "project-object", "api", api_id],
                            capture_output=True, text=True, check=True)
    secret = result.stdout.rstrip("\n")
    if not secret or "\r" in secret or "\n" in secret:
        raise ValueError("No valid credential in keyring for this API")
    return secret
