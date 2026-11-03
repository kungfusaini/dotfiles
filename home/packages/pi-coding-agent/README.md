# Pi local UI patches

Local override of the locked `unstable.pi-coding-agent` (0.87.1), selected by
`hosts/kirax1/modules/users/sumeet.nix`. This does not change model inference,
agent event delivery, tool execution, sessions, or JSONL persistence.

Upstream reports:
- https://github.com/earendil-works/pi/issues/6665
- https://github.com/earendil-works/pi/issues/3881
- https://github.com/earendil-works/pi/issues/9255

## Changes

- Limit background TUI rendering to 10 frames/second, rather than ~60.
- Defer assistant streaming Markdown component construction until `render()`;
  multiple deltas before a frame rebuild only the newest complete message.
- Keep non-streaming content construction synchronous and draw `message_end`
  immediately, including error and cancellation output.
- Preserve the existing immediate keyboard-input rendering path.

Intermediate display frames may be skipped; content is never truncated or
removed. Both main-screen and fullscreen renderers share the frame scheduler.
Animations use the background frame limit too. This is a mitigation, not a full
incremental-rendering/cache implementation: a long transcript is still traversed
for each displayed frame. Recheck the patch and tests whenever Pi is updated.
Nix's source patching/build should fail rather than silently patch unrelated code.

## Model-mode UI

`model-mode-ui.patch` keeps the native selector and footer rather than replacing
usage accounting or model display in an extension:

- `ctx.ui.select(..., { initialIndex })` starts on the current mode. Other
  selectors still start at row zero; invalid indices default or clamp safely.
- The local `model-mode` extension status is right-aligned on the row beneath
  the native model/thinking display. Other extension statuses stay on the left;
  narrow layouts reserve room for the mode without exceeding terminal width.
- The model-mode extension determines the current mode from the actual model and
  thinking level, not a remembered label. Non-matching combinations have no mode.

This patch changes Pi core code. Existing Pi processes need restarting/resuming
once to load it; resource reload alone cannot replace their loaded UI components.
The extension itself and future policy updates remain reloadable.

Test both actual package builds without provider requests:

```sh
node home/packages/pi-coding-agent/test-model-mode-ui.mjs STOCK_STORE_PATH PATCHED_STORE_PATH
node --test tests/pi-model-modes.test.mjs
```

## Verification

Build the actual selected package without activating anything:

```sh
drv=$(nix eval --raw .#nixosConfigurations.kirax1.config.users.users.sumeet.packages \
  --apply 'ps: (builtins.head ps).drvPath')
nix build --no-link --print-out-paths "${drv}^*"
```

Use the unmodified and resulting store paths (not their `bin/pi` executables):

```sh
node home/packages/pi-coding-agent/test.mjs STOCK_STORE_PATH PATCHED_STORE_PATH
node home/packages/pi-coding-agent/benchmark.mjs STOCK_STORE_PATH 5000
node home/packages/pi-coding-agent/benchmark.mjs PATCHED_STORE_PATH 5000
```

Tests compare 196 rendered outputs against stock Pi, covering visible/hidden
thinking, Markdown, Unicode, resizing, tool calls, aborted/error/length stops,
padding, and invalidation. They also check latest-content coalescing, immediate
keyboard input, final rendering, and cancellation of pending frames on shutdown.

The benchmark uses actual installed Pi components, a 10k-line synthetic history,
and a growing Markdown response; it does not contact providers, read real
sessions, or write to a real terminal. On kirax1, three 5-second runs averaged
~105% of one logical core for stock and ~46% for the patch (~56% lower). The patch
processed more input chunks because the event loop was less blocked. This is a
stress/throughput result, not a fixed-input latency benchmark or a prediction of
whole-system battery savings. A V8 CPU profile of stock reproduced Markdown
parsing, terminal width scanning, and full-transcript rendering hot paths.

Live watt savings need a separate representative A/B after starting new sessions
with the patched package. Running Pi sessions are not modified or terminated;
`/reload` alone does not replace their already-loaded core renderer.
