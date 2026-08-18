#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const dir = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(dir, 'footer.ts'), 'utf8');

assert.match(source, /const AGENT_SPINNER_FRAMES = \["⠋".*"⠏"\]/, 'footer must define a compact braille spinner');
assert.match(source, /const AGENT_SPINNER_INTERVAL_MS = 100/, 'spinner cadence must remain restrained');
assert.match(source, /setInterval\(\(\) => \{\s*agentSpinnerIndex = .*activeTui\?\.requestRender\(\)/s, 'spinner must animate through TUI rerenders');
assert.match(source, /setAgentSpinnerRunning\(Boolean\(agentCount\)\)/, 'spinner must run only while the running-agent count is visible');
assert.match(source, /theme\.fg\("accent", AGENT_SPINNER_FRAMES\[agentSpinnerIndex\]\)/, 'spinner must use the existing accent theme token');
assert.match(source, /statusItems\.push\(`\$\{theme\.fg\("muted", agentCount\)\} \$\{spinner\}`\)/, 'agent count must appear before the spinner');
assert.match(source, /ownerSessionId\?: unknown/, 'registry records must expose their owning Pi session');
assert.match(source, /record\.ownerSessionId === ownerSessionId && isRunningOrchestratorRecord\(record\)/, 'agent count must exclude workers owned by other sessions');
assert.match(source, /runningOrchestratorAgentCount\(ctx\.sessionManager\.getSessionId\(\)\)/, 'footer rendering must scope the count to the current session');
assert.match(source, /ORCHESTRATOR_AGENT_COUNT_TTL_MS = 1_000/, 'animation renders must not rescan every worker record at frame rate');
assert.match(source, /dispose\(\) \{\s*unsub\(\);\s*setAgentSpinnerRunning\(false\)/s, 'replacing the footer must stop the spinner timer');
assert.match(source, /pi\.on\("session_shutdown"[\s\S]*setAgentSpinnerRunning\(false\)/, 'session shutdown must stop the spinner timer');
assert.match(source, /orchestratorAgentCountCache\.clear\(\)/, 'session shutdown must clear per-session count caches');

console.log('footer spinner static tests passed');
