import ast
import copy
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = ROOT / "bin" / "project-picker-gui"
HOME_MANAGER_MODULE = ROOT / "nix" / "home-manager-module.nix"


class PickerGuiSourceTests(unittest.TestCase):
    def test_invalid_stream_diagnostics_cannot_open_close_resume_or_archive(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        names = {"open_selected", "request_close_workspace", "resume_stream_pi", "request_archive_project", "toggle_selected_project", "show_create_stream"}
        methods = [copy.deepcopy(node) for node in picker.body if isinstance(node, ast.FunctionDef) and node.name in names]
        error_type = type("StreamRegistryErrorRow", (), {})
        row = error_type()
        row.error = "UI Development: invalid worktree branch"
        backend = mock.Mock()
        namespace = {"backend": backend, "StreamRegistryErrorRow": error_type}
        namespace.update({name: type(name, (), {}) for name in ("ProjectRow", "ProjectWorkspaceRow", "StreamRow")})
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        app = SimpleNamespace(listbox=SimpleNamespace(get_selected_row=lambda: row), destructive_action_pending=False)
        for name in names:
            namespace[name](app)
        self.assertEqual(backend.notify_error.call_count, 5)
        backend.enter_project.assert_not_called()
        backend.enter_stream.assert_not_called()
        backend.write_json_atomic.assert_not_called()

    def test_discovery_rows_include_healthy_stream_and_named_diagnostic(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "list_rows"))
        project = {"id": "project", "name": "Alpha", "mainDirectory": "/tmp"}
        good = {"id": "healthy", "name": "Healthy"}
        error = "UI Development: invalid worktree branch"
        backend = mock.Mock()
        backend.workspace_name.return_value = "Alpha"
        backend.scope_is_open.return_value = False
        backend.load_stream_registry_view.return_value = {"streams": [good], "errors": [error]}
        namespace = {"backend": backend}
        for name in ("ProjectRow", "ProjectWorkspaceRow", "StreamRow", "StreamRegistryErrorRow"):
            namespace[name] = mock.Mock(name=name)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        app = SimpleNamespace(
            search=SimpleNamespace(get_text=lambda: ""),
            project_items=lambda: [(project, "closed")], current_workspace="Other",
            session={}, expanded_project_ids={"project"}, agent_activity={},
            stream_items=lambda project, registry: [(good, "closed")],
        )
        rows = namespace["list_rows"](app)
        self.assertEqual(len(rows), 4)
        namespace["StreamRegistryErrorRow"].assert_called_once_with(error)
        namespace["StreamRow"].assert_called_once_with(project, good, "closed", working=False)
        self.assertEqual(namespace["ProjectRow"].call_args.kwargs["errors"], [error])

    def test_project_and_stream_creation_shortcuts_are_visible(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        constants = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"CREATE_FOOTER_HINT"}
        }

        self.assertEqual(
            constants["CREATE_FOOTER_HINT"],
            "Ctrl+N New project   Ctrl+Shift+N New stream",
        )
        self.assertIn("Gtk.Label(label=CREATE_FOOTER_HINT", source)

    def test_super_x_routes_active_managed_scope_through_picker_close_confirmation(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        picker = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PickerApplication"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in picker.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        close_active = methods["request_close_active_workspace"]

        self.assertIn("backend.active_workspace_name()", close_active)
        self.assertIn("backend.workspace_name(project) == active_workspace", close_active)
        self.assertIn("backend.stream_workspace_name(project, item) == active_workspace", close_active)
        self.assertIn("if self.destructive_action_pending", close_active)
        self.assertIn("self.show_window(after_place=present_confirmation)", close_active)
        self.assertIn("self.request_close_workspace()", close_active)
        self.assertNotIn("self.show_window()", close_active)
        self.assertIn("self.destructive_action_pending = True", methods["request_close_workspace"])
        self.assertIn("self.destructive_action_pending = False", methods["request_close_workspace"])
        self.assertIn("self.move_picker_to_workspace(target_workspace)", methods["show_window"])
        self.assertIn("after_place()", methods["show_window"])
        self.assertIn("signal.SIGUSR2", source)
        self.assertIn(
            '"$mod, X, exec, ${package}/bin/project-picker --close-active-workspace"',
            HOME_MANAGER_MODULE.read_text(),
        )

    def test_keyboard_selection_wraps_and_scrolls_selected_row_into_view(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        picker = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PickerApplication"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in picker.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        self.assertIn("self.list_scroll = Gtk.ScrolledWindow", source)
        self.assertIn("self.select_visible_row", methods["refresh_rows"])
        self.assertIn("(index + delta) % len(self.rows)", methods["move_selection"])
        self.assertNotIn("max(0", methods["move_selection"])
        self.assertIn("self.select_visible_row", methods["move_selection"])
        self.assertIn("self.select_visible_row", methods["select_edge"])
        self.assertIn("GLib.idle_add(self.reveal_row, row)", methods["select_visible_row"])
        self.assertIn("adjustment.clamp_page", methods["reveal_row"])

    def test_project_header_aggregates_both_agent_states_without_other_projects(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "list_rows"))
        project = {"id": "project", "name": "Alpha", "mainDirectory": "/tmp"}
        backend = mock.Mock()
        backend.workspace_name.return_value = "Alpha"
        backend.scope_is_open.return_value = False
        backend.load_stream_registry_view.return_value = {"streams": [], "errors": []}
        row = mock.Mock()
        namespace = {"backend": backend, "ProjectRow": row}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        app = SimpleNamespace(
            search=SimpleNamespace(get_text=lambda: ""),
            project_items=lambda: [(project, "closed")], current_workspace="Other",
            session={}, expanded_project_ids=set(), stream_items=lambda *args: [],
        )
        for states in (set(), {"idle"}, {"working"}, {"idle", "working"}):
            with self.subTest(states=states):
                app.agent_activity = {
                    ("project", None): states & {"idle"},
                    ("project", "stream"): states & {"working"},
                    ("unrelated", None): {"idle", "working"},
                }
                namespace["list_rows"](app)
                self.assertEqual(row.call_args.kwargs["agent_states"], states)
                self.assertNotIn("workspace_count", row.call_args.kwargs)
                self.assertNotIn("open_workspace_count", row.call_args.kwargs)

    def test_activity_widgets_and_error_warning(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        class Widget:
            def __init__(self, **kwargs):
                self.props = kwargs
                self.children = []
                self.classes = set()
                self.spinning = False
            def add_css_class(self, name): self.classes.add(name)
            def append(self, child): self.children.append(child)
            def set_child(self, child): self.children = [child]
            def set_tooltip_text(self, text): self.tooltip = text
            def set_size_request(self, *args): self.size = args
            def set_valign(self, value): pass
            def set_hexpand(self, value): pass
            def start(self): self.spinning = True
        class Spinner(Widget): pass
        gtk = SimpleNamespace(ListBoxRow=Widget, Box=Widget, Label=Widget, Spinner=Spinner,
                              Orientation=SimpleNamespace(HORIZONTAL=0), Align=SimpleNamespace(CENTER=0))
        names = {"working_spinner", "workspace_indicator", "ProjectRow", "ProjectWorkspaceRow", "StreamRow"}
        nodes = [copy.deepcopy(node) for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
        namespace = {"Gtk": gtk}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        project = {"name": "Alpha"}
        for states in (set(), {"idle"}, {"working"}, {"idle", "working"}):
            with self.subTest(states=states):
                row = namespace["ProjectRow"](project, agent_states=states)
                children = row.children[0].children
                self.assertEqual(sum(isinstance(child, Spinner) and child.spinning for child in children), int("working" in states))
                self.assertEqual(sum("agent-status-idle" in child.classes for child in children), int("idle" in states))
                self.assertFalse(any("stream-count" in child.classes for child in children))
                if states == {"idle", "working"}:
                    self.assertIn("agent-status-idle", children[-2].classes)
                    self.assertIsInstance(children[-1], Spinner)
        row = namespace["ProjectRow"](project, errors=["Broken stream"])
        self.assertEqual(row.children[0].children[-1].props["label"], "⚠ 1 stream error(s)")
        self.assertEqual(row.tooltip, "Broken stream")
        for name in ("ProjectWorkspaceRow", "StreamRow"):
            for state in ("closed", "open", "current"):
                for working in (False, True):
                    args = (project, {"name": "Stream"}, state) if name == "StreamRow" else (project, state)
                    row = namespace[name](*args, working=working)
                    self.assertIn("project-name", row.children[0].children[0].classes)
                    indicator = row.children[0].children[-1]
                    self.assertEqual(isinstance(indicator, Spinner), working and state != "closed")
                    if isinstance(indicator, Spinner):
                        self.assertTrue(indicator.spinning)
                    else:
                        self.assertEqual(indicator.props["label"], "○" if state == "closed" else "●")
                    self.assertEqual("active-workspace-row" in row.classes, state == "current")

    def test_refresh_keeps_unchanged_rows_mapped_across_expansion_and_updates(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "refresh_rows"))
        class Row:
            def __init__(self, key, label="▸"):
                self.render_key = key
                self.parent = None
                self.arrow = mock.Mock()
                self.arrow.get_label.return_value = label
            def get_parent(self): return self.parent
        class ListBox:
            def __init__(self):
                self.rows = []
                self.removed = []
            def remove(self, row):
                self.rows.remove(row)
                self.removed.append(row)
                row.parent = None
            def insert(self, row, index):
                self.rows.insert(index, row)
                row.parent = self
            def get_row_at_index(self, index):
                return self.rows[index] if index < len(self.rows) else None
        namespace = {"ProjectRow": Row}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        box = ListBox()
        first, second = Row("first"), Row("second")
        box.insert(first, 0)
        box.insert(second, 1)
        app = SimpleNamespace(rows=[first, second], listbox=box, selected_scope="second",
                              row_scope=lambda row: row.render_key, select_visible_row=mock.Mock())
        def refresh(candidates):
            app.list_rows = lambda: candidates
            namespace["refresh_rows"](app)
            self.assertEqual(box.rows, app.rows)
        child = Row("child")
        refresh([Row("first", "▾"), child, Row("second")])
        self.assertEqual(app.rows, [first, child, second])
        self.assertEqual(box.removed, [])
        first.arrow.set_label.assert_called_with("▾")
        app.select_visible_row.assert_called_with(second)
        refresh([Row("first"), Row("second")])
        self.assertEqual(box.removed, [child])
        self.assertEqual(app.rows, [first, second])
        # A changed presentation must replace the stale widget, while unrelated
        # working rows stay mapped. Reordering and filtering remain supported.
        changed = Row("second-updated")
        refresh([Row("first"), changed])
        self.assertEqual(box.removed, [child, second])
        self.assertEqual(app.rows, [first, changed])
        refresh([Row("second-updated"), Row("first")])
        self.assertEqual(app.rows, [changed, first])
        refresh([Row("first")])
        self.assertEqual(app.rows, [first])
        refresh([])
        self.assertEqual(app.rows, [])

    def test_visible_picker_refreshes_every_scope_context(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        picker = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PickerApplication"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in picker.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        poll_context = methods["poll_context"]
        finish_refresh = methods["finish_context_refresh"]

        self.assertIn("self.context_refresh_pending", poll_context)
        self.assertIn("targets = self.context_targets()", poll_context)
        self.assertIn("for project, stream in targets", poll_context)
        self.assertIn("backend.load_scope_context(project, stream)", poll_context)
        self.assertIn("threading.Thread", poll_context)
        self.assertIn("GLib.idle_add(self.finish_context_refresh, contexts, targets)", poll_context)
        self.assertIn("self.context_cache.update(contexts)", finish_refresh)
        self.assertIn("self.context_scope_targets = targets", finish_refresh)
        self.assertIn("self.context_refresh_pending = False", finish_refresh)
        self.assertIn("self.paint_context_inspector()", finish_refresh)
        self.assertNotIn("self.paint_context_inspector(refresh=True)", finish_refresh)
        self.assertNotIn("backend.load_stream_registry", methods["project_preview_target"])
        self.assertNotIn("backend.load_stream_registry", methods["attention_scopes"])
        self.assertNotIn("backend.load_scope_context", methods["scope_requires_attention"])

    def test_next_attention_key_uses_explicit_window_handler(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        picker = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PickerApplication"
        )
        methods = {
            node.name: ast.unparse(node)
            for node in picker.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        key_handler = methods["on_key_pressed"]
        key_matcher = methods["is_next_attention_key"]

        self.assertIn("if self.is_next_attention_key(keyval, state)", key_handler)
        self.assertIn("not state & blocked", key_matcher)
        self.assertIn("keyval in (Gdk.KEY_n, Gdk.KEY_N)", key_matcher)
        self.assertIn("keyval != Gdk.KEY_N or bool(state & Gdk.ModifierType.LOCK_MASK)", key_matcher)
        for modifier in ("SHIFT", "CONTROL", "ALT", "SUPER", "HYPER", "META", "BUTTON1", "BUTTON2", "BUTTON3", "BUTTON4", "BUTTON5"):
            self.assertIn(f"Gdk.ModifierType.{modifier}_MASK", key_matcher)
        self.assertNotIn("MOD2_MASK", key_matcher)
        self.assertIn("self.activate_action('next-attention', None)", key_handler)
        self.assertNotIn("self.select_next_attention()", key_handler)
        self.assertIn('"next-attention": (self.select_next_attention, ["n"])', source)

        matcher_node = copy.deepcopy(next(
            node for node in picker.body
            if isinstance(node, ast.FunctionDef) and node.name == "is_next_attention_key"
        ))
        matcher_node.decorator_list = []

        class ModifierType:
            SHIFT_MASK = 1
            LOCK_MASK = 2
            CONTROL_MASK = 4
            ALT_MASK = 8
            BUTTON1_MASK = 256
            BUTTON2_MASK = 512
            BUTTON3_MASK = 1024
            BUTTON4_MASK = 2048
            BUTTON5_MASK = 4096
            SUPER_MASK = 1 << 26
            HYPER_MASK = 1 << 27
            META_MASK = 1 << 28

        class FakeGdk:
            KEY_n = 110
            KEY_N = 78

        FakeGdk.ModifierType = ModifierType
        namespace = {"Gdk": FakeGdk}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[matcher_node], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        matches = namespace["is_next_attention_key"]

        unknown_num_lock = 1 << 20
        for state in (0, ModifierType.LOCK_MASK, unknown_num_lock, ModifierType.LOCK_MASK | unknown_num_lock):
            self.assertTrue(matches(FakeGdk.KEY_n, state))
        self.assertTrue(matches(FakeGdk.KEY_N, ModifierType.LOCK_MASK))
        self.assertTrue(matches(FakeGdk.KEY_N, ModifierType.LOCK_MASK | unknown_num_lock))
        self.assertFalse(matches(FakeGdk.KEY_N, 0))
        self.assertFalse(matches(FakeGdk.KEY_N, unknown_num_lock))
        for modifier in (
            ModifierType.SHIFT_MASK, ModifierType.CONTROL_MASK, ModifierType.ALT_MASK,
            ModifierType.SUPER_MASK, ModifierType.HYPER_MASK, ModifierType.META_MASK,
            ModifierType.BUTTON1_MASK, ModifierType.BUTTON2_MASK, ModifierType.BUTTON3_MASK,
            ModifierType.BUTTON4_MASK, ModifierType.BUTTON5_MASK,
        ):
            self.assertFalse(matches(FakeGdk.KEY_n, modifier))
            self.assertFalse(matches(FakeGdk.KEY_n, unknown_num_lock | modifier))


if __name__ == "__main__":
    unittest.main()
