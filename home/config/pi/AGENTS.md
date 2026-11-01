# Global Agent Guidance

These instructions apply to every Pi session. Project, stream, and repository instructions add narrower context and govern local implementation details. Follow all compatible instructions; do not use a narrower scope to weaken the authorization, safety, secret-handling, or change-discipline rules here.

## Authorization and investigation

- Read-only investigation is always allowed without prior permission. Inspect files, Git state, logs, documentation, running state, and other local evidence as deeply as needed to understand the task.
- Before modifying files, Git state, system or application state, or external services, summarize the intended change and affected areas and obtain Sumeet's explicit approval.
- Approval covers the agreed scope as a whole; it does not require another interruption before every file edit.
- Obtain fresh approval before materially expanding the scope or performing a destructive operation that was not part of the approved plan.
- A request to investigate, explain, review, or propose a change is not authorization to implement it.

## Operational autonomy

- Minimize mechanical work for Sumeet. After receiving approval, carry out the authorized work end-to-end using available tools wherever practical.
- Once a goal or plan is approved, continue through its concrete steps without waiting for Sumeet to say "continue", "go ahead", or otherwise renew momentum. Intermediate findings, progress reports, commits, and completed substeps are not stopping points; do not create artificial micro-scopes merely to pause between them.
- Keep execution directed by the agreed goal and remaining plan. Do not invent unrelated work, expand the scope for its own sake, or continue indefinitely after the goal is complete.
- Stop only when the approved goal is complete and verified; progress is genuinely blocked by missing access, credentials, dependencies, or required human action; a necessary decision cannot safely be inferred; an authorization, safety, policy, or secret-handling boundary prevents execution; or the next action requires fresh approval because it materially expands scope or risk. If one path is blocked but other approved plan steps remain independent, authorized, and safe, continue those steps first.
- Do not ask Sumeet to run commands, edit files, navigate a GUI, copy output, or perform other steps that the agent can safely perform itself.
- Ask for manual action only when it genuinely requires Sumeet's privileges, credentials, physical presence, judgment, or access to an interface the agent cannot operate.
- When manual action is unavoidable, request the smallest precise action needed, explain why it cannot be performed autonomously, and resume verification afterward where practical.
- From a Project Object terminal, launch graphical applications with `project-workspace-exec COMMAND [ARG ...]` so their windows open on the agent's own Hyprland workspace. Use another workspace only when the task explicitly requires it.
- Operational autonomy does not expand authorization. Do not bypass approval requirements, safety boundaries, secret-handling rules, or destructive-operation safeguards.

## External research

- When an answer relies on external research, include clickable links to the most relevant primary sources, attached to the claims or recommendations they support.
- For product recommendations, link each shortlisted product and include a current purchase link when useful. Clearly qualify unverified compatibility, pricing, and availability.

## Change and commit discipline

- Preserve unrelated work. Never overwrite, revert, reformat, stage, or commit pre-existing changes unless Sumeet explicitly includes them in the approved scope.
- Make the smallest coherent change that fully solves the approved task. Avoid drive-by refactors and cleanup.
- Once implementation is approved, agents may create the Git commit without asking separately.
- One commit must represent one complete atomic piece of work. Include its implementation, focused verification, necessary documentation, and corrections discovered during the work.
- If a problem with that atomic change is found before the work is handed off, fix it and amend the same commit rather than adding a follow-up "fix the previous commit" commit.
- Keep separate concerns in separate commits. Never absorb unrelated dirty-tree changes merely to make the worktree clean.
- Do not commit credentials, tokens, private keys, decrypted secrets, local caches, generated state, or machine-specific runtime artifacts.

## NixOS configuration

The canonical system configuration is the Git repository at:

```text
/home/sumeet/.config/nixos
```

Manage system and user configuration declaratively through this repository wherever practical. Inspect and follow its existing placement, naming, module, package, and test conventions before adding anything.

- `hosts/kirax1/` owns machine-wide configuration for the current laptop: boot, kernel, hardware, networking, users, privileged services, udev rules, and policies that must work without a graphical login.
- `home/modules/` owns Home Manager behavior and user-session integrations.
- `home/config/` holds static source files deployed by Home Manager.
- `home/packages/` holds locally packaged applications or substantial tools with multiple implementation files.
- `home/scripts/` holds user-side script sources that must be packaged or deployed through Home Manager rather than invoked from the checkout.
- `hosts/kirax1/scripts/` holds host-specific script sources that must be packaged or deployed through NixOS rather than invoked from the checkout.
- Split mixed features according to ownership instead of forcing the whole feature into one layer.

Do not directly edit generated files, deployed Nix-store files, or Home Manager symlink targets. Change their canonical source in the Nix repository. Do not introduce mutable out-of-store configuration or runtime dependencies on the repository checkout unless Sumeet explicitly approves that exception.

A completed Nix change must leave the `kirax1` flake evaluable and deployable with the ordinary command. Every new file referenced by the flake must be Git-tracked and included in the atomic commit; do not ask Sumeet to rebuild from an incomplete or uncommitted tree.

Run appropriate non-privileged evaluation, syntax, and focused tests. Do not run the privileged NixOS rebuild or improvise a different deployment command. Ask Sumeet to run:

```bash
sudo nixos-rebuild switch --flake /home/sumeet/.config/nixos#kirax1
```

After Sumeet rebuilds, verify where practical that the new generation is active and that affected processes loaded the intended configuration. Do not claim deployment success from source evaluation alone.

## System layout

Keep `$HOME` clean. Do not create new top-level folders unless explicitly asked.

When changing managed configuration, edit the canonical Nix source under `~/.config/nixos`, not generated files or deployed symlinks. After deployment, verify that restarted processes are actually running the new generation and have loaded the new configuration.

Important roots:

- `~/matrix` — technical, code, AI, data, and model work.
- `~/codex` — notes, knowledge, personal writing, timelines, and narratives. This is a Git repository.
- `~/Documents` — official records, proofs, and durable reference documents.
- `~/Pictures` — personal images, photos, and art.
- `~/Music` — music libraries, Logic files, and practice or creation material.
- `~/Videos` — personal and project video output.
- `~/Downloads` and `~/Desktop` — temporary inboxes only; do not archive material there.
- `~/.config`, `~/.local`, and `~/.cache` — XDG configuration, data/state, and cache locations.

### `~/matrix`

`~/matrix` is the technical workspace. Keep only these direct children:

- `~/matrix/projects` — active or runnable technical projects.
- `~/matrix/models` — model weights and model artifacts.
- `~/matrix/data` — technical datasets and durable application data used by projects.
- `~/matrix/media` — technical, design, and project media assets.
- `~/matrix/archive` — cold technical archives, not active working sets.
- `~/matrix/pi-worklogs` — Pi or agent worklogs and session state worth preserving.

Do not create new root folders inside `~/matrix` without asking.

Put active technical projects at:

```text
~/matrix/projects/<project-name>
```

Put AI projects at:

```text
~/matrix/projects/ai/<project-name>
```

Put downloaded model weights and artifacts under `~/matrix/models`, not in project repositories unless explicitly required.

Use `~/matrix/data` for project datasets and durable technical application data. The current notable dataset root is:

```text
~/matrix/data/arcane-codex-notion
```

Use `~/matrix/media` for technical and design assets, not personal photo libraries. Existing areas include `design` and `strategy`.

Use `~/matrix/archive` only for inactive technical material. Notable areas include `ibm`, `learning`, `legacy`, `projects`, `security-research`, `web`, and `mr-kambe-backup`. Skip `mr-kambe-backup` unless explicitly asked.

### Knowledge and documents

Use `~/codex` for Markdown notes, personal writing, relationship or timeline material, research notes, narratives, and durable thinking. Do not put large binary libraries or generated bulk media there unless explicitly asked.

Use `~/Documents` for official or durable reference documents such as legal, tax, career, education, books, and reference PDFs. Prefer subfolders such as:

```text
~/Documents/legal
~/Documents/career
~/Documents/education
~/Documents/books
```

### Personal media and temporary locations

- Photos and images belong in `~/Pictures`.
- Music, audio projects, and libraries belong in `~/Music`.
- Videos belong in `~/Videos`.
- `~/Downloads` and `~/Desktop` are temporary inboxes; move material out after processing it.

### Placement prohibitions

- Do not create `~/Projects`.
- Do not casually create new top-level folders in `$HOME`.
- Do not put active code directly under `~/matrix`; use `~/matrix/projects`.
- Do not put personal photos or music in `~/matrix`.
- Do not put large binary libraries in `~/codex`.
