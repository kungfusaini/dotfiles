// Local-only comparative probe; modules are explicit packaged/test dependencies.
import {pathToFileURL} from 'node:url';
const [backend, modulePath, endpoint, origin] = process.argv.slice(2);
const lib = await import(pathToFileURL(modulePath).href);
let browser;
async function attach() {
  browser = backend === 'playwright'
    ? await lib.chromium.connectOverCDP(endpoint, {timeout: 10000, noDefaults: true})
    : await lib.default.connect({browserWSEndpoint: endpoint, defaultViewport: null, protocolTimeout: 10000});
  const deadline = Date.now() + 5000;
  while (true) {
    const pages = backend === 'playwright' ? browser.contexts().flatMap(c => c.pages()) : await browser.pages();
    const task = pages.filter(p => p.url().startsWith(origin + '/'));
    if (task.length > 1) throw Error('Ambiguous synthetic task');
    if (task.length === 1) {
      task[0].setDefaultTimeout(5000);
      return task[0];
    }
    if (Date.now() >= deadline) throw Error('Missing synthetic task');
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}
async function detach() {
  if (!browser) return;
  if (backend === 'playwright') await browser.close(); // Attached CDP: disconnect, not owned launch.
  else browser.disconnect();
  browser = undefined;
}
try {
  const page = await attach();
  const version = await browser.version();
  const userAgent = await page.evaluate(() => navigator.userAgent);
  const reopen = process.env.PI_PROBE_REOPEN === '1';
  if (reopen && await page.evaluate(() => localStorage.getItem('backend-probe')) !== 'synthetic-retained')
    throw Error('Fixture state did not survive browser restart');
  let extensionChecked = false;
  if (backend === 'playwright' && process.env.PI_PROBE_EXTENSION === '1') {
    const context = page.context();
    const prefix = 'chrome-extension://nngceckbapebfimnlniiiahkandclblb/';
    const worker = context.serviceWorkers().find(w => w.url().startsWith(prefix))
      ?? await context.waitForEvent('serviceworker', {predicate: w => w.url().startsWith(prefix), timeout: 5000});
    const previous = await worker.evaluate(() => chrome.storage.local.get('piBackendSynthetic'));
    if (reopen && previous.piBackendSynthetic !== 'retained') throw Error('Synthetic extension state did not survive restart');
    await worker.evaluate(() => chrome.storage.local.set({piBackendSynthetic: 'retained'}));
    extensionChecked = true;
  }
  const popupPromise = new Promise(resolve => page.once('popup', resolve));
  await page.click('#popup');
  const popup = await popupPromise;
  if (backend === 'playwright')
    await popup.waitForFunction(() => document.querySelector('img')?.naturalWidth > 0, null, {timeout: 5000});
  else
    await popup.waitForFunction(() => document.querySelector('img')?.naturalWidth > 0, {timeout: 5000});
  await popup.close();
  await page.goto(origin + '/ordinary', {waitUntil: 'load', timeout: 10000});
  await page.click('#continue');
  const status = await page.evaluate(() => document.querySelector('#status').textContent);
  if (status !== 'Agent continued') throw Error('Ordinary navigation/click failed');
  await page.evaluate(() => localStorage.setItem('backend-probe', 'synthetic-retained'));
  await detach();
  const resumed = await attach();
  const marker = await resumed.evaluate(() => localStorage.getItem('backend-probe'));
  if (marker !== 'synthetic-retained') throw Error('Same-browser reconnect lost fixture state');
  console.log(JSON.stringify({backend, version, userAgent, popup: true, navigation: true,
    reconnect: true, stateRetained: true, browserRestartChecked: reopen, extensionChecked}));
} finally {
  await detach();
}
