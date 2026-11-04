from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import re
import subprocess
import time
import unicodedata
import uuid

REGISTRY_VERSION = 1
STREAM_REGISTRY_VERSION = 1
STREAM_WORKSPACE_SEPARATOR = " · "
BROWSER_ROLE_NAME = "Browser"
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


def _subsequence_cost(needle: str, haystack: str) -> int | None:
    position = -1
    cost = 0
    for character in needle:
        next_position = haystack.find(character, position + 1)
        if next_position < 0:
            return None
        cost += next_position - position - 1
        if next_position == 0 or haystack[next_position - 1] in "/._- ":
            cost -= 2
        position = next_position
    return cost + position


def fuzzy_directory_score(query: str, candidate: str, *, home: Path | None = None) -> int | None:
    """Return a lower-is-better fuzzy path score, or None when it does not match."""
    raw_query = unicodedata.normalize("NFKC", query.strip()).casefold()
    normalized_candidate = unicodedata.normalize("NFKC", candidate).casefold()
    if not raw_query:
        return 0

    home = home or Path.home()
    expanded_query = raw_query
    if raw_query == "~" or raw_query.startswith("~/"):
        expanded_query = str(home).casefold() + raw_query[1:]

    if normalized_candidate == expanded_query:
        return -10_000

    basename = Path(candidate).name.casefold()
    if basename == raw_query:
        return -8_000 + len(candidate)
    if basename.startswith(raw_query):
        return -6_000 + len(basename)

    direct_position = normalized_candidate.find(expanded_query)
    if direct_position >= 0:
        return -4_000 + direct_position * 4 + len(candidate)

    token_query = raw_query
    for separator in ("/", "\\", "_", "-", "."):
        token_query = token_query.replace(separator, " ")
    tokens = [token for token in token_query.split() if token and token != "~"]
    if not tokens:
        return None

    total = len(candidate)
    cursor = 0
    for token in tokens:
        position = normalized_candidate.find(token, cursor)
        if position < 0:
            position = normalized_candidate.find(token)
        if position >= 0:
            total += position * 3
            if position == 0 or normalized_candidate[position - 1] in "/._- ":
                total -= 12
            cursor = position + len(token)
            continue
        subsequence = _subsequence_cost(token, normalized_candidate)
        if subsequence is None:
            return None
        total += 200 + subsequence * 4
    return total


def fuzzy_directory_matches(
    query: str,
    candidates: list[str],
    *,
    limit: int = 8,
    home: Path | None = None,
) -> list[str]:
    """Rank unique directory candidates while preserving discovery order for an empty query."""
    ranked: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for index, candidate in enumerate(candidates):
        if candidate in seen:
            continue
        seen.add(candidate)
        score = fuzzy_directory_score(query, candidate, home=home)
        if score is not None:
            ranked.append((score, index, candidate))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [candidate for _score, _index, candidate in ranked[:limit]]


def validate_project_name(value: object) -> str:
    if not isinstance(value, str):
        raise RegistryError("Project name must be a string")
    if value != value.strip() or not value:
        raise RegistryError("Project name must be non-empty and have no surrounding whitespace")
    if any(character in value for character in "\r\n\t"):
        raise RegistryError("Project name must fit on one line")
    if any(unicodedata.category(character) in ("Cc", "Cs") for character in value):
        raise RegistryError("Project name must not contain control characters or unpaired surrogates")
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


def project_browser_workspace_name(project_name: str) -> str:
    return f"{validate_project_name(project_name)}{STREAM_WORKSPACE_SEPARATOR}{BROWSER_ROLE_NAME}"


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
        worktree = stream.get("worktree")
        if worktree is not None:
            if not isinstance(worktree, dict):
                raise RegistryError(f"Stream {stream_id} has invalid worktree metadata")
            expected_directory = str((data_root / "worktrees" / project_id / stream_id).resolve(strict=False))
            repository = worktree.get("repository")
            directory = worktree.get("directory")
            branch = worktree.get("branch")
            base_commit = worktree.get("baseCommit")
            if not isinstance(repository, str) or validate_main_directory(repository) != repository:
                raise RegistryError(f"Stream {stream_id} has invalid worktree repository")
            if directory != expected_directory or stream.get("mainDirectory") != expected_directory:
                raise RegistryError(f"Stream {stream_id} has invalid worktree directory")
            if branch != f"project-object/{stream_id}":
                raise RegistryError(f"Stream {stream_id} has invalid worktree branch")
            if not isinstance(base_commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", base_commit):
                raise RegistryError(f"Stream {stream_id} has invalid worktree base commit")
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
    except (OSError, ValueError) as error:
        raise RegistryError(f"Cannot read {registry_path}: {error}") from error
    return validate_stream_registry(parsed, data_root, project)


def _registry_diagnostic(value: object) -> str:
    # JSON may contain escaped lone surrogates or controls that GTK cannot
    # display. Diagnostics are data, never markup or executable scope names.
    return "".join(character if character.isprintable() else character.encode("unicode_escape").decode("ascii") for character in str(value))


def read_stream_registry_view(data_root: Path, project: dict) -> dict:
    """Read-only discovery; never write this partial view back to the registry.

    blockedNames are comparison-only hints, never executable scopes. None means
    names are unknown, so automatic attachment must distrust this namespace.
    """
    def unavailable(error):
        return {"version": STREAM_REGISTRY_VERSION, "streams": [], "errors": [_registry_diagnostic(error)], "blockedNames": [None]}

    try:
        return {**read_stream_registry(data_root, project), "errors": [], "blockedNames": []}
    except (RegistryError, OSError, ValueError) as error:
        registry_error = _registry_diagnostic(error)
    try:
        path = project_home(data_root, project["id"]) / "streams.json"
    except (RegistryError, OSError, ValueError) as error:
        return unavailable(error)
    if path.is_symlink():
        return unavailable(registry_error)
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return unavailable(registry_error)
    if not isinstance(value, dict) or value.get("version") != STREAM_REGISTRY_VERSION or not isinstance(value.get("streams"), list):
        return unavailable(registry_error)

    records = value["streams"]
    ids = Counter(raw["id"] for raw in records if isinstance(raw, dict) and isinstance(raw.get("id"), str))
    names = Counter(normalized_name(raw["name"]) for raw in records if isinstance(raw, dict) and isinstance(raw.get("name"), str))
    streams, errors, blocked_names = [], [], []
    for index, raw in enumerate(records):
        raw_name = raw.get("name") if isinstance(raw, dict) and isinstance(raw.get("name"), str) else None
        label = raw_name if raw_name is not None else f"Stream record {index + 1}"
        try:
            stream = validate_stream_registry({"version": STREAM_REGISTRY_VERSION, "streams": [raw]}, data_root, project)["streams"][0]
            # Quarantine every ambiguous record, not just the second duplicate.
            if ids[stream["id"]] != 1 or names[normalized_name(stream["name"])] != 1:
                raise RegistryError("Duplicate stream ID or normalized name")
            streams.append(stream)
        except (RegistryError, OSError, ValueError) as error:
            errors.append(_registry_diagnostic(f"{label}: {error}"))
            blocked_names.append(raw_name)
    return {"version": STREAM_REGISTRY_VERSION, "streams": streams, "errors": errors, "blockedNames": blocked_names}


def verify_worktree_checkout(worktree: dict, git_executable: str = "git") -> None:
    directory = Path(worktree["directory"])
    if directory.is_symlink() or not directory.is_dir():
        raise RegistryError(f"Stream worktree is not a safe prepared directory: {directory}")

    def git_output(repository: str | Path, *arguments: str) -> str:
        result = subprocess.run(
            [git_executable, "-C", str(repository), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "Git command failed"
            raise RegistryError(detail)
        return result.stdout.strip()

    top_level = str(Path(git_output(directory, "rev-parse", "--show-toplevel")).resolve())
    if top_level != str(directory.resolve()):
        raise RegistryError(f"Stream worktree resolves to an unexpected checkout: {top_level}")
    # The recorded branch is a creation default, not the worktree's identity.
    # Branch switches, renames and detached HEAD do not change containment.
    source_common = Path(git_output(worktree["repository"], "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    worktree_common = Path(git_output(directory, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    if source_common != worktree_common:
        raise RegistryError("Stream worktree belongs to a different Git repository")


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
