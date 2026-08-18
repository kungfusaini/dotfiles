# UI Craft themes

Themes are ordinary Markdown files that describe visual direction. They are guidance overlays, not framework-specific stylesheets and not replacements for product requirements or accessibility checks.

## Supplying a theme

Give the agent any one of:

- a bundled name such as `default` or `gruvbox-dark`
- a local Markdown file path
- pasted Markdown theme content

A theme may be detailed or sparse. Useful sections include visual character, color tokens, typography, spacing/shape, elevation, interaction, motion, and things to avoid. There is no required frontmatter or rigid schema.

Existing project tokens and components fill any gaps first; map the theme’s intent into them rather than creating a second competing system. When the project has no system, missing guidance inherits from [`default.md`](default.md).

## Bundled themes

- [`default.md`](default.md) — quiet neutral light product baseline
- [`gruvbox-dark.md`](gruvbox-dark.md) — warm Gruvbox dark, cream text, orange accent, mono-forward typography

## Minimal custom example

```markdown
# Field Notes

Warm paper surfaces, dark olive text, and rust as the only accent.
Use a readable serif for prose and a compact sans-serif for controls.
Prefer square geometry, hairline rules, and no shadows.
Motion should be nearly imperceptible.
```

The agent keeps omitted details from the existing project system, falls back to the default only where needed, checks contrast and interaction states, and records any consequential interpretation it had to make.
