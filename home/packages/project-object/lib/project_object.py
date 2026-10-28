from __future__ import annotations

import json
import os
from pathlib import Path
import time
import unicodedata
import uuid

REGISTRY_VERSION = 1
STREAM_REGISTRY_VERSION = 1
STREAM_WORKSPACE_SEPARATOR = " · "
DIRECTORY_MODE = 0o700
FILE_MODE = 0o600


class RegistryError(RuntimeError):
    pass


class AtomicWriteCommittedError(RuntimeError):
    """The replacement is visible, but a post-commit durability check failed."""

    committed = True


def ensure_private_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
    if directory.is_symlink() or not directory.is_dir():
        raise RegistryError(f"Unsafe directory: {directory}")
    directory.chmod(DIRECTORY_MODE)


def ensure_private_file(file: Path) -> None:
    if file.is_symlink() or not file.is_file():
        raise RegistryError(f"Unsafe file: {file}")
    file.chmod(FILE_MODE)


def canonical_uuid(value: object, *, kind: str = "Project") -> str:
    if not isinstance(value, str):
        raise RegistryError(f"{kind} ID must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise RegistryError(f"Invalid {kind.lower()} UUID: {value!r}") from error
    canonical = str(parsed)
    if value != canonical:
        raise RegistryError(f"{kind} UUID is not canonical: {value!r}")
    return canonical


def normalized_name(name: str) -> str:
    return unicodedata.normalize("NFKC", name.strip()).lower()


def validate_project_name(value: object) -> str:
    if not isinstance(value, str):
        raise RegistryError("Project name must be a string")
    if value != value.strip() or not value:
        raise RegistryError("Project name must be non-empty and have no surrounding whitespace")
    if any(character in value for character in "\r\n\t"):
        raise RegistryError("Project name must fit on one line")
    return value


def validate_main_directory(value: object, *, require_exists: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryError("Project mainDirectory must be a non-empty string")
    directory = Path(value)
    if not directory.is_absolute():
        raise RegistryError(f"Project mainDirectory must be absolute: {value!r}")
    normalized = str(directory.resolve(strict=False))
    if normalized != value:
        raise RegistryError(f"Project mainDirectory must be normalized: {value!r}")
    if require_exists and (not directory.exists() or not directory.is_dir()):
        raise RegistryError(f"Project mainDirectory is not a directory: {value}")
    return value


def project_home(data_root: Path, project_id: str) -> Path:
    project_id = canonical_uuid(project_id)
    projects_root = data_root / "projects"
    candidate = projects_root / project_id
    if projects_root.is_symlink() or candidate.is_symlink():
        raise RegistryError(f"Project home contains a symlinked managed component: {candidate}")
    resolved_root = projects_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise RegistryError(f"Project home escapes data root: {candidate}")
    return candidate


def project_session_directory(state_root: Path, project_id: str) -> Path:
    project_id = canonical_uuid(project_id)
    projects_root = state_root / "projects"
    candidate = projects_root / project_id / "pi-sessions"
    project_root = projects_root / project_id
    if projects_root.is_symlink() or project_root.is_symlink() or candidate.is_symlink():
        raise RegistryError(f"Project session path contains a symlinked managed component: {candidate}")
    resolved_root = projects_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise RegistryError(f"Project session directory escapes state root: {candidate}")
    return candidate


def stream_home(data_root: Path, project_id: str, stream_id: str) -> Path:
    project_root = project_home(data_root, project_id)
    stream_id = canonical_uuid(stream_id, kind="Stream")
    streams_root = project_root / "streams"
    candidate = streams_root / stream_id
    if streams_root.is_symlink() or candidate.is_symlink():
        raise RegistryError(f"Stream home contains a symlinked managed component: {candidate}")
    resolved_root = streams_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise RegistryError(f"Stream home escapes project home: {candidate}")
    return candidate


def stream_session_directory(state_root: Path, project_id: str, stream_id: str) -> Path:
    project_id = canonical_uuid(project_id)
    stream_id = canonical_uuid(stream_id, kind="Stream")
    projects_root = state_root / "projects"
    project_root = projects_root / project_id
    streams_root = project_root / "streams"
    stream_root = streams_root / stream_id
    candidate = stream_root / "pi-sessions"
    if any(component.is_symlink() for component in (projects_root, project_root, streams_root, stream_root, candidate)):
        raise RegistryError(f"Stream session path contains a symlinked managed component: {candidate}")
    resolved_root = streams_root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise RegistryError(f"Stream session directory escapes state root: {candidate}")
    return candidate


def stream_workspace_name(project_name: str, stream_name: str) -> str:
    return f"{validate_project_name(project_name)}{STREAM_WORKSPACE_SEPARATOR}{validate_project_name(stream_name)}"


def validate_registry(value: object, data_root: Path) -> tuple[dict, bool]:
    if not isinstance(value, dict) or value.get("version") != REGISTRY_VERSION or not isinstance(value.get("projects"), list):
        raise RegistryError("Unsupported or malformed project registry")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    changed = False
    projects: list[dict] = []

    for index, raw in enumerate(value["projects"]):
        if not isinstance(raw, dict):
            raise RegistryError(f"Project record {index} must be an object")
        project = dict(raw)
        project_id = canonical_uuid(project.get("id"))
        name = validate_project_name(project.get("name"))
        validate_main_directory(project.get("mainDirectory"))
        if project_id in seen_ids:
            raise RegistryError(f"Duplicate project ID: {project_id}")
        name_key = normalized_name(name)
        if name_key in seen_names:
            raise RegistryError(f"Duplicate normalized project name: {name}")
        seen_ids.add(project_id)
        seen_names.add(name_key)

        archived_at = project.get("archivedAt")
        if archived_at is not None and not isinstance(archived_at, str):
            raise RegistryError(f"Project {project_id} has invalid archivedAt")
        for field in ("createdAt", "updatedAt"):
            if field in project and not isinstance(project[field], str):
                raise RegistryError(f"Project {project_id} has invalid {field}")

        canonical_home = project_home(data_root, project_id)
        legacy_home = project.get("projectHome")
        if legacy_home is not None:
            if not isinstance(legacy_home, str) or Path(legacy_home) != canonical_home:
                raise RegistryError(f"Project {project_id} has unsafe non-canonical projectHome")
            del project["projectHome"]
            changed = True
        projects.append(project)

    normalized_registry = dict(value)
    normalized_registry["projects"] = projects
    return normalized_registry, changed


def read_registry(registry_path: Path, data_root: Path) -> tuple[dict, bool]:
    if not registry_path.exists():
        return {"version": REGISTRY_VERSION, "projects": []}, False
    try:
        parsed = json.loads(registry_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"Cannot read {registry_path}: {error}") from error
    return validate_registry(parsed, data_root)


def validate_stream_registry(value: object, data_root: Path, project: dict) -> dict:
    project_id = canonical_uuid(project.get("id"))
    if not isinstance(value, dict) or value.get("version") != STREAM_REGISTRY_VERSION or not isinstance(value.get("streams"), list):
        raise RegistryError(f"Unsupported or malformed stream registry for project {project_id}")

    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    streams: list[dict] = []
    for index, raw in enumerate(value["streams"]):
        if not isinstance(raw, dict):
            raise RegistryError(f"Stream record {index} must be an object")
        stream = dict(raw)
        stream_id = canonical_uuid(stream.get("id"), kind="Stream")
        name = validate_project_name(stream.get("name"))
        if stream_id in seen_ids:
            raise RegistryError(f"Duplicate stream ID: {stream_id}")
        name_key = normalized_name(name)
        if name_key in seen_names:
            raise RegistryError(f"Duplicate normalized stream name: {name}")
        seen_ids.add(stream_id)
        seen_names.add(name_key)

        if "mainDirectory" in stream and stream["mainDirectory"] is not None:
            validate_main_directory(stream["mainDirectory"])
        archived_at = stream.get("archivedAt")
        if archived_at is not None and not isinstance(archived_at, str):
            raise RegistryError(f"Stream {stream_id} has invalid archivedAt")
        for field in ("createdAt", "updatedAt"):
            if field in stream and not isinstance(stream[field], str):
                raise RegistryError(f"Stream {stream_id} has invalid {field}")
        stream_home(data_root, project_id, stream_id)
        streams.append(stream)

    return {**value, "streams": streams}


def read_stream_registry(data_root: Path, project: dict) -> dict:
    home = project_home(data_root, project["id"])
    registry_path = home / "streams.json"
    if registry_path.is_symlink():
        raise RegistryError(f"Unsafe stream registry: {registry_path}")
    if not registry_path.exists():
        return {"version": STREAM_REGISTRY_VERSION, "streams": []}
    try:
        parsed = json.loads(registry_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryError(f"Cannot read {registry_path}: {error}") from error
    return validate_stream_registry(parsed, data_root, project)


def find_stream(stream_registry: dict, stream_id: str | None = None, name: str | None = None) -> dict | None:
    if stream_id is not None:
        canonical_uuid(stream_id, kind="Stream")
        return next((stream for stream in stream_registry["streams"] if stream["id"] == stream_id and not stream.get("archivedAt")), None)
    if name is None:
        return None
    return next((stream for stream in stream_registry["streams"] if stream["name"] == name and not stream.get("archivedAt")), None)


def write_json_atomic(file: Path, value: object) -> None:
    ensure_private_directory(file.parent)
    temporary = file.with_name(f".{file.name}.tmp-{os.getpid()}-{time.time_ns()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, FILE_MODE)
    committed = False
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, file)
        committed = True
        directory_descriptor = os.open(file.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except Exception as error:
        if committed:
            raise AtomicWriteCommittedError(f"{file} was replaced, but durability confirmation failed: {error}") from error
        temporary.unlink(missing_ok=True)
        raise


def find_project(registry: dict, project_id: str | None = None, workspace: str | None = None) -> dict | None:
    if project_id is not None:
        canonical_uuid(project_id)
        return next((project for project in registry["projects"] if project["id"] == project_id and not project.get("archivedAt")), None)
    if workspace is None:
        return None
    return next((project for project in registry["projects"] if project["name"] == workspace and not project.get("archivedAt")), None)
