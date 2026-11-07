import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'home/config/squeekboard-preview'
LAYOUT = ASSETS / 'keyboards/gb_wide.yaml'


class KeyboardPreviewTests(unittest.TestCase):
    def test_native_layout_validator(self):
        validator = os.environ.get('SQUEEKBOARD_TEST_LAYOUT') or shutil.which('squeekboard-test-layout')
        if not validator:
            self.skipTest('Set SQUEEKBOARD_TEST_LAYOUT to the installed Squeekboard validator')
        result = subprocess.run([validator, str(LAYOUT)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Test result: OK', result.stdout + result.stderr)

    def test_four_rows_and_working_view_targets(self):
        text = LAYOUT.read_text()
        view_text = text.split('views:\n', 1)[1].split('\nbuttons:', 1)[0]
        views = re.split(r'^  (\w+):\n', view_text, flags=re.M)
        rows = {views[i]: re.findall(r'^    - "(.*)"$', views[i+1], flags=re.M)
                for i in range(1, len(views), 2)}
        self.assertEqual(set(rows), {'base', 'upper', 'numbers', 'symbols'})
        for name, lines in rows.items():
            self.assertEqual(len(lines), 4, name)
            self.assertTrue(lines[-1].endswith('Return'), name)
            self.assertIn('BackSpace', lines[-2], name)
        for target in re.findall(r'(?:set_view: |lock_view: |unlock_view: )(\w+)', text):
            self.assertIn(target, rows)
        self.assertIn('! quote £ $ % ^ & * ( )', rows['numbers'])
        self.assertIn('label: English (UK)', text)
        self.assertNotIn('keysym: Super', text)

    def test_wide_geometry_avoids_stretch_fallback(self):
        text = LAYOUT.read_text()
        width, height = map(int, re.search(r'default: \{ width: (\d+), height: (\d+) \}', text).groups())
        top, bottom, side = map(int, re.search(
            r'margins: \{ top: (\d+), bottom: (\d+), side: (\d+) \}', text).groups())
        inner_width = 10 * width
        total_width = inner_width + 2 * side
        total_height = 4 * height + top + bottom
        h_scale = 1536 / total_width
        v_scale = 290 / total_height
        self.assertLessEqual(h_scale / v_scale, 1.4)
        self.assertGreater(inner_width / total_width, .85)
        self.assertLess(inner_width / total_width, .95)
        self.assertGreater(height * v_scale, 60)

    def test_theme_is_keyboard_scoped_and_dark_variant_is_shared(self):
        css = (ASSETS/'resource/style.css').read_text()
        dark = ASSETS/'resource/style-Adwaita:dark.css'
        self.assertTrue(dark.is_symlink())
        self.assertEqual(dark.resolve(), (ASSETS/'resource/style.css').resolve())
        self.assertIn('background: #151922;', css)
        self.assertIn('sq_button:active', css)
        self.assertIn('#Return:active', css)
        self.assertNotRegex(css, r'(?:^|\n)(?:window|entry|button|\*)\s*\{')
        self.assertIn('resource:///sm/puri/squeekboard/common.css', css)

    def test_native_gtk_wide_colours_preserve_press_and_shift_feedback(self):
        try:
            import gi
            gi.require_version('Gtk', '3.0')
            from gi.repository import Gtk
        except (ImportError, ValueError):
            self.skipTest('GTK3/PyGObject typelibs required for computed-style test')
        if not Gtk.init_check([])[0]:
            self.skipTest('Computed-style test needs a display connection, but creates no windows')
        # The import provides font/geometry defaults, not these colour rules.
        css = (ASSETS/'resource/style.css').read_text().replace(
            '@import url("resource:///sm/puri/squeekboard/common.css");', '')
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())

        def background(classes=(), state=Gtk.StateFlags.NORMAL, name=None):
            path = Gtk.WidgetPath()
            parent = path.append_type(Gtk.DrawingArea)
            path.iter_set_object_name(parent, 'sq_view')
            path.iter_add_class(parent, 'wide')
            child = path.append_type(Gtk.Button)
            path.iter_set_object_name(child, 'sq_button')
            if name:
                path.iter_set_name(child, name)
            for style_class in classes:
                path.iter_add_class(child, style_class)
            context = Gtk.StyleContext()
            context.set_path(path)
            context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            context.set_state(state)
            return context.get_background_color(state).to_string()

        self.assertNotEqual(background(), background(state=Gtk.StateFlags.ACTIVE))
        self.assertNotEqual(background(['altline']), background(['altline', 'latched']))
        self.assertNotEqual(background(['altline']), background(['altline', 'locked']))
        self.assertNotEqual(background(name='space'), background(name='space', state=Gtk.StateFlags.ACTIVE))
        self.assertNotEqual(background(name='Return'), background(name='Return', state=Gtk.StateFlags.ACTIVE))

    def test_no_deployed_module_or_dock_changes_required(self):
        module = (ROOT/'home/modules/tablet-workspace.nix').read_text()
        # Assets are now packaged for an explicit reversible trial, never
        # installed as global GTK resources or auto-started at session login.
        self.assertIn('export SQUEEKBOARD_KEYBOARDSDIR=${../config/squeekboard-preview}/keyboards', module)
        self.assertNotIn('xdg.configFile."squeekboard', module)
        self.assertIn('GIO_EXTRA_MODULES=${lib.getLib pkgs.dconf}/lib/gio/modules', module)
        self.assertNotIn('/bin/tablet-iterate daemon', module)
        self.assertNotIn('squeekboard-preview', (ROOT/'home/config/quickshell/tablet-workspace/shell.qml').read_text())


if __name__ == '__main__':
    unittest.main()
