# Private chat for Pi

Run `/private` in normal interactive Pi, or run the installed `pi-private` command.
Normal Pi releases the terminal while a separate, chat-only Pi RPC client and a
dedicated local llama.cpp server run inside Bubblewrap. Exiting returns to the
unchanged normal session. No normal messages, session IDs, project guidance,
credentials, tool results or model selections are forwarded.

## Use

- Type plain text and press Enter (single-line input in this first version).
- `/new` starts another private conversation.
- `/history` lists saved private conversations, newest first.
- `/resume NUMBER` reopens a listed conversation and displays its messages.
- `/exit`, `/quit`, EOF or Ctrl-C exits private mode.
- Only one installed private chat may be open at a time, to avoid concurrent writes.

The launcher flushes unread terminal input before normal Pi resumes, including
on startup failure. Normal Pi is shielded from foreground Ctrl-C while the private
launcher shuts down and reaps its sandbox. A parent-death signal and extension
shutdown cleanup also tear down private processes if normal Pi exits. If input flushing fails, normal Pi
shuts down rather than accepting a potentially private input queue.

The entry point does not accept a prompt argument. Private input is never sent to
the parent Pi. The `/private` command itself is not a promise to conceal that the
feature was opened. The extension uses an alternate terminal screen and clears
it before returning. Model/history output is plain text with terminal control
and Unicode format characters removed; no OSC clipboard writes or live links.

Private conversations are **unencrypted**, saved with restrictive permissions at
`~/.local/state/pi-private/sessions/`, outside normal Pi's session/history and
Project Object worklogs. They remain accessible to root and other programs
running as the same user. This is not protection against a compromised host,
terminal recording, backups, swap, memory inspection or arbitrary host searches.
Do not run host tools over this directory or submit its contents to a cloud model.
No private content should be placed in source control, worklogs or test artifacts.

## Boundary

- The **entire** private environment, including inference, uses fresh mount,
  process, IPC, user and network namespaces. There is no external interface,
  route, host loopback connection or network proxy. User-namespace failures
  abort launch; there is no less-private fallback.
- Only the Nix store (read-only), the selected GGUF (read-only), separate history
  (read-write), minimal virtual devices and private temporary directories are
  exposed. Host home, credentials, D-Bus/SSH/browser sockets, `/run/user` and
  project directories are not mounted. Environment variables are allowlisted.
- This first version uses the existing Qwen3.5-4B-Q4_K_M weights from
  `~/matrix/models/LLM/`, CPU inference, four threads, an 8192-token context and
  a 1024-token response limit. It starts/stops its own server and never stops or
  reconfigures existing model services. Weights are never downloaded at runtime.
- Pi runs offline with no tools, discovered extensions, skills, templates,
  context files or ordinary package settings. Its bundled llama command is
  intrinsically registered in Pi 0.87.1, but cannot be dispatched through this UI.
- The custom text-only frontend allowlists RPC operations. There is no native
  Pi TUI command dispatch, user shell, file attachment, model switching, export,
  share, editor, clipboard or external-browser operation. `@paths` inside prose
  are just text, not file expansion. Leading shell/attachment/unknown slash
  commands are rejected. Chat is still Pi's session and inference engine, not a
  separately implemented conversation store.
- Server and RPC diagnostics stay in sandbox tmpfs, not the system journal.
  Completed conversation messages persist through Pi's normal JSONL mechanism.
  An interrupted generation may be incomplete. History is never automatically
  merged into normal Pi or cloud sessions.

Bubblewrap is a sandbox construction tool, not a complete policy by itself:
https://github.com/containers/bubblewrap . The mounts, environment and namespace
arguments in `launcher.py` define this feature's policy. It is not a VM; the
host kernel and installed Nix dependencies remain trusted.

## Verification

```sh
python3 -B tests/test_pi_private.py
node --test tests/pi-private.test.mjs
python3 -B tests/test_pi_private.py --package /nix/store/…-pi-private-0.1.0
python3 -B tests/test_pi_private_terminal.py --package /nix/store/…-pi-private-0.1.0 --pi /nix/store/…-pi-coding-agent-0.87.1/bin/pi
pi-private --check
```

The packaged test uses synthetic prompts and a temporary history directory,
checks actual blocked external/host-loopback connectivity and distinct network
namespace identity, performs real isolated local inference, verifies restrictive
history permissions, then reopens that conversation in a fresh sandbox. It does
not read existing chats or call a cloud model. Hidden PTY tests run actual Pi
without graphical windows, verifying startup-failure input isolation and Ctrl-C
return to the original model/session, and full private-process teardown when
only the normal Pi parent is terminated. `--check` performs no inference.
