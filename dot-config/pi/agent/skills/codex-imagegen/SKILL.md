---
name: codex-imagegen
description: Generate, edit, and display images from Pi using the local codex-imagegen CLI backed by the user's Codex/ChatGPT login. Use when the user asks Pi to create an image, make a picture, generate art/icons/illustrations, edit an existing image, use a reference image, or show generated output in the terminal.
compatibility: Requires codex-imagegen on PATH and a valid Codex ChatGPT login at ~/.codex/auth.json from `codex login`.
---

# Codex Image Generation

Use the local `codex-imagegen` wrapper to generate and edit images from Pi. This wrapper is installed via the user's Nix flake and automatically sets the Codex version compatibility environment.

## Before generating

1. If the user has not described the image clearly, ask for the missing creative direction only when it materially affects the output.
2. Prefer a concise, literal prompt. Add "no text" unless the user explicitly wants text in the image.
3. For user-visible test generations, use `--term` so generated images render inline in Kitty. With `--term`, the wrapper auto-adds `--force`, auto-creates an output path when missing, and displays every generated PNG/WebP path it sees.
4. For scripted or non-terminal generation, pass an explicit `--out` path and do not use `--term` unless the user asked to view output inline.

## Readiness check

If unsure whether setup is complete:

```bash
command -v codex-imagegen
codex-imagegen --version
test -f ~/.codex/auth.json && echo "codex auth exists"
```

If auth is missing, tell the user to run:

```bash
codex login
```

and choose ChatGPT login, not API-key login.

## Generate images

Use this for normal terminal-visible output:

```bash
codex-imagegen generate \
  --prompt "A simple friendly robot holding a small green plant, clean white background, soft cheerful illustration, no text" \
  --term
```

The wrapper will save to:

```text
~/Pictures/codex-imagegen/YYYYMMDD-HHMMSS.png
```

To generate several alternatives at once, use `--n`. With `--term`, the wrapper prints and displays each generated image inline:

```bash
codex-imagegen generate \
  --prompt "Four cute robot mascot variations, clean white background, soft cheerful illustration, no text" \
  --n 4 \
  --term
```

When `--n` is used with a base `--out`, upstream writes numbered files such as `robot-1.png`, `robot-2.png`, etc.

If the user specified a destination, include `--out`:

```bash
codex-imagegen generate \
  --prompt "..." \
  --out /path/to/output.png \
  --term
```

## Edit an image

Use one to five input images. Preserve the user's requested subject/style constraints.

```bash
codex-imagegen edit \
  --image /path/to/input.png \
  --prompt "Make this a warm pencil sketch while preserving the subject and composition, no text" \
  --out /path/to/edited.png \
  --term
```

For style references, use `--style-image` when appropriate:

```bash
codex-imagegen edit \
  --image /path/to/content.png \
  --style-image /path/to/style-reference.png \
  --prompt "Apply the visual style while preserving the main subject" \
  --out /path/to/output.png \
  --term
```

## Batch jobs

For batch work, write a JSONL file and use the upstream CLI's `batch` command. Do not add `--term` for batch unless the user only wants command output.

```bash
codex-imagegen batch --input jobs.jsonl
```

## Output handling

After generation, report the saved file path or paths clearly. If `--term` was used, every generated PNG/WebP path printed by the CLI should also render inline via Kitty's `icat` kitten.

## Caveats

- This uses an unofficial/private Codex/ChatGPT image backend through the local CLI. It can break if OpenAI changes the backend.
- Use only for the user's personal account/workflow. Do not automate a public image-generation service.
- Avoid rapid parallel generations; respect usage limits and failures.
