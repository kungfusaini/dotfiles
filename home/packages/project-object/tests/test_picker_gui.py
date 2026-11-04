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

    def test_project_header_working_state_outranks_idle_state(self):
        source = GUI_SOURCE.read_text()
        tree = ast.parse(source)
        picker = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "PickerApplication"
        )
        list_rows = ast.unparse(next(
            node for node in picker.body
            if isinstance(node, ast.FunctionDef) and node.name == "list_rows"
        ))

        self.assertIn(
            "project_agent_state = 'working' if 'working' in project_agent_states else 'idle' if 'idle' in project_agent_states else None",
            list_rows,
        )
        self.assertNotIn(
            "project_agent_state = 'idle' if 'idle' in project_agent_states else 'working'",
            list_rows,
        )

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
