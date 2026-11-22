---
name: codex-imagegen
description: Generate or edit images with codex_imagegen, including emoji, icons, illustrations and visual variations. For generated transparent emoji, automatically normalize visible artwork bounds and padding before delivery, while preserving raw originals and exact provenance.
compatibility: Requires the installed codex_imagegen tool and pi-normalize-emoji command. Generation uses the user's existing Codex login; never inspect its credential files.
---

# Codex image generation

Use the `codex_imagegen` tool for generation/editing, not the CLI through bash. Respect the agreed scope and image-generation limits; avoid rapid parallel requests. Use concise literal subject prompts and no text unless requested. A failed named-character request may be retried as an original character described by traits, but record the fallback honestly and never label it as the requested likeness.

## Installed tool interface

The tool accepts `prompt`, optional `images` (up to five absolute reference paths), `count` (1–4), `size`, `quality`, and `output`. It has no `preset`, `styleImage`, `background`, `mode`, or `display` parameter. Use a supplied image through `images`, explicitly identifying whether it is a style-only reference. Do not invent parameters from another extension version.

Set an explicit task-appropriate output path: private project media stays in the project's private data directory; personal images belong in Pictures. Never put private assets/prompts in a public code repository. Save generation output to a fresh raw filename, not over an original or a previously accepted image. The current wrapper overwrites its output path, so check that the raw destination is unused first.

## Emoji visual language

Unless the user specifies otherwise, use `assets/emoji-style-reference.png` beside this skill as a **style-only** image reference. This is the original public emoji reference sheet from [pi-codex-imagegen at revision 5aa8d0e](https://github.com/kungfusaini/pi-codex-imagegen/tree/5aa8d0eaf7f0d20c072c6fb67af73704106eef86/presets/emoji), not a subject/composition to reproduce. Resolve the path relative to this skill's directory.

A compact prompt core:

> An emoji of [specific subject]. Use the attached sheet only as an emoji STYLE reference, not its subjects or layout. One simple platform emoji, rounded shallow 3D forms, broad colour blocks, soft shading, bold silhouette readable at 32px. Centred with balanced padding. No scenery, tiny details, realistic texture, lettering or watermark. Output one emoji only.

Prefer a single clear silhouette and a few essential forms, not product-render detail, elaborate scenes, surface texture or decorative framing. Preserve the requested subject; do not silently substitute a generic symbol. Requested dimensions/background are not evidence of actual dimensions/transparency—inspect the result.

## Required automatic emoji finishing

For **every generated transparent emoji**, finish these steps within the approved generation task before presenting it as complete. No separate request to normalize is needed. This is a skill workflow, not a claim that the backend/tool itself crops its raw output.

1. Preserve the raw tool output unchanged.
2. Run the packaged helper on that raw original, using a **new** normalized PNG path:

   ```sh
   pi-normalize-emoji /absolute/path/subject-raw.png /absolute/path/subject.png
   ```

3. Keep the helper's JSON report alongside the exact generation prompt/tool/parameters. It records source/output SHA256, visible bounds and the transformation. Deliver/assign the normalized derivative, not the padded raw file, and use that same derivative in galleries/previews. Keep the raw source linked in provenance.
4. Inspect the normalized result at 32px on light and dark backgrounds. Check the entire silhouette, fine distinguishing features, soft edges and centring. For a batch, compare a labelled contact sheet so equal canvases also have consistent visible scale. Do not stretch shapes or equalize pixel area at the expense of proportions; narrow subjects naturally retain space on their short axis.

The helper uses Pillow's alpha-channel bounds after ignoring near-transparent noise below **16/255**, retains a small nearby feather, scales proportionally to about **90% of the square canvas on the longest visible axis**, and centres the visible silhouette. Default canvas: 1024px; `--size` supports 32–4096px. It never overwrites a destination or original. A normal nonzero-alpha trim is insufficient: nearly invisible scattered pixels can keep the actual subject tiny even when the nominal crop looks filled. Do not use whole-image `-trim` as a substitute or fix inconsistent asset padding with page-specific CSS.

Opaque, wholly transparent, animated or extremely faint inputs are rejected deliberately. Do not erase white, black, pale or translucent subject parts with a colour-key guess. If real transparency/matting is needed, diagnose and establish that first within the approved task; then normalize. If a faint/atmospheric subject or intentional framing makes the standard unsuitable, preserve it and disclose the exception rather than silently cropping away meaningful art. Do not apply emoji normalization to arbitrary photographs, banners or illustrations.

## Provenance and handoff

Record the exact prompt actually sent, actual tool, reference source/hash when used, raw-output hash and normalization report. Report an image-model identity only if the backend actually provides it; otherwise leave it unknown. Newly written/reconstructed prompts are not historical originals. Optional project-specific credits must use that project's existing private metadata/viewer contract, not a parallel implementation. Do not assign assets, change galleries or publish beyond the approved scope.

Return the final normalized path(s) concisely. Do not auto-open viewers or use global input; browser/app placement and any manual interaction follow the inherited guidance.
