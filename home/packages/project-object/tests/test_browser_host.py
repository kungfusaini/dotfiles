import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
loader = importlib.machinery.SourceFileLoader('browser_host_test', str(ROOT / 'bin/project-browser-host'))
spec = importlib.util.spec_from_loader(loader.name, loader)
host = importlib.util.module_from_spec(spec)
loader.exec_module(host)


class HostIdentityTests(unittest.TestCase):
    def test_replay_requires_exact_receiving_browser_identity(self):
        identity = {'pid': 42, 'startTime': '123', 'profile': '/private/profile'}
        expected = {**identity, 'instance': 'adapter-one'}
        request = {'op': 'restore', 'expectedIdentity': expected}
        host.validate_restore_identity(request, identity, 'adapter-one')
        for key, replacement in [('pid', 43), ('startTime', '124'), ('profile', '/other/profile')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                host.validate_restore_identity(request, {**identity, key: replacement}, 'adapter-one')
        with self.assertRaises(ValueError):
            host.validate_restore_identity(request, identity, 'replacement-adapter')
        with self.assertRaises(ValueError):
            host.validate_restore_identity({'op': 'restore'}, identity, 'adapter-one')
        host.validate_restore_identity({'op': 'inventory'}, identity, 'adapter-one')
