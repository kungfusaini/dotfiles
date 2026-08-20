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

const parentNotification = between('async function notifyParentOfWorkerUpdates', '\n\tasync function refreshOwnedWorkersStateOnly');
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
assert.match(source, /const WorkerScopeSchema = StringEnum\(\["owned", "all"\]/, 'worker scope schema must exist');
assert.match(source, /scope: Type\.Optional\(WorkerScopeSchema\)/, 'public worker inspection tools must expose scope overrides');
assert.match(source, /function workerScope\(records: TerminalRecord\[], ctx: ExtensionContext, scope: WorkerScope\)/, 'worker scope filter helper must exist');
assert.match(source, /assertWorkerReadable\(record, ctx, params\.scope \?\? "owned"\)/, 'worker read must enforce default ownership');
assert.doesNotMatch(watcherRefresh, /captureWorkerOutput|capture-pane|parseStructuredResult/, 'watcher must not read or parse transcripts');
assert.doesNotMatch(watcherRefresh, /autoSurfaceBlockedWorker|surfaceTerminal/, 'watcher must not auto-surface hidden workers');
assert.match(source, /withTerminalRecordLock\(record\.name/, 'registry writes must use per-worker lock');
assert.doesNotMatch(source, /const cached = terminals\.get\(name\);\s*if \(cached\) return cached;/, 'loadTerminalRecord must not return stale cached records across processes');
assert.match(source, /applyLifecycleRecord\(record, lifecycle\);\s*applyExitMetadata\(record, \{\}\);/s, 'exit metadata must be reapplied after lifecycle so failed/exited terminal state remains authoritative');
assert.match(source, /exited successfully/, 'plain process exits must replace stale running status text');
assert.match(source, /source: "manual"/, 'manual marks must also write lifecycle state');
assert.match(source, /worker\.state === "done" \|\| worker\.state === "exited"/, 'done and exited must both group as completed');
assert.match(source, /PI_ORCHESTRATOR_WATCH_INTERVAL_MS/, 'watch interval config must exist');
assert.match(source, /parentNotificationKey\?: string/, 'worker records must persist parent notification deduplication keys');
assert.match(source, /function parentWakeEventKey/, 'notifications must key lifecycle events so repeated blocked transitions can wake the parent again');
assert.match(parentNotification, /pi\.sendMessage\(/, 'terminal worker states must notify the parent agent');
assert.match(parentNotification, /deliverAs: "followUp", triggerTurn: true/, 'parent notification must wake an idle agent or follow an active turn');
assert.match(parentNotification, /display: false/, 'internal lifecycle messages should not be shown as user-facing chat');
assert.match(parentNotification, /dispatch follow-up workers when appropriate/, 'the parent must be told to continue orchestration when useful');
assert.match(source, /await notifyParentOfWorkerUpdates\(refreshed\)/, 'the background watcher must queue parent updates after refresh');
assert.match(source, /pollWorkersOnce\(pi, ctx, [^\n]+, params\.scope \?\? "owned"\)/, 'default list/status/poll calls must use owned scope');
assert.match(source, /pi\.on\("session_shutdown"/, 'the watcher must stop with its owning Pi session');

console.log('orchestrator static tests passed');
