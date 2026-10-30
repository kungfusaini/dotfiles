---
name: init
description: Initialize a newly created Project Object project's or stream's minimal durable artifacts from the user's stated goal and current conversation. Use only when explicitly directed by the Project Object /init command.
disable-model-invocation: true
---

# Initialize a Project Object scope

This is a one-time, low-ceremony orientation pass for the attached project or stream. It establishes enough durable state to resume the scope later. It does not begin substantive work.

## Preconditions

1. Require `PROJECT_OBJECT_ID` and `PROJECT_OBJECT_HOME`. When `PROJECT_OBJECT_STREAM_ID` is present, also require `PROJECT_OBJECT_STREAM_HOME`.
2. Resolve paths relative to this skill directory.
3. Treat existing scope artifacts and worklog entries as context to preserve, not as a reason to refuse initialization.

## Determine the goal

Use the user's `/init` arguments and the active conversation as evidence. Read existing inherited instructions and immediately relevant repository documentation only when needed to avoid inventing facts.

If the attached scope's goal is still genuinely unclear, ask at most one concise clarifying question and make no changes yet. Otherwise initialize directly without presenting a lengthy questionnaire or draft ceremony.

## Write the minimum useful state

Modify artifacts owned by the attached scope only. For a stream, never edit project-level artifacts during initialization.

### `AGENTS.md`

When present, replace the `<!-- project-object:init-scope -->` placeholder with a concise objective, initial boundary, authoritative source, and any stable constraints or safety rules future agents must always receive. If the placeholder is already absent, preserve the existing guidance and make only the smallest addition needed to capture the stated goal. Keep it short because this file is injected into every attached session. Do not add temporary status, mutable figures, task detail, or a transcript summary.

Separate known facts from hypotheses. Do not claim that exploratory assumptions are established architecture, and never erase existing guidance merely to normalize the file.

### `TODO.md`

Use the existing `Now`, `Next`, and `Waiting` sections. Preserve existing tasks and merge roughly three to seven immediate, scope-owned actions without duplication. Prefer discovery and decision steps before implementation when the goal is exploratory. Put real external blockers under `Waiting`; do not duplicate completed history.

### `NOTES.md` and `plans/`

Leave them untouched by default. Use `NOTES.md` only when the user already supplied rough, changing, or unverified material worth retaining. Use `plans/` only for an actual detailed plan; do not create one merely because the directory exists.

### Worklog

Ensure the worklog records why the attached scope exists and its first next action. Reuse an existing accurate `start` entry rather than duplicating it; otherwise append one with `project_worklog_append`. Do not fabricate historical events. For a stream, do not set `projectAttention` during initialization unless the user explicitly identified an immediate parent-project concern.

## Finish atomically

After all intended artifact edits and the start worklog succeed, run:

```bash
python3 scripts/mark.py
```

This safely records that one-time initialization completed; it does not inspect or reject existing scope content. If marking fails, report it and stop. Never retry by overwriting artifacts.

Reply with only:

- the scope objective in one sentence;
- files changed;
- the first `Now` action and any `Waiting` blocker.

## Hard boundaries

- Do not SSH, call external services, modify repositories, run deployments, or begin implementation.
- Do not copy credentials, tokens, private keys, secret values, or sensitive command output into artifacts or worklogs.
- For stream initialization, do not edit project-level artifacts or automatically promote stream information.
- Do not rerun initialization after the one-time initialization marker has been written.
- Preserve and merge existing scope content; never erase it merely because it predates `/init`.
