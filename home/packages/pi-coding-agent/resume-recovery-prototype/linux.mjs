// Native interfaces only; no network probes, shell commands, or elevated privileges.
import { spawn, execFile } from 'node:child_process';
import { createInterface } from 'node:readline';
import { promisify } from 'node:util';
import { setTimeout as delay } from 'node:timers/promises';
const run = promisify(execFile);
const match = "type='signal',sender='org.freedesktop.login1',interface='org.freedesktop.login1.Manager',member='PrepareForSleep',path='/org/freedesktop/login1'";

export function sleepSignalParser(onSleep) {
  let awaitingBoolean = false;
  return line => {
    if (line.startsWith('signal ')) {
      awaitingBoolean = /path=\/org\/freedesktop\/login1;/.test(line) &&
        /interface=org\.freedesktop\.login1\.Manager; member=PrepareForSleep\s*$/.test(line);
    } else if (awaitingBoolean) {
      awaitingBoolean = false;
      const value = /^\s+boolean (true|false)\s*$/.exec(line);
      if (value) onSleep(value[1] === 'true');
    }
  };
}

export function watchSleep(onSleep, { onFailure = () => {}, spawnProcess = spawn } = {}) {
  // busctl monitor is denied by this host's policy. dbus-monitor falls back to
  // ordinary signal subscription (AddMatch), which is permitted without root.
  const child = spawnProcess('dbus-monitor', ['--system', match], { stdio: ['ignore', 'pipe', 'pipe'] });
  const lines = createInterface({ input: child.stdout });
  const parse = sleepSignalParser(onSleep);
  let stopped = false;
  lines.on('line', parse);
  child.stderr.resume(); // Avoid blocked pipes; don't copy bus data to logs.
  child.on('error', () => { if (!stopped) onFailure('sleep watcher could not start'); });
  child.on('exit', () => { if (!stopped) onFailure('sleep watcher exited'); });
  return {
    child,
    dispose() { if (stopped) return; stopped = true; lines.close(); child.kill(); },
  };
}

export async function waitForNetwork(signal, { query = run, pollMs = 250 } = {}) {
  for (;;) {
    signal.throwIfAborted();
    let stdout;
    try {
      ({ stdout } = await query('busctl', ['--system', '--json=short', 'get-property',
        'org.freedesktop.NetworkManager', '/org/freedesktop/NetworkManager',
        'org.freedesktop.NetworkManager', 'State'], { signal, timeout: 3000, maxBuffer: 4096 }));
    } catch (error) {
      signal.throwIfAborted();
      // NetworkManager/the bus can briefly disappear during resume. Do not
      // consume Pi's model retry budget before there is even a usable route.
      const transient = error.code === 'ETIMEDOUT' || (error.killed && error.signal === 'SIGTERM') ||
        /ServiceUnknown|NameHasNoOwner|NoReply|Disconnected|name .* was not provided by any \.service files|connection (?:was )?(?:closed|reset)|timed out/i.test(`${error.message ?? ''}\n${error.stderr ?? ''}`);
      if (!transient) throw error; // Missing executable/permissions/config need attention.
      await delay(pollMs, undefined, { signal });
      continue;
    }
    const state = JSON.parse(stdout);
    // CONNECTED_LOCAL (50) doesn't imply a usable route; require SITE or GLOBAL.
    // This is a routing hint, NOT proof the model endpoint is reachable. Native
    // provider error/retry handling remains authoritative after the gate opens.
    if (state.type !== 'u' || !Number.isInteger(state.data)) throw new Error('Invalid NetworkManager state');
    if (state.data >= 60) return;
    await delay(pollMs, undefined, { signal });
  }
}
