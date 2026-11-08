// Real packaged SDK, synthetic OAuth and mocked HTTP. No live accounts/network.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { run } from '../model.mjs';
import { zstdDecompressSync } from 'node:zlib';

function successfulStream() {
  const text = JSON.stringify({ideas: [], summary: 'No new candidates.'});
  const item = {id: 'msg_synthetic', type: 'message', role: 'assistant',
    content: [{type: 'output_text', text, annotations: []}]};
  const events = [
    {type: 'response.created', response: {id: 'resp_synthetic', model: 'gpt-6-luna'}},
    {type: 'response.output_item.added', output_index: 0, item: {...item, content: []}},
    {type: 'response.content_part.added', output_index: 0, content_index: 0,
      item_id: item.id, part: {type: 'output_text', text: '', annotations: []}},
    {type: 'response.output_text.delta', output_index: 0, content_index: 0, item_id: item.id, delta: text},
    {type: 'response.output_item.done', output_index: 0, item},
    {type: 'response.completed', response: {id: 'resp_synthetic', status: 'completed',
      output: [item], usage: {input_tokens: 100, output_tokens: 10,
        input_tokens_details: {cached_tokens: 0}, output_tokens_details: {reasoning_tokens: 0}}}},
  ];
  return events.map(event => `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`).join('');
}

for (const status of [503, 200]) test(`real SDK HTTP ${status}: one bounded request and persisted transcript`,
  {skip: !process.env.PI_WEEKLY_SDK}, async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'weekly-sdk-'));
  const oldFetch = globalThis.fetch;
  const oldAgent = process.env.PI_CODING_AGENT_DIR;
  const oldOffline = process.env.PI_OFFLINE;
  let calls = 0;
  try {
    process.env.PI_CODING_AGENT_DIR = root;
    process.env.PI_OFFLINE = '1';
    const claims = Buffer.from(JSON.stringify({'https://api.openai.com/auth': {chatgpt_account_id: 'synthetic-account'}})).toString('base64url');
    fs.writeFileSync(path.join(root, 'auth.json'), JSON.stringify({'openai-codex': {
      type: 'oauth', access: `synthetic.${claims}.synthetic`, refresh: 'synthetic-refresh', expires: Date.now() + 3600000,
    }}), {mode: 0o600});
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.match(String(url), /^https:\/\/chatgpt\.com\/backend-api\//);
      const bytes = typeof options.body === 'string' ? null : Buffer.from(options.body);
      const body = JSON.parse(bytes ? (bytes[0] === 0x28 ? zstdDecompressSync(bytes) : bytes).toString('utf8') : options.body);
      assert.equal(body.model, 'gpt-6-luna');
      assert.equal(body.tools?.length ?? 0, 0);
      return status === 200 ? new Response(successfulStream(), {status: 200, headers: {'Content-Type': 'text/event-stream'}})
        : new Response('synthetic transport failure', {status});
    };
    const sdk = await import(pathToFileURL(process.env.PI_WEEKLY_SDK).href);
    const invocation = run({agentDir: root, stateRoot: root, sessionRoot: path.join(root, 'sessions'),
      model: 'gpt-6-luna'}, {week: 'synthetic', sources: [], catalogue: []}, sdk);
    if (status === 503) await assert.rejects(invocation, /incomplete_model_reply/);
    else {
      const result = await invocation;
      assert.equal(result.calls, 1, 'actual SDK streamFunction wrapper was invoked');
      assert.equal(JSON.parse(result.text).summary, 'No new candidates.');
      assert.equal(result.usage.input, 100);
    }
    assert.equal(calls, 1, 'no provider retry, cache warming or transport fallback');
    const sessions = fs.readdirSync(path.join(root, 'sessions')).filter(f => f.endsWith('.jsonl'));
    assert.equal(sessions.length, 1);
    const rows = fs.readFileSync(path.join(root, 'sessions', sessions[0]), 'utf8').trim().split('\n').map(JSON.parse);
    assert.ok(rows.some(row => row.type === 'session_info' && row.name.includes('Agent Techniques weekly')));
    assert.ok(rows.some(row => row.message?.role === 'assistant' && row.message.stopReason === (status === 200 ? 'stop' : 'error')));
  } finally {
    globalThis.fetch = oldFetch;
    if (oldAgent === undefined) delete process.env.PI_CODING_AGENT_DIR; else process.env.PI_CODING_AGENT_DIR = oldAgent;
    if (oldOffline === undefined) delete process.env.PI_OFFLINE; else process.env.PI_OFFLINE = oldOffline;
    fs.rmSync(root, {recursive: true, force: true});
  }
});
