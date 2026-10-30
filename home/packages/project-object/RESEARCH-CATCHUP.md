# Research: Catching up on a project

Date: 2026-10-14

## Question

How have other tools approached the problem of returning to a project after time away, understanding what happened, and resuming work across coding-agent sessions?

## Summary

There is no single established solution for a system-wide project catch-up spanning desktop windows, tasks, notes, worklogs, agents, and multiple repositories. Existing projects solve narrower parts of the problem.

The strongest recurring pattern is **layered, progressively disclosed context**:

1. a small current-status briefing;
2. active tasks, streams, and handoffs;
3. recent activity and decisions;
4. durable project knowledge;
5. raw transcripts and event history available only when more detail is needed.

Tools that simply restore a transcript help resume one conversation, but they do not explain the state of a whole project. Tools that retain every event need summaries, indexing, or tiered storage to avoid overwhelming both humans and agents.

## Relevant projects

### 1. CatchUp

Source: <https://github.com/wilbeibi/catchup>

CatchUp reads local sessions from many coding agents—including Pi, Claude Code, Codex, OpenCode, Cursor, and others—and renders them as clean Markdown. It can search old sessions and hand a session from one agent to another.

Useful ideas:

- tool-independent access to agent session history;
- local-first operation;
- search across projects and agents;
- clean session digests;
- explicit handoff to another agent.

Limitations for this project:

- centered on one session at a time;
- does not merge concurrent histories;
- does not model project tasks, streams, desktop state, or a project-level current truth.

### 2. sessions

Source: <https://github.com/nicknisi/sessions>

`sessions` builds one index over Claude Code, Codex, Pi, and OpenCode transcripts. It provides a `/context` skill and `get_context_primer` operation intended to answer “what was I doing here?” It also generates bounded session digests, project activity summaries, and explanations connecting code changes to prior agent sessions.

Useful ideas:

- one index across agent tools;
- repo-scoped context primer;
- recent sessions shown in detail, older sessions reduced to headlines;
- targeted expansion rather than loading entire transcripts;
- provenance linking summaries back to sessions;
- explicit human triage before mined facts become durable memory.

Limitations:

- repository identity is the main scope;
- it reconstructs from agent transcripts rather than representing the complete project;
- desktop, notes, non-code streams, and live application state remain outside it.

### 3. Agent Context Kit

Source: <https://github.com/siudajakub/agent-context-kit>

Agent Context Kit separates memory by how quickly it changes:

| Layer | Intended lifetime | Example |
|---|---|---|
| Durable knowledge | Months | Rules and architecture |
| Current truth | Days or weeks | A dated, verified project-status snapshot |
| In-flight context | Hours or a day | Active session worklogs and next steps |
| Awareness | Current session | Automatically injected summaries of parallel work |

Its session lifecycle folds durable facts into the current project status and deletes completed in-flight worklogs.

Useful ideas:

- current truth is separate from history and backlog;
- active worklogs answer what is happening now;
- context has an explicit lifecycle;
- completed temporary context is pruned;
- parallel sessions receive awareness without loading every detail.

Limitations:

- repository-local Markdown convention;
- relies on agents following a protocol;
- no system-wide project or desktop model;
- the project is very new and has little adoption.

### 4. agent-work-mem

Source: <https://github.com/daystar7777/agent-work-mem>

This project uses Markdown and an append-only work log shared across agent vendors. It divides history into hot, warm, and cold tiers:

- recent events remain in a small work log;
- older events move into dated archives;
- long periods can be compressed into explicit digests;
- an index directs agents to relevant older material.

It detects unfinished work by finding a start event without a matching end event.

Useful ideas:

- append-only multi-agent activity log;
- explicit agent identity on events;
- unfinished-work detection;
- bounded hot context with indexed history;
- optional human-readable browsing through Obsidian.

Limitations:

- convention rather than enforced state;
- agents can omit or incorrectly write events;
- shared append-only files require care under concurrent or multi-machine use;
- it records agent work rather than the full project environment.

### 5. ProjectMem

Source: <https://github.com/riponcm/projectmem>

ProjectMem stores typed events such as issues, attempts, fixes, decisions, and notes. Its `pjm brief` command provides a one-screen answer to “where was I?” containing active warnings, potentially stale memories, open issues, recent decisions, stack-specific problems, and summary metrics.

Useful ideas:

- typed events are more useful than undifferentiated transcripts;
- project intent/plans are kept separate from the record of what actually happened;
- stale memories are flagged rather than silently trusted or deleted;
- old decisions can be superseded while preserving history;
- raw event logs are distilled into bounded summaries instead of being sent directly to an agent;
- every summary can retain provenance to underlying events.

Limitations:

- focused on coding repositories and agent judgment;
- MCP and memory machinery may be heavier than this project needs;
- does not include desktop or live multi-agent workspace state.

### 6. agent-handover

Source: <https://github.com/hikari716/agent-handover>

Agent Handover uses three Markdown layers: dated session notes, an overwritten current-state file, and periodic archives. Handover steps are checkpointed so a crash cannot leave an apparently complete but partially written handoff.

Useful ideas:

- “where are we now?” is a distinct artifact from chronological notes;
- writing a catch-up state should be crash-safe;
- local files remain the source of truth;
- remote or semantic memory can be an optional accelerator rather than a dependency.

Limitations:

- session handoff rather than project-wide coordination;
- early-stage project with little adoption.

### 7. Beads

Source: <https://github.com/gastownhall/beads>

Beads is a mature structured task and dependency graph for coding agents. `bd prime` gives agents workflow context and persistent memories; `bd ready` identifies work with no unresolved blockers. It supports hierarchical tasks and compacts old completed work.

Useful ideas:

- task state and dependencies should be structured rather than inferred from prose;
- “what can be acted on now?” is a useful catch-up view;
- historical closed work can be compacted;
- task/project memory can remain agent-independent.

Limitations:

- primarily an issue tracker and agent memory system;
- does not represent broader project context or desktop state;
- adopting its complete data model would impose substantial machinery.

### 8. Claude-Mem

Source: <https://github.com/thedotmack/claude-mem>

Claude-Mem automatically captures agent tool activity, generates semantic summaries, and injects relevant observations into later sessions. It supports progressive disclosure, search, citations, and several agent integrations.

Useful ideas:

- automatic capture reduces reliance on agents remembering to write handoffs;
- progressive disclosure keeps initial context small;
- summaries should link back to source observations;
- sensitive activity needs explicit exclusion controls.

Limitations:

- primarily an agent-memory product rather than a human project overview;
- more infrastructure and semantic processing than a simple worklog;
- automatically inferred memory may not match the user’s intended project structure.

## What appears to work across these systems

### Separate kinds of truth

The most convincing systems do not treat one giant log as project context. They distinguish:

- what the project is;
- what is true now;
- what is actively being worked on;
- what recently happened;
- what was learned or decided;
- the raw evidence behind those summaries.

### Keep the first view small

A catch-up command should not begin by replaying months of events. Existing systems use a primer, brief, current-state snapshot, or recent-work tail, then provide paths into deeper history.

### Preserve provenance

Generated summaries become more trustworthy when each claim can be expanded back to a worklog entry, task, agent session, commit, or decision.

### Treat stale context explicitly

A stored fact may stop being true. ProjectMem’s approach—marking it stale or superseded while retaining history—is safer than silently trusting it or deleting it.

### Make promotion deliberate

Several systems separate temporary session observations from durable knowledge. This aligns with the interview’s emerging requirement that stream details should not automatically pollute project-level context.

### Combine state with history

A chronological log answers “what happened?” but not necessarily “what should I do now?” A useful catch-up needs both a current snapshot and access to history.

## A possible catch-up shape to discuss later

This is not a decided specification. It is a synthesis of the recurring patterns:

```text
Project: Elijah

Needs attention
- Agents waiting for input
- Blocked or failed work

Where things stand
- Short current project summary
- Active streams and one-line state for each

What changed
- Important activity since the project was last visited
- Recent decisions and completed work

What is next
- Ready tasks, blockers, and explicit next steps

Resume
- Relevant agent, window, stream, note, or task to open

Evidence
- Links to the underlying worklogs, sessions, tasks, commits, and documents
```

The strongest lesson is that a future `catchup` command should likely be a **project-level composition of existing authoritative records**, not a new free-form summary that becomes another competing source of truth.
