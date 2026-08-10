---
name: codex-imagegen
description: Generate and edit images from Pi using the upstream local codex-imagegen CLI backed by the user's Codex/ChatGPT login. Use when the user asks Pi to create an image, make a picture, generate art/icons/illustrations, edit an existing image, use a reference image, or save generated output.
compatibility: Requires codex-imagegen on PATH and a valid Codex ChatGPT login at ~/.codex/auth.json from `codex login`.
---

# Codex Image Generation

Use the upstream `codex-imagegen` CLI to generate and edit images from Pi. Do not assume custom wrapper flags exist.

## Before generating

1. If the user has not described the image clearly, ask for missing creative direction only when it materially affects the output.
2. Prefer a concise, literal prompt. Add "no text" unless the user explicitly wants text in the image.
3. Always pass an explicit `--out` path for `generate` and `edit`; upstream requires it.
4. Use `--force` when writing to an auto-created/test output path or when the user has asked to overwrite.
5. Do **not** use `--term`; upstream `codex-imagegen` does not support it. To display in Kitty after generation, run `kitty +kitten icat <path>` separately.
6. Until Codex in nixpkgs is new enough, prefix generation commands with `CODEX_IMAGEGEN_CODEX_VERSION=0.200.0` unless the user/environment explicitly overrides it.

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

Create an output directory and pass `--out` explicitly:

```bash
outdir="$HOME/Pictures/codex-imagegen/$(date +%Y%m%d-%H%M%S)-robot"
mkdir -p "$outdir"
CODEX_IMAGEGEN_CODEX_VERSION=0.200.0 codex-imagegen generate \
  --prompt "A simple friendly robot holding a small green plant, clean white background, soft cheerful illustration, no text" \
  --out "$outdir/robot.png" \
  --force
```

To generate several alternatives at once, use `--n`. Upstream writes numbered files such as `robot-1.png`, `robot-2.png`, etc. when needed:

```bash
outdir="$HOME/Pictures/codex-imagegen/$(date +%Y%m%d-%H%M%S)-robot-variations"
mkdir -p "$outdir"
CODEX_IMAGEGEN_CODEX_VERSION=0.200.0 codex-imagegen generate \
  --prompt "Four cute robot mascot variations, clean white background, soft cheerful illustration, no text" \
  --n 4 \
  --out "$outdir/robot.png" \
  --force
find "$outdir" -maxdepth 1 -type f -name '*.png' -print
```

## Display output in Kitty

After generation, display saved image paths separately:

```bash
kitty +kitten icat /path/to/output.png
```

For multiple outputs:

```bash
find "$outdir" -maxdepth 1 -type f \( -name '*.png' -o -name '*.webp' \) -print0 |
  while IFS= read -r -d '' img; do
    printf '\n%s\n' "$img"
    kitty +kitten icat "$img" || true
  done
```

## Edit an image

Use one to five input images. Preserve the user's requested subject/style constraints.

```bash
outdir="$HOME/Pictures/codex-imagegen/$(date +%Y%m%d-%H%M%S)-edit"
mkdir -p "$outdir"
CODEX_IMAGEGEN_CODEX_VERSION=0.200.0 codex-imagegen edit \
  --image /path/to/input.png \
  --prompt "Make this a warm pencil sketch while preserving the subject and composition, no text" \
  --out "$outdir/edited.png" \
  --force
```

For style references, use `--style-image` when appropriate:

```bash
CODEX_IMAGEGEN_CODEX_VERSION=0.200.0 codex-imagegen edit \
  --image /path/to/content.png \
  --style-image /path/to/style-reference.png \
  --prompt "Apply the visual style while preserving the main subject" \
  --out /path/to/output.png \
  --force
```

## Batch jobs

For batch work, write a JSONL file and use the upstream CLI's `batch` command.

```bash
CODEX_IMAGEGEN_CODEX_VERSION=0.200.0 codex-imagegen batch --input jobs.jsonl
```

## Output handling

After generation, report the saved file path or paths clearly. If the user asked to see the image in the terminal, display it with `kitty +kitten icat` after the files exist.

## Caveats

- This uses an unofficial/private Codex/ChatGPT image backend through the local CLI. It can break if OpenAI changes the backend.
- Use only for the user's personal account/workflow. Do not automate a public image-generation service.
- Avoid rapid parallel generations; respect usage limits and failures.
