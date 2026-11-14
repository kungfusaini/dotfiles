# Life Atlas audio transcript editor

Standalone text-only review component for the approved daily audio-log workflow.
**No timer, discovery, automatic backfill, queue bridge or audio access is installed
by this package.** Phone selection/date metadata and end-to-end scheduling remain
pending. This is not yet a live unattended transcript pipeline.

Adopts Pi's supported [JSON CLI](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/json.md)
rather than implementing provider authentication or an AI API client. Uses the
same managed Pi package and existing local login as chat: provider `openai-codex`,
model `gpt-6.1-sol`. No credentials are printed, copied to Aether, or embedded in
Nix. A future queue bridge running here will depend on this laptop being awake,
online and logged in; server-side ASR need not wait for laptop availability.
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
Only transcript text, segment anchors and the documented uncalibrated low-token
hint are sent to the model. No audio or unrelated metadata is sent.

All built-in/extension tools, extensions, context files, skills, templates, themes
and session persistence are disabled. The policy treats speech as untrusted data,
not instructions. Inputs use stdin, not process arguments. Model events (including
private generated reasoning), requests, stderr, proposals and receipts remain in
the private review directory. No speech or model diagnostics are printed. Failures
retain partial private artifacts but do not publish a final proposal/receipt.
Each bounded chunk has a ten-minute process-group deadline; no unattended retries
or credential changes are performed. A new invocation never overwrites a result.

The output `proposal.json` is **not an accepted transcript**. Its receipt says
`proposed-awaiting-server-validation`. Before publication, the queue bridge must
return it to Aether and successfully run the existing `review.apply_proposal`
against the exact hash-identified raw ASR; that enforces lexical-preserving
formatting and renders every guess/unresolved span in timestamped brackets.
The local client validates source identity, spans, chunk ownership and edit shape,
not linguistic accuracy or the server's lexical formatting rules. Raw ASR remains
unchanged. Guesses are never declared verbatim; no summary or life analysis is
requested. If the speaker cannot recall a term, any defensible suggestion is a
separate bracketed insertion, preserving the original admission.

The final receipt binds packet, policy, proposal and event hashes and exact model
identity. A future runtime must verify it and reject incomplete/changed output,
never treat directory existence or a zero exit code alone as accepted editorial
completion. Private runtime artifacts are not installed into the Nix store and
must not be committed. Independent backup remains a separate requirement.
