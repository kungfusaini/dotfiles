/* Deliberately no tabs, host permissions, HTTP, page scripts, or eval. */
let active = null;
chrome.runtime.onConnectExternal.addListener(ui => {
  if (ui.sender?.id !== 'mpognobbkildjkofajifpdfhcoklimli' || ui.name !== 'project-object-v1' || active) {
    ui.disconnect();
    return;
  }
  active = ui;
  const host = chrome.runtime.connectNative('org.project_object.browser');
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    void chrome.runtime.lastError;
    active = null;
    ui.disconnect();
    host.disconnect();
  };
  host.onMessage.addListener(message => { if (!closed) ui.postMessage(message); });
  ui.onMessage.addListener(message => { if (!closed) host.postMessage(message); });
  host.onDisconnect.addListener(close);
  ui.onDisconnect.addListener(close);
});
