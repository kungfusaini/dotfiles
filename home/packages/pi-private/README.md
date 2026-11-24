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
- `/image <description>` generates a local image; Escape cancels and reaps its server.
- A permanent native footer says **PRIVATE · LOCAL ONLY · chat + /image**.
- Only one installed private chat may be open, preventing concurrent writes.

There is no replacement text frontend or numbered `/resume NUMBER` interface.
Existing private JSONL conversations remain compatible; no migration, copying,
merging or deletion is performed. Normal Pi's package, settings, selected model
and history are untouched.

## Private local images

Reopen `/private` after deployment, then try:

```text
/image A red ceramic teapot on a wooden table beside a sunlit window
```

A single pinned extension exposes this **human-only command**, not a model tool.
It uses [stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)'s
Vulkan backend and the existing read-only
`~/matrix/models/image/checkpoints/Juggernaut-XL_v9_RunDiffusionPhoto_v2.safetensors`.
No new image weights are downloaded. The first version generates one 512×512 PNG,
20 Euler steps, CFG 5, with an on-demand server that exits after each request.
A harmless synthetic test took about 46 seconds including model startup on
kirax1; load and thermal conditions vary. Chat remains usable if image weights
are missing; `/image` reports unavailability rather than downloading/falling back.

The loader captures input until the request finishes or is cancelled; wait for
chat generation to finish before using `/image`. Prompts travel over worker stdin
and sandbox-only HTTP (`127.0.0.1:18081`), not process command lines or a host-facing
port. User text cannot inject backend configuration tags or CLI arguments. Fixed
limits bound prompt length, dimensions, batch size, steps and response size.
Backend logs stay in sandbox tmpfs; no diagnostics are sent to the journal.

The result has a small **64×64-pixel, ANSI half-block terminal preview** and a full
PNG saved under `~/.local/state/pi-private/images/`. The preview uses numeric RGB
values only, not terminal image/file-transfer protocols, clipboard or external
viewers. The directory is mode 0700, images are mode 0600, and PNG metadata is
stripped before an atomic, non-overwriting save. Descriptions and thumbnails are
saved in private session history and reopen with `/resume`, including image-only
sessions and their branches. The text chat model receives the textual result,
not image pixels, and cannot inspect generated images. No images are copied into
normal Pi history, exported, uploaded or opened outside private mode automatically.

Saved images, prompts and thumbnails are **unencrypted**, like private chat
history. Same-user/root access, terminal recording, backups and shared-GPU risks
still apply; this is not a vault. Cancelling a request does not delete previously
saved images. No generic image-file reader or shell tool is enabled.

## Privacy boundary

The complete environment, **including inference**, uses fresh mount, process,
IPC, user and network namespaces. It cannot reach external networking, host
loopback, desktop sockets, host home or projects. Only the read-only Nix store,
read-only selected GGUF, optional read-only image weights, separate writable
history and separate private image output are mounted, along with
minimal virtual devices and private temporary directories. GPU acceleration adds
only `/dev/dri/renderD128` and six read-only Intel PCI identity files (`uevent`,
`vendor`, `device`, `subsystem_vendor`, `subsystem_device`, `revision`) in a minimal
synthetic sysfs discovery tree. No display/card device, input/audio device, whole
host sysfs, desktop socket or driver runtime directory is mounted. The PCI path
and render node target kirax1's Intel Arc B390; hardware-layout changes fail closed.
A pinned Mesa Intel Vulkan ICD comes from the Nix store, not the host environment.
Environment variables are allowlisted. Namespace/device failures abort; there is
no less-private or cloud fallback.

GPU access is a deliberate expansion of the trusted surface: the sandbox now
shares the kernel GPU driver and physical GPU with the desktop. Render-only
access does not grant desktop capture, but does not isolate GPU resource use,
driver vulnerabilities or GPU side channels. Network and filesystem boundaries
remain in place.

Private mode uses `~/matrix/models/LLM/Qwen3.5-4B-abliterated.Q4_K_M.gguf`.
The original weights and private history remain untouched; exit and reopen
`/private` to use the new weights. The internal `private-qwen` ID is retained
for history compatibility. Abliteration reduces refusals but does not guarantee
unrestricted responses or factual accuracy, and does not itself improve speed.

Weights: [mradermacher/Qwen3.5-4B-abliterated-GGUF](https://huggingface.co/mradermacher/Qwen3.5-4B-abliterated-GGUF),
revision `f3b61227dde75c72d12391c443efd6fa0229e0eb`, file
`Qwen3.5-4B-abliterated.Q4_K_M.gguf` (2,707,514,688 bytes), SHA-256
`1ec0b30c75b49223c82542caf2635a7af4edcda80d8c89759cc000d3871bf48e`.
The file is downloaded separately and verified against the publisher's LFS hash;
it is not included in Git or downloaded at private-mode startup.

Inference uses llama.cpp's Vulkan backend with all 33 layers offloaded to the
Intel GPU, four CPU helper threads, an 8192-token context and a 1024-token response
limit. `Vulkan0` is required explicitly; unavailable GPU startup fails rather than
silently changing to a CPU or cloud service. Flash attention is explicitly off.
Private mode never downloads weights or stops/reconfigures existing model
services. Diagnostics stay in sandbox tmpfs, not the system journal.

A dedicated package variant (`native-chat.patch`) restricts the **actual Pi UI**:

- Tools, discovered extensions, skills, templates and project context are off.
  Only the explicitly pinned `/image` extension is loaded from the Nix store;
  this does not enable arbitrary extension discovery or model-callable tools.
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
  PI_PRIVATE_IMAGE_EXTENSION=/nix/store/…-pi-private-0.1.0/lib/pi-private/private-image.ts \
  node --test tests/pi-private-native.test.mjs
python3 -B tests/test_pi_private_native.py --package /nix/store/…-pi-private-0.1.0
python3 -B tests/test_pi_private_terminal.py --package /nix/store/…-pi-private-0.1.0 --pi /nix/store/…-normal-pi/bin/pi
# Use the Pillow-enabled Python pinned in the packaged image extension:
/nix/store/…-python3-env/bin/python3 -B tests/test_pi_private_images.py --package /nix/store/…-pi-private-0.1.0
pi-private --check
# Optional: compare against the pre-GPU package, using only synthetic chats.
python3 -B tests/test_pi_private_performance.py --package /nix/store/…-gpu-pi-private-0.1.0 \
  --baseline-package /nix/store/…-cpu-pi-private-0.1.0
```

Tests use only synthetic prompts and temporary histories. Hidden PTY tests
exercise actual native Pi, multiline editing, command/shortcut restrictions,
real isolated local inference, native named-history reopening, queued-input
failure isolation, Ctrl-C return and parent-death teardown. They open no windows
and inspect no existing chats. `--check` performs no inference, checks render-only
exposure/read-only PCI metadata, and requires the render device to exist. The
packaged tests also enumerate Vulkan devices inside the sandbox. Image tests
exercise actual `/image` generation, metadata stripping, mode-0600 outputs,
pixel-only preview, image-only history persistence/reopening, rejected backend
tags, and Escape-driven server teardown, using only synthetic temporary data.

The synthetic performance test uses the same weights, 8192-token context, four
threads, 61-token chat input and 64 generated tokens, with cache reuse disabled.
On kirax1 under existing desktop/private-session load, two CPU responses took
32.825/67.000 seconds versus 5.091/5.305 seconds with Vulkan (9.60x aggregate
wall-time speedup). GPU decoding measured 17.90/18.15 tokens/sec and diagnostics
confirmed 33/33 layer offload. These are loaded-system observations, not guaranteed
latencies; startup, longer context and concurrent CPU/GPU activity can differ.
The probe keeps synthetic responses and diagnostics in sandbox tmpfs and outputs
only timing/offload evidence. It never opens real private history.
