import { test } from 'node:test';
import assert from 'node:assert/strict';
import { run, instruction } from '../model.mjs';

function fixture({subscription = true, reason = 'stop'} = {}) {
  let options, streamOptions, disposed = false, requests = 0;
  const model = {provider: 'openai-codex', id: 'test-model'};
  const session = {
    agent: {streamFunction: (_model, _context, opts) => { streamOptions = opts; requests++; }},
    setSessionName(name) { assert.match(name, /Agent Techniques weekly/); },
    messages: [], sessionFile: '/synthetic/pi-session.jsonl',
    subscribe() {}, abort: async () => {},
    async prompt() {
      await this.agent.streamFunction(model, {}, {});
      this.messages.push({role: 'assistant', stopReason: reason, provider: 'openai-codex',
        model: 'test-model', content: [{type: 'text', text: '{}'}], usage: {input: 10, output: 5}});
    },
    getLastAssistantText: () => '{}',
    dispose() { disposed = true; },
  };
  const sdk = {
    ModelRuntime: {create: async opts => {
      assert.equal(opts.modelsPath, null); assert.equal(opts.allowModelNetwork, false); assert.equal(opts.refreshOnCreate, true);
      return {getModel: () => model, isUsingSubscription: () => subscription};
    }},
    createAgentSession: async opts => { options = opts; return {session}; },
    createExtensionRuntime: () => ({}),
    SettingsManager: {inMemory: settings => settings},
    SessionManager: {create: (cwd, path) => ({cwd, path})},
  };
  return {sdk, session, state: () => ({options, streamOptions, disposed, requests})};
}
const config = {agentDir: '/synthetic/agent', stateRoot: '/synthetic/state', sessionRoot: '/synthetic/sessions', model: 'test-model'};

test('one persisted no-tools session with in-memory limits and bounded output', async () => {
  const f = fixture();
  const result = await run(config, {week: '2026-11-08'}, f.sdk);
  const {options, streamOptions, requests, disposed} = f.state();
  assert.equal(result.calls, 1); assert.equal(requests, 1); assert.equal(disposed, true);
  assert.equal(result.session_file, '/synthetic/pi-session.jsonl');
  assert.deepEqual(options.tools, []); assert.equal(options.noTools, true);
  assert.deepEqual(options.settingsManager, {retry: {enabled: false, provider: {maxRetries: 0}},
    compaction: {enabled: false}, cacheWarming: 'off', transport: 'sse'});
  assert.equal(options.sessionManager.path, config.sessionRoot);
  assert.equal(options.thinkingLevel, 'low'); assert.equal(streamOptions.maxTokens, 4096);
  assert.equal(streamOptions.maxRetries, 0); assert.equal(streamOptions.transport, 'sse');
  assert.deepEqual(options.resourceLoader.getAgentsFiles(), {agentsFiles: []});
  assert.deepEqual(options.resourceLoader.getSkills().skills, []);
  assert.match(instruction, /untrusted data/);
});
test('no paid-key fallback', async () => {
  const f = fixture({subscription: false});
  await assert.rejects(run(config, {week: 'x'}, f.sdk), /subscription_unavailable/);
  assert.equal(f.state().requests, 0);
});
test('incomplete response fails and disposes', async () => {
  const f = fixture({reason: 'length'});
  await assert.rejects(run(config, {week: 'x'}, f.sdk), /incomplete_model_reply/);
  assert.equal(f.state().disposed, true);
});
test('second model call refused', async () => {
  const f = fixture();
  f.session.prompt = async function () {
    this.agent.streamFunction({}, {}, {});
    this.agent.streamFunction({}, {}, {});
  };
  await assert.rejects(run(config, {week: 'x'}, f.sdk), /call_budget_exceeded/);
  assert.equal(f.state().requests, 1);
});
