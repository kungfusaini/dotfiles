# Life Atlas audio transcript editor

Text-only editor and queue bridge for the approved selected-audio-log workflow.
The Home Manager module installs a two-minute user timer for the Aether transcript
queue. It never accesses the phone or audio; empty queues cause no model calls.
The standalone editor still processes only an explicitly supplied private packet.
Automatic phone upload is independently restricted to the existing nightly server
reception window; queue polling is not a more frequent phone upload schedule.

Adopts Pi's supported [JSON CLI](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/json.md)
rather than implementing provider authentication or an AI API client. Uses the
same managed Pi package and existing local login as chat: provider `openai-codex`,
model `gpt-6.1-sol`. No credentials are printed, copied to Aether, or embedded in
Nix. The queue bridge depends on this laptop being awake, online and logged in;
server-side ASR continues independently on Aether. If the laptop is unavailable,
completed raw transcripts wait privately for later cleanup; no wake or login is
forced.
No alternate provider/model fallback is permitted. Model identity and successful
settlement are checked from authoritative Pi events.

```sh
life-atlas-audio-editor --packet /PRIVATE/packet.json --out /PRIVATE/new-review
```

Inputs must be caller-owned private files outside Git. Output parent must already
be private and caller-owned; the output directory must be fresh. Packets are the
`review.py packet` format from Aether's `services/life-atlas-audio/review.py`.
Explicit sharing authorization is required for the selected recordings before
invocation. The component does not discover recordings or grant itself scope.
Only transcript text, segment anchors, the documented uncalibrated low-token
hint, and optional approved frozen name-spelling candidates are sent to the model.
No audio or unrelated metadata is sent. Names come from the source-bound Aether
packet, not a mutable laptop config or personal data embedded in the Nix store.
The packet/receipt hashes bind those hints. Names remain distinct candidates,
never aliases/global replacements; lexical name repairs must remain bracketed.
Absent hints preserve compatibility with older jobs. Recognition improvement
must be judged on future recordings, not inferred from successful API plumbing.

All built-in/extension tools, extensions, context files, skills, templates, themes
and session persistence are disabled. The policy treats speech as untrusted data,
not instructions. Inputs use stdin, not process arguments. Model events (including
private generated reasoning), requests, stderr, proposals and receipts remain in
the private review directory. No speech or model diagnostics are printed. Failures
retain partial private artifacts but do not publish a final proposal/receipt.
Each bounded chunk has a ten-minute process-group deadline; no unattended retries
or credential changes are performed. A new invocation never overwrites a result.

The output `proposal.json` is **not an accepted transcript**. Its receipt says
`proposed-awaiting-server-validation`. The bridge returns it to Aether, which
runs the existing `review.apply_proposal` against exact hash-identified raw ASR
before publication. This enforces lexical-preserving formatting and renders every
guess/unresolved span in timestamped brackets.
The local client validates source identity, spans, chunk ownership and edit shape,
not linguistic accuracy or the server's lexical formatting rules. Raw ASR remains
unchanged. Guesses are never declared verbatim; no summary or life analysis is
requested. If the speaker cannot recall a term, any defensible suggestion is a
separate bracketed insertion, preserving the original admission.

The final receipt binds packet, policy, proposal and event hashes and exact model
identity. The bridge verifies packet/proposal hashes and provider/model; the server
also verifies packet/proposal/source identity and deterministically validates edits.
It rejects incomplete/changed output rather than trusting directory existence or a
zero exit code alone. Server validation rejections permit bounded regeneration;
ambiguous transport failures reuse the completed proposal. At most three local
model attempts per source are made, with failed/rejected artifacts retained.
A server-accepted review skips model work on subsequent backup retries.

Bridge state is private at `~/.local/state/life-atlas-audio/`. Only content-free
counts/status reach journald. The bridge uses existing SSH configuration/agent
with strict host checking; no credentials are moved. Its sandbox SSH command
explicitly selects the existing caller-owned `~/.ssh/config`: user mount namespaces
map Nix-store root ownership to nobody, which otherwise makes OpenSSH reject the
irrelevant global systemd-proxy Include. The configured global known-hosts file
and disabled X11 forwarding are retained explicitly; host-key checking is never
relaxed. Aether publishes daily files,
backs up compact audio/raw-ASR/provenance into encrypted same-VPS restic, verifies
exact recovery and then removes only hash-verified worker-owned staged source/PCM.
Incoming Syncthing originals remain to avoid a delete/reupload loop, and phone
originals are untouched. Low disk headroom blocks intake rather than deleting
history. This is not independent off-server protection.

Inspect `systemctl --user status life-atlas-audio-review.timer` and private
`health.json` for queue state; do not dump private packets/model events into chat. Private runtime artifacts are not installed into the Nix store and
must not be committed. Independent backup remains a separate requirement.
