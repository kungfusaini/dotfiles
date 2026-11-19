#!/usr/bin/env python3
"""Real GTK consent tests; run ONLY inside browser_restore_integration's hidden desktop."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', required=True)
    parser.add_argument('--hyprctl', required=True)
    parser.add_argument('--wrapped', action='store_true')
    args = parser.parse_args()
    if os.environ.get('BROWSER_RESTORE_PRIVATE_BUS') != '1':
        raise RuntimeError('This test requires the private regression desktop/bus')
    if not args.wrapped:
        package = Path(args.package)
        values = (package / 'bin/project-browser').read_bytes().split(b'\0')
        env = dict(os.environ)
        for key in ('GI_TYPELIB_PATH', 'PYTHONPATH', 'GIO_EXTRA_MODULES', 'XDG_DATA_DIRS'):
            env[key] = values[values.index(key.encode()) - 1].decode() + ':' + env.get(key, '')
        python = (package / 'bin/.project-browser-wrapped').read_text().splitlines()[0][2:]
        os.execve(python, [python, __file__, *sys.argv[1:], '--wrapped'], env)

    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Adw, GLib, Gtk
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
    from browser_confirmation import confirm_recovery

    def query(name):
        return json.loads(subprocess.check_output([args.hyprctl, name, '-j'], text=True, timeout=5))
    initial_workspace = query('activeworkspace')['name']
    initial_focus = query('activewindow').get('address')
    observed = []
    def clients():
        observed.append(query('activewindow').get('address'))
        return query('clients')
    api = SimpleNamespace(HYPRCTL=args.hyprctl, active_workspace_name=lambda: initial_workspace,
                          clients=clients, client_workspace=lambda c: c['workspace']['name'])
    for response in ('cancel', 'restore', 'close', 'misplaced'):
        responded = []
        def answer():
            for window in Gtk.Window.list_toplevels():
                if isinstance(window, Adw.MessageDialog) and window.get_visible():
                    assert window.get_default_response() == 'cancel'
                    assert window.get_close_response() == 'cancel'
                    assert 'duplicate windows' in window.get_body()
                    if response == 'misplaced':
                        return False  # The verifier must refuse and destroy it.
                    if window.get_response_enabled('restore'):
                        responded.append(True)
                        if response == 'close':
                            window.close()
                        else:
                            window.response(response)
                        return False
            return True
        timer = GLib.timeout_add(100, answer)
        try:
            if response == 'misplaced':
                api.client_workspace = lambda _c: 'wrong-workspace'
                try:
                    confirm_recovery(api, {'name': 'Alpha <not markup>'}, 1)
                except RuntimeError as error:
                    assert 'placement' in str(error)
                else:
                    raise AssertionError('Unverified dialog must not authorize restoration')
            else:
                assert confirm_recovery(api, {'name': 'Alpha <not markup>'}, 1) == (response == 'restore')
                assert responded
            assert query('activeworkspace')['name'] == initial_workspace
            assert all(value == initial_focus for value in observed), observed
            print('PASS real GTK recovery confirmation:', response, flush=True)
        finally:
            if GLib.MainContext.default().find_source_by_id(timer):
                GLib.source_remove(timer)


if __name__ == '__main__':
    main()
