"""Check the namespace contract before any compositor or X server is started."""
import ast
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).with_name('tablet_proof_live.py')


class ProbeIsolationTests(unittest.TestCase):
    def load_outer(self):
        # Load just the launcher, without importing GUI/HTTP fixture dependencies.
        tree = ast.parse(SOURCE.read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'outer')
        namespace = dict(Path=Path, os=os, subprocess=subprocess, tempfile=tempfile,
                         sys=__import__('sys'), __file__=str(SOURCE))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        return namespace['outer']

    def test_private_x_paths_network_processes_and_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(tempfile, 'mkdtemp', return_value=directory), \
                    patch.object(subprocess, 'call', return_value=0) as launch, \
                    patch.dict(os.environ, {'DISPLAY': ':0', 'WAYLAND_DISPLAY': 'host',
                                           'DBUS_SESSION_BUS_ADDRESS': 'host-bus'}):
                self.assertEqual(self.load_outer()(), 0)
            args = launch.call_args.args[0]
            env = launch.call_args.kwargs['env']
            self.assertIn('--unshare-net', args)
            self.assertIn('--unshare-pid', args)
            self.assertIn('--die-with-parent', args)
            triples = [args[i:i+3] for i in range(len(args)-2)]
            self.assertIn(['--ro-bind', '/', '/'], triples)
            self.assertIn(['--bind', str(root), str(root)], triples)
            self.assertIn(['--dev-bind', '/dev/dri/renderD128', '/dev/dri/renderD128'], triples)
            self.assertNotIn(['--dev-bind', '/dev', '/dev'], triples)
            self.assertTrue(any(args[i:i+2] == ['--tmpfs', '/tmp'] for i in range(len(args)-1)))
            self.assertTrue(any(args[i:i+2] == ['--dev', '/dev'] for i in range(len(args)-1)))
            for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS'):
                self.assertNotIn(key, env)
            self.assertEqual(env['XDG_RUNTIME_DIR'], str(root/'r'))
            self.assertEqual(env['HOME'], str(root/'home'))

    def test_refuse_partial_namespace_isolation(self):
        with patch.object(subprocess, 'call') as launch:
            for network, processes in ((False, True), (True, False), (False, False)):
                with self.assertRaisesRegex(RuntimeError, 'require network and PID isolation'):
                    self.load_outer()(isolated_network=network, isolated_processes=processes)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
