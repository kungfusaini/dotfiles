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


if __name__ == "__main__":
    unittest.main()
