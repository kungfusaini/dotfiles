import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { createResumeRecovery } from './recovery.mjs';

const root = process.env.PI_TEST_ROOT;
if (!root) throw new Error('Set PI_TEST_ROOT to the installed pi-monorepo directory');
const sdk = await import(`${root}/dist/index.js`);
const { AssistantMessageEventStream } = await import(`${root}/node_modules/@earendil-works/pi-ai/dist/utils/event-stream.js`);
const codex = await import(`${root}/node_modules/@earendil-works/pi-ai/dist/api/openai-codex-responses.js`);
const { isRetryableAssistantError } = await import(`${root}/node_modules/@earendil-works/pi-ai/dist/utils/retry.js`);
const model = { id: 'resume-test', name: 'Resume test', api: 'openai-codex-responses',
  provider: 'openai-codex', baseUrl: 'https://example.invalid/backend-api',
  reasoning: false, input: ['text'], cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
  contextWindow: 1000000, maxTokens: 1024 };
const usage = () => ({ input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } });
const message = (content = [], stopReason = 'stop') => ({ role: 'assistant', content,
  api: model.api, provider: model.provider, model: model.id, usage: usage(), stopReason, timestamp: Date.now() });
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
async function until(check) {
  for (let n = 0; n < 200; n++) { if (check()) return; await delay(5); }
  assert.fail('condition did not become true within 1s');
}
function streamReply(reply) {
  const out = new AssistantMessageEventStream();
  out.push({ type: 'start', partial: reply });
  out.push({ type: 'done', reason: reply.stopReason, message: reply }); out.end(); return out;
}
function hanging(options, partial = message([], 'pending')) {
  const out = new AssistantMessageEventStream();
  out.push({ type: 'start', partial });
  const abort = () => {
    const error = { ...partial, stopReason: 'aborted', errorMessage: 'Request was aborted' };
    out.push({ type: 'error', reason: 'aborted', error }); out.end();
  };
  if (options.signal.aborted) abort();
  else options.signal.addEventListener('abort', abort, { once: true });
  return out;
}
async function fixture(t, provider, { waitForNetwork = async () => {}, tools = [], settings = {} } = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'pi-resume-sdk-'));
  const runtime = await sdk.ModelRuntime.create({ authPath: join(dir, 'auth.json'), modelsPath: null,
    refreshOnCreate: false, allowModelNetwork: false });
  // All streaming is replaced below; bypass auth preflight without reading credentials.
  runtime.hasConfiguredAuth = () => true;
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(), waitForNetwork });
  runtime.streamSimple = recovery.wrap(provider);
  const resources = {
    getExtensions: () => ({ extensions: [], errors: [], runtime: sdk.createExtensionRuntime() }),
    getSkills: () => ({ skills: [], diagnostics: [] }), getPrompts: () => ({ prompts: [], diagnostics: [] }),
    getThemes: () => ({ themes: [], diagnostics: [] }), getAgentsFiles: () => ({ agentsFiles: [] }),
    getSystemPrompt: () => 'Isolated synthetic recovery test.', getSystemPromptSource: () => undefined,
    getAppendSystemPrompt: () => [], getAppendSystemPromptSources: () => [],
    extendResources() {}, async reload() {},
  };
  const { session } = await sdk.createAgentSession({ cwd: dir, agentDir: dir, model,
    modelRuntime: runtime, resourceLoader: resources, tools: tools.map(tool => tool.name), customTools: tools,
    sessionManager: sdk.SessionManager.inMemory(dir), settingsManager: sdk.SettingsManager.inMemory({
      compaction: { enabled: false }, cacheWarming: 'off', enableAnalytics: false, enableInstallTelemetry: false,
      httpIdleTimeoutMs: 300000, retry: { enabled: true, maxRetries: 3, baseDelayMs: 1 }, ...settings,
    }) });
  const events = []; session.subscribe(e => events.push(e.type));
  t.after(async () => { await session.abort(); recovery.dispose(); session.dispose(); await rm(dir, { recursive: true, force: true }); });
  return { session, recovery, events };
}

test('actual Pi SDK retries interrupted request only after connectivity returns', { timeout: 5000 }, async t => {
  let calls = 0; let firstSignal; const online = deferred();
  const { session, recovery, events } = await fixture(t, (_m, _c, o) => {
    calls++; if (calls === 1) { firstSignal = o.signal; return hanging(o); }
    return streamReply(message([{ type: 'text', text: 'Recovered' }]));
  }, { waitForNetwork: signal => Promise.race([online.promise, new Promise((_, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }))]) });
  const run = session.prompt('synthetic prompt');
  await until(() => calls === 1);
  const start = performance.now(); recovery.prepareForSleep(true); recovery.prepareForSleep(false);
  await until(() => firstSignal.aborted);
  await delay(30); assert.equal(calls, 1, 'no retry sent while offline');
  online.resolve(); await run;
  assert.equal(calls, 2); assert.equal(session.getLastAssistantText(), 'Recovered');
  assert.ok(events.includes('auto_retry_start')); assert.equal(events.at(-1), 'agent_settled');
  assert.equal(recovery.activeRequests, 0);
  console.log(`wake-to-recovered (synthetic, includes 30ms offline gate): ${Math.round(performance.now() - start)}ms`);
});

test('sleep during a running tool neither cancels nor replays the tool', { timeout: 5000 }, async t => {
  let calls = 0, executions = 0, toolSignal; const finish = deferred();
  const { session, recovery } = await fixture(t, (_m, context) => {
    calls++;
    if (calls === 1) return streamReply(message([{ type: 'toolCall', id: 'test-call', name: 'once', arguments: {} }], 'toolUse'));
    assert.ok(context.messages.some(m => m.role === 'toolResult'));
    return streamReply(message([{ type: 'text', text: 'Tool preserved' }]));
  }, { tools: [{ name: 'once', label: 'Once', description: 'Synthetic tool',
    parameters: { type: 'object', properties: {} },
    execute: async (_id, _args, signal) => { executions++; toolSignal = signal; await finish.promise;
      return { content: [{ type: 'text', text: 'done once' }], details: {} }; } }] });
  const run = session.prompt('synthetic tool prompt'); await until(() => executions === 1);
  assert.equal(recovery.activeRequests, 0);
  recovery.prepareForSleep(true); recovery.prepareForSleep(false);
  assert.equal(toolSignal.aborted, false); finish.resolve(); await run;
  assert.equal(executions, 1); assert.equal(calls, 2); assert.equal(session.getLastAssistantText(), 'Tool preserved');
});

test('manual cancel takes precedence over wake recovery and does not retry', { timeout: 5000 }, async t => {
  let calls = 0;
  const { session, recovery, events } = await fixture(t, (_m, _c, o) => { calls++; return hanging(o); });
  const run = session.prompt('cancel test'); await until(() => calls === 1);
  recovery.prepareForSleep(true); await session.abort(); recovery.prepareForSleep(false); await run;
  assert.equal(calls, 1); assert.ok(!events.includes('auto_retry_start'));
  assert.equal(session.messages.at(-1).stopReason, 'aborted');
});

test('manual cancel while waiting for network stops recovery', { timeout: 5000 }, async t => {
  let calls = 0, waiting = false;
  const { session, recovery } = await fixture(t, (_m, _c, o) => { calls++; return hanging(o); }, {
    waitForNetwork: signal => new Promise((_, reject) => { waiting = true;
      signal.addEventListener('abort', () => reject(signal.reason), { once: true }); }),
  });
  const run = session.prompt('offline cancel'); await until(() => calls === 1);
  recovery.prepareForSleep(true); recovery.prepareForSleep(false); await until(() => waiting);
  await session.abort(); await run; assert.equal(calls, 1); assert.equal(recovery.activeRequests, 0);
});

test('ordinary slow response retains original timeout and is not retried', { timeout: 5000 }, async t => {
  let calls = 0, signal, timeout; const complete = deferred();
  const { session, events } = await fixture(t, (_m, _c, o) => {
    calls++; signal = o.signal; timeout = o.timeoutMs;
    const out = new AssistantMessageEventStream();
    void complete.promise.then(() => { const reply = message([{ type: 'text', text: 'Slow but healthy' }]);
      out.push({ type: 'done', reason: 'stop', message: reply }); out.end(); }); return out;
  });
  const run = session.prompt('slow response'); await until(() => calls === 1); await delay(80);
  assert.equal(signal.aborted, false); assert.equal(timeout, 300000); complete.resolve(); await run;
  assert.equal(calls, 1); assert.ok(!events.includes('auto_retry_start'));
});

test('actual Codex SSE header wait is cancelled without waiting five minutes', { timeout: 5000 }, async () => {
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(), waitForNetwork: async () => {} });
  const claims = Buffer.from(JSON.stringify({ 'https://api.openai.com/auth': { chatgpt_account_id: 'synthetic' } })).toString('base64url');
  let fetchStarted = false, aborted = false;
  const stream = recovery.wrap(codex.stream)(model, { messages: [{ role: 'user', content: 'fake', timestamp: Date.now() }] }, {
    apiKey: `test.${claims}.test`, transport: 'sse', timeoutMs: 300000,
    fetch: async (_url, options) => new Promise((_, reject) => {
      fetchStarted = true; options.signal.addEventListener('abort', () => {
        aborted = true; reject(new DOMException('aborted', 'AbortError'));
      }, { once: true });
    }),
  });
  try {
    await until(() => fetchStarted); recovery.prepareForSleep(true); recovery.prepareForSleep(false);
    const result = await stream.result(); assert.equal(aborted, true);
    assert.equal(result.stopReason, 'error'); assert.ok(isRetryableAssistantError(result));
    assert.match(result.errorMessage, /system sleep/);
  } finally { recovery.dispose(); }
});

test('actual Codex SSE cancellation feeds actual Pi SDK auto-retry end to end', { timeout: 5000 }, async t => {
  let calls = 0;
  const claims = Buffer.from(JSON.stringify({ 'https://api.openai.com/auth': { chatgpt_account_id: 'synthetic' } })).toString('base64url');
  const { session, recovery, events } = await fixture(t, (m, context, options) => codex.stream(m, context, {
    ...options, apiKey: `test.${claims}.test`, transport: 'sse',
    fetch: async (_url, request) => {
      calls++;
      if (calls === 1) return new Promise((_, reject) => request.signal.addEventListener('abort', () => {
        reject(new DOMException('aborted', 'AbortError'));
      }, { once: true }));
      const completed = { type: 'response.completed', response: { id: 'synthetic-response', status: 'completed', output: [],
        usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 } } };
      return new Response(`data: ${JSON.stringify(completed)}\n\n`, { headers: { 'content-type': 'text/event-stream' } });
    },
  }));
  const run = session.prompt('synthetic end-to-end SSE'); await until(() => calls === 1);
  recovery.prepareForSleep(true); recovery.prepareForSleep(false); await run;
  assert.equal(calls, 2); assert.ok(events.includes('auto_retry_start'));
  assert.equal(session.messages.at(-1).stopReason, 'stop'); assert.equal(events.at(-1), 'agent_settled');
});

test('actual Codex WebSocket stream is cancelled and its socket discarded on wake', { timeout: 5000 }, async () => {
  const original = globalThis.WebSocket;
  let socket, sent = false;
  class FakeWebSocket extends EventTarget {
    readyState = 0;
    constructor() { super(); socket = this; queueMicrotask(() => {
      this.readyState = 1; this.dispatchEvent(new Event('open'));
    }); }
    send() { sent = true; this.dispatchEvent(new MessageEvent('message', {
      data: JSON.stringify({ type: 'response.created', response: { id: 'synthetic-response' } }),
    })); }
    close() { this.readyState = 3; this.dispatchEvent(new Event('close')); }
  }
  globalThis.WebSocket = FakeWebSocket;
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(), waitForNetwork: async () => {} });
  const claims = Buffer.from(JSON.stringify({ 'https://api.openai.com/auth': { chatgpt_account_id: 'synthetic' } })).toString('base64url');
  try {
    const stream = recovery.wrap(codex.stream)(model, { messages: [{ role: 'user', content: 'fake', timestamp: Date.now() }] }, {
      apiKey: `test.${claims}.test`, transport: 'websocket', timeoutMs: 300000, cacheRetention: 'none',
    });
    await until(() => sent); recovery.prepareForSleep(true); recovery.prepareForSleep(false);
    const result = await stream.result();
    assert.equal(socket.readyState, 3); assert.equal(result.stopReason, 'error');
    assert.ok(isRetryableAssistantError(result)); assert.match(result.errorMessage, /system sleep/);
  } finally { recovery.dispose(); globalThis.WebSocket = original; }
});

test('a partial tool call in an interrupted response is never executed', { timeout: 5000 }, async t => {
  let calls = 0, executions = 0;
  const { session, recovery } = await fixture(t, (_m, _c, o) => {
    calls++;
    if (calls === 1) return hanging(o, message([{ type: 'toolCall', id: 'unfinished', name: 'once', arguments: {} }], 'pending'));
    return streamReply(message([{ type: 'text', text: 'Recovered without executing partial tool' }]));
  }, { tools: [{ name: 'once', label: 'Once', description: 'Synthetic tool', parameters: { type: 'object', properties: {} },
    execute: async () => { executions++; return { content: [], details: {} }; } }] });
  const run = session.prompt('partial tool'); await until(() => calls === 1);
  recovery.prepareForSleep(true); recovery.prepareForSleep(false); await run;
  assert.equal(executions, 0); assert.equal(calls, 2);
});

test('new sleep cycle invalidates an older connectivity check', async () => {
  const checks = []; let calls = 0;
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(),
    waitForNetwork: () => { const next = deferred(); checks.push(next); return next.promise; } });
  try {
    const wrapped = recovery.wrap(() => { calls++; return streamReply(message()); });
    recovery.prepareForSleep(true); recovery.prepareForSleep(false);
    const pending = wrapped(model, { messages: [] }); await until(() => checks.length === 1);
    recovery.prepareForSleep(true); recovery.prepareForSleep(false); checks[0].resolve();
    await until(() => checks.length === 2); assert.equal(calls, 0);
    checks[1].resolve(); await pending.result(); assert.equal(calls, 1);
  } finally { recovery.dispose(); }
});

test('parallel provider requests are invalidated independently without aborting their parents', async () => {
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(), waitForNetwork: async () => {} });
  const parents = [new AbortController(), new AbortController()];
  const wrapped = recovery.wrap((_m, _c, options) => hanging(options));
  try {
    const streams = parents.map(parent => wrapped(model, { messages: [] }, { signal: parent.signal }));
    await until(() => recovery.activeRequests === 2);
    recovery.prepareForSleep(true); recovery.prepareForSleep(false);
    const results = await Promise.all(streams.map(stream => stream.result()));
    assert.ok(results.every(isRetryableAssistantError)); assert.ok(parents.every(parent => !parent.signal.aborted));
    await until(() => recovery.activeRequests === 0);
  } finally { recovery.dispose(); }
});

test('duplicate wake notifications and idle wake do not create model requests', async () => {
  let calls = 0;
  const recovery = createResumeRecovery({ createStream: () => new AssistantMessageEventStream(), waitForNetwork: async () => {} });
  const wrapped = recovery.wrap(() => { calls++; return streamReply(message()); });
  recovery.prepareForSleep(false); recovery.prepareForSleep(true); recovery.prepareForSleep(false);
  recovery.prepareForSleep(false); assert.equal(calls, 0);
  await wrapped(model, { messages: [] }).result(); assert.equal(calls, 1); recovery.dispose();
});
