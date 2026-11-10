const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const root = path.join(__dirname, '../home/packages/tablet-proof/media');
const source = fs.readFileSync(path.join(root, 'background.js'), 'utf8');
const helper = fs.readFileSync(path.join(root, 'media.js'), 'utf8');
const event = () => { const listeners = new Set(); return {listeners, addListener: f => listeners.add(f), removeListener: f => listeners.delete(f)}; };

function fixture() {
  class Media { constructor() { this.paused = false; this.ended = false; } pause() { this.paused = true; } }
  const media = new Map([[101, new Media()], [202, new Media()]]);
  const tabs = [{id: 101, windowId: 7, url: 'https://video.example.test/fixture', audible: true},
                {id: 202, windowId: 8, url: 'https://news.example.test/other', audible: true}];
  const shadows = new Map();
  const renderers = new Map();
  const executed = []; const failedInjection = new Set();
  const runtimeMessages = event();
  const attached = event();
  const detached = event();
  const chrome = {
    storage: {session: {get: async () => ({}), set: async () => {}}},
    runtime: {id: 'fixture-extension', getURL: p => 'chrome-extension://fixture-extension/'+p,
      connectNative: () => ({onMessage: event(), onDisconnect: event(), postMessage() {}}), onMessage: runtimeMessages},
    action: {onClicked: event(), setBadgeText: async () => {}},
    windows: {get: async id => ({id, type: 'normal', incognito: false}), onRemoved: event()},
    tabs: {
      onAttached: attached, onDetached: detached,
      query: async query => tabs.filter(t => query.url ? t.url === query.url : t.windowId === query.windowId).map(t => ({...t})),
      get: async id => ({...tabs.find(t => t.id === id)}),
      sendMessage: async (id, message) => {
        const renderer = renderers.get(id);
        if (!renderer) throw new Error('No receiver');
        return new Promise(resolve => { for (const fn of renderer.messages.listeners) fn(message, {id: chrome.runtime.id}, resolve); });
      }
    },
    scripting: {executeScript: async ({target, files}) => {
      executed.push(target.tabId); assert.equal(target.allFrames, true); assert.deepEqual([...files], ['media.js']);
      if (failedInjection.has(target.tabId)) throw new Error('Cannot access protected page');
      let renderer = renderers.get(target.tabId);
      if (!renderer) {
        const messages = event(); const play = event();
        const context = vm.createContext({HTMLMediaElement: Media,
          document: {querySelectorAll: selector => selector === '*'
              ? (shadows.get(target.tabId) || []).map(root => ({shadowRoot: root}))
              : media.has(target.tabId) ? [media.get(target.tabId)] : [],
            addEventListener: (_, f) => play.addListener(f), removeEventListener: (_, f) => play.removeListener(f)},
          chrome: {runtime: {id: chrome.runtime.id, onMessage: messages,
            sendMessage: message => new Promise(resolve => {
              const tab = tabs.find(t => t.id === target.tabId);
              for (const fn of runtimeMessages.listeners) fn(message, {tab: {...tab}, frameId: 0, url: tab.url}, resolve);
            })}}});
        renderer = {context, messages, play}; renderers.set(target.tabId, renderer);
      }
      return [{frameId: 0, result: await vm.runInContext(helper, renderer.context)}];
    }}
  };
  const context = vm.createContext({URL, setTimeout, clearTimeout, console, chrome});
  vm.runInContext(source, context);
  return {media, tabs, renderers, executed, failedInjection, run: code => vm.runInContext(code, context),
    addShadow(id) {
      const element = new Media(); const play = event();
      const root = {element, play, querySelectorAll: selector => selector === '*' ? [] : [element],
        addEventListener: (_, f) => play.addListener(f), removeEventListener: (_, f) => play.removeListener(f)};
      shadows.set(id, [...shadows.get(id) || [], root]);
      return root;
    },
    async playShadow(root) {
      root.element.paused = false;
      await Promise.all([...root.play.listeners].map(fn => fn({target: root.element})));
    },
    async move(id, windowId) {
      for (const fn of detached.listeners) await fn(id, {});
      tabs.find(t => t.id === id).windowId = windowId;
      for (const fn of attached.listeners) await fn(id, {newWindowId: windowId});
    },
    async play(id) {
      const element = media.get(id); element.paused = false;
      await Promise.all([...renderers.get(id)?.play.listeners || []].map(fn => fn({target: element})));
    }};
}

test('already-loaded documents receive a verified gate and only tablet media pauses', async () => {
  const f = fixture();
  assert.equal(f.renderers.size, 0); // No declarative helper exists in these documents.
  const result = await f.run('handleHost({op: "pause", windowId: 7})');
  assert.equal(result.elements, 1); assert.equal(result.playing, 0);
  assert.equal(f.media.get(101).paused, true);
  assert.equal(f.media.get(202).paused, false);
  assert.deepEqual(f.executed, [101]);
  await f.play(101); assert.equal(f.media.get(101).paused, true);
  await f.play(202); assert.equal(f.media.get(202).paused, false);
});

test('returning unblocks without auto-play and repeated injection is idempotent', async () => {
  const f = fixture();
  await f.run('handleHost({op: "pause", windowId: 7})');
  await f.run('handleHost({op: "pause", windowId: 7})');
  await f.run('handleHost({op: "resume", windowId: 7})');
  assert.equal(f.media.get(101).paused, true);
  assert.equal(f.media.get(202).paused, false);
  assert.equal(f.renderers.get(101).play.listeners.size, 1);
  assert.equal(f.renderers.get(101).messages.listeners.size, 1);
  await f.play(101); assert.equal(f.media.get(101).paused, false);
});

test('moving a blocked tab to a laptop window releases its gate without auto-play', async () => {
  const f = fixture();
  await f.run('handleHost({op: "pause", windowId: 7})');
  await f.move(101, 8);
  assert.equal(f.media.get(101).paused, true);
  await f.play(101); assert.equal(f.media.get(101).paused, false);
  await f.run('handleHost({op: "resume", windowId: 7})');
  assert.equal(f.media.get(101).paused, false);
});

test('moving an unblocked tab into suspended tablet window installs its gate', async () => {
  const f = fixture();
  await f.run('handleHost({op: "pause", windowId: 7})');
  await f.move(202, 7);
  assert.equal(f.media.get(202).paused, true);
  await f.play(202); assert.equal(f.media.get(202).paused, true);
});

test('play checks current sender window even before tab-move notifications arrive', async () => {
  const f = fixture();
  await f.run('handleHost({op: "pause", windowId: 7})');
  f.tabs.find(tab => tab.id === 101).windowId = 8;
  await f.play(101); assert.equal(f.media.get(101).paused, false);
  f.tabs.find(tab => tab.id === 101).windowId = 7;
  await f.play(101); assert.equal(f.media.get(101).paused, true);
});

test('HTTP and HTTPS media tabs in tablet window pause together across sites', async () => {
  const f = fixture();
  f.tabs.push({id: 303, windowId: 7, url: 'http://radio.example.test/stream', audible: true});
  f.media.set(303, {paused: false, ended: false, pause() { this.paused = true; }});
  const result = await f.run('handleHost({op: "pause", windowId: 7})');
  assert.equal(result.elements, 2);
  assert.equal(f.media.get(101).paused, true);
  assert.equal(f.media.get(303).paused, true);
  assert.equal(f.media.get(202).paused, false);
});

test('open shadow-root media is paused and gated without accumulating listeners', async () => {
  const f = fixture();
  const shadow = f.addShadow(101);
  const result = await f.run('handleHost({op: "pause", windowId: 7})');
  assert.equal(result.elements, 2);
  assert.equal(shadow.element.paused, true);
  await f.playShadow(shadow); assert.equal(shadow.element.paused, true);
  await f.run('handleHost({op: "pause", windowId: 7})');
  assert.equal(shadow.play.listeners.size, 1);
  await f.run('handleHost({op: "resume", windowId: 7})');
  assert.equal(shadow.element.paused, true);
  await f.playShadow(shadow); assert.equal(shadow.element.paused, false);
  assert.equal(f.media.get(202).paused, false);
});

test('one rejected injection does not skip later tablet players or fake a complete ACK', async () => {
  const f = fixture(); f.tabs[0].audible = false; f.failedInjection.add(101);
  f.tabs.push({id: 303, windowId: 7, url: 'http://radio.example.test/stream', audible: true});
  f.media.set(303, {paused: false, ended: false, pause() { this.paused = true; }});
  await assert.rejects(f.run('handleHost({op: "pause", windowId: 7})'), /could not be verified/);
  assert.equal(f.media.get(303).paused, true);
  assert.equal(f.media.get(202).paused, false);
});

test('audible HTTP player with no reachable media fails rather than claiming pause', async () => {
  const f = fixture(); f.media.delete(101);
  await assert.rejects(f.run('handleHost({op: "pause", windowId: 7})'), /could not be paused/);
  assert.equal(f.media.get(202).paused, false);
});

test('unsupported audible tab is an explicit failure, not a fake guarantee', async () => {
  const f = fixture();
  f.tabs.push({id: 303, windowId: 7, audible: true});
  await assert.rejects(f.run('handleHost({op: "pause", windowId: 7})'), /could not be paused/);
  assert.equal(f.media.get(202).paused, false);
});

test('registration must still be in intended unique window', async () => {
  const f = fixture();
  await assert.rejects(f.run('handleHost({op: "verify", windowId: 8, tabId: 101, url: "https://video.example.test/fixture"})'), /moved|ambiguous/);
});

test('all HTTP(S) sites are permitted, not local files or internal browser pages', () => {
  const f = fixture();
  for (const url of ['https://youtube.com/', 'https://podcast.example.test/', 'http://radio.example.test/', 'http://127.0.0.1:1234/'])
    assert.equal(f.run(`permitted({url:${JSON.stringify(url)}})`), true);
  for (const url of ['file:///private.html', 'vivaldi://extensions', 'chrome://settings', 'chrome-extension://id/pair.html', 'data:text/html,fixture', 'not a url'])
    assert.equal(f.run(`permitted({url:${JSON.stringify(url)}})`), false);
});

test('production manifest grants only HTTP(S) hosts, not privileged data APIs', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'manifest.json')));
  for (const permission of ['tabs', 'history', 'debugger', 'cookies', 'webRequest']) assert.ok(!manifest.permissions.includes(permission));
  assert.ok(!JSON.stringify(manifest).includes('<all_urls>'));
  assert.deepEqual(manifest.host_permissions, ['http://*/*', 'https://*/*']);
  assert.equal(manifest.content_scripts[1].all_frames, true);
  assert.equal(manifest.content_scripts[1].match_origin_as_fallback, true);
});
