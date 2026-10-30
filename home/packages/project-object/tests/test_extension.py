import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = (ROOT / "integrations" / "pi" / "project-object.ts").as_uri()


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = self.root / "data"
        self.home = self.data / "projects"
        self.project_id = str(uuid.uuid4())
        self.main = self.root / "main"
        self.main.mkdir()
        (self.home / self.project_id).mkdir(parents=True)
        self.registry = {
            "version": 1,
            "projects": [{
                "id": self.project_id,
                "name": "Alpha",
                "mainDirectory": str(self.main),
                "archivedAt": None,
            }],
        }
        self.write_registry()

    def tearDown(self):
        self.temporary.cleanup()

    def write_registry(self):
        self.data.mkdir(exist_ok=True)
        (self.data / "projects.json").write_text(json.dumps(self.registry))

    def node(self, expression, extra_environment=None):
        environment = {**os.environ, "PROJECT_OBJECT_DATA_DIR": str(self.data)}
        for name in (
            "PROJECT_OBJECT_ID",
            "PROJECT_OBJECT_NAME",
            "PROJECT_OBJECT_HOME",
            "PROJECT_OBJECT_MAIN_DIRECTORY",
            "PROJECT_OBJECT_STREAM_ID",
            "PROJECT_OBJECT_STREAM_HOME",
            "PROJECT_OBJECT_STREAM_CLI",
            "PI_CODING_AGENT_SESSION_DIR",
        ):
            environment.pop(name, None)
        environment.update(extra_environment or {})
        script = f"import fs from 'node:fs'; import * as m from {json.dumps(EXTENSION)}; {expression}"
        return subprocess.run(["node", "--no-warnings", "--experimental-strip-types", "--input-type=module", "-e", script], env=environment, text=True, capture_output=True)

    def test_explicit_archived_project_is_not_resolved(self):
        self.registry["projects"][0]["archivedAt"] = "2026-01-01T00:00:00Z"
        self.write_registry()
        result = self.node("console.log(JSON.stringify(m.resolveProject()))", {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})

    def test_malformed_registry_surfaces_an_error(self):
        (self.data / "projects.json").write_text("{")
        result = self.node("console.log(JSON.stringify(m.resolveProject()))", {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot load project registry", json.loads(result.stdout)["error"])

    def test_unicode_name_normalization_matches_registry_rules(self):
        self.registry["projects"][0]["name"] = "Kelvin"
        self.registry["projects"].append({**self.registry["projects"][0], "id": str(uuid.uuid4()), "name": "kelvin"})
        self.write_registry()
        result = self.node("console.log(JSON.stringify(m.resolveProject()))", {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("duplicate normalized project name", json.loads(result.stdout)["error"])

    def test_symlinked_stream_registry_is_rejected(self):
        stream_id = str(uuid.uuid4())
        outside = self.root / "outside-streams.json"
        outside.write_text(json.dumps({"version": 1, "streams": [{"id": stream_id, "name": "Focused Work"}]}))
        (self.home / self.project_id / "streams.json").symlink_to(outside)
        result = self.node("console.log(JSON.stringify(m.resolveProject()))", {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_ID": stream_id,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("non-symlink", json.loads(result.stdout)["error"])

    def test_ambiguous_workspace_does_not_attach_first_match(self):
        stream_id = str(uuid.uuid4())
        colliding_id = str(uuid.uuid4())
        colliding_home = self.home / colliding_id
        colliding_home.mkdir()
        self.registry["projects"].append({
            "id": colliding_id,
            "name": "Alpha · Focused Work",
            "mainDirectory": str(self.main),
            "archivedAt": None,
        })
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused Work", "mainDirectory": None, "archivedAt": None}],
        }))
        self.write_registry()
        hyprctl = self.root / "hyprctl"
        hyprctl.write_text("""#!/usr/bin/env python3
import json
print(json.dumps({'name':'Alpha · Focused Work'}))
""")
        hyprctl.chmod(0o755)
        result = self.node("console.log(JSON.stringify(m.resolveProject()))", {"PROJECT_PICKER_HYPRCTL": str(hyprctl)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ambiguous project or stream workspace", json.loads(result.stdout)["error"])

    def test_stream_activity_tracks_working_idle_and_shutdown(self):
        stream_id = str(uuid.uuid4())
        stream_home = self.home / self.project_id / "streams" / stream_id
        stream_home.mkdir(parents=True)
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Models", "mainDirectory": None, "archivedAt": None}],
        }))
        runtime = self.root / "runtime"
        expression = """
const handlers = {};
const pi = {
  on: (name, handler) => { handlers[name] = handler; },
  registerTool: () => {}, registerCommand: () => {}, sendUserMessage: () => {},
};
m.default(pi);
const ctx = { hasUI: false, mode: 'rpc', sessionManager: { getSessionId: () => 'restore-session-123' }, ui: { setStatus: () => {}, notify: () => {}, theme: { fg: (_tone, text) => text } } };
await handlers.session_start({}, ctx);
const file = `${process.env.PROJECT_OBJECT_RUNTIME_DIR}/pi-activity/${process.pid}.json`;
const idle = JSON.parse(fs.readFileSync(file, 'utf8'));
const closeDirectory = `${process.env.PROJECT_OBJECT_RUNTIME_DIR}/pi-close`;
fs.mkdirSync(closeDirectory, { recursive: true, mode: 0o700 });
const closeToken = '12345678-1234-4123-8123-123456789abc';
fs.writeFileSync(`${closeDirectory}/${process.pid}.request.json`, JSON.stringify({ version: 1, pid: process.pid, token: closeToken, processStartTime: idle.processStartTime }));
await new Promise((resolve) => setTimeout(resolve, 100));
const closeAck = JSON.parse(fs.readFileSync(`${closeDirectory}/${process.pid}.ack.json`, 'utf8'));
fs.unlinkSync(`${closeDirectory}/${process.pid}.request.json`);
await handlers.agent_start({}, ctx);
const working = JSON.parse(fs.readFileSync(file, 'utf8'));
await handlers.agent_settled({}, ctx);
const settled = JSON.parse(fs.readFileSync(file, 'utf8'));
await handlers.session_shutdown({}, ctx);
console.log(JSON.stringify({idle, working, settled, closeAck, existsAfterShutdown: fs.existsSync(file)}));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_ID": stream_id,
            "PROJECT_OBJECT_RUNTIME_DIR": str(runtime),
            "KITTY_PID": str(os.getpid()),
            "KITTY_WINDOW_ID": "17",
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["idle"]["state"], "idle")
        self.assertEqual(output["working"]["state"], "working")
        self.assertEqual(output["settled"]["state"], "idle")
        self.assertEqual(output["working"]["projectId"], self.project_id)
        self.assertEqual(output["working"]["streamId"], stream_id)
        self.assertEqual(output["working"]["sessionId"], "restore-session-123")
        self.assertEqual(output["working"]["kittyPid"], os.getpid())
        self.assertRegex(output["working"]["processStartTime"], r"^\d+$")
        self.assertRegex(output["working"]["kittyStartTime"], r"^\d+$")
        self.assertEqual(output["working"]["kittyWindowId"], 17)
        self.assertEqual(output["closeAck"]["token"], "12345678-1234-4123-8123-123456789abc")
        self.assertFalse(output["existsAfterShutdown"])
        self.assertEqual((runtime / "pi-activity").stat().st_mode & 0o777, 0o700)

    def test_init_command_supports_projects_and_streams_with_preserving_skill_request(self):
        expression = """
const commands = {};
let sent;
const notices = [];
const pi = {
  on: () => {}, registerTool: () => {},
  registerCommand: (name, command) => { commands[name] = command; },
  sendUserMessage: (message) => { sent = message; },
};
m.default(pi);
await commands.init.handler('Coordinate agent tooling safely', {
  isIdle: () => true,
  ui: { notify: (message) => notices.push(message) },
});
console.log(JSON.stringify({sent, notices}));
"""
        project_result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(project_result.returncode, 0, project_result.stderr)
        project_output = json.loads(project_result.stdout)
        self.assertIn("Initialize the Alpha project", project_output["sent"])
        self.assertIn("Coordinate agent tooling safely", project_output["sent"])

        stream_id = str(uuid.uuid4())
        stream_home = self.home / self.project_id / "streams" / stream_id
        stream_home.mkdir(parents=True)
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Models", "mainDirectory": None, "archivedAt": None}],
        }))
        result = self.node(expression.replace("Coordinate agent tooling safely", "Inspect model separation safely"), {"PROJECT_OBJECT_ID": self.project_id, "PROJECT_OBJECT_STREAM_ID": stream_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("project-object/init/SKILL.md", output["sent"])
        self.assertIn("Inspect model separation safely", output["sent"])
        self.assertIn("existing scope artifacts or worklog entries", output["sent"])
        self.assertIn("do not begin substantive", output["sent"])

        (stream_home / ".project-object-initialized.json").write_text("{}\n")
        result = self.node(expression.replace("Coordinate agent tooling safely", "Inspect model separation safely"), {"PROJECT_OBJECT_ID": self.project_id, "PROJECT_OBJECT_STREAM_ID": stream_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIsNone(output.get("sent"))
        self.assertTrue(any("already been initialized" in notice for notice in output["notices"]))

    def test_catchup_command_requests_recent_work_and_next_step_only(self):
        expression = """
const commands = {};
let sent;
const pi = {
  on: () => {},
  registerTool: () => {},
  registerCommand: (name, command) => { commands[name] = command; },
  sendUserMessage: (message) => { sent = message; },
};
m.default(pi);
await commands.catchup.handler('picker follow-up', {
  isIdle: () => true,
  ui: { notify: () => {} },
});
console.log(JSON.stringify(sent));
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        prompt = json.loads(result.stdout)
        self.assertIn("What we were doing", prompt)
        self.assertIn("Where we left off", prompt)
        self.assertIn("What's next", prompt)
        self.assertIn("newest relevant worklog entries", prompt)
        self.assertIn("worklogs/events.jsonl", prompt)
        self.assertIn("Do not introduce or explain the project", prompt)
        self.assertIn("picker follow-up", prompt)

    def test_stream_create_tool_registers_stream_without_opening_workspace(self):
        hyprctl = self.root / "hyprctl"
        calls = self.root / "hyprctl-calls"
        hyprctl.write_text(f"""#!/usr/bin/env python3
import json
import sys
with open({str(calls)!r}, "a") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1:] == ["workspaces", "-j"]:
    print("[]")
else:
    raise SystemExit(2)
""")
        hyprctl.chmod(0o755)
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_stream_create.execute('call', {
  name: 'Picker Polish',
  useWorktree: false,
  scope: 'Improve the project picker while preserving its keyboard-first behavior.',
  initialTasks: ['Review picker interaction pain points.', 'Implement the agreed picker improvements.'],
});
console.log(JSON.stringify(result));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_CLI": str(ROOT / "bin" / "project-picker-tui"),
            "PROJECT_PICKER_HYPRCTL": str(hyprctl),
            "PROJECT_OBJECT_RUNTIME_DIR": str(self.root / "runtime"),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        streams = json.loads((self.home / self.project_id / "streams.json").read_text())["streams"]
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]["name"], "Picker Polish")
        stream_home = self.home / self.project_id / "streams" / streams[0]["id"]
        self.assertIn("Improve the project picker", (stream_home / "AGENTS.md").read_text())
        todo = (stream_home / "TODO.md").read_text()
        self.assertIn("- Review picker interaction pain points.", todo)
        self.assertIn("- Implement the agreed picker improvements.", todo)
        self.assertEqual((stream_home / "NOTES.md").read_text(), "# Notes\n")
        self.assertEqual(response["details"]["streamId"], streams[0]["id"])
        self.assertIn("available in the project picker", response["content"][0]["text"])
        self.assertEqual(calls.read_text().splitlines(), ['["workspaces", "-j"]'])
        self.assertFalse((self.root / "runtime" / "session.json").exists())

    def test_stream_scoped_session_creates_sibling_under_parent_project(self):
        current_stream_id = str(uuid.uuid4())
        current_stream_home = self.home / self.project_id / "streams" / current_stream_id
        current_stream_home.mkdir(parents=True)
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": current_stream_id, "name": "Current Work", "mainDirectory": None, "archivedAt": None}],
        }))
        hyprctl = self.root / "hyprctl"
        hyprctl.write_text("#!/bin/sh\nprintf '[]\\n'\n")
        hyprctl.chmod(0o755)
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_stream_create.execute('call', {
  name: 'Sibling Cleanup',
  useWorktree: false,
  scope: 'Clean inherited lint failures without changing product behavior.',
  initialTasks: ['Categorize inherited lint failures.'],
});
console.log(JSON.stringify(result));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_ID": current_stream_id,
            "PROJECT_OBJECT_STREAM_CLI": str(ROOT / "bin" / "project-picker-tui"),
            "PROJECT_PICKER_HYPRCTL": str(hyprctl),
            "PROJECT_OBJECT_RUNTIME_DIR": str(self.root / "runtime"),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        streams = json.loads((self.home / self.project_id / "streams.json").read_text())["streams"]
        self.assertEqual([stream["name"] for stream in streams], ["Current Work", "Sibling Cleanup"])
        self.assertEqual(response["details"]["projectId"], self.project_id)
        self.assertNotEqual(response["details"]["streamId"], current_stream_id)

    def test_stream_archive_runs_only_after_final_response_settles(self):
        stream_id = str(uuid.uuid4())
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Finished Work", "mainDirectory": None, "archivedAt": None}],
        }))
        calls = self.root / "archive-calls"
        lifecycle = self.root / "stream-lifecycle"
        lifecycle.write_text(f"""#!/usr/bin/env python3
import json
import sys
with open({str(calls)!r}, "a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "--check-archive-stream":
    print(json.dumps({{"projectId": {self.project_id!r}, "streamId": {stream_id!r}, "name": "Finished Work"}}))
""")
        lifecycle.chmod(0o755)
        expression = """
const handlers = {};
const tools = {};
const pi = {
  on: (name, handler) => { handlers[name] = handler; },
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_stream_archive.execute('call', {});
const beforeSettled = fs.readFileSync(process.env.ARCHIVE_CALLS, 'utf8').trim().split('\\n').length;
handlers.agent_settled();
await new Promise((resolve) => setTimeout(resolve, 200));
const calls = fs.readFileSync(process.env.ARCHIVE_CALLS, 'utf8').trim().split('\\n').map(JSON.parse);
console.log(JSON.stringify({ result, beforeSettled, calls }));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_ID": stream_id,
            "PROJECT_OBJECT_STREAM_CLI": str(lifecycle),
            "PROJECT_OBJECT_RUNTIME_DIR": str(self.root / "runtime"),
            "ARCHIVE_CALLS": str(calls),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["beforeSettled"], 1)
        self.assertEqual(output["calls"], [
            ["--check-archive-stream", "--project-id", self.project_id, "--stream-id", stream_id],
            ["--archive-stream", "--project-id", self.project_id, "--stream-id", stream_id],
        ])
        self.assertTrue(output["result"]["details"]["pending"])
        self.assertIn("final response", output["result"]["content"][0]["text"])

    def test_stream_archive_closes_named_sibling_immediately_and_keeps_session_active(self):
        current_stream_id = str(uuid.uuid4())
        sibling_stream_id = str(uuid.uuid4())
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [
                {"id": current_stream_id, "name": "Current Work", "mainDirectory": None, "archivedAt": None},
                {"id": sibling_stream_id, "name": "Finished Cleanup", "mainDirectory": None, "archivedAt": None},
            ],
        }))
        calls = self.root / "archive-calls"
        lifecycle = self.root / "stream-lifecycle"
        lifecycle.write_text(f"""#!/usr/bin/env python3
import json
import sys
with open({str(calls)!r}, "a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[1] == "--check-archive-stream":
    print(json.dumps({{"projectId": {self.project_id!r}, "streamId": {sibling_stream_id!r}, "name": "Finished Cleanup"}}))
""")
        lifecycle.chmod(0o755)
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_stream_archive.execute('call', { stream: 'finished cleanup' });
const calls = fs.readFileSync(process.env.ARCHIVE_CALLS, 'utf8').trim().split('\\n').map(JSON.parse);
console.log(JSON.stringify({ result, calls }));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_ID": current_stream_id,
            "PROJECT_OBJECT_STREAM_CLI": str(lifecycle),
            "ARCHIVE_CALLS": str(calls),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["calls"], [
            ["--check-archive-stream", "--project-id", self.project_id, "--stream-id", sibling_stream_id],
            ["--archive-stream", "--project-id", self.project_id, "--stream-id", sibling_stream_id],
        ])
        self.assertFalse(output["result"]["details"]["pending"])
        self.assertTrue(output["result"]["details"]["archived"])
        self.assertIn("session remains active", output["result"]["content"][0]["text"])

    def test_stream_archive_accepts_named_stream_from_project_scoped_session(self):
        stream_id = str(uuid.uuid4())
        (self.home / self.project_id / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Finished Work", "mainDirectory": None, "archivedAt": None}],
        }))
        lifecycle = self.root / "stream-lifecycle"
        lifecycle.write_text(f"""#!/usr/bin/env python3
import json
import sys
if sys.argv[1] == "--check-archive-stream":
    print(json.dumps({{"projectId": {self.project_id!r}, "streamId": {stream_id!r}, "name": "Finished Work"}}))
""")
        lifecycle.chmod(0o755)
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_stream_archive.execute('call', { stream: process.env.TARGET_STREAM_ID });
console.log(JSON.stringify(result));
"""
        result = self.node(expression, {
            "PROJECT_OBJECT_ID": self.project_id,
            "PROJECT_OBJECT_STREAM_CLI": str(lifecycle),
            "TARGET_STREAM_ID": stream_id,
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertTrue(output["details"]["archived"])
        self.assertEqual(output["details"]["streamId"], stream_id)

    def test_stream_archive_requires_name_from_project_scoped_session(self):
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
try {
  await tools.project_stream_archive.execute('call', {});
  console.log('unexpected success');
} catch (error) {
  console.log(error.message);
}
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Pass a stream name or ID", result.stdout)

    def test_project_stream_routing_is_global_not_project_specific(self):
        expression = """
const handlers = {};
const tools = {};
const pi = {
  on: (name, handler) => { handlers[name] = handler; },
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
await handlers.session_start({}, { mode: 'rpc', hasUI: false, sessionManager: { getSessionId: () => 'routing-session' }, ui: { setStatus: () => {}, theme: { fg: (_tone, text) => text } } });
const event = { systemPromptOptions: { sections: {} } };
handlers.before_agent_start(event);
console.log(JSON.stringify({
  prompt: event.systemPromptOptions.sections.project_object,
  description: tools.project_stream_create.description,
  guidelines: tools.project_stream_create.promptGuidelines,
  createParameters: tools.project_stream_create.parameters,
  archiveDescription: tools.project_stream_archive.description,
  archiveGuidelines: tools.project_stream_archive.promptGuidelines,
}));
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("use project_stream_create", output["prompt"])
        self.assertIn("Do not use the workstream skill", output["prompt"])
        self.assertIn("project picker", output["description"])
        self.assertIn("prepared lazily", output["description"])
        self.assertIn("repository", output["createParameters"]["properties"])
        self.assertIn("useWorktree", output["createParameters"]["properties"])
        self.assertTrue(any("project_stream_create" in text for text in output["guidelines"]))
        self.assertTrue(any("useWorktree=false" in text for text in output["guidelines"]))
        self.assertIn("sibling stream is snapshotted", output["archiveDescription"])
        self.assertTrue(any("sibling archival completes immediately" in text for text in output["archiveGuidelines"]))
        self.assertTrue(any("final tool operation" in text for text in output["archiveGuidelines"]))

    def test_worklog_tool_appends_private_structured_entry(self):
        expression = """
const tools = {};
const pi = {
  on: () => {},
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
const result = await tools.project_worklog_append.execute('call', {
  type: 'decision',
  summary: ' Keep the worklog in project home. ',
  reason: ' It remains independent of the checkout. ',
  next: 'Add catchup coverage.',
  files: [' integrations/pi/project-object.ts '],
}, undefined, undefined, { sessionManager: { getSessionId: () => 'session-123' } });
console.log(JSON.stringify(result));
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        worklog = self.home / self.project_id / "worklogs" / "events.jsonl"
        self.assertEqual(response["details"]["worklog"], str(worklog))
        entry = json.loads(worklog.read_text())
        self.assertEqual(entry["v"], 1)
        self.assertEqual(entry["project"], self.project_id)
        self.assertEqual(entry["session"], "session-123")
        self.assertEqual(entry["type"], "decision")
        self.assertEqual(entry["summary"], "Keep the worklog in project home.")
        self.assertEqual(entry["reason"], "It remains independent of the checkout.")
        self.assertEqual(entry["files"], ["integrations/pi/project-object.ts"])
        self.assertEqual(worklog.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(worklog.stat().st_mode & 0o777, 0o600)

    def test_stream_context_inherits_project_instructions_and_scopes_worklog(self):
        stream_id = str(uuid.uuid4())
        project_home = self.home / self.project_id
        stream_home = project_home / "streams" / stream_id
        stream_home.mkdir(parents=True)
        (project_home / "AGENTS.md").write_text("project authority")
        (stream_home / "AGENTS.md").write_text("stream detail")
        (project_home / "streams.json").write_text(json.dumps({
            "version": 1,
            "streams": [{"id": stream_id, "name": "Focused Work", "mainDirectory": None, "archivedAt": None}],
        }))
        worklogs = stream_home / "worklogs"
        worklogs.mkdir()
        (worklogs / "events.jsonl").write_text("".join(
            json.dumps({
                "v": 1,
                "time": f"2026-10-28T12:{index:02d}:00.000Z",
                "project": self.project_id,
                "scope": "stream",
                "stream": {"id": stream_id, "name": "Focused Work"},
                "session": "prior-session",
                "type": "progress",
                "summary": f"worklog-event-{index:02d}",
                "next": f"next-step-{index:02d}",
                "files": ["not-injected.txt"],
            }) + "\n"
            for index in range(1, 13)
        ))
        expression = """
const handlers = {};
const tools = {};
const pi = {
  on: (name, handler) => { handlers[name] = handler; },
  registerTool: (tool) => { tools[tool.name] = tool; },
  registerCommand: () => {},
};
m.default(pi);
await handlers.session_start({}, { mode: 'rpc', hasUI: false, sessionManager: { getSessionId: () => 'stream-session' }, ui: { setStatus: () => {}, theme: { fg: (_kind, text) => text } } });
const event = { systemPromptOptions: { sections: {} } };
handlers.before_agent_start(event);
const result = await tools.project_worklog_append.execute('call', { type: 'note', summary: 'Stream-only detail', projectAttention: true }, undefined, undefined, { sessionManager: { getSessionId: () => 'stream-session' } });
console.log(JSON.stringify({ prompt: event.systemPromptOptions.sections.project_object, result }));
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id, "PROJECT_OBJECT_STREAM_ID": stream_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertLess(output["prompt"].index("project authority"), output["prompt"].index("stream detail"))
        self.assertNotIn("worklog-event-02", output["prompt"])
        self.assertLess(output["prompt"].index("worklog-event-03"), output["prompt"].index("worklog-event-12"))
        self.assertIn("next-step-12", output["prompt"])
        self.assertNotIn("not-injected.txt", output["prompt"])
        self.assertEqual(output["result"]["details"]["scope"], "stream")
        self.assertEqual(output["result"]["details"]["streamId"], stream_id)
        entry = json.loads((stream_home / "worklogs" / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(entry["scope"], "stream")
        self.assertEqual(entry["stream"]["id"], stream_id)
        self.assertTrue(entry["projectAttention"])
        self.assertFalse((project_home / "worklogs" / "events.jsonl").exists())

    def test_recent_worklog_context_has_a_hard_byte_cap(self):
        worklogs = self.home / self.project_id / "worklogs"
        worklogs.mkdir()
        (worklogs / "events.jsonl").write_text("".join(
            json.dumps({
                "v": 1,
                "time": f"2026-10-28T12:{index:02d}:00.000Z",
                "project": self.project_id,
                "scope": "project",
                "session": "prior-session",
                "type": "finish",
                "summary": f"large-event-{index:02d} " + "s" * 1900,
                "result": "r" * 3900,
                "next": "n" * 3900,
            }) + "\n"
            for index in range(1, 13)
        ))
        project = {
            "id": self.project_id,
            "name": "Alpha",
            "mainDirectory": str(self.main),
            "projectHome": str(self.home / self.project_id),
            "agentsFile": str(self.home / self.project_id / "AGENTS.md"),
        }
        expression = f"""
const context = m.readRecentWorklog({json.dumps(project)});
console.log(JSON.stringify({{context, bytes: Buffer.byteLength(context)}}));
"""
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertLessEqual(output["bytes"], 8 * 1024)
        self.assertIn("large-event-12", output["context"])
        self.assertNotIn("large-event-03", output["context"])

    def test_worklog_tool_enforces_quality_fields(self):
        expression = """
const tools = {};
const pi = { on: () => {}, registerTool: (tool) => { tools[tool.name] = tool; }, registerCommand: () => {} };
m.default(pi);
try {
  await tools.project_worklog_append.execute('call', { type: 'mistake', summary: 'Skipped validation' }, undefined, undefined, { sessionManager: { getSessionId: () => 'session-123' } });
} catch (error) {
  console.log(error.message);
}
"""
        result = self.node(expression, {"PROJECT_OBJECT_ID": self.project_id})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mistake entries require lesson", result.stdout)
        self.assertFalse((self.home / self.project_id / "worklogs" / "events.jsonl").exists())

    def test_worklog_tool_rejects_symlinked_worklogs_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.home / self.project_id / "worklogs").symlink_to(outside, target_is_directory=True)
        project = {
            "id": self.project_id,
            "name": "Alpha",
            "mainDirectory": str(self.main),
            "projectHome": str(self.home / self.project_id),
            "agentsFile": str(self.home / self.project_id / "AGENTS.md"),
        }
        expression = f"""
try {{
  m.appendProjectWorklogEntry({json.dumps(project)}, {{ type: 'note', summary: 'Unsafe append' }}, 'session-123');
}} catch (error) {{
  console.log(error.message);
}}
"""
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot open worklogs directory safely", result.stdout)
        self.assertFalse((outside / "events.jsonl").exists())

    def test_worklog_tool_rejects_symlinked_events_file(self):
        worklogs = self.home / self.project_id / "worklogs"
        worklogs.mkdir()
        outside = self.root / "outside.jsonl"
        outside.write_text("")
        (worklogs / "events.jsonl").symlink_to(outside)
        project = {
            "id": self.project_id,
            "name": "Alpha",
            "mainDirectory": str(self.main),
            "projectHome": str(self.home / self.project_id),
            "agentsFile": str(self.home / self.project_id / "AGENTS.md"),
        }
        expression = f"""
try {{
  m.appendProjectWorklogEntry({json.dumps(project)}, {{ type: 'note', summary: 'Unsafe append' }}, 'session-123');
}} catch (error) {{
  console.log(error.message);
}}
"""
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot open worklog safely", result.stdout)
        self.assertEqual(outside.read_text(), "")

    def test_oversized_agents_file_is_rejected(self):
        agents = self.home / self.project_id / "AGENTS.md"
        agents.write_bytes(b"x" * (64 * 1024 + 1))
        expression = f"try {{ m.readAgentInstructions({{id:{json.dumps(self.project_id)}, name:'Alpha', projectHome:{json.dumps(str(agents.parent))}, agentsFile:{json.dumps(str(agents))}}}); }} catch (e) {{ console.log(e.message); }}"
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("65536-byte limit", result.stdout)

    def test_symlinked_agents_file_is_rejected(self):
        outside = self.root / "outside.md"
        outside.write_text("unsafe")
        agents = self.home / self.project_id / "AGENTS.md"
        agents.symlink_to(outside)
        expression = f"try {{ m.readAgentInstructions({{id:{json.dumps(self.project_id)}, name:'Alpha', projectHome:{json.dumps(str(agents.parent))}, agentsFile:{json.dumps(str(agents))}}}); }} catch (e) {{ console.log(e.message); }}"
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot open AGENTS.md safely", result.stdout)

    def test_symlinked_project_home_is_rejected(self):
        project_home = self.home / self.project_id
        shutil.rmtree(project_home)
        other = self.home / str(uuid.uuid4())
        other.mkdir()
        agents = other / "AGENTS.md"
        agents.write_text("wrong project")
        project_home.symlink_to(other, target_is_directory=True)
        expression = f"try {{ m.readAgentInstructions({{id:{json.dumps(self.project_id)}, name:'Alpha', projectHome:{json.dumps(str(project_home))}, agentsFile:{json.dumps(str(project_home / 'AGENTS.md'))}}}); }} catch (e) {{ console.log(e.message); }}"
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("cannot open project home safely", result.stdout)

    def test_ancestor_replacement_after_open_reads_from_pinned_directory(self):
        project_home = self.home / self.project_id
        agents = project_home / "AGENTS.md"
        agents.write_text("original instructions")
        moved = self.home / "moved-original"
        replacement = self.home / "replacement"
        replacement.mkdir()
        (replacement / "AGENTS.md").write_text("replacement instructions")
        project = f"{{id:{json.dumps(self.project_id)}, name:'Alpha', projectHome:{json.dumps(str(project_home))}, agentsFile:{json.dumps(str(agents))}}}"
        hook = f"() => {{ fs.renameSync({json.dumps(str(project_home))}, {json.dumps(str(moved))}); fs.symlinkSync({json.dumps(str(replacement))}, {json.dumps(str(project_home))}, 'dir'); }}"
        result = self.node(f"console.log(m.readAgentInstructions({project}, {hook}))")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "original instructions")

    def test_normal_agents_file_is_read(self):
        agents = self.home / self.project_id / "AGENTS.md"
        agents.write_text("project instructions\n")
        expression = f"console.log(m.readAgentInstructions({{id:{json.dumps(self.project_id)}, name:'Alpha', projectHome:{json.dumps(str(agents.parent))}, agentsFile:{json.dumps(str(agents))}}}))"
        result = self.node(expression)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "project instructions")


if __name__ == "__main__":
    unittest.main()
