"""Folded-mode reconciliation tests; no real compositor, sudo, or input access."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "home/scripts/display"


class HeadlessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="headless-tests.")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.write_text("active")
        self.monitors = self.root / "monitors"
        self.calls = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.root) + ":" + os.environ["PATH"],
                        XDG_RUNTIME_DIR=str(self.root), TEST_ROOT=str(self.root),
                        TEST_STATE=str(self.state), TEST_MONITORS=str(self.monitors),
                        TEST_CALLS=str(self.calls))
        self.outputs(panel=True)
        self.exe("sudo", 'import os, sys\nos.execv(sys.argv[2], sys.argv[2:])\n')
        self.exe("control", '''import os, sys
from pathlib import Path
if sys.argv[1] == 'status': print(Path(os.environ['TEST_STATE']).read_text())
elif sys.argv[1] == 'probe-external': raise SystemExit(int(os.environ.get('PROBE_FAIL', '0')))
else: raise SystemExit('Unexpected privileged transition')
''')
        self.exe("hyprctl", '''import json, os, sys
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['TEST_CALLS'], 'a') as f: f.write(json.dumps(args)+'\\n')
p=Path(os.environ['TEST_MONITORS'])
ms=json.loads(p.read_text())
if args == ['monitors', 'all', '-j']: print(json.dumps(ms))
elif args == ['keyword', 'monitor', 'eDP-1,disable']:
    if os.environ.get('DISABLE_FAIL'): raise SystemExit(1)
    if not os.environ.get('DISABLE_IGNORED'):
        for m in ms:
            if m['name'] == 'eDP-1': m['disabled']=True
        p.write_text(json.dumps(ms))
elif args[0] != 'notify': raise SystemExit('Unexpected compositor mutation: '+repr(args))
''')
        self.exe("sleep", "pass\n")
        source = (SCRIPTS / "headless-mode").read_text()
        source = source.replace("control=/run/current-system/sw/bin/headless-mode-control",
                                f"control={self.root}/control")
        source = source.replace("sudo=/run/wrappers/bin/sudo", f"sudo={self.root}/sudo")
        # Recovery itself has hardware-specific effects. Assert the safety
        # handoff rather than letting these tests touch sensors/displays.
        source = source.replace('case "${1:-toggle}" in',
                                'restore_mode() { echo restore >> "$TEST_CALLS"; }\ncase "${1:-toggle}" in', 1)
        self.script = self.root / "mode-script"
        self.script.write_text(source)

    def exe(self, name, body):
        path = self.root / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)

    def outputs(self, panel=True, external=True, mirror=False):
        self.monitors.write_text(json.dumps([
            dict(name="eDP-1", disabled=not panel),
            dict(name="DP-1", disabled=not external, mirrorOf="eDP-1" if mirror else "none")]))

    def run_mode(self):
        result = subprocess.run(["bash", str(self.script), "reconcile"], env=self.env,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.calls.read_text() if self.calls.exists() else ""

    def test_reload_drift_disables_panel_and_preserves_external(self):
        calls = self.run_mode()
        self.assertIn('eDP-1,disable', calls)
        self.assertNotIn('restore', calls)
        monitors = json.loads(self.monitors.read_text())
        self.assertTrue(monitors[0]['disabled'])
        self.assertFalse(monitors[1]['disabled'])

    def test_healthy_headless_has_no_mutations(self):
        self.outputs(panel=False)
        calls = self.run_mode()
        self.assertNotIn('keyword', calls)
        self.assertNotIn('restore', calls)

    def test_inactive_or_restoring_state_never_disables_panel(self):
        for state in ('off', 'primed', 'priming', 'restoring', 'restore-failed'):
            with self.subTest(state=state):
                self.state.write_text(state)
                self.assertEqual(self.run_mode(), '')

    def test_external_loss_restores_instead_of_blanking_only_screen(self):
        self.outputs(external=False)
        calls = self.run_mode()
        self.assertIn('restore', calls)
        self.assertNotIn('keyword', calls)

    def test_mirror_is_not_a_safe_independent_output(self):
        self.outputs(mirror=True)
        calls = self.run_mode()
        self.assertIn('restore', calls)
        self.assertNotIn('keyword', calls)

    def test_failed_physical_probe_restores(self):
        self.env['PROBE_FAIL'] = '1'
        calls = self.run_mode()
        self.assertIn('restore', calls)
        self.assertNotIn('keyword', calls)

    def test_disable_failure_restores(self):
        self.env['DISABLE_FAIL'] = '1'
        self.assertIn('restore', self.run_mode())

    def test_success_exit_without_actual_disable_is_not_accepted(self):
        self.env['DISABLE_IGNORED'] = '1'
        self.assertIn('restore', self.run_mode())

    def test_busy_transition_is_not_queued(self):
        runtime = self.root / 'headless-mode'
        runtime.mkdir()
        with (runtime / 'lock').open('w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.assertEqual(self.run_mode(), '')

    def test_layout_helpers_cannot_override_headless_or_restoring(self):
        for name in ('display-layout-apply', 'display-mode-toggle'):
            for state in ('active', 'priming', 'restoring', 'restore-failed'):
                with self.subTest(name=name, state=state):
                    self.state.write_text(state)
                    source = (SCRIPTS / name).read_text().replace('/run/headless-mode/state', str(self.state))
                    result = subprocess.run(['bash', '-c', source, name, 'custom', '100', '0', '1'],
                                            env={**self.env, 'DISPLAY_TRANSITION_LOCKED': '1'},
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls.read_text()
        self.assertNotIn('keyword', calls)
        self.assertNotIn('monitors', calls)

    def test_watcher_reconciles_on_reload_and_periodic_recovery(self):
        source = (SCRIPTS / 'headless-monitor-watch').read_text()
        self.assertIn('configreloaded\\>\\>*) check_recovery ;;', source)
        source = source.split('# Track connected outputs')[0]
        source = source.replace('/run/headless-mode/state', str(self.state))
        source = source.replace('sudo=/run/wrappers/bin/sudo', f'sudo={self.root}/sudo')
        source = source.replace('control=/run/current-system/sw/bin/headless-mode-control',
                                f'control={self.root}/control')
        self.exe('headless-mode', "import os, sys\nfrom pathlib import Path\nPath(os.environ['TEST_CALLS']).write_text(' '.join(sys.argv[1:]))\n")
        result = subprocess.run(['bash', '-c', source + '\ncheck_recovery\n'],
                                env={**self.env, 'HYPRLAND_INSTANCE_SIGNATURE': 'isolated'},
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text(), 'reconcile')


if __name__ == '__main__':
    unittest.main()
