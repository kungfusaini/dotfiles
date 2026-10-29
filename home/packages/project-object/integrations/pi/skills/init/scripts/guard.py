#!/usr/bin/env python3

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
MARKER_NAME = ".project-object-initialized.json"
SCOPE_PLACEHOLDER = "<!-- project-object:init-scope -->"
PRISTINE_FILES = {
    "NOTES.md": "# Notes\n",
    "TODO.md": "# Todo\n\n## Now\n\n## Next\n\n## Waiting\n",
}


class InitRefused(RuntimeError):
    pass


def data_root() -> Path:
    home = Path.home()
    return Path(os.environ.get("PROJECT_OBJECT_DATA_DIR", Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")) / "project-object"))


def stream_home() -> Path:
    project_id = os.environ.get("PROJECT_OBJECT_ID", "")
    stream_id = os.environ.get("PROJECT_OBJECT_STREAM_ID", "")
    supplied_home = os.environ.get("PROJECT_OBJECT_STREAM_HOME", "")
    if not UUID_PATTERN.fullmatch(project_id):
        raise InitRefused("/init requires a stream-attached Pi session with a canonical project ID")
    if not UUID_PATTERN.fullmatch(stream_id):
        raise InitRefused("/init requires a stream-attached Pi session with a canonical stream ID")
    expected = data_root() / "projects" / project_id / "streams" / stream_id
    if not supplied_home or Path(supplied_home) != expected:
        raise InitRefused("the attached stream home does not match its canonical UUID path")
    if expected.is_symlink() or not expected.is_dir():
        raise InitRefused("the canonical stream home is missing or unsafe")
    return expected


def marker_path(home: Path) -> Path:
    marker = home / MARKER_NAME
    if marker.is_symlink():
        raise InitRefused("the stream initialization marker is unsafe")
    return marker


def populated_artifacts(home: Path) -> list[str]:
    populated = []
    agents = home / "AGENTS.md"
    try:
        if agents.is_symlink() or not agents.is_file():
            populated.append("AGENTS.md is missing or unsafe")
        elif SCOPE_PLACEHOLDER not in agents.read_text():
            populated.append("AGENTS.md already contains initialized stream scope")
    except OSError as error:
        populated.append(f"AGENTS.md cannot be read: {error}")

    for name, pristine in PRISTINE_FILES.items():
        path = home / name
        if path.is_symlink() or not path.is_file():
            populated.append(f"{name} is missing or unsafe")
            continue
        try:
            content = path.read_text()
        except OSError as error:
            populated.append(f"{name} cannot be read: {error}")
            continue
        if content != pristine:
            populated.append(f"{name} already contains stream material")

    plans = home / "plans"
    if plans.is_symlink() or not plans.is_dir():
        populated.append("plans/ is missing or unsafe")
    else:
        try:
            if any(plans.iterdir()):
                populated.append("plans/ already contains stream material")
        except OSError as error:
            populated.append(f"plans/ cannot be read: {error}")

    events = home / "worklogs" / "events.jsonl"
    if events.is_symlink():
        populated.append("the stream worklog is unsafe")
    elif events.exists():
        try:
            if events.stat().st_size > 0:
                populated.append("the stream worklog already contains events")
        except OSError as error:
            populated.append(f"the stream worklog cannot be inspected: {error}")
    return populated


def check(home: Path) -> None:
    marker = marker_path(home)
    if marker.exists():
        raise InitRefused("this stream has already been initialized")
    populated = populated_artifacts(home)
    if populated:
        raise InitRefused("initialization refused: " + "; ".join(populated))
    print(json.dumps({"ok": True, "streamHome": str(home), "state": "pristine"}))


def mark(home: Path) -> None:
    marker = marker_path(home)
    if marker.exists():
        raise InitRefused("this stream has already been initialized")
    agents = home / "AGENTS.md"
    if SCOPE_PLACEHOLDER in agents.read_text():
        raise InitRefused("cannot mark an incomplete initialization: AGENTS.md scope")
    todo = home / "TODO.md"
    if todo.read_text() == PRISTINE_FILES["TODO.md"]:
        raise InitRefused("cannot mark an incomplete initialization: TODO.md")
    value = {
        "version": 1,
        "initializedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "projectId": os.environ["PROJECT_OBJECT_ID"],
        "streamId": os.environ["PROJECT_OBJECT_STREAM_ID"],
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(marker, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        marker.unlink(missing_ok=True)
        raise
    directory_descriptor = os.open(home, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)
    print(json.dumps({"ok": True, "streamHome": str(home), "state": "initialized", "marker": str(marker)}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Guard one-time Project Object stream initialization")
    parser.add_argument("action", choices=("check", "mark"))
    arguments = parser.parse_args()
    try:
        home = stream_home()
        check(home) if arguments.action == "check" else mark(home)
    except (InitRefused, OSError, KeyError) as error:
        print(f"stream-init: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
