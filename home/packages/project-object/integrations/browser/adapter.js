/* Native session adapter, loaded only in Vivaldi's own main UI document.
 * This is not a web content script. No eval, HTTP, credentials, or debugger.
 */
(() => {
  'use strict';
  const EXTENSION = 'gkagbidkbfggbfholmeainnbjjbcapfo';
  const instance = crypto.randomUUID();
  const nap = ms => new Promise(resolve => setTimeout(resolve, ms));
  const uuid = value => typeof value === 'string' && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(value);
  const sessionName = value => typeof value === 'string' && /^po-[0-9a-f-]{36}-[0-9a-f-]{36}-[0-9]{1,3}$/.test(value);
  const metadata = value => { try { return JSON.parse(value || '{}'); } catch { throw Error('Invalid browser metadata'); } };
  const tag = window => {
    const data = metadata(window.vivExtData);
    if (data.projectObjectProjectId && data.projectObjectWindowKey)
      return {projectId: data.projectObjectProjectId, windowKey: data.projectObjectWindowKey};
    // Named sessions omit window vivExtData but retain tab vivExtData. Only
    // unanimous tab provenance may recover a window's durable ownership.
    const tabs = (window.tabs || []).map(tab => metadata(tab.vivExtData));
    const first = tabs[0];
    if (first && uuid(first.projectObjectProjectId) && uuid(first.projectObjectWindowKey) &&
        tabs.every(tab => tab.projectObjectProjectId === first.projectObjectProjectId &&
          tab.projectObjectWindowKey === first.projectObjectWindowKey))
      return {projectId: first.projectObjectProjectId, windowKey: first.projectObjectWindowKey};
    return {};
  };
  const describe = window => ({
    id: window.id, incognito: window.incognito, type: window.type, ...tag(window),
    provenance: [...new Set((window.tabs || []).map(tab => metadata(tab.vivExtData).projectObjectProjectId).filter(Boolean))],
    tabs: (window.tabs || []).map(tab => {
      const data = metadata(tab.vivExtData);
      return {id: tab.id, url: tab.pendingUrl || tab.url, pinned: tab.pinned,
        group: data.group || '', groupTitle: data.fixedGroupTitle || '',
        fixedTitle: data.fixedTitle || '', workspace: data.workspaceId || 0};
    }),
  });
  const inventory = async () => (await chrome.windows.getAll({populate: true})).map(describe);
  const getWindow = async id => {
    if (!Number.isInteger(id) || id <= 0) throw Error('Invalid browser window ID');
    const window = await chrome.windows.get(id, {populate: true});
    if (window.incognito || window.type !== 'normal' || !window.tabs?.length)
      throw Error('Only non-private normal browser windows can be checkpointed');
    return window;
  };
  const equal = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const findSession = (items, name) => {
    const matches = [];
    for (const item of items) {
      if (item.name === name) matches.push(item);
      matches.push(...findSession(item.children || [], name));
    }
    return matches;
  };
  async function session(name) {
    if (!sessionName(name)) throw Error('Invalid project session name');
    const model = await vivaldi.sessionsPrivate.getAll();
    if (model.loadingFailed) throw Error('Vivaldi session index could not be loaded');
    const found = findSession(model.items, name);
    if (found.length !== 1) throw Error('Project session is missing or ambiguous');
    return found[0];
  }
  const challenges = new Map();
  async function operation(request) {
    switch (request.op) {
      case 'inventory': return inventory();
      case 'challenge': {
        if (!/^POB-[0-9a-f]{32}$/.test(request.marker || '')) throw Error('Invalid identity challenge');
        await getWindow(request.windowId);
        let views = [];
        for (let attempt = 0; attempt < 30; attempt++) {
          views = chrome.extension.getViews().filter(view => view.vivaldiWindowId === request.windowId);
          if (views.length === 1) break;
          await nap(100);
        }
        if (views.length !== 1) throw Error('Browser window view not ready');
        const view = views[0];
        if (challenges.has(request.windowId)) challenges.get(request.windowId)();
        const original = view.document.title;
        const restore = () => {
          clearInterval(interval); clearTimeout(timer);
          if (view.document.title === request.marker) view.document.title = original;
          challenges.delete(request.windowId);
        };
        const interval = setInterval(() => { view.document.title = request.marker; }, 50);
        const timer = setTimeout(restore, 3000);
        challenges.set(request.windowId, restore);
        view.document.title = request.marker;
        return true;
      }
      case 'unchallenge':
        for (const restore of [...challenges.values()]) restore();
        return true;
      case 'tag': {
        if (!uuid(request.projectId) || !uuid(request.windowKey)) throw Error('Invalid project identity');
        const window = await getWindow(request.windowId);
        const previous = tag(window);
        if ((previous.projectId && previous.projectId !== request.projectId) ||
            window.tabs.some(tab => {
              const data = metadata(tab.vivExtData);
              return data.projectObjectProjectId && data.projectObjectProjectId !== request.projectId;
            }))
          throw Error('Browser contains another project\'s tabs; ownership left unchanged');
        const data = metadata(window.vivExtData);
        data.projectObjectProjectId = request.projectId;
        data.projectObjectWindowKey = request.windowKey;
        await chrome.windows.update(window.id, {vivExtData: JSON.stringify(data)});
        for (const tab of window.tabs) {
          const tabData = metadata(tab.vivExtData);
          tabData.projectObjectProjectId = request.projectId;
          tabData.projectObjectWindowKey = request.windowKey;
          await chrome.tabs.update(tab.id, {vivExtData: JSON.stringify(tabData)});
        }
        return describe(await getWindow(window.id));
      }
      case 'save': {
        if (!sessionName(request.name)) throw Error('Invalid project session name');
        const window = await getWindow(request.windowId);
        const before = describe(window);
        if (!uuid(before.projectId) || !uuid(before.windowKey)) throw Error('Unowned project browser');
        if (before.provenance.some(project => project !== before.projectId))
          throw Error('Conflicting project tab ownership; nothing saved');
        // Native Workspaces need the UI's workspace-registry reconstruction too.
        // Until that is covered, refuse rather than silently lose workspace tabs.
        if (before.tabs.some(tab => tab.workspace !== 0))
          throw Error('Vivaldi internal Workspaces are not yet supported; browser windows left open');
        const model = await vivaldi.sessionsPrivate.getAll();
        if (findSession(model.items, request.name).length) throw Error('Checkpoint already exists');
        const result = await vivaldi.sessionsPrivate.add({name: request.name, filename: request.name,
          parentId: model.rootId, index: 0, owner: 'project-object', windowId: window.id});
        if (result !== 0) throw Error('Native session save failed');
        const saved = await session(request.name);
        const content = await vivaldi.sessionsPrivate.getContent(saved.id);
        const expected = before.tabs.map(tab => tab.id).sort((a, b) => a - b);
        const actual = (content.windows || []).flatMap(w => w.tabs).map(tab => tab.id).sort((a, b) => a - b);
        if (saved.windows !== 1 || content.windows.length !== 1 || !equal(expected, actual) || !actual.length)
          throw Error('Saved native session does not match selected window');
        if (!equal(before, describe(await getWindow(window.id)))) throw Error('Browser changed during checkpoint');
        return {window: before, content};
      }
      case 'close': {
        if (!Array.isArray(request.windows) || !request.windows.length || request.windows.length > 128)
          throw Error('Invalid browser checkpoint');
        // Validate the entire set before the first destructive operation.
        for (const expected of request.windows) {
          const current = describe(await getWindow(expected.id));
          if (!equal(expected, current)) throw Error('Browser changed after checkpoint; windows left open');
          for (const tab of current.tabs) {
            const handlers = await vivaldi.tabsPrivate.hasBeforeUnloadOrUnload(tab.id);
            if (handlers !== false) throw Error('A page has unload handlers; browser windows left open');
          }
        }
        for (const expected of request.windows) {
          if (!equal(expected, describe(await getWindow(expected.id)))) throw Error('Browser changed before closure');
          // Vivaldi otherwise migrates pinned tabs to another project's window.
          for (const tab of expected.tabs.filter(tab => tab.pinned)) await chrome.tabs.remove(tab.id);
          const live = (await inventory()).find(window => window.id === expected.id);
          if (live) {
            const remaining = {...expected, tabs: expected.tabs.filter(tab => !tab.pinned)};
            if (!equal(live, remaining)) throw Error('Browser changed during closure; checkpoint retained');
            await chrome.windows.remove(expected.id);
          }
        }
        return true;
      }
      case 'restore': {
        const saved = await session(request.name);
        const before = await inventory();
        if (!before.length) throw Error('Browser is not ready for restoration');
        await vivaldi.sessionsPrivate.open(saved.id, before[0].id,
          {newWindow: true, oneWindow: false, withWorkspace: true, workspaceAsTabs: false, tabIds: []});
        const previous = new Set(before.map(window => window.id));
        for (let attempt = 0; attempt < 100; attempt++) {
          const added = (await inventory()).filter(window => !previous.has(window.id));
          if (added.length === 1 && added[0].tabs.length === saved.tabs &&
              uuid(added[0].projectId) && uuid(added[0].windowKey)) return added[0];
          if (added.length > 1) throw Error('Ambiguous restored windows; checkpoint retained');
          await nap(100);
        }
        throw Error('Native restore timed out; inspect existing windows before retrying');
      }
      default: throw Error('Unsupported project browser operation');
    }
  }
  let busy = false;
  function connect() {
    let port;
    try { port = chrome.runtime.connect(EXTENSION, {name: 'project-object-v1'}); }
    catch { setTimeout(connect, 2000); return; }
    port.onMessage.addListener(async message => {
      if (message.event === 'hello' && message.protocol === 1) {
        port.postMessage({event: 'ready', protocol: 1, instance});
        return;
      }
      if (typeof message.id !== 'string' || !/^[a-f0-9]{32}$/.test(message.id)) return;
      if (busy) { port.postMessage({id: message.id, response: {ok: false, error: 'Browser adapter busy'}}); return; }
      busy = true;
      try { port.postMessage({id: message.id, response: {ok: true, value: await operation(message.request)}}); }
      catch (error) {
        // Messages are authored above or native API diagnostics; never include
        // URLs, page text, captured session contents, or entire native responses.
        port.postMessage({id: message.id, response: {ok: false, error: String(error.message).slice(0, 200)}});
      } finally { busy = false; }
    });
    port.onDisconnect.addListener(() => { void chrome.runtime.lastError; setTimeout(connect, 2000); });
  }
  connect();
})();
