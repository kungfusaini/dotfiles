import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';
import { EventEmitter } from 'node:events';
import { sleepSignalParser, watchSleep, waitForNetwork } from './linux.mjs';

const header = 'signal time=1 sender=:1.2 -> destination=(null destination) serial=1 path=/org/freedesktop/login1; interface=org.freedesktop.login1.Manager; member=PrepareForSleep';
test('sleep parser accepts only a matching signal followed by its boolean', () => {
  const values = []; const parse = sleepSignalParser(value => values.push(value));
  parse('   boolean false'); parse(header); parse('   boolean true'); parse('   boolean false');
  parse(header.replace('PrepareForSleep', 'PrepareForShutdown')); parse('   boolean false');
  parse(header.replace('/org/freedesktop/login1;', '/unrelated;')); parse('   boolean false');
  parse(header); parse('  string "false"'); parse(header); parse('   boolean false');
  assert.deepEqual(values, [true, false]);
});
test('watcher is filtered, reports failures and has idempotent cleanup', () => {
  const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
  let kills = 0, failures = 0; const values = []; child.kill = () => { kills++; };
  const watcher = watchSleep(v => values.push(v), {
    onFailure: () => failures++, spawnProcess: (command, args) => {
      assert.equal(command, 'dbus-monitor'); assert.equal(args[0], '--system');
      assert.match(args[1], /sender='org.freedesktop.login1'/); return child;
    },
  });
  child.stdout.write(`${header}\n   boolean true\n${header}\n   boolean false\n`);
  assert.deepEqual(values, [true, false]); child.emit('exit', 1); assert.equal(failures, 1);
  watcher.dispose(); watcher.dispose(); assert.equal(kills, 1); child.emit('exit', 0); assert.equal(failures, 1);
});
test('network gate tolerates transient service restart but exposes permanent failures', async () => {
  let calls = 0;
  await waitForNetwork(new AbortController().signal, { pollMs: 1, query: async () => {
    calls++;
    if (calls === 1) throw new Error('The name org.freedesktop.NetworkManager was not provided by any .service files');
    if (calls === 2) throw Object.assign(new Error('Command timed out'), { killed: true, signal: 'SIGTERM' });
    return { stdout: '{"type":"u","data":70}' };
  } });
  assert.equal(calls, 3);
  await assert.rejects(waitForNetwork(new AbortController().signal, { query: async () => {
    throw Object.assign(new Error('spawn busctl ENOENT'), { code: 'ENOENT' });
  } }), { code: 'ENOENT' });
  await assert.rejects(waitForNetwork(new AbortController().signal, { query: async () => {
    throw new Error('Access denied');
  } }), /Access denied/);
});

test('network gate waits for routing and honors cancellation', async () => {
  const states = [20, 40, 50, 60]; let calls = 0;
  await waitForNetwork(new AbortController().signal, { pollMs: 1, query: async (command, args, options) => {
    assert.equal(command, 'busctl'); assert.equal(options.timeout, 3000);
    assert.ok(args.includes('State')); calls++; return { stdout: JSON.stringify({ type: 'u', data: states.shift() }) };
  } });
  assert.equal(calls, 4);
  const controller = new AbortController();
  const pending = waitForNetwork(controller.signal, { pollMs: 1000,
    query: async () => ({ stdout: '{"type":"u","data":20}' }) });
  controller.abort(); await assert.rejects(pending, { name: 'AbortError' });
});
