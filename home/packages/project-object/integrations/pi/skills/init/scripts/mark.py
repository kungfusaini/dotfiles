#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
MARKER_NAME = ".project-object-initialized.json"


class MarkRefused(RuntimeError):
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
        raise MarkRefused("/init requires a project-attached Pi session with a canonical project ID")

    expected_project = data_root() / "projects" / project_id
    if not supplied_project_home or Path(supplied_project_home) != expected_project:
        raise MarkRefused("the attached project home does not match its canonical UUID path")

    if stream_id:
        if not UUID_PATTERN.fullmatch(stream_id):
            raise MarkRefused("/init requires a canonical stream ID when a stream is attached")
        expected = expected_project / "streams" / stream_id
        if not supplied_stream_home or Path(supplied_stream_home) != expected:
            raise MarkRefused("the attached stream home does not match its canonical UUID path")
        scope = "stream"
    else:
        if supplied_stream_home:
            raise MarkRefused("a stream home was supplied without an attached stream ID")
        expected = expected_project
        scope = "project"

    if expected.is_symlink() or not expected.is_dir():
        raise MarkRefused(f"the canonical {scope} home is missing or unsafe")
    return expected, scope, project_id, stream_id or None


def mark(home: Path, scope: str, project_id: str, stream_id: str | None) -> None:
    marker = home / MARKER_NAME
    if marker.is_symlink():
        raise MarkRefused(f"the {scope} initialization marker is unsafe")
    if marker.exists():
        raise MarkRefused(f"this {scope} has already been initialized")

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
    try:
        mark(*attached_scope())
    except (MarkRefused, OSError, KeyError) as error:
        print(f"scope-init: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
