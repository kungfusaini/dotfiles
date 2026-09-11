import assert from "node:assert/strict";
import test from "node:test";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { fitViewportLines, inspectDataForTarget, sanitizeText } from "./inspection.mjs";

function withTempEnvs(testCase) {
  const base = mkdtempSync(path.join(tmpdir(), "picker-inspection-"));
  const dataHome = path.join(base, "share");
  const stateHome = path.join(base, "state");
  mkdirSync(dataHome, { recursive: true });
  mkdirSync(stateHome, { recursive: true });

  const originalData = process.env.XDG_DATA_HOME;
  const originalState = process.env.XDG_STATE_HOME;
  process.env.XDG_DATA_HOME = dataHome;
  process.env.XDG_STATE_HOME = stateHome;

  try {
    return testCase({ base, dataHome, stateHome });
  } finally {
    process.env.XDG_DATA_HOME = originalData;
    process.env.XDG_STATE_HOME = originalState;
    rmSync(base, { recursive: true, force: true });
  }
}

function writeJson(file, value) {
  mkdirSync(path.dirname(file), { recursive: true });
  writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

test("inspectDataForTarget resolves owner filtering and includes hidden children", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "project-demo-1";
    const projectPath = path.join(dataHome, "pi", "projects", projectID);
    const streamID = "stream-alpha";

    writeJson(path.join(projectPath, "sessions.json"), {
      v: 1,
      sessions: {
        "owner-project": {
          id: "owner-project",
          scope: "project",
          projectID,
          updatedAt: "2026-01-01T00:00:00.000Z",
        },
      },
    });

    writeJson(path.join(projectPath, "streams", streamID, "sessions.json"), {
      v: 1,
      sessions: {
        ownerA: {
          scope: "stream",
          projectID,
          streamID,
          updatedAt: "2026-02-02T00:00:00.000Z",
        },
        ownerB: {
          scope: "stream",
          projectID,
          streamID,
          updatedAt: "2026-02-02T01:00:00.000Z",
        },
      },
    });

    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "a.json"), {
      name: "active stream worker",
      ownerSessionId: "ownerA",
      task: "stream task",
      state: "running",
      visibility: "hidden",
      updatedAt: "2026-03-03T00:00:00.000Z",
    });

    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "b.json"), {
      name: "hidden stream worker",
      ownerSessionId: "ownerB",
      task: "archived stream task",
      state: "running",
      visibility: "hidden",
      updatedAt: "2026-03-03T00:00:00.001Z",
    });

    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "c.json"), {
      name: "unrelated",
      ownerSessionId: "owner-other",
      task: "other scope",
      state: "running",
      visibility: "visible",
      updatedAt: "2026-03-03T00:00:00.000Z",
    });

    const result = inspectDataForTarget({ pi: { projectID, name: "Demo" } }, {
      special: "stream",
      stream: { id: streamID },
      record: { pi: { projectID, name: "Demo" } },
    });

    const children = result.children.map((entry) => entry.ownerSessionId).sort();
    assert.deepEqual(children, ["ownerA", "ownerB"]);
    const childMap = Object.fromEntries(result.children.map((entry) => [entry.ownerSessionId, entry]));
    assert.equal(childMap.ownerA.visibility, "hidden");
    assert.ok(result.warnings.length >= 0);
  });
});

test("inspectDataForTarget reports corrupt index and malformed registry warnings", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "project-demo-2";
    const projectPath = path.join(dataHome, "pi", "projects", projectID);
    const streamID = "stream-beta";
    mkdirSync(path.join(projectPath, "streams", streamID), { recursive: true });

    writeFileSync(path.join(projectPath, "sessions.json"), "not-json", "utf8");
    writeFileSync(path.join(projectPath, "streams", streamID, "sessions.json"), "not-json", "utf8");

    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "corrupt.json"), {
      name: "broken",
      ownerSessionId: "owner-fail",
    });
    writeFileSync(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "bad.json"), "bad", "utf8");

    const result = inspectDataForTarget({ pi: { projectID, name: "Demo" } }, {
      special: "project-scope",
      record: { pi: { projectID, name: "Demo" } },
    });

    const warnings = (result.warnings || []).join("\n");
    assert.match(warnings, /unavailable|unreadable|corrupt/i);
    assert.equal(result.children.length, 0);
  });
});

test("sanitizeText normalizes control chars and strips ANSI/CSI", () => {
  const sanitized = sanitizeText("safe\x1b[31mline one\x1b[0m\nline\ttwo\r\x9b31mterm\x07text");
  assert.equal(sanitized, "safeline one line two termtext");
});

test("fitViewportLines clips row count", () => {
  const lines = ["one", "two", "three", "four"];
  const clipped = fitViewportLines(lines, 2);
  assert.deepEqual(clipped, ["one", "two"]);
});

test("stream owner resolution follows latest session entry across sibling streams", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "project-demo-3";
    const oldStreamID = "stream-old";
    const newStreamID = "stream-new";
    const projectPath = path.join(dataHome, "pi", "projects", projectID);

    writeJson(path.join(projectPath, "streams", oldStreamID, "sessions.json"), {
      v: 1,
      sessions: {
        moved: {
          id: "moved-owner",
          scope: "stream",
          projectID,
          streamID: oldStreamID,
          updatedAt: "2026-01-01T00:00:00.000Z",
        },
      },
    });

    writeJson(path.join(projectPath, "streams", newStreamID, "sessions.json"), {
      v: 1,
      sessions: {
        moved: {
          id: "moved-owner",
          scope: "stream",
          projectID,
          streamID: newStreamID,
          updatedAt: "2026-02-01T00:00:00.000Z",
        },
      },
    });

    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "moved.json"), {
      ownerSessionId: "moved-owner",
      name: "moved worker",
      task: "stream task",
    });

    const staleResult = inspectDataForTarget({ pi: { projectID, name: "Moved" } }, {
      special: "stream",
      stream: { id: oldStreamID },
      record: { pi: { projectID, name: "Moved" } },
    });
    assert.equal(staleResult.children.length, 0);

    const activeResult = inspectDataForTarget({ pi: { projectID, name: "Moved" } }, {
      special: "stream",
      stream: { id: newStreamID },
      record: { pi: { projectID, name: "Moved" } },
    });
    assert.equal(activeResult.children.length, 1);
    assert.equal(activeResult.children[0].ownerSessionId, "moved-owner");
  });
});

test("empty index state returns warnings", () => {
  withTempEnvs(({ dataHome }) => {
    const projectID = "project-empty";
    const result = inspectDataForTarget({ pi: { projectID, name: "Empty" } }, {
      special: "project-scope",
      record: { pi: { projectID, name: "Empty" } },
    });
    assert.equal(result.children.length, 0);
    assert.match((result.warnings || []).join("\n"), /unavailable|unreadable/i);
  });
});

test("session records use Pi session names without loading transcript bodies", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "named-session-project";
    const sessionID = "named-session-id";
    writeJson(path.join(dataHome, "pi", "projects", projectID, "streams", "stream-a", "sessions.json"), {
      sessions: { [sessionID]: { id: sessionID, projectID, scope: "stream", streamID: "stream-a" } },
    });
    const sessionFile = path.join(stateHome, "pi", "agent", "sessions", `2026-01-01_${sessionID}.jsonl`);
    mkdirSync(path.dirname(sessionFile), { recursive: true });
    writeFileSync(sessionFile, [
      JSON.stringify({ type: "session", id: sessionID }),
      JSON.stringify({ type: "message", message: { role: "user", content: "Fallback prompt" } }),
      JSON.stringify({ type: "session_info", name: "Readable operator title" }),
    ].join("\n"), "utf8");
    const result = inspectDataForTarget({ pi: { projectID } }, { special: "stream", stream: { id: "stream-a" } });
    assert.equal(result.owners[0].title, "Readable operator title");
    assert.equal(result.owners[0].sessionFile, sessionFile);
  });
});

test("orchestrator child sessions attach to their parent instead of appearing as root sessions", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "session-tree-project";
    const streamID = "stream-a";
    const parentID = "parent-session";
    const childID = "child-session";
    writeJson(path.join(dataHome, "pi", "projects", projectID, "streams", streamID, "sessions.json"), {
      sessions: {
        [parentID]: { id: parentID, projectID, scope: "stream", streamID, updatedAt: "2026-01-02" },
        [childID]: { id: childID, projectID, scope: "stream", streamID, updatedAt: "2026-01-01" },
      },
    });
    const sessionDir = path.join(stateHome, "pi", "agent", "sessions");
    mkdirSync(sessionDir, { recursive: true });
    writeFileSync(path.join(sessionDir, `root_${parentID}.jsonl`), JSON.stringify({ type: "session_info", name: "Operator session" }), "utf8");
    writeFileSync(path.join(sessionDir, `child_${childID}.jsonl`), JSON.stringify({
      type: "message",
      message: { role: "user", content: "You are a hidden Pi worker started by the parent orchestrator.\n\nWorker: reviewer\nCWD: /tmp\n\nTask: Review" },
    }), "utf8");
    writeJson(path.join(stateHome, "pi", "orchestrator", "terminals", "registry", "reviewer.json"), {
      name: "reviewer", ownerSessionId: parentID, state: "done", visibility: "hidden",
    });
    const result = inspectDataForTarget({ pi: { projectID } }, { special: "stream", stream: { id: streamID } });
    assert.deepEqual(result.owners.map((session) => session.id), [parentID]);
    assert.equal(result.children.length, 1);
    assert.equal(result.children[0].ownerSessionId, parentID);
    assert.equal(result.children[0].session.id, childID);
    assert.equal(result.children[0].session.workerName, "reviewer");
  });
});

test("empty project index does not warn inside a populated stream", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "empty-project-populated-stream";
    const base = path.join(dataHome, "pi", "projects", projectID);
    writeJson(path.join(base, "sessions.json"), { sessions: {} });
    writeJson(path.join(base, "streams", "stream-a", "sessions.json"), {
      sessions: { owner: { id: "owner", projectID, scope: "stream", streamID: "stream-a" } },
    });
    const result = inspectDataForTarget({ pi: { projectID } }, {
      special: "stream", stream: { id: "stream-a" },
    });
    assert.equal(result.owners.length, 1);
    assert.ok(!result.warnings.some((warning) => /No sessions in index/.test(warning)));
  });
});

test("picker labels keep navigation icons without implementation jargon", () => {
  withTempEnvs(({ base, dataHome }) => {
    const project = { id: "demo", name: "Pi", root: base, pi: { projectID: "demo", name: "Pi" } };
    writeJson(path.join(dataHome, "herdr-pi", "workspaces.json"), { workspaces: { demo: project } });
    writeJson(path.join(dataHome, "pi", "projects", "demo", "streams", "s", "stream.json"), { id: "s", name: "Orchestrator" });
    const result = spawnSync(process.execPath, [fileURLToPath(new URL("./picker.mjs", import.meta.url))], {
      encoding: "utf8",
      env: { ...process.env, HERDR_BIN_PATH: "/usr/bin/false", HERDR_PI_PICKER_STATE: path.join(base, "picker-state.json"), PICKER_DUMP: "1", PICKER_EXPAND_PROJECT: "Pi", NO_COLOR: "1" },
    });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Orchestrator/);
    assert.match(result.stdout, /\+ New project/);
    assert.match(result.stdout, /\+ New scratch space/);
    assert.match(result.stdout, //);
    assert.doesNotMatch(result.stdout, /project \+ space|space only|shared project|unlinked/i);
  });
});

test("owners are preserved even when no orchestrator children exist", () => {
  withTempEnvs(({ dataHome, stateHome }) => {
    const projectID = "project-demo-4";
    const projectPath = path.join(dataHome, "pi", "projects", projectID);

    writeJson(path.join(projectPath, "sessions.json"), {
      v: 1,
      sessions: {
        stale: {
          id: "stale-owner",
          scope: "project",
          projectID,
          updatedAt: "2026-02-02T00:00:00.000Z",
        },
      },
    });
    mkdirSync(path.join(stateHome, "pi", "orchestrator", "terminals", "registry"), { recursive: true });

    const result = inspectDataForTarget({ pi: { projectID, name: "Orphans" } }, {
      special: "project-scope",
      record: { pi: { projectID, name: "Orphans" } },
    });

    assert.equal(result.owners.length, 1);
    assert.equal(result.owners[0].id, "stale-owner");
    assert.equal(result.children.length, 0);
  });
});
