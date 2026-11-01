import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUI_SOURCE = ROOT / "bin" / "project-picker-gui"


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
