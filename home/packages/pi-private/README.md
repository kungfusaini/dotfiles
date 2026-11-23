# Private mode with Pi's native interface

Run `/private` in normal interactive Pi, or run installed `pi-private` directly.
Normal Pi releases the terminal while a **native Pi TUI** and a dedicated local
llama.cpp server run inside Bubblewrap. `/quit` (or `/exit`) returns to normal Pi
without transferring conversation context. Native editor, Markdown, streaming,
scrolling, message navigation and history selection remain Pi's own components.
The private TUI uses fullscreen mode to keep private output off shell scrollback.

## Use

- Type with Pi's normal editor, including multiline and terminal text paste.
- `/new` starts a private conversation.
- `/resume` opens Pi's native picker, containing only private history.
- `/name`, `/session`, `/tree`, `/fork`, `/clone`, `/compact` and `/hotkeys` remain.
- `/quit` or `/exit` returns to normal Pi. Ctrl-C follows native Pi's clear/exit
  behavior; during startup it cancels launch and returns safely.
- A permanent native footer says **PRIVATE · LOCAL ONLY · chat only**.
- Only one installed private chat may be open, preventing concurrent writes.

There is no replacement text frontend or numbered `/resume NUMBER` interface.
Existing private JSONL conversations remain compatible; no migration, copying,
merging or deletion is performed. Normal Pi's package, settings, selected model
and history are untouched.

## Privacy boundary

The complete environment, **including inference**, uses fresh mount, process,
IPC, user and network namespaces. It cannot reach external networking, host
loopback, desktop sockets, host home or projects. Only the read-only Nix store,
read-only selected GGUF and separate writable history are mounted, along with
minimal virtual devices and private temporary directories. Environment variables
are allowlisted. Namespace failures abort; there is no less-private fallback.

The existing Qwen3.5-4B-Q4_K_M weights come from `~/matrix/models/LLM/`. Inference
uses CPU/four threads, an 8192-token context and a 1024-token response limit.
Private mode never downloads weights or stops/reconfigures existing model
services. Diagnostics stay in sandbox tmpfs, not the system journal.

A dedicated package variant (`native-chat.patch`) restricts the **actual Pi UI**:

- Tools, discovered extensions, skills, templates and project context are off.
- Shell, attachments, exports/imports/uploads, login, cloud/model switching,
  settings, external editors, clipboard operations, debugging and suspend are
  blocked. Native handlers are guarded, including shortcut/menu paths; hiding
  slash suggestions is not the enforcement mechanism.
- Slash completion includes only supported private commands; file/path
  completion is disabled. `@paths` typed in prose are literal text, not reads.
- Pi's session engine rejects non-pinned models and image attachments.
- Native Markdown preserves theme formatting but filters raw terminal-control
  input. Private history is also sanitized on append/read, covering tree/list
  previews and older saved conversations, not just the main transcript.
- Fullscreen copy-on-select and the renderer's clipboard/browser callbacks are
  disabled. Even forced transcript/fatal exits leave fullscreen without printing
  conversation text or a normal-Pi resume command into shell scrollback.
- The bundled `/llama` extension intrinsically exists in Pi 0.87.1, but private
  UI dispatch blocks it. Offline flags reduce automatic activity; the sandbox,
  not those flags, enforces the network boundary.

The launcher flushes unread private keystrokes before normal input resumes,
including startup failures. Normal Pi is shielded from foreground SIGINT while
launching. Parent-death protection and shutdown cleanup terminate/reap private
processes when normal Pi exits. Failed input flushing shuts normal Pi down
rather than handing a potentially private input queue to it.

Private history is **unencrypted**, under `~/.local/state/pi-private/sessions/`
with restrictive permissions, outside normal Pi and Project Object histories.
It remains accessible to root and programs running as the same user. This does
not protect against a compromised host, terminal recording, backups, swap,
memory inspection, arbitrary host searches or deliberate human copying/link
opening through the terminal. Do not submit this directory to a cloud model.
The `/private` invocation itself is not concealed from the normal environment.

Bubblewrap supplies mechanisms; these mounts and namespaces define the policy:
https://github.com/containers/bubblewrap . The host kernel and installed Nix
software are trusted. This is not a VM or a promise that a same-user host app
cannot read local files.

## Verification

```sh
python3 -B tests/test_pi_private.py --package /nix/store/…-pi-private-0.1.0
node --test tests/pi-private.test.mjs
PI_PRIVATE_TEST_ROOT=/nix/store/…-pi-coding-agent-0.87.1/lib/node_modules/pi-monorepo \
  node --test tests/pi-private-native.test.mjs
python3 -B tests/test_pi_private_native.py --package /nix/store/…-pi-private-0.1.0
python3 -B tests/test_pi_private_terminal.py --package /nix/store/…-pi-private-0.1.0 --pi /nix/store/…-normal-pi/bin/pi
pi-private --check
```

Tests use only synthetic prompts and temporary histories. Hidden PTY tests
exercise actual native Pi, multiline editing, command/shortcut restrictions,
real isolated local inference, native named-history reopening, queued-input
failure isolation, Ctrl-C return and parent-death teardown. They open no windows
and inspect no existing chats. `--check` performs no inference.
