---
name: workstream
description: Probe, open, join, resume, return, collect, and close persistent Git-worktree Pi workers. Use only when the user explicitly wants an isolated Git worktree or worker session. Never use for Project Object streams shown in the project picker; those use project_stream_create.
---

# Workstream

Use `scripts/workstream.py` relative to this skill directory for deterministic lifecycle operations.

A probe is a cheap, read-only investigation owned by the coordinator. A workstream is a persistent worker session allocated by the coordinator and then directed privately by the user.

This skill is not the Project Object stream system. If a project-attached user asks for a “stream under this project,” a stream in the picker, or a project workspace, do not use this skill; use `project_stream_create`.

## Core model

A workstream has only three durable artifacts:

- `metadata.ini`: machine identity and lifecycle state.
- `brief.md`: a compact starting contract for the worker.
- `return.md`: created only when the user explicitly requests a return.

Do not copy coordinator transcripts, raw probe reports, exhaustive file inventories, or speculative requirements into the worker brief. The worker should build context through repository exploration and direct collaboration with the user.

There is no live worker-to-coordinator reporting channel.

## Coordinator role

### Probe

Use a probe to answer one allocation or feasibility question before opening implementation workstreams.

```bash
python scripts/workstream.py probe \
  --repo /absolute/repository/path \
  --question "Where is completed-forecast selection state owned?" \
  --decision "Whether graph navigation can be an independent workstream" \
  --scope "frontend graph and report surfaces" \
  --budget "Inspect the smallest relevant set of files"
```

A probe is non-persistent, read-only, has no branch or worktree, and returns concise evidence to the coordinator. Compress only material findings into a later worker brief.

Use `--dry-run` to inspect the generated probe command and prompt without launching Pi.

### Open

1. Confirm the repository, base ref, short ID, profile, and compact brief.
2. Check the current branch and worktree state. Do not modify or clean unrelated changes.
3. Run:

```bash
python scripts/workstream.py open \
  --repo /absolute/repository/path \
  --base main \
  --id short-slug \
  --profile coding \
  --title "Short title" \
  --goal "The outcome to deliver" \
  --done "First observable completion condition" \
  --done "Second observable completion condition" \
  --guardrail "Important boundary or non-goal" \
  --start "Relevant path, symbol, command, or compact probe conclusion" \
  --review "How the user will inspect the result"
```

Use `--profile ui` when the worker needs a running interface. This reserves a local port and includes it in the brief.

4. Report the workspace, branch, state directory, session ID, port if any, first-launch command, and exact-resume command.
5. Start the worker only when the user asks. Prefer a separate visible terminal for interactive collaboration.

### Collect

Run:

```bash
python scripts/workstream.py show --state <state-directory-or-id>
```

Then inspect the returned commit and diff. Do not merge, cherry-pick, push, close, delete, or remove anything without explicit user approval.

### List

```bash
python scripts/workstream.py list
```

### Close

Only after explicit approval:

```bash
python scripts/workstream.py close --state <state-directory-or-id>
```

Close refuses dirty worktrees, removes the worktree, and preserves the branch.

## Worker role

### Join

When invoked with `join <state-directory>`:

1. Read `metadata.ini` and `brief.md` from the state directory.
2. Verify the current directory, branch, and Pi session ID match the recorded workstream.
3. Work only in that worktree. Do not merge or push.
4. Read repository instructions and explore the repository as needed rather than asking for a larger preload.
5. Treat the brief as the starting contract. The user's later instructions are the active working context.
6. If a user request crosses a guardrail or may conflict with another stream, warn the user locally and ask how to proceed. Do not contact or report to the coordinator.
7. For a UI profile, start the real development server on the reserved port and give the user the review URL as soon as it is usable. If a static preview is necessary, disclose that clearly.

### Return

Return only when the user explicitly asks to return the workstream.

1. Run focused checks.
2. Commit one logical change. Never push or merge unless separately asked.
3. Ensure the worktree is clean.
4. Run:

```bash
python scripts/workstream.py return \
  --state <state-directory> \
  --summary "What changed" \
  --checks "Commands and observed results" \
  --review "URL, file, command, or artifact" \
  --integration "Material scope changes, interface effects, conflicts, or none"
```

5. Tell the user the workstream ID, branch, commit, state directory, and the phrase `collect <id>`.

If blocked, use `--result blocked` and explain the blocker in `--integration`. Do not claim completion with a dirty worktree.

## Profiles

- `coding`: isolated Git worktree, persistent Pi session, commit, and focused verification.
- `ui`: `coding` plus a reserved port, running review surface, and exact review URL.

Keep the lifecycle small. Add machinery only after a real workstream demonstrates the need.
