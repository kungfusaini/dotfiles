// Fixed, idempotent helper. Explicit injection also covers documents that
// predate extension installation/reload. No page text or credentials collected.
(() => {
  const name = '__machineTabletMediaGate';
  try { globalThis[name]?.dispose(); } catch (_) {}
  let blocked = false;
  let generation = 0;
  const roots = new Set();
  function watchRoot(root) {
    if (roots.has(root)) return;
    roots.add(root);
    root.addEventListener('play', play, true);
  }
  function pauseHere() {
    const found = new Set();
    function scan(root) {
      watchRoot(root);
      for (const item of root.querySelectorAll('audio,video')) found.add(item);
      for (const element of root.querySelectorAll('*')) {
        if (element.shadowRoot) scan(element.shadowRoot);
      }
    }
    scan(document);
    const media = [...found];
    for (const item of media) item.pause();
    return {elements: media.length, playing: media.filter(item => !item.paused && !item.ended).length};
  }
  async function refresh() {
    const version = ++generation;
    try {
      // Sender.tab.windowId is supplied by Chrome at request time. Never use
      // a window ID remembered inside a document that can move to another window.
      const state = await chrome.runtime.sendMessage({op: 'state'});
      if (version !== generation) return {installed: true, stale: true};
      blocked = state?.blocked === true;
      return {installed: true, blocked, ...(blocked ? pauseHere() : {elements: 0, playing: 0})};
    } catch (_) {
      blocked = false;
      return {installed: false};
    }
  }
  const play = event => {
    // Tab movement and renderer messages are asynchronous. Recheck Chrome's
    // current sender window before pausing, rather than trusting a cached gate.
    if (event.target instanceof HTMLMediaElement) return refresh();
  };
  const message = (value, sender, reply) => {
    if (sender.id !== chrome.runtime.id) return;
    if (value.op === 'detach') { blocked = false; ++generation; reply({ok: true}); return; }
    if (value.op !== 'state') return;
    refresh().then(reply);
    return true;
  };
  watchRoot(document);
  chrome.runtime.onMessage.addListener(message);
  globalThis[name] = {
    refresh,
    dispose() {
      blocked = false; ++generation;
      for (const root of roots) root.removeEventListener('play', play, true);
      chrome.runtime.onMessage.removeListener(message);
    }
  };
  return refresh();
})()
