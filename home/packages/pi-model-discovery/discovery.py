#!/usr/bin/env python3
"""Read-only Codex catalog discovery. Never refresh auth or invoke a model."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 4 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}\Z")
EFFORT = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")


class CheckError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def parse_catalog(data):
    if not isinstance(data, dict) or not isinstance(data.get("models"), list) or not data["models"]:
        raise CheckError("schema_error")
    models = []
    seen = set()
    for item in data["models"]:
        if not isinstance(item, dict) or not isinstance(item.get("slug"), str) or not ID.fullmatch(item["slug"]):
            raise CheckError("schema_error")
        if item["slug"] in seen:
            raise CheckError("schema_error")
        seen.add(item["slug"])
        if item.get("visibility") not in ("list", "hide") or not isinstance(item.get("supported_in_api"), bool):
            raise CheckError("schema_error")
        levels = item.get("supported_reasoning_levels")
        if not isinstance(levels, list) or any(not isinstance(v, dict) or not isinstance(v.get("effort"), str) or not EFFORT.fullmatch(v["effort"]) for v in levels):
            raise CheckError("schema_error")
        # Persist an allowlist only: no descriptions, instructions, identity or raw payload.
        models.append({"id": item["slug"], "listed": item["visibility"] == "list",
                       "supportedInApi": item["supported_in_api"],
                       "thinkingLevels": sorted({v["effort"] for v in levels})})
    return sorted(models, key=lambda m: m["id"])


def fetch_catalog(auth_path, client_version, opener=None):
    try:
        auth = json.loads(auth_path.read_text())["openai-codex"]
        token, account = auth["access"], auth["accountId"]
        if any(not isinstance(v, str) or not v or not v.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in v)
               for v in (token, account)):
            raise ValueError()
        if auth.get("expires", 0) <= time.time() * 1000 + 1000:
            raise CheckError("auth_expired")
    except (OSError, ValueError, KeyError, TypeError):
        raise CheckError("auth_missing") from None
    url = "https://chatgpt.com/backend-api/codex/models?" + urllib.parse.urlencode({"client_version": client_version})
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token, "ChatGPT-Account-Id": account,
        "Accept": "application/json", "User-Agent": "codex_cli_rs/" + client_version,
        "originator": "codex_cli_rs",
    })
    try:
        with (opener or urllib.request.build_opener(NoRedirect)).open(request, timeout=20) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise CheckError("response_too_large")
        return parse_catalog(json.loads(raw))
    except urllib.error.HTTPError as exc:
        raise CheckError("auth_expired" if exc.code == 401 else f"http_{exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
        raise CheckError("network_error") from None
    except (ValueError, TypeError):
        raise CheckError("schema_error") from None


def read_state(path):
    try:
        data = json.loads(path.read_text())
        if data.get("version") == 1:
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {}


def collect(auth_path, state_path, client_version, fetch=fetch_catalog):
    old = read_state(state_path)
    now = int(time.time() * 1000)
    state = {"version": 1, "provider": "openai-codex", "checkedAt": now,
             "clientVersion": client_version, "status": "ok"}
    try:
        state["models"] = fetch(auth_path, client_version)
        state["lastSuccessAt"] = now
    except CheckError as exc:
        state["status"] = str(exc)
        # An unsuccessful fetch must not masquerade as an empty/removed catalog.
        state["models"] = old.get("models", [])
        state["lastSuccessAt"] = old.get("lastSuccessAt")
    state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state_path.parent.is_symlink() or state_path.parent.stat().st_uid != os.getuid():
        raise CheckError("unsafe_state_directory")
    state_path.parent.chmod(0o700)
    fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=state_path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, state_path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "status"])
    parser.add_argument("--client-version", default="@CODEX_VERSION@")
    args = parser.parse_args()
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", config / "pi/agent"))
    path = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "pi-model-discovery/catalog.json"
    try:
        if args.command == "status":
            print(json.dumps(read_state(path), indent=2))
            return 0
        state = collect(agent / "auth.json", path, args.client_version)
        print("Model catalog check: " + state["status"])
        return 0 if state["status"] == "ok" else 1
    except (OSError, CheckError):
        print("Model discovery could not read or write local state", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
