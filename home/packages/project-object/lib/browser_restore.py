"""Private native-session checkpoints; never reconstruct a session from URLs.

The local bridge is same-UID IPC, not a sandbox against other user processes.
All compositor placement uses a per-window title challenge, never focus/order.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import time
import uuid

from browser_protocol import VERSION, receive, send
from project_object import ensure_private_directory, write_json_atomic


class Bridge:
    def __init__(self, runtime: Path):
        self.path = runtime / "browser-bridge.sock"

    def request(self, op: str, **values):
        try:
            metadata = self.path.lstat()
            if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
                raise ValueError("Unsafe browser bridge socket")
            with socket.socket(socket.AF_UNIX) as connection:
                connection.settimeout(55)
                connection.connect(str(self.path))
                with connection.makefile("rwb", buffering=0) as stream:
                    send(stream, {"op": op, **values})
                    result = receive(stream)
            if result.get("ok") is not True:
                raise RuntimeError(result.get("error", "Native browser operation failed"))
            return result.get("value", result)
        except (OSError, EOFError, ValueError) as error:
            raise RuntimeError("Native browser bridge unavailable; browser windows left open. Start the configured Vivaldi with its companion extension.") from error

    def identity(self):
        value = self.request("hello")
        if value.get("protocol") != VERSION or value.get("ready") is not True:
            raise RuntimeError("Native browser adapter is not ready")
        proc = Path("/proc") / str(value["pid"])
        if proc.joinpath("stat").read_text().rsplit(")", 1)[1].split()[19] != value["startTime"]:
            raise RuntimeError("Browser process identity changed")
        return value


def private_file(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise RuntimeError("Unsafe browser checkpoint file")
        return stream.read()


def fsync_directory(path: Path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_private_directory(path: Path):
    """Persist each new directory entry, not only the leaf's contents."""
    missing = []
    parent = path
    while not parent.exists():
        if parent.is_symlink():
            raise RuntimeError("Unsafe browser checkpoint directory")
        missing.append(parent)
        parent = parent.parent
    if parent.is_symlink() or not parent.is_dir():
        raise RuntimeError("Unsafe browser checkpoint directory")
    for directory in reversed(missing):
        ensure_private_directory(directory)
        fsync_directory(directory)
        fsync_directory(directory.parent)
    ensure_private_directory(path)
    fsync_directory(path)
    # Also cover ancestors left behind by a failed earlier attempt. Existence
    # does not prove their directory entries reached persistent storage.
    for ancestor in path.parents:
        fsync_directory(ancestor)


def fingerprint(window):
    """Session IDs/groups are regenerated; preserve group relationships instead."""
    groups = {}
    result = []
    for tab in window["tabs"]:
        group = tab.get("group", "")
        if group:
            groups.setdefault(group, len(groups) + 1)
        result.append({"url": tab["url"], "pinned": tab["pinned"],
                       "group": groups.get(group, 0), "groupTitle": tab.get("groupTitle", ""),
                       "fixedTitle": tab.get("fixedTitle", ""), "workspace": tab.get("workspace", 0)})
    return result


class Restoration:
    def __init__(self, api):
        self.api = api
        self.bridge = Bridge(api.RUNTIME_ROOT)

    def home(self, project):
        # Registry IDs must not turn into paths, even when invoked directly.
        if str(uuid.UUID(project["id"])) != project["id"]:
            raise RuntimeError("Invalid project browser identity")
        return self.api.DATA_ROOT / "projects" / project["id"] / "browser"

    def checkpoint(self, project):
        path = self.home(project) / "checkpoint.json"
        if not path.exists() and not path.is_symlink():
            return None
        value = json.loads(private_file(path))
        if value.get("version") != 1 or value.get("projectId") != project["id"] or not value.get("windows"):
            raise RuntimeError("Invalid browser checkpoint; refusing to open a duplicate")
        keys = [record["key"] for record in value["windows"]]
        if len(keys) != len(set(keys)):
            raise RuntimeError("Browser checkpoint contains duplicate recovery keys")
        return value

    def address(self, window_id, identity):
        marker = "POB-" + uuid.uuid4().hex
        self.bridge.request("challenge", windowId=window_id, marker=marker)
        try:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                candidates = [client for client in self.api.browser_clients()
                              if marker in client.get("title", "") and client.get("pid") == identity["pid"]]
                if len(candidates) == 1:
                    address = self.api.client_address(candidates[0])
                    if address:
                        return address
                if len(candidates) > 1:
                    break
                time.sleep(.03)
            raise RuntimeError("Could not uniquely identify native browser window; windows left open")
        finally:
            self.bridge.request("unchallenge")

    def bindings(self, windows, identity):
        result = {}
        for window in windows:
            # App/private windows are deliberately not managed here.
            if window.get("type") == "normal" and not window.get("incognito"):
                result[window["id"]] = self.address(window["id"], identity)
        return result

    def native_file(self, identity, name):
        root = Path(identity["profile"]) / "Sessions"
        index = json.loads(private_file(root / "sessions.json"))
        def walk(items):
            for item in items:
                if item.get("title") == name:
                    yield item
                yield from walk(item.get("children", []))
        entries = list(walk(index))
        if len(entries) != 1:
            raise RuntimeError("Native checkpoint is missing or ambiguous")
        entry = entries[0]
        filename = entry["filename"]
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise RuntimeError("Unsafe native session filename")
        if entry.get("windowscount") != 1 or entry.get("tabscount", 0) < 1:
            raise RuntimeError("Native checkpoint is empty")
        return root / filename

    def backup(self, identity, name, destination):
        deadline = time.monotonic() + 12
        previous = None
        while time.monotonic() < deadline:
            try:
                path = self.native_file(identity, name)
                content = private_file(path)
            except (OSError, RuntimeError, ValueError):
                previous = None
                time.sleep(.2)
                continue
            # Native add resolves before async disk persistence. Require two
            # matching reads, then fsync the independently owned backup.
            if content and content == previous:
                # Persistence errors are fatal, not readiness retries: a failed
                # ancestor fsync must not become an apparently existing/safe
                # directory on the next polling attempt.
                durable_private_directory(destination.parent)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                fsync_directory(destination.parent)
                return hashlib.sha256(content).hexdigest()
            previous = content
            time.sleep(.2)
        raise RuntimeError("Native checkpoint did not persist; browser windows left open")

    def close(self, project):
        workspace = self.api.validate_browser_role(self.api.load_registry(), project)
        clients = self.api.browser_clients(workspace=workspace)
        if not clients:
            return
        previous = self.checkpoint(project)
        if previous and previous.get("phase") == "closing":
            raise RuntimeError("Previous browser closure is unresolved; its complete checkpoint was retained. Inspect recovery before closing again")
        # Refuse to close unknown application windows parked in Browser.
        if len(clients) != len([c for c in self.api.clients() if self.api.client_workspace(c) == workspace]):
            raise RuntimeError("Project Browser contains an unmanaged window; nothing closed")
        identity = self.bridge.identity()
        windows = self.bridge.request("inventory")
        bindings = self.bindings(windows, identity)
        addresses = {self.api.client_address(client) for client in clients}
        selected = [window for window in windows if bindings.get(window["id"]) in addresses]
        if len(selected) != len(addresses) or None in addresses:
            raise RuntimeError("Browser ownership mapping is incomplete; nothing closed")
        keys = [window["windowKey"] for window in selected if window.get("windowKey")]
        if len(keys) != len(set(keys)):
            raise RuntimeError("Split browser windows share a recovery key; nothing saved or closed")
        if previous and {record["key"] for record in previous["windows"]} - set(keys):
            raise RuntimeError("Previous browser checkpoint has unrecovered windows; its complete manifest was retained")
        generation = str(uuid.uuid4())
        base = self.home(project) / "checkpoints" / generation
        records = []
        for index, window in enumerate(selected):
            if window.get("projectId") not in (None, project["id"]):
                raise RuntimeError("Browser belongs to another project; nothing closed")
            key = window.get("windowKey") or str(uuid.uuid4())
            tagged = self.bridge.request("tag", windowId=window["id"], projectId=project["id"], windowKey=key)
            name = f"po-{project['id']}-{generation}-{index}"
            saved = self.bridge.request("save", windowId=window["id"], name=name)
            if saved["window"] != tagged:
                raise RuntimeError("Browser changed during checkpoint; nothing closed")
            digest = self.backup(identity, name, base / f"{index}.bin")
            records.append({"key": key, "name": name, "sha256": digest,
                            "backup": f"checkpoints/{generation}/{index}.bin", "window": tagged})
        # Durable commit precedes the first removal. Interrupted closure is
        # reconciled by provenance on next startup/open, never blindly replayed.
        checkpoint = {"version": 1, "projectId": project["id"], "identity": identity,
                      "generation": generation, "phase": "closing", "windows": records}
        write_json_atomic(self.home(project) / "checkpoint.json", checkpoint)
        if self.bridge.identity() != identity:
            raise RuntimeError("Browser changed before closure; checkpoint retained")
        current = self.api.browser_clients(workspace=workspace)
        if {self.api.client_address(c) for c in current} != addresses:
            raise RuntimeError("Browser workspace changed; checkpoint retained, nothing closed")
        # Map again immediately before closing so moved windows are not closed
        # merely because their old address was once in this workspace.
        if self.bindings([r["window"] for r in records], identity) != {w["id"]: bindings[w["id"]] for w in selected}:
            raise RuntimeError("Browser mapping changed; checkpoint retained")
        if {self.api.client_address(c) for c in self.api.browser_clients(workspace=workspace)} != addresses:
            raise RuntimeError("Browser moved during verification; checkpoint retained")
        try:
            self.bridge.request("close", windows=[record["window"] for record in records])
        except RuntimeError:
            # Closing the last browser window can terminate native messaging
            # before its acknowledgement. Only accept compositor-confirmed exit.
            if self.api.browser_clients(workspace=workspace):
                raise
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not self.api.browser_clients(workspace=workspace):
                checkpoint["phase"] = "closed"
                write_json_atomic(self.home(project) / "checkpoint.json", checkpoint)
                return
            time.sleep(.05)
        raise RuntimeError("Browser did not close; checkpoint retained")

    def ready(self):
        if not self.api.browser_clients():
            self.api.launch_urls([], new_window=False)  # No synthetic launch tab.
        deadline = time.monotonic() + 15
        while True:
            try:
                return self.bridge.identity()
            except RuntimeError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)

    def restore(self, project):
        checkpoint = self.checkpoint(project)
        if not checkpoint:
            return []
        identity = self.ready()
        if identity["profile"] != checkpoint["identity"]["profile"]:
            raise RuntimeError("Checkpoint belongs to a different browser profile")
        inventory = self.bridge.request("inventory")
        expected = {record["key"] for record in checkpoint["windows"]}
        if any((project["id"] in window.get("provenance", []) and window.get("projectId") != project["id"]) or
               (window.get("projectId") == project["id"] and any(owner != project["id"] for owner in window.get("provenance", [])))
               for window in inventory):
            raise RuntimeError("Mixed recovered browser provenance; inspect windows before restoring")
        recovered = [window for window in inventory if window.get("projectId") == project["id"]]
        keys = [window.get("windowKey") for window in recovered]
        if len(keys) != len(set(keys)) or any(key not in expected for key in keys):
            raise RuntimeError("Ambiguous recovered project windows; inspect them before restoring")
        restored = {window["windowKey"]: window for window in recovered}
        for record in checkpoint["windows"]:
            if record["key"] in restored:
                if checkpoint.get("phase") == "closing" and fingerprint(restored[record["key"]]) != fingerprint(record["window"]):
                    raise RuntimeError("Interrupted browser closure; saved tabs remain in the private checkpoint. Inspect the partial window before restoring")
                continue  # Preserve live recovered edits, do not replay stale state.
            if identity["instance"] != checkpoint["identity"]["instance"]:
                # No proven normal-startup SessionRestore completion signal is
                # exposed by the supported adapter yet. A quiet inventory is
                # not proof: late recovery could otherwise duplicate this key.
                raise RuntimeError("Startup recovery completion cannot yet be verified; missing saved windows were not replayed")
            backup = self.home(project) / record["backup"]
            expected_path = f"checkpoints/{checkpoint['generation']}/{checkpoint['windows'].index(record)}.bin"
            if record["backup"] != expected_path:
                raise RuntimeError("Invalid checkpoint backup path")
            if hashlib.sha256(private_file(backup)).hexdigest() != record["sha256"]:
                raise RuntimeError("Private browser checkpoint failed integrity verification")
            native = self.native_file(identity, record["name"])
            if hashlib.sha256(private_file(native)).hexdigest() != record["sha256"]:
                raise RuntimeError("Native saved session changed; private checkpoint retained, nothing replayed")
            window = self.bridge.request("restore", name=record["name"])
            if window.get("projectId") != project["id"] or window.get("windowKey") != record["key"]:
                raise RuntimeError("Restored browser ownership mismatch; inspect windows before retrying")
            if fingerprint(window) != fingerprint(record["window"]):
                raise RuntimeError("Restored browser content mismatch; checkpoint retained")
            restored[record["key"]] = window
        workspace = self.api.validate_browser_role(self.api.load_registry(), project)
        addresses = []
        for window in restored.values():
            address = self.address(window["id"], identity)
            self.api.dispatch("movetoworkspacesilent", f"name:{workspace},address:{address}")
            if not self.api.live_address(address, workspace):
                raise RuntimeError("Restored browser placement could not be verified")
            addresses.append(address)
        if checkpoint.get("phase") == "closing":
            # Only explicit, fully verified recovery resolves an interrupted
            # transaction. Startup placement by itself cannot do so.
            checkpoint["phase"] = "recovered"
            write_json_atomic(self.home(project) / "checkpoint.json", checkpoint)
        return addresses

    def reconcile_startup(self):
        # Recovered windows are adopted, not restored or closed. This avoids
        # duplicate replay after an immediate shutdown with stale live sessions.
        identity = self.bridge.identity()
        inventory = self.bridge.request("inventory")
        registry = self.api.load_registry()
        for project in registry["projects"]:
            if project.get("archivedAt"):
                continue
            checkpoint = self.checkpoint(project)
            if not checkpoint or identity["profile"] != checkpoint["identity"]["profile"]:
                continue
            owned = [w for w in inventory if w.get("projectId") == project["id"]]
            if any(any(owner != project["id"] for owner in window.get("provenance", [])) for window in owned):
                raise RuntimeError("Conflicting startup project ownership; windows left untouched")
            keys = [w.get("windowKey") for w in owned]
            expected = {r["key"] for r in checkpoint["windows"]}
            if len(keys) != len(set(keys)) or any(key not in expected for key in keys):
                raise RuntimeError("Ambiguous startup browser recovery; no automatic replay")
            if checkpoint.get("phase") == "closing":
                records = {record["key"]: record for record in checkpoint["windows"]}
                if any(fingerprint(window) != fingerprint(records[window["windowKey"]]["window"]) for window in owned):
                    raise RuntimeError("Interrupted browser closure; partial startup windows were not adopted")
            workspace = self.api.validate_browser_role(registry, project)
            for window in owned:
                address = self.address(window["id"], identity)
                self.api.dispatch("movetoworkspacesilent", f"name:{workspace},address:{address}")
