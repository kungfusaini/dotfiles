/* No tabs/history permission, remote scripts, page-text or credential collection. */
const HOST = "org.machine.tablet_media";
let port;
let sequence = 0;
const pending = new Map();
let blocked = new Set();
const loaded = chrome.storage.session.get("blocked").then(value => {
  blocked = new Set(value.blocked || []);
});

function request(op, data = {}) {
  if (!port) return Promise.reject(new Error("Companion host unavailable"));
  const id = `extension-${++sequence}`;
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => { pending.delete(id); reject(new Error("Companion request timed out")); }, 12000);
    pending.set(id, {resolve, reject, timeout});
    port.postMessage({id, op, ...data});
  });
}

function permitted(tab) {
  if (!tab.url) return false;
  try {
    const url = new URL(tab.url);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch (_) { return false; }
}

async function refreshTab(tabId, expectedWindow = undefined) {
  const tab = await chrome.tabs.get(tabId);
  if (expectedWindow !== undefined && tab.windowId !== expectedWindow) return [];
  if (!permitted(tab)) return [];
  // Always install/refresh the fixed helper. Declarative scripts do not cover
  // pages already loaded when the extension was installed or reloaded.
  const frames = await chrome.scripting.executeScript({target: {tabId, allFrames: true}, files: ["media.js"]});
  const after = await chrome.tabs.get(tabId);
  if (after.windowId !== tab.windowId) {
    await chrome.tabs.sendMessage(tabId, {op: "detach"}).catch(() => {});
    await chrome.tabs.sendMessage(tabId, {op: "state"}).catch(() => {});
    throw new Error("Tab moved during media operation");
  }
  if (!frames.length || frames.some(frame => !frame.result?.installed || frame.result.stale))
    throw new Error("Media helper installation could not be verified");
  return frames.map(frame => frame.result);
}

async function setBlocked(windowId, value) {
  await loaded;
  if (value) blocked.add(windowId); else blocked.delete(windowId);
  await chrome.storage.session.set({blocked: [...blocked]});
  const tabs = await chrome.tabs.query({windowId});
  let elements = 0;
  let playing = 0;
  let unsupportedAudible = 0;
  let failedTabs = 0;
  for (const tab of tabs) {
    if (!permitted(tab)) { if (tab.audible) unsupportedAudible++; continue; }
    try {
      const frames = await refreshTab(tab.id, windowId);
      // An audible custom player with no reachable HTML media is not evidence
      // of a successful pause (e.g. Web Audio or inaccessible shadow media).
      if (value && tab.audible && frames.reduce((total, frame) => total + frame.elements, 0) === 0)
        unsupportedAudible++;
      for (const frame of frames) {
        if (frame.blocked !== value) throw new Error("Media helper has stale window state");
        elements += frame.elements;
        playing += frame.playing;
      }
    } catch (_) {
      // Protected pages, missing grants or a tab closing must not prevent
      // attempts on the remaining tablet tabs. Still fail the overall ACK.
      failedTabs++;
    }
  }
  return {elements, playing, unsupportedAudible, failedTabs};
}

async function handleHost(message) {
  const window = await chrome.windows.get(message.windowId);
  if (window.incognito || window.type !== "normal") throw new Error("Unsupported window");
  if (message.op === "verify") {
    const tab = await chrome.tabs.get(message.tabId);
    const matches = await chrome.tabs.query({url: message.url});
    if (tab.windowId !== window.id || tab.url !== message.url || matches.length !== 1 || matches[0].id !== tab.id)
      throw new Error("Registration moved or became ambiguous");
    return {};
  }
  if (!["pause", "resume"].includes(message.op)) throw new Error("Unsupported operation");
  const result = await setBlocked(window.id, message.op === "pause");
  if (result.failedTabs) throw new Error("Some tablet media helpers could not be verified");
  if (message.op === "pause" && (result.playing || result.unsupportedAudible))
    throw new Error("Some tablet media could not be paused with the granted site access");
  return result; // Resume only refreshes/unblocks; never calls play().
}

function connect() {
  const connection = chrome.runtime.connectNative(HOST);
  port = connection;
  connection.onMessage.addListener(message => {
    if (pending.has(message.id)) {
      const value = pending.get(message.id); pending.delete(message.id); clearTimeout(value.timeout);
      if (message.ok) value.resolve(message); else value.reject(new Error(message.error || "Companion request failed"));
      return;
    }
    if (!message.id || !["verify", "pause", "resume"].includes(message.op)) return;
    const reply = value => { try { connection.postMessage(value); } catch (_) {} };
    handleHost(message).then(result => reply({id: message.id, ok: true, ...result}))
      .catch(() => reply({id: message.id, ok: false, error: "Window-scoped media operation failed"}));
  });
  connection.onDisconnect.addListener(() => {
    void chrome.runtime.lastError;
    port = undefined;
    for (const value of pending.values()) { clearTimeout(value.timeout); value.reject(new Error("Companion disconnected")); }
    pending.clear();
    setTimeout(connect, 1000);
  });
}
connect();

async function pairWindow(windowId) {
  // A unique registration tab proves which native window contains this
  // Chrome window ID. Focus alone is never a pairing identity.
  const value = await request("prepare-existing");
  await chrome.tabs.create({windowId, url: value.url, active: true});
}
chrome.action.onClicked.addListener(async tab => {
  try {
    await pairWindow(tab.windowId);
    await chrome.action.setBadgeText({text: ""});
  } catch (_) { await chrome.action.setBadgeText({text: "!"}); }
});

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (!sender.tab) return;
  if (message.op === "pair-window" && sender.url === chrome.runtime.getURL("pair.html") && sender.frameId === 0) {
    pairWindow(sender.tab.windowId).then(() => reply({ok: true})).catch(() => reply({ok: false}));
    return true;
  }
  if (message.op === "state") {
    loaded.then(() => reply({blocked: blocked.has(sender.tab.windowId)}));
    return true;
  }
  if (message.op !== "register" || sender.frameId !== 0 || !sender.url) return;
  const url = new URL(sender.url);
  if (url.protocol !== "http:" || url.hostname !== "tablet.localhost" || !/^\/register\/[a-f0-9]{64}$/.test(url.pathname)) return;
  request("register", {nonce: url.pathname.split("/").pop(), windowId: sender.tab.windowId, tabId: sender.tab.id})
    .then(async value => {
      reply({ok: true});
      if (value.closeRegistration) {
        const tabs = await chrome.tabs.query({windowId: sender.tab.windowId});
        const current = await chrome.tabs.get(sender.tab.id);
        if (tabs.length > 1 && current.windowId === sender.tab.windowId && current.url === sender.url)
          await chrome.tabs.remove(sender.tab.id); // Only our newly-created pairing tab.
      }
    }).catch(() => reply({ok: false}));
  return true;
});

chrome.tabs.onDetached.addListener(async tabId => {
  // A document in transit is no longer owned by its old window.
  await chrome.tabs.sendMessage(tabId, {op: "detach"}).catch(() => {});
});
chrome.tabs.onAttached.addListener(async tabId => {
  try { await loaded; await refreshTab(tabId); }
  catch (_) { await chrome.action.setBadgeText({text: "!"}); }
});

chrome.windows.onRemoved.addListener(async windowId => {
  await loaded;
  blocked.delete(windowId);
  await chrome.storage.session.set({blocked: [...blocked]});
});
