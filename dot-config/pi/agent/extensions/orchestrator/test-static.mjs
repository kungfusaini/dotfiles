#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(dir, 'index.ts'), 'utf8');
const readme = readFileSync(join(dir, 'README.md'), 'utf8');
const guidance = `${source}\n${readme}`;

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
assert.match(source, /one worker per review unit/, 'tool guidance must enforce review-unit worker scoping');
assert.match(source, /one branch\/PR per review unit/, 'tool guidance must map review units to branch/PR layers');
assert.match(source, /do not bundle unrelated units/i, 'child task prompt must warn workers not to expand review scope');
assert.match(source, /Do not make duplicate workers for the same task/, 'tool guidance must warn against duplicate workers');
assert.match(source, /do not use scope=all for normal task management/, 'worker inspection guidance must forbid scope=all for normal orchestration');
assert.match(source, /explicitly asks to inspect global\/orphaned\/other-session workers/, 'scope=all guidance must require explicit global-debug intent');
assert.match(source, /read-only stream scout/, 'tool guidance must introduce read-only stream scouts');
assert.match(source, /compact STREAM_BRIEF/, 'stream scouts must produce compact handoff briefs');
assert.match(source, /research\/stream-briefs\/<stream-slug>\.md/, 'stream scout briefs must be stored under stream research/stream-briefs');
assert.match(source, /must not implement, create branches\/PRs, or launch workers/, 'stream scouts must not implement or spawn nested workers');
assert.match(source, /local PR-layer invariant check/, 'orchestrator guidance must require local PR-layer invariant checks');
assert.match(source, /Avoid full-stack audits unless topology changed or the user requested them/, 'PR invariant guidance must avoid unnecessary full-stack audits');
assert.match(guidance, /full ticket\/issue description and acceptance criteria|full ticket or issue description and acceptance criteria/, 'tracker-backed delegation must require full ticket context, not only summaries');
assert.match(guidance, /missing acceptance criteria, wrong-ticket scope, scope spill/i, 'proper review guidance must compare PR diffs against ticket criteria');
assert.match(guidance, /likely bugs\/regressions/i, 'proper review guidance must include bug and regression review');
assert.match(source, /do not treat passing CI\/lint\/codequality as sufficient/i, 'child review prompt must forbid mechanical-only review for ticket-backed PRs');
assert.match(guidance, /Parent orchestrator owns review units, stream\/stack topology, worker launch, PR-layer checks, and user-facing synthesis/, 'guidance must define parent responsibility boundaries');
assert.match(guidance, /Review-unit implementers own exactly one review unit by default/, 'guidance must define review-unit implementer responsibility boundaries');
assert.match(guidance, /Shell\/test workers run deterministic commands only and do not edit code/, 'guidance must define shell/test worker responsibility boundaries');
assert.match(guidance, /Prefer structured worker state\/results over raw transcript reads/, 'guidance must prefer structured worker results over transcript reads');
assert.match(guidance, /write detailed handoff artifacts to files and report paths/, 'worker prompt must require file artifacts instead of long transcript output');
assert.match(guidance, /Stop when the assigned output or decision is clear enough/, 'worker prompt must include bounded reading stop condition');
assert.match(guidance, /do not keep reading or auditing for completeness beyond the task/, 'worker guidance must forbid exhaustive reading beyond task needs');
assert.match(guidance, /Do not close blocked\/failed workers that contain task context unless the user explicitly approves/, 'guidance must preserve blocked worker context');
assert.match(guidance, /Model-limit\/provider-limit workers are preserved state, not disposable failures/, 'guidance must preserve model-limit blocked workers');

console.log('orchestrator static tests passed');
