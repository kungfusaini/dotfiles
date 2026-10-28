---
name: init
description: Initialize a newly created Project Object stream's minimal durable artifacts from the user's stated goal and current conversation. Use only when explicitly directed by the Project Object /init command.
disable-model-invocation: true
---

# Initialize a Project Object stream

This is a one-time, low-ceremony orientation pass. It establishes enough durable state to resume the stream later. It does not begin the substantive work.

## Preconditions

1. Require `PROJECT_OBJECT_ID`, `PROJECT_OBJECT_STREAM_ID`, and `PROJECT_OBJECT_STREAM_HOME`.
2. Resolve paths relative to this skill directory.
3. Run:

```bash
python3 scripts/guard.py check
```

If it refuses, stop immediately. Do not edit, merge, reset, or overwrite any artifact. Report the reason concisely.

## Determine the goal

Use the user's `/init` arguments and the active conversation as evidence. Read existing project and stream instructions plus immediately relevant repository documentation only when needed to avoid inventing facts.

If the stream goal is still genuinely unclear, ask at most one concise clarifying question and make no changes yet. Otherwise initialize directly without presenting a lengthy questionnaire or draft ceremony.

## Write the minimum useful state

Modify stream-owned artifacts only. Never edit project-level artifacts during initialization.

### `CONTEXT.md`

Keep it short. Record:

- the objective;
- the initial scope or discovery boundary;
- confirmed constraints.

Separate known facts from hypotheses. Do not summarize the whole transcript or claim that exploratory assumptions are established architecture.

### `STATUS.md`

Keep exactly the useful current boundary:

- `Current:` what the stream is starting with;
- `Next:` the first concrete action;
- `Blocked:` a real known blocker, or `None known.`

### `TODO.md`

Create roughly three to seven immediate, stream-owned actions. Prefer discovery and decision steps before implementation when the goal is exploratory.

### `NOTES.md` and `plans/`

Leave them untouched by default. Use them only when the user already supplied material that clearly belongs there. Do not create a plan merely because the directory exists.

### `AGENTS.md`

Leave the generated guide intact by default. Append one short `## Operational guardrails` section only when the work has an obvious safety boundary that future agents must receive automatically—for example read-only remote discovery before any production changes. Do not add temporary status or task detail.

### Worklog

Append one `start` entry with `project_worklog_append`. Summarize why the stream exists and state the first next action. Do not fabricate historical events. Do not set `projectAttention` during initialization unless the user explicitly identified an immediate parent-project concern.

## Finish atomically

After all intended artifact edits and the start worklog succeed, run:

```bash
python3 scripts/guard.py mark
```

If marking fails, report it and stop. Never retry by overwriting artifacts.

Reply with only:

- the stream objective in one sentence;
- files changed;
- current, next, and blocked state.

## Hard boundaries

- Do not SSH, call external services, modify repositories, run deployments, or begin implementation.
- Do not copy credentials, tokens, private keys, secret values, or sensitive command output into artifacts or worklogs.
- Do not edit project-level artifacts or automatically promote stream information.
- Do not rerun initialization against populated or previously initialized artifacts.
