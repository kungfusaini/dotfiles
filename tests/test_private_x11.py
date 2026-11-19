"""Live regression: PRIVATE_X11_RUN=/nix/store/.../bin/private-x11-run python3 tests/test_private_x11.py.

Never launches an X server outside the runner. Does not delete any host socket.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class PrivateX11Tests(unittest.TestCase):
    def test_isolation_and_server_cleanup(self):
        runner = os.environ.get("PRIVATE_X11_RUN") or shutil.which("private-x11-run")
        if not runner:
            self.skipTest("Build/install private-x11-run or set PRIVATE_X11_RUN")
        socket_dir = Path("/tmp/.X11-unix")

        def snapshot():
            return {p.name: (p.lstat().st_ino, p.lstat().st_mode,
                             os.readlink(p) if p.is_symlink() else None)
                    for p in socket_dir.iterdir()}

        before = snapshot()
        host_net = os.readlink("/proc/self/ns/net")
        host_pid = os.readlink("/proc/self/ns/pid")
        with tempfile.NamedTemporaryFile(prefix="private-x11-host-marker-") as marker:
            probe = r'''
import json, os, pathlib, socket, subprocess, time
assert not pathlib.Path(os.environ.get('HOST_MARKER_SHOULD_NOT_LEAK', '/nonexistent')).exists()
assert not pathlib.Path(MARKER).exists(), 'host /tmp exposed'
for key in ('WAYLAND_DISPLAY', 'HYPRLAND_INSTANCE_SIGNATURE', 'PULSE_SERVER', 'PIPEWIRE_REMOTE'):
    assert key not in os.environ, key
assert os.environ['HOME'] == '/tmp/work/home'
assert os.environ['XDG_RUNTIME_DIR'] == '/tmp/work/runtime'
assert pathlib.Path('/run/user').is_dir() and not list(pathlib.Path('/run/user').iterdir())
assert os.readlink('/proc/self/ns/net') != HOST_NET
assert os.readlink('/proc/self/ns/pid') != HOST_PID
assert pathlib.Path('/tmp/.X11-unix/X99').is_socket()
# The culprit pattern, now isolated: automatic display selection starts at :0.
r, w = os.pipe()
x = subprocess.Popen(['Xvfb', '-displayfd', str(w), '-screen', '0', '640x480x24',
                      '-nolisten', 'tcp'], pass_fds=[w], stdout=subprocess.DEVNULL,
                     stderr=subprocess.PIPE)
os.close(w)
try:
    import select
    assert select.select([r], [], [], 10)[0], 'Xvfb startup timed out'
    number = os.read(r, 30).decode().strip()
    assert number == '0', number
    p = pathlib.Path('/tmp/.X11-unix/X0')
    assert p.is_socket()
    s = socket.socket(socket.AF_UNIX); s.settimeout(2); s.connect(str(p)); s.close()
finally:
    os.close(r)
    x.terminate()
    x.wait(timeout=10)
assert not pathlib.Path('/tmp/.X11-unix/X0').exists()
assert pathlib.Path('/tmp/.X11-unix/X99').is_socket()
pathlib.Path('/tmp/work/probe.json').write_text(json.dumps({'display': os.environ['DISPLAY']}))
print('PASS: nested Xvfb :0 startup/cleanup stays private; desktop sessions inaccessible')
'''
            probe = ("MARKER=" + repr(marker.name) + "\nHOST_NET=" + repr(host_net)
                     + "\nHOST_PID=" + repr(host_pid) + "\n" + probe)
            env = {**os.environ, "WAYLAND_DISPLAY": "must-not-leak", "PULSE_SERVER": "must-not-leak"}
            result = subprocess.run([runner, shutil.which("python3"), "-c", probe],
                                    env=env, text=True, capture_output=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: nested Xvfb", result.stdout)
            self.assertTrue(Path(marker.name).exists())
        self.assertEqual(snapshot(), before, "Host X11 paths changed during the test")

    def test_command_failure_is_preserved(self):
        runner = os.environ.get("PRIVATE_X11_RUN") or shutil.which("private-x11-run")
        if not runner:
            self.skipTest("private-x11-run unavailable")
        result = subprocess.run([runner, shutil.which("python3"), "-c", "raise SystemExit(23)"],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 23, result.stderr)


if __name__ == "__main__":
    unittest.main()
