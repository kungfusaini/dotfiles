---
name: to-tickets
description: Break a plan, spec, issue, or the current conversation into tracer-bullet tickets with explicit blocking edges, then draft or publish them to the project-selected destination. Use when turning planned work into agent-grabbable tickets.
license: MIT
metadata:
  adapted-from: https://github.com/mattpocock/skills/blob/main/skills/engineering/to-tickets/SKILL.md
  adapted-from-license: MIT
disable-model-invocation: true
---

# To Tickets

Break a plan, spec, issue, or conversation into a set of **tickets** — tracer-bullet vertical slices, each declaring the tickets that **block** it.

This skill is tracker-agnostic. The ticket destination and triage/status vocabulary may be provided by project instructions. If not, ask the user before publishing.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments.

Check local project instructions for ticketing guidance before asking the user. Useful places include already-loaded system/project instructions, `AGENTS.md`, `CLAUDE.md`, `.agents/`, `.pi/`, `README.md`, or other repo docs that clearly define the project's tracker conventions.

Do not assume a tracker, label, status, project, team, milestone, or output directory unless it is present in the project instructions or the user explicitly chooses it.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests) — vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first

</vertical-slice-rules>

Give each ticket its **blocking edges** — the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change — rename a column, retype a shared symbol — whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket — green is promised only there.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct — does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?

Iterate until the user approves the breakdown.

Do not publish issues or write ticket files until the user has approved the breakdown.

### 5. Determine the ticket destination

Before publishing, determine where tickets should go:

1. Use project instructions if they specify a tracker or local ticket convention.
2. If no destination is specified, ask the user which destination to use.
3. If the destination is ambiguous, ask rather than guessing.
4. If publishing to an external tracker, confirm before creating or modifying remote issues.

Suggested destination choices:

- **Draft only** → return the approved ticket set in chat or as a single draft document, but do not create ticket files or tracker issues.
- **Local files** → write one file per ticket under the project-specified directory, or `.scratch/<feature-slug>/issues/<NN>-<slug>.md` if the user chooses local files and gives no other path.
- **GitHub Issues** → create one issue per ticket using `gh` if available and authenticated.
- **Linear** → create one issue per ticket only if the project/team/workspace and credentials are available or supplied by the user.
- **Other/custom** → ask for the exact command, API, path, or process to use.

The tickets are the same either way; only the shape of the blocking edges changes.

### 6. Publish the tickets

Publish only the approved tickets to the selected destination:

- **Draft only** → show the full approved ticket bodies in dependency order.
- **Local files** → write one file per ticket, numbered from `01` in dependency order (blockers first). Each file's "Blocked by" lists the numbers/titles it depends on. Use the per-ticket file template below — one ticket per file, never a single combined file unless the user selected draft-only or explicitly asked for one combined file.
- **A real issue tracker (GitHub, Linear, …)** → publish one issue per ticket in dependency order (blockers first) so each ticket's blocking edges can reference real identifiers. Use the platform's native blocking / sub-issue relationship where it has one; otherwise set each ticket's "Blocked by" to the blocking issues.

Apply triage labels/statuses only if project instructions or the user specify them. If no triage vocabulary is specified, use plain text status in the ticket body or ask the user.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<local-ticket-template>

# <NN> — <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective — not a layer-by-layer implementation list.

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None — can start immediately".

**Status:** <project-specified status/label, or "ready-for-agent" only if the user/project uses that vocabulary>

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

</local-ticket-template>

<issue-template>

## Parent

A reference to the parent issue on the tracker (if the source was an existing issue, otherwise omit this section).

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective — not layer-by-layer implementation.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- A reference to each blocking ticket, or "None — can start immediately".

</issue-template>

In either form, avoid specific file paths or code snippets — they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts — not a working demo, just the important bits.

## Attribution

This standalone Pi skill is adapted from Matt Pocock's `to-tickets` skill under the MIT License. See `NOTICE.md` in this skill directory.
