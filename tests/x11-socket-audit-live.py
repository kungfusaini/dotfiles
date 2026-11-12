#!/usr/bin/env python3
"""Run as root after deployment; never modify existing socket entries."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout


assert os.geteuid() == 0, "root is required to read audit evidence"
key = "x11_socket_changes"
rules = run("auditctl", "-l")
assert rules.count(f"key={key}") == 2, "both architecture rules must be loaded"
assert "dir=/tmp/.X11-unix" in rules
assert run("systemctl", "is-active", "auditd").strip() == "active"
assert (Path("/var/log/audit").stat().st_mode & 0o777) == 0o700
assert (Path("/var/log/audit/audit.log").stat().st_mode & 0o077) == 0

# Keep the old paths in audit evidence but remove only our own regular files.
paths = []
try:
    for directory in ("/tmp/.X11-unix", "/tmp"):
        fd, name = tempfile.mkstemp(prefix="x11-audit-probe-", dir=directory)
        os.close(fd)
        destination = name + ".renamed"
        paths.extend((Path(name), Path(destination)))
        os.rename(name, destination)
        os.unlink(destination)

    deadline = time.monotonic() + 12
    while True:
        inside = subprocess.run(
            ["ausearch", "-k", key, "-f", str(paths[1]), "--raw"],
            text=True, capture_output=True,
        )
        # Inspect only controlled probe events; do not print raw process args.
        matching = [line for line in inside.stdout.splitlines()
                    if line.startswith("type=SYSCALL ") and "success=yes" in line]
        if len(matching) >= 2:
            break
        assert time.monotonic() < deadline, "rename/unlink audit evidence missing"
        time.sleep(0.5)
    outside = subprocess.run(
        ["ausearch", "-k", key, "-f", str(paths[3]), "--raw"],
        text=True, capture_output=True,
    )
    assert outside.returncode == 1 and "type=SYSCALL" not in outside.stdout, "outside path unexpectedly matched"
    status = dict(line.split(maxsplit=1) for line in run("auditctl", "-s").splitlines() if " " in line)
    assert status["enabled"] == "1"
    assert status["lost"] == "0", "audit events have been lost"
    print(json.dumps({"result": "passed", "architectureRules": 2,
                      "renameAndUnlinkRecorded": True, "outsidePathExcluded": True,
                      "rootOnlyLogs": True, "lostEvents": 0}))
finally:
    for path in paths:
        if path.exists():
            assert path.is_file() and not path.is_symlink()
            path.unlink()
