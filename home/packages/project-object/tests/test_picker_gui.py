import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = ROOT / "bin" / "project-picker-gui"
HOME_MANAGER_MODULE = ROOT / "nix" / "home-manager-module.nix"


class PickerGuiSourceTests(unittest.TestCase):
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
        self.assertIn("self.request_close_workspace()", close_active)
        self.assertIn("self.destructive_action_pending = True", methods["request_close_workspace"])
        self.assertIn("self.destructive_action_pending = False", methods["request_close_workspace"])
        self.assertIn("signal.SIGUSR2", source)
        self.assertIn(
            '"$mod, X, exec, ${package}/bin/project-picker --close-active-workspace"',
            HOME_MANAGER_MODULE.read_text(),
        )

    def test_keyboard_selection_scrolls_selected_row_into_view(self):
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
        self.assertIn("self.select_visible_row", methods["move_selection"])
        self.assertIn("self.select_visible_row", methods["select_edge"])
        self.assertIn("GLib.idle_add(self.reveal_row, row)", methods["select_visible_row"])
        self.assertIn("adjustment.clamp_page", methods["reveal_row"])


if __name__ == "__main__":
    unittest.main()
