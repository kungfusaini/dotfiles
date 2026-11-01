import assert from "node:assert/strict";
import { chmodSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import commandTerminalExtension, {
  terminalArguments,
} from "../home/config/pi/extensions/command-terminal.ts";

function fakePi() {
  const tools = new Map();
  return {
    api: {
      registerTool(definition) {
        tools.set(definition.name, definition);
      },
    },
    tools,
  };
}

test("builds an argument-safe same-workspace terminal launch", () => {
  const command = "printf '%s\\n' 'argument with spaces' && sudo true";
  const arguments_ = terminalArguments(command, "/tmp/path with spaces", {
    PROJECT_WORKSPACE_EXEC: "/test/project-workspace-exec",
    PI_COMMAND_TERMINAL: "/test/kitty",
  });

  assert.equal(arguments_[0], "/test/project-workspace-exec");
  assert.equal(arguments_[1], "/test/kitty");
  assert.equal(arguments_[2], "--hold");
  assert.equal(arguments_[6], "/tmp/path with spaces");
  assert.equal(arguments_.at(-1), command);
  assert.match(arguments_[9], /Command requiring your attention/);
  assert.match(arguments_[9], /exec bash -lc "\$1"/);
});

test("tool delegates placement to project-workspace-exec without shell interpolation", async () => {
  const temporary = mkdtempSync(join(tmpdir(), "pi-command-terminal-test-"));
  const launcher = join(temporary, "project-workspace-exec");
  const captured = join(temporary, "captured.json");
  const oldLauncher = process.env.PROJECT_WORKSPACE_EXEC;
  const oldTerminal = process.env.PI_COMMAND_TERMINAL;
  const oldCaptured = process.env.CAPTURED;

  writeFileSync(launcher, `#!/usr/bin/env node
const { writeFileSync } = require("node:fs");
writeFileSync(process.env.CAPTURED, JSON.stringify({ argv: process.argv.slice(2), cwd: process.cwd() }));
`);
  chmodSync(launcher, 0o755);
  process.env.PROJECT_WORKSPACE_EXEC = launcher;
  process.env.PI_COMMAND_TERMINAL = "/exact/kitty";
  process.env.CAPTURED = captured;

  try {
    const fake = fakePi();
    commandTerminalExtension(fake.api);
    const tool = fake.tools.get("open_command_terminal");
    assert.ok(tool);
    const command = "sudo sh -c 'printf \\\"a b\\\"' && echo done";
    const result = await tool.execute("call", { command }, undefined, undefined, { cwd: temporary });
    const invocation = JSON.parse(readFileSync(captured, "utf8"));

    assert.equal(invocation.cwd, temporary);
    assert.equal(invocation.argv[0], "/exact/kitty");
    assert.equal(invocation.argv.at(-1), command);
    assert.match(result.content[0].text, /beside this Pi window/);
  } finally {
    if (oldLauncher === undefined) delete process.env.PROJECT_WORKSPACE_EXEC;
    else process.env.PROJECT_WORKSPACE_EXEC = oldLauncher;
    if (oldTerminal === undefined) delete process.env.PI_COMMAND_TERMINAL;
    else process.env.PI_COMMAND_TERMINAL = oldTerminal;
    if (oldCaptured === undefined) delete process.env.CAPTURED;
    else process.env.CAPTURED = oldCaptured;
    rmSync(temporary, { recursive: true, force: true });
  }
});

test("tool reports a fail-closed placement error", async () => {
  const temporary = mkdtempSync(join(tmpdir(), "pi-command-terminal-failure-"));
  const launcher = join(temporary, "project-workspace-exec");
  const oldLauncher = process.env.PROJECT_WORKSPACE_EXEC;
  writeFileSync(launcher, "#!/bin/sh\nexit 1\n");
  chmodSync(launcher, 0o755);
  process.env.PROJECT_WORKSPACE_EXEC = launcher;

  try {
    const fake = fakePi();
    commandTerminalExtension(fake.api);
    await assert.rejects(
      fake.tools.get("open_command_terminal").execute("call", { command: "sudo true" }, undefined, undefined, { cwd: temporary }),
      /launcher exited with status 1/,
    );
  } finally {
    if (oldLauncher === undefined) delete process.env.PROJECT_WORKSPACE_EXEC;
    else process.env.PROJECT_WORKSPACE_EXEC = oldLauncher;
    rmSync(temporary, { recursive: true, force: true });
  }
});
