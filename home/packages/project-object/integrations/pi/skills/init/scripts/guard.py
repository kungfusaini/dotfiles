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


def attached_scope() -> tuple[Path, str, str, str | None]:
    project_id = os.environ.get("PROJECT_OBJECT_ID", "")
    supplied_project_home = os.environ.get("PROJECT_OBJECT_HOME", "")
    stream_id = os.environ.get("PROJECT_OBJECT_STREAM_ID", "")
    supplied_stream_home = os.environ.get("PROJECT_OBJECT_STREAM_HOME", "")
    if not UUID_PATTERN.fullmatch(project_id):
        raise InitRefused("/init requires a project-attached Pi session with a canonical project ID")

    expected_project = data_root() / "projects" / project_id
    if not supplied_project_home or Path(supplied_project_home) != expected_project:
        raise InitRefused("the attached project home does not match its canonical UUID path")

    if stream_id:
        if not UUID_PATTERN.fullmatch(stream_id):
            raise InitRefused("/init requires a canonical stream ID when a stream is attached")
        expected = expected_project / "streams" / stream_id
        if not supplied_stream_home or Path(supplied_stream_home) != expected:
            raise InitRefused("the attached stream home does not match its canonical UUID path")
        scope = "stream"
    else:
        if supplied_stream_home:
            raise InitRefused("a stream home was supplied without an attached stream ID")
        expected = expected_project
        scope = "project"

    if expected.is_symlink() or not expected.is_dir():
        raise InitRefused(f"the canonical {scope} home is missing or unsafe")
    return expected, scope, project_id, stream_id or None


def marker_path(home: Path, scope: str) -> Path:
    marker = home / MARKER_NAME
    if marker.is_symlink():
        raise InitRefused(f"the {scope} initialization marker is unsafe")
    return marker


def populated_artifacts(home: Path, scope: str) -> list[str]:
    populated = []
    agents = home / "AGENTS.md"
    try:
        if agents.is_symlink() or not agents.is_file():
            populated.append("AGENTS.md is missing or unsafe")
        elif SCOPE_PLACEHOLDER not in agents.read_text():
            populated.append(f"AGENTS.md already contains initialized {scope} scope")
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
            populated.append(f"{name} already contains {scope} material")

    plans = home / "plans"
    if plans.is_symlink() or not plans.is_dir():
        populated.append("plans/ is missing or unsafe")
    else:
        try:
            if any(plans.iterdir()):
                populated.append(f"plans/ already contains {scope} material")
        except OSError as error:
            populated.append(f"plans/ cannot be read: {error}")

    events = home / "worklogs" / "events.jsonl"
    if events.is_symlink():
        populated.append(f"the {scope} worklog is unsafe")
    elif events.exists():
        try:
            if events.stat().st_size > 0:
                populated.append(f"the {scope} worklog already contains events")
        except OSError as error:
            populated.append(f"the {scope} worklog cannot be inspected: {error}")
    return populated


def check(home: Path, scope: str) -> None:
    marker = marker_path(home, scope)
    if marker.exists():
        raise InitRefused(f"this {scope} has already been initialized")
    populated = populated_artifacts(home, scope)
    if populated:
        raise InitRefused("initialization refused: " + "; ".join(populated))
    print(json.dumps({"ok": True, "scope": scope, "scopeHome": str(home), "state": "pristine"}))


def mark(home: Path, scope: str, project_id: str, stream_id: str | None) -> None:
    marker = marker_path(home, scope)
    if marker.exists():
        raise InitRefused(f"this {scope} has already been initialized")
    agents = home / "AGENTS.md"
    if SCOPE_PLACEHOLDER in agents.read_text():
        raise InitRefused("cannot mark an incomplete initialization: AGENTS.md scope")
    todo = home / "TODO.md"
    if todo.read_text() == PRISTINE_FILES["TODO.md"]:
        raise InitRefused("cannot mark an incomplete initialization: TODO.md")
    value = {
        "version": 1,
        "initializedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "scope": scope,
        "projectId": project_id,
    }
    if stream_id:
        value["streamId"] = stream_id
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
    print(json.dumps({"ok": True, "scope": scope, "scopeHome": str(home), "state": "initialized", "marker": str(marker)}))


def main() -> None:
    parser = argparse.ArgumentParser(description="Guard one-time Project Object project or stream initialization")
    parser.add_argument("action", choices=("check", "mark"))
    arguments = parser.parse_args()
    try:
        home, scope, project_id, stream_id = attached_scope()
        check(home, scope) if arguments.action == "check" else mark(home, scope, project_id, stream_id)
    except (InitRefused, OSError, KeyError) as error:
        print(f"scope-init: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
