// Isolated SDK prototype. Not imported by the installed Pi package or extensions.
export function createResumeRecovery({ createStream, waitForNetwork, onState = () => {} }) {
  const lifetime = new AbortController();
  const active = new Set();
  let sleeping = false;
  let needsNetwork = false;
  let generation = 0;
  const wakeWaiters = new Set();

  function prepareForSleep(start) {
    if (lifetime.signal.aborted) return;
    if (start) {
      if (!sleeping) generation++;
      sleeping = true;
      return;
    }
    if (!sleeping) return; // Ignore duplicate/unsolicited wake notifications.
    sleeping = false;
    needsNetwork = true;
    for (const request of active) {
      request.interrupted = true;
      request.controller.abort(); // Never abort the parent agent/tool signal.
    }
    for (const wake of wakeWaiters) wake();
    wakeWaiters.clear();
  }

  async function ready(signal) {
    while (sleeping) {
      signal.throwIfAborted();
      await new Promise((resolve, reject) => {
        const finish = () => { cleanup(); resolve(); };
        const cancel = () => { cleanup(); reject(signal.reason); };
        const cleanup = () => {
          wakeWaiters.delete(finish);
          signal.removeEventListener('abort', cancel);
        };
        wakeWaiters.add(finish);
        signal.addEventListener('abort', cancel, { once: true });
      });
    }
    if (needsNetwork) {
      const checkingGeneration = generation;
      onState('waiting-for-network');
      await waitForNetwork(signal);
      signal.throwIfAborted();
      // Old readiness results cannot open the gate after a newer sleep/wake.
      if (sleeping || checkingGeneration !== generation) return ready(signal);
      needsNetwork = false;
      onState('ready');
    }
  }

  function wrap(inner) {
    return (model, context, options = {}) => {
      const output = createStream();
      const signal = AbortSignal.any([lifetime.signal, ...(options.signal ? [options.signal] : [])]);
      let latest;
      const request = { controller: new AbortController(), interrupted: false };
      const failedMessage = (error) => ({
        role: 'assistant', content: [], api: model.api, provider: model.provider,
        model: model.id, timestamp: Date.now(),
        usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 } },
        ...latest,
        stopReason: signal.aborted ? 'aborted' : 'error',
        errorMessage: signal.aborted ? 'Request was aborted' : request.interrupted
          ? 'Network error: provider request interrupted by system sleep; retry after resume'
          : String(error?.message ?? error),
      });
      void (async () => {
        try {
          do { await ready(signal); } while (sleeping || needsNetwork);
          signal.throwIfAborted();
          active.add(request);
          const upstream = await inner(model, context, {
            ...options, signal: AbortSignal.any([signal, request.controller.signal]),
          });
          for await (const event of upstream) {
            latest = event.partial ?? event.message ?? event.error ?? latest;
            if (event.type === 'error' && request.interrupted) {
              const message = failedMessage(new Error(event.error.errorMessage));
              output.push({ type: 'error', reason: message.stopReason, error: message });
            } else {
              output.push(event);
            }
            if (event.type === 'error' || event.type === 'done') return;
          }
          throw new Error('Provider stream ended without a terminal event');
        } catch (error) {
          const message = failedMessage(error);
          output.push({ type: 'error', reason: message.stopReason, error: message });
        } finally {
          active.delete(request);
          output.end();
        }
      })();
      return output;
    };
  }

  return {
    wrap, prepareForSleep,
    get activeRequests() { return active.size; },
    dispose() {
      lifetime.abort();
      wakeWaiters.clear();
    },
  };
}
