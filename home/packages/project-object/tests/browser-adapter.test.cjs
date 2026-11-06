const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');

const alpha = '11111111-1111-4111-8111-111111111111';
const beta = '22222222-2222-4222-8222-222222222222';
const key = '33333333-3333-4333-8333-333333333333';
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
  const vivaldi = {tabsPrivate: {hasBeforeUnloadOrUnload: async () => false}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/browser/adapter.js'), 'utf8'),
    {chrome, vivaldi, crypto, setTimeout, clearTimeout, setInterval, clearInterval});
  return {mutations, async request(request) {
    await callback({id: 'a'.repeat(32), request});
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
  console.log('PASS conflicting provenance is immutable; partial pin-removal failure is reported');
})().catch(error => {console.error(error); process.exitCode = 1;});
