const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const alpha = '11111111-1111-4111-8111-111111111111';
const beta = '22222222-2222-4222-8222-222222222222';
const key = '33333333-3333-4333-8333-333333333333';
const sessionName = `po-${alpha}-${key}-0`;
const adapterInstance = crypto.randomUUID();
const owned = project => JSON.stringify({projectObjectProjectId: project, projectObjectWindowKey: key});
function fixture(window) {
  let callback;
  const replies = [];
  const mutations = [];
  const port = {onMessage: {addListener: fn => {callback = fn;}},
    onDisconnect: {addListener() {}}, postMessage: value => replies.push(value)};
  const chrome = {
    runtime: {connect: () => port},
    windows: {
      get: async () => structuredClone(window),
      getAll: async () => [structuredClone(window)],
      update: async (_id, change) => {mutations.push(change); Object.assign(window, change);},
      remove: async () => {throw Error('injected close failure');},
    },
    tabs: {
      update: async (id, change) => {mutations.push(change); Object.assign(window.tabs.find(t => t.id === id), change);},
      remove: async id => {mutations.push({remove: id}); window.tabs = window.tabs.filter(t => t.id !== id);},
    },
  };
  const vivaldi = {tabsPrivate: {hasBeforeUnloadOrUnload: async () => false},
    sessionsPrivate: {
      getAll: async () => ({items: [{id: 1, name: sessionName}]}),
      open: async () => {mutations.push({open: true}); throw Error('unexpected native replay');},
    }};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/browser/adapter.js'), 'utf8'),
    {chrome, vivaldi, crypto: {...crypto, randomUUID: () => adapterInstance}, setTimeout, clearTimeout, setInterval, clearInterval});
  return {mutations, async request(request) {
    await callback({id: 'a'.repeat(32), request: {expectedIdentity: {instance: adapterInstance}, ...request}});
    return replies.at(-1).response;
  }};
}
(async () => {
  for (const windowTag of ['', owned(alpha)]) {
    const window = {id: 1, type: 'normal', incognito: false, vivExtData: windowTag,
      tabs: [{id: 2, url: 'https://alpha.invalid', pinned: false, vivExtData: owned(alpha)},
             {id: 3, url: 'https://beta.invalid', pinned: false, vivExtData: owned(beta)}]};
    const test = fixture(window);
    const response = await test.request({op: 'tag', windowId: 1, projectId: alpha, windowKey: key});
    assert.equal(response.ok, false);
    assert.match(response.error, /another project/);
    assert.equal(test.mutations.length, 0, 'ownership rejection must precede every mutation');
  }
  const window = {id: 1, type: 'normal', incognito: false, vivExtData: owned(alpha),
    tabs: [{id: 2, url: 'https://alpha.invalid/pin', pinned: true, vivExtData: owned(alpha)},
           {id: 3, url: 'https://alpha.invalid/rest', pinned: false, vivExtData: owned(alpha)}]};
  const test = fixture(window);
  const inventory = await test.request({op: 'inventory'});
  const close = await test.request({op: 'close', windows: inventory.value});
  assert.equal(close.ok, false);
  assert.match(close.error, /injected close failure/);
  assert.deepEqual(window.tabs.map(t => t.id), [3], 'failure injection exercises genuinely partial removal');
  for (const windowTag of [owned(alpha), '']) {
    const late = fixture({id: 1, type: 'normal', incognito: false, vivExtData: windowTag,
      tabs: [{id: 2, url: 'https://alpha.invalid', pinned: false, vivExtData: owned(alpha)}]});
    const response = await late.request({op: 'restore', name: sessionName, projectId: alpha, windowKey: key});
    assert.equal(response.ok, false);
    assert.match(response.error, /recovery changed before replay/);
    assert.equal(late.mutations.length, 0, 'late recovered key must not be replayed');
  }
  const changed = await test.request({op: 'restore', name: sessionName, projectId: alpha, windowKey: key,
    expectedIdentity: {instance: crypto.randomUUID()}});
  assert.equal(changed.ok, false);
  assert.match(changed.error, /Browser changed before replay/);
  const invalid = await test.request({op: 'restore', name: sessionName});
  assert.equal(invalid.ok, false);
  assert.match(invalid.error, /Invalid recovery identity/);
  console.log('PASS conflicting provenance, partial pin-removal failure, and late-key replay rejection');
})().catch(error => {console.error(error); process.exitCode = 1;});
