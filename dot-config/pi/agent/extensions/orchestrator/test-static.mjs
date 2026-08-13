#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(dir, 'index.ts'), 'utf8');

function between(startNeedle, endNeedle) {
  const start = source.indexOf(startNeedle);
  assert.notEqual(start, -1, `missing start needle: ${startNeedle}`);
  const end = source.indexOf(endNeedle, start);
  assert.notEqual(end, -1, `missing end needle: ${endNeedle}`);
  return source.slice(start, end);
}

const watcherRefresh = between('async function refreshOwnedWorkersStateOnly', '\n\tfunction ensureWatcherStarted');
assert.match(source, /type WorkerState = .*"done"/s, 'done must be a first-class worker state');
assert.match(source, /const AgentLifecycleReportParams = Type\.Object/, 'report-state params must exist');
assert.match(source, /name: "orchestrator_report_state"/, 'child report-state tool must be registered');
assert.match(source, /PI_ORCHESTRATOR_WORKER_NAME/, 'worker name env must be injected');
assert.match(source, /PI_ORCHESTRATOR_OWNER_SESSION_ID/, 'owner session env must be injected');
assert.match(source, /PI_ORCHESTRATOR_STATE_FILE/, 'state file env must be injected');
assert.match(source, /ownerSessionId !== record\.ownerSessionId/, 'child report must validate owner session');
assert.match(source, /lifecycle state file mismatch/, 'child report must validate lifecycle file path');
assert.match(source, /record\.ownerSessionId === currentSessionId/, 'watcher must be session-scoped');
assert.doesNotMatch(watcherRefresh, /captureWorkerOutput|capture-pane|parseStructuredResult/, 'watcher must not read or parse transcripts');
assert.doesNotMatch(watcherRefresh, /autoSurfaceBlockedWorker|surfaceTerminal/, 'watcher must not auto-surface hidden workers');
assert.match(source, /withTerminalRecordLock\(record\.name/, 'registry writes must use per-worker lock');
assert.doesNotMatch(source, /const cached = terminals\.get\(name\);\s*if \(cached\) return cached;/, 'loadTerminalRecord must not return stale cached records across processes');
assert.match(source, /applyLifecycleRecord\(record, lifecycle\);\s*applyExitMetadata\(record, \{\}\);/s, 'exit metadata must be reapplied after lifecycle so failed/exited terminal state remains authoritative');
assert.match(source, /source: "manual"/, 'manual marks must also write lifecycle state');
assert.match(source, /worker\.state === "done" \|\| worker\.state === "exited"/, 'done and exited must both group as completed');
assert.match(source, /PI_ORCHESTRATOR_WATCH_INTERVAL_MS/, 'watch interval config must exist');

console.log('orchestrator static tests passed');
