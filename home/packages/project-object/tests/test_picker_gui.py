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
            context_key=lambda project, stream=None: (project["id"], stream["id"] if stream else None),
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

    def test_center_destination_after_layout_and_clamp_at_list_edges(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        methods = [copy.deepcopy(node) for node in picker.body if isinstance(node, ast.FunctionDef) and node.name in {"reveal_row", "center_row_after_layout"}]
        glib = mock.Mock(SOURCE_REMOVE=False)
        namespace = {"GLib": glib}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        row, listbox, adjustment, bounds = (mock.Mock() for _ in range(4))
        row.get_parent.return_value = listbox
        row.compute_bounds.return_value = (True, bounds)
        listbox.get_selected_row.return_value = row
        adjustment.get_lower.return_value = 0
        adjustment.get_upper.return_value = 2000
        adjustment.get_page_size.return_value = 400
        bounds.get_height.return_value = 40
        app = SimpleNamespace(rows=[row], listbox=listbox, list_scroll=SimpleNamespace(get_vadjustment=lambda: adjustment))
        app.reveal_row = lambda *args: namespace["reveal_row"](app, *args)
        self.assertFalse(namespace["center_row_after_layout"](app, row, None))
        glib.idle_add.assert_called_once_with(app.reveal_row, row, True)
        for y, expected in [(800, 620), (0, 0), (1960, 1600)]:
            bounds.get_y.return_value = y
            app.reveal_row(row, True)
            adjustment.set_value.assert_called_with(expected)
        adjustment.set_value.reset_mock()
        listbox.get_selected_row.return_value = None
        app.reveal_row(row, True)
        adjustment.set_value.assert_not_called()
        listbox.get_selected_row.return_value = row
        row.get_parent.return_value = None
        app.reveal_row(row, True)
        adjustment.set_value.assert_not_called()
        row.get_parent.return_value = listbox
        app.reveal_row(row)
        adjustment.clamp_page.assert_called_once_with(1960, 2000)

    def test_project_header_aggregates_only_open_scopes_with_working_priority(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "list_rows"))
        project = {"id": "project", "name": "Alpha", "mainDirectory": "/tmp"}
        backend = mock.Mock()
        backend.workspace_name.return_value = "Alpha"
        backend.scope_is_open.return_value = True
        backend.load_stream_registry_view.return_value = {"streams": [], "errors": []}
        row = mock.Mock()
        namespace = {"backend": backend, "ProjectRow": row}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        app = SimpleNamespace(
            search=SimpleNamespace(get_text=lambda: ""),
            project_items=lambda: [(project, "closed")], current_workspace="Other",
            session={}, expanded_project_ids=set(),
            context_key=lambda project, stream=None: (project["id"], stream["id"] if stream else None),
        )
        cases = [
            (True, set(), "open", set(), set()),
            (True, {"idle"}, "closed", set(), {"idle"}),
            (True, {"idle", "working"}, "open", {"working"}, {"working"}),
            (True, {"working"}, "open", {"idle"}, {"idle", "working"}),
            (False, {"idle"}, "closed", {"idle"}, set()),
            (False, {"working"}, "open", {"idle"}, {"idle"}),
            (True, set(), "open", {"idle", "working"}, {"working"}),
        ]
        for main_open, main_states, stream_state, stream_states, expected in cases:
            with self.subTest(main_open=main_open, main=main_states, stream=stream_states, stream_state=stream_state):
                backend.scope_is_open.return_value = main_open
                app.stream_items = lambda *args: [({"id": "stream", "name": "Stream"}, stream_state)]
                app.agent_activity = {
                    ("project", None): main_states,
                    ("project", "stream"): stream_states,
                    ("project", "unknown"): {"idle", "working"},
                    ("unrelated", None): {"idle", "working"},
                }
                namespace["list_rows"](app)
                self.assertEqual(row.call_args.kwargs["agent_states"], expected)
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

    def test_global_next_attention_jumps_from_active_workspace_without_showing_picker(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        names = {"scope_requires_attention", "attention_scopes", "jump_next_attention"}
        methods = [copy.deepcopy(node) for node in picker.body if isinstance(node, ast.FunctionDef) and node.name in names]
        backend = mock.Mock()
        backend.project_scope.side_effect = lambda p: {"kind": "project", "projectId": p["id"]}
        backend.stream_scope.side_effect = lambda p, s: {"kind": "stream", "projectId": p["id"], "streamId": s["id"]}
        backend.workspace_name.side_effect = lambda p: p["id"]
        backend.stream_workspace_name.side_effect = lambda p, s: p["id"] + "/" + s["id"]
        backend.scope_is_open.side_effect = lambda session, scope: scope not in closed
        backend.run.return_value.returncode = 0
        namespace = {"backend": backend, "GLib": SimpleNamespace(SOURCE_CONTINUE=True)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        project = {"id": "a"}
        targets = [(project, None)] + [(project, {"id": name}) for name in ("working", "mixed", "settled", "closed", "empty")]
        targets.append(({"id": "b"}, None))
        scopes = [backend.stream_scope(p, s) if s else backend.project_scope(p) for p, s in targets]
        closed = [scopes[4]]
        activity = {
            ("a", None): {"idle"}, ("a", "working"): {"working"},
            ("a", "mixed"): {"idle", "working"}, ("a", "settled"): {"idle"},
            ("a", "closed"): {"idle"}, ("b", None): {"idle"},
        }
        app = SimpleNamespace(
            destructive_action_pending=False, context_targets=lambda: targets,
            context_key=lambda p, s=None: (p["id"], s["id"] if s else None),
            load_agent_activity=lambda: activity, expanded_project_ids=set(),
            save_picker_state=mock.Mock(), dismiss_window=mock.Mock(),
            selected_scope=scopes[-1], show_window=mock.Mock(),
        )
        app.scope_requires_attention = lambda *args: namespace["scope_requires_attention"](app, *args)
        app.attention_scopes = lambda: namespace["attention_scopes"](app)
        for active, expected in [("a", "a/settled"), ("a/working", "a/settled"),
                                 ("a/settled", "b"), ("b", "a"), ("unmanaged", "a")]:
            with self.subTest(active=active):
                backend.active_workspace_name.return_value = active
                self.assertTrue(namespace["jump_next_attention"](app))
                backend.run.assert_called_with([backend.HYPRCTL, "dispatch", "workspace", "name:" + expected])
        app.show_window.assert_not_called()
        self.assertEqual(activity[("a", None)], {"idle"})
        # No qualifying scopes: notify, do not dispatch or change selection.
        activity.clear()
        backend.run.reset_mock()
        previous = app.selected_scope
        namespace["jump_next_attention"](app)
        backend.run.assert_not_called()
        self.assertEqual(app.selected_scope, previous)
        backend.notify_warning.assert_called_once()
        # A dispatch failure must not persist or dismiss anything.
        activity[("a", None)] = {"idle"}
        backend.run.return_value.returncode = 1
        app.save_picker_state.reset_mock()
        app.dismiss_window.reset_mock()
        namespace["jump_next_attention"](app)
        app.save_picker_state.assert_not_called()
        app.dismiss_window.assert_not_called()
        backend.notify_error.assert_called_once()
        backend.run.reset_mock()
        app.destructive_action_pending = True
        namespace["jump_next_attention"](app)
        backend.run.assert_not_called()

    def test_next_attention_targets_open_settled_scopes_and_moves_forward(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        names = {"scope_requires_attention", "attention_scopes", "select_next_attention"}
        methods = [copy.deepcopy(node) for node in picker.body if isinstance(node, ast.FunctionDef) and node.name in names]
        backend = mock.Mock()
        backend.project_scope.side_effect = lambda p: {"kind": "project", "projectId": p["id"]}
        backend.stream_scope.side_effect = lambda p, s: {"kind": "stream", "projectId": p["id"], "streamId": s["id"]}
        backend.workspace_name.side_effect = lambda p: p["id"]
        backend.stream_workspace_name.side_effect = lambda p, s: p["id"] + "/" + s["id"]
        backend.scope_is_open.side_effect = lambda session, scope: scope in session["openWorkspaces"]
        namespace = {"backend": backend, "GLib": mock.Mock()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        project = {"id": "a"}
        targets = [(project, None)] + [(project, {"id": name}) for name in ("working", "mixed", "settled", "closed", "empty", "later")]
        targets.append(({"id": "b"}, None))
        scopes = [backend.stream_scope(p, s) if s else backend.project_scope(p) for p, s in targets]
        app = SimpleNamespace(
            session={"openWorkspaces": [s for s in scopes if s.get("streamId") != "closed"]},
            current_workspace="elsewhere", context_scope_targets=targets,
            context_key=lambda p, s=None: (p["id"], s["id"] if s else None),
            context_cache={("a", None): {"briefAttention": "none"}, ("a", "empty"): {"briefAttention": "action"}},
            agent_activity={
                ("a", None): {"idle"}, ("a", "working"): {"working"},
                ("a", "mixed"): {"idle", "working"}, ("a", "settled"): {"idle"},
                ("a", "closed"): {"idle"}, ("a", "later"): {"idle"},
                ("b", None): {"idle"},
            },
            expanded_project_ids=set(), footer_hint=mock.Mock(), restore_footer_hint=mock.Mock(),
            search=mock.Mock(), save_picker_state=mock.Mock(), refresh_rows=mock.Mock(),
            listbox=mock.Mock(), center_row_after_layout=mock.Mock(),
        )
        app.search.get_text.return_value = "hidden by search"
        app.scope_requires_attention = lambda *args: namespace["scope_requires_attention"](app, *args)
        app.attention_scopes = lambda: namespace["attention_scopes"](app)
        self.assertEqual(app.attention_scopes(), [scopes[0], scopes[3], scopes[6], scopes[7]])
        # Main scope with briefAttention=none still qualifies; action-only empty
        # scope and stale idle activity on a closed workspace do not.
        for anchor, expected in [
            (scopes[1], scopes[3]), (scopes[2], scopes[3]),
            (scopes[3], scopes[6]), (scopes[6], scopes[7]), (scopes[7], scopes[0]),
            ({"kind": "project-header", "projectId": "a"}, scopes[0]),
            (None, scopes[0]),
        ]:
            with self.subTest(anchor=anchor):
                app.selected_scope = anchor
                namespace["select_next_attention"](app)
                self.assertEqual(app.selected_scope, expected)
                self.assertIn(expected["projectId"], app.expanded_project_ids)
        app.search.set_text.assert_called_with("")
        app.refresh_rows.assert_called()
        app.listbox.get_selected_row.return_value.add_tick_callback.assert_called_with(app.center_row_after_layout)
        # Current compositor workspace is open even before session state catches up.
        app.current_workspace = "a/closed"
        self.assertIn(scopes[4], app.attention_scopes())
        app.current_workspace = "elsewhere"
        app.agent_activity = {}
        app.selected_scope = scopes[2]
        app.refresh_rows.reset_mock()
        namespace["select_next_attention"](app)
        self.assertEqual(app.selected_scope, scopes[2])
        app.refresh_rows.assert_not_called()
        app.footer_hint.set_text.assert_called_with("No open workspace has a settled agent")
        backend.notify_error.assert_not_called()

    def test_toggle_all_collapses_if_any_project_is_expanded(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "toggle_all_projects"))
        backend = mock.Mock()
        namespace = {"backend": backend}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        for expanded, expected in [
            (set(), {"a", "b"}), ({"a"}, set()), ({"b"}, set()),
            ({"a", "b"}, set()), ({"deleted"}, {"a", "b"}),
        ]:
            with self.subTest(expanded=expanded):
                app = SimpleNamespace(
                    project_items=lambda: [({"id": "a"}, "open"), ({"id": "b"}, "closed")],
                    expanded_project_ids=expanded.copy(),
                    selected_scope={"kind": "stream", "projectId": "b", "streamId": "s"},
                    search=mock.Mock(), save_picker_state=mock.Mock(), refresh_rows=mock.Mock(),
                )
                namespace["toggle_all_projects"](app)
                self.assertEqual(app.expanded_project_ids, expected)
                app.save_picker_state.assert_called_once_with()
                app.refresh_rows.assert_called_once_with()
                if not expected:
                    self.assertEqual(app.selected_scope, {"kind": "project-header", "projectId": "b"})
                    app.search.set_text.assert_called_once_with("")
                else:
                    self.assertEqual(app.selected_scope["kind"], "stream")
                    app.search.set_text.assert_not_called()
        app.project_items = lambda: []
        app.selected_scope = None
        namespace["toggle_all_projects"](app)
        self.assertEqual(app.expanded_project_ids, set())
        app.refresh_rows.side_effect = RuntimeError("refresh failed")
        namespace["toggle_all_projects"](app)
        backend.notify_error.assert_called_once_with("refresh failed")

    def test_shift_tab_toggles_all_but_tab_only_toggles_selection(self):
        tree = ast.parse(GUI_SOURCE.read_text())
        picker = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PickerApplication")
        method = copy.deepcopy(next(node for node in picker.body if isinstance(node, ast.FunctionDef) and node.name == "on_key_pressed"))
        keys = {node.attr for node in ast.walk(method) if isinstance(node, ast.Attribute) and node.attr.startswith("KEY_")}
        gdk = SimpleNamespace(**{key: index for index, key in enumerate(sorted(keys), 1)})
        gdk.ModifierType = SimpleNamespace(SHIFT_MASK=1, CONTROL_MASK=2)
        namespace = {"Gdk": gdk}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), GUI_SOURCE, "exec"), namespace)
        for key, state, all_projects in [
            (gdk.KEY_Tab, 0, False), (gdk.KEY_Tab, 1, True),
            (gdk.KEY_ISO_Left_Tab, 1, True), (gdk.KEY_ISO_Left_Tab, 0, True),
        ]:
            app = SimpleNamespace(
                stack=SimpleNamespace(get_visible_child_name=lambda: "list"), search_mode=False,
                is_next_attention_key=lambda *args: False,
                toggle_all_projects=mock.Mock(), toggle_selected_project=mock.Mock(),
            )
            self.assertTrue(namespace["on_key_pressed"](app, None, key, 0, state))
            self.assertEqual(app.toggle_all_projects.call_count, int(all_projects))
            self.assertEqual(app.toggle_selected_project.call_count, int(not all_projects))
            app.search_mode = True
            self.assertFalse(namespace["on_key_pressed"](app, None, key, 0, state))
            app.search_mode = False
            app.stack.get_visible_child_name = lambda: "create-stream"
            self.assertFalse(namespace["on_key_pressed"](app, None, key, 0, state))

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
