#!/usr/bin/env python3
"""Extract a public Gemini shared chat transcript to Markdown.

Usage:
  python extract-gemini-share.py URL -o transcript.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import subprocess
import urllib.parse
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari"


def fetch_text(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[str, str]:
    args = ["curl", "--disable", "--fail", "--silent", "--show-error",
            "--location", "--max-redirs", "5", "--max-time", "45",
            "--proto", "=https", "--proto-redir", "=https", "--user-agent", UA]
    for key, value in (headers or {}).items():
        args.extend(["--header", f"{key}: {value}"])
    if data is not None:
        args.extend(["--data-binary", "@-"])
    args.extend(["--write-out", "\\n%{url_effective}", url])
    result = subprocess.run(args, input=data, capture_output=True, check=True)
    text, final_url = result.stdout.decode("utf-8").rsplit("\n", 1)
    return final_url, text


def resolve_share(url: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port:
        raise ValueError("Expected an HTTPS Gemini public share URL")
    if parsed.hostname == "share.gemini.google":
        # Resolve only the short link; following it with the old Python transport
        # can get stuck in a Google redirect loop.
        result = subprocess.run(
            ["curl", "--disable", "--fail", "--silent", "--show-error", "--head",
             "--max-time", "45", "--proto", "=https", "--output", "/dev/null",
             "--write-out", "%{redirect_url}", url],
            capture_output=True, text=True, check=True,
        )
        parsed = urllib.parse.urlsplit(result.stdout.strip())
    if (parsed.scheme != "https" or parsed.hostname != "gemini.google.com"
            or parsed.username or parsed.password or parsed.port
            or not re.fullmatch(r"/share/[A-Za-z0-9_-]+/?", parsed.path)):
        raise ValueError("Link did not resolve to a Gemini public share")
    share_id = find_share_id(parsed.path, "")
    return share_id, f"https://gemini.google.com/share/{share_id}?hl=en"


def find_share_id(url: str, html_text: str) -> str:
    candidates = [url, html_text]
    for value in candidates:
        m = re.search(r"/share/([A-Za-z0-9_-]+)", value)
        if m:
            return m.group(1)
    raise ValueError("Could not find Gemini share id in URL/page")


def find_bl(html_text: str) -> str:
    # Prefer the deployed BardChatUi build label from script URLs/config.
    patterns = [
        r"boq-gemini-web-uiserver\.BardChatUi\.([A-Za-z0-9_.-]+?\.L\.X\.O)",
        r"ck=boq-gemini-web-uiserver\.BardChatUi\.([A-Za-z0-9_.-]+?\.L\.X\.O)",
    ]
    for pat in patterns:
        matches = re.findall(pat, html_text)
        if matches:
            return "boq-gemini-web-uiserver.BardChatUi." + matches[-1]
    # Fallback: observed value may still work for a while, but prefer scraping above.
    return "boq-gemini-web-uiserver.BardChatUi.ZEktCH5hx9k.L.X.O"


def call_shared_rpc(share_id: str, bl: str) -> list:
    base = "https://gemini.google.com/_/BardChatUi/data/batchexecute"
    params = {
        "rpcids": "ujx1Bf",  # BardFrontendService.GetSharedConversation
        "source-path": f"/share/{share_id}",
        "bl": bl,
        "hl": "en-US",
        "_reqid": "12345",
        "rt": "c",
    }
    url = base + "?" + urllib.parse.urlencode(params)
    # Request shape observed from Gemini web client. [4] appears to request full shared content.
    f_req = [[["ujx1Bf", json.dumps([None, share_id, [4]], separators=(",", ":")), None, "generic"]]]
    body = ("f.req=" + urllib.parse.quote(json.dumps(f_req, separators=(",", ":"))) + "&at=").encode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "Origin": "https://gemini.google.com",
        "Referer": f"https://gemini.google.com/share/{share_id}",
    }
    _, text = fetch_text(url, data=body, headers=headers)
    lines = text.splitlines()
    # Batchexecute response alternates length lines and JSON lines after XSSI prefix.
    json_line = None
    for line in lines:
        if line.startswith("[[\"wrb.fr\",\"ujx1Bf\""):
            json_line = line
            break
    if not json_line:
        raise ValueError("Could not find ujx1Bf RPC payload in response")
    outer = json.loads(json_line)
    payload_str = outer[0][2]
    if not payload_str:
        raise ValueError("Shared conversation payload was empty")
    return json.loads(payload_str)


def extract_turns(payload: list) -> list[tuple[str, str]]:
    try:
        turns_raw = payload[0][1]
    except (IndexError, TypeError) as exc:
        raise ValueError("Unexpected shared-conversation payload shape") from exc
    if not isinstance(turns_raw, list) or not turns_raw:
        raise ValueError("No conversation turns returned")
    turns: list[tuple[str, str]] = []
    for turn in turns_raw:
        try:
            user = turn[2][0][0]
            chunks = turn[3][0][0][1]
            if user is None:
                user = ""
            if chunks is None:
                chunks = []
            if not isinstance(chunks, list) or not all(isinstance(c, str) for c in chunks):
                raise ValueError("Unexpected Gemini message chunks")
            assistant = "".join(chunks)
        except (IndexError, TypeError, KeyError) as exc:
            raise ValueError("Malformed message structure; refusing a partial capture") from exc
        if not isinstance(user, str) or not isinstance(assistant, str):
            raise ValueError("Unexpected message text shape")
        if not user.strip() and not assistant.strip():
            raise ValueError("A turn contained no extractable text; refusing a partial capture")
        turns.append((user, assistant))
    return turns


def markdown(url: str, final_url: str, share_id: str, turns: list[tuple[str, str]]) -> str:
    now = dt.datetime.now().isoformat(timespec="seconds")
    parts = [
        "# Gemini Chat Capture\n\n",
        f"_Source URL: {url}_\n",
        f"_Final URL: {final_url}_\n",
        f"_Share ID: `{share_id}`_\n",
        f"_Captured on: {now}_\n\n",
        "## Notes\n\n",
        "- Extracted from a public Gemini shared conversation.\n",
        "- Dictated speech may contain transcription artifacts.\n",
        "- Text-only capture of the turns returned by Google; attachments and completeness are not verified.\n\n",
        "---\n\n",
        "## Full transcript\n",
    ]
    for i, (user, assistant) in enumerate(turns, 1):
        parts.append(f"\n### Turn {i}\n")
        parts.append("**User:**\n\n")
        parts.append((user if user else "_[empty / no extracted user text]_") + "\n\n")
        parts.append("**Gemini:**\n\n")
        parts.append((assistant if assistant else "_[empty / no extracted Gemini text]_") + "\n")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", help="Gemini shared chat URL")
    ap.add_argument("-o", "--output", help="Output Markdown path")
    args = ap.parse_args()

    try:
        share_id, page_url = resolve_share(args.url)
        final_url, page = fetch_text(page_url)
        payload = call_shared_rpc(share_id, find_bl(page))
        turns = extract_turns(payload)
    except (ValueError, TypeError, IndexError, OSError, subprocess.SubprocessError) as exc:
        print(f"Capture failed: {exc}", file=sys.stderr)
        return 1
    print(f"Retrieved {len(turns)} exchanges; "
          f"{sum(len(u) + len(a) for u, a in turns)} text characters. "
          "Full-history completeness is not verified.", file=sys.stderr)
    doc = markdown(args.url, final_url, share_id, turns)

    if args.output:
        out = Path(args.output).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x", encoding="utf-8") as handle:
            handle.write(doc)
        print(f"Wrote {len(turns)} turns to {out}")
    else:
        sys.stdout.write(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
