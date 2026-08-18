# Gruvbox Dark

A warm, retro-computing dark theme based on the visual language of `sumeetsaini.com`, with the expressive restraint of Arcane Codex. It should feel tactile, focused, and human—not neon, cyberpunk, or terminal cosplay.

## Visual character

- Warm charcoal surfaces rather than neutral black.
- Cream foregrounds rather than pure white.
- Orange is the single product accent; red, yellow, and green remain semantic state colors.
- Compact geometry, mono-forward typography, and hierarchy through surface shifts.
- No glow, gradients, glass effects, or gray card outlines.

## Color tokens

| Token | Value | Use |
|---|---:|---|
| `canvas` | `#1d2021` | Deep app/page background |
| `surface` | `#282828` | Main work surface |
| `surface-raised` | `#3c3836` | Menus, selected rows, grouped regions |
| `surface-active` | `#504945` | Hover/pressed surfaces and strong separators |
| `surface-muted` | `#665c54` | Non-text decoration only |
| `text` | `#ebdbb2` | Body text and headings |
| `text-strong` | `#fbf1c7` | High-emphasis text |
| `accent` | `#fe8019` | Primary actions, indicators, focus, large-bold accent text |
| `accent-deep` | `#d65d03` | Active fills or decoration; not small text |
| `danger` | `#fb4934` | Errors and destructive states only |
| `warning` | `#fabd2f` | Warnings and focus fallback only |
| `success` | `#b8bb26` | Success state only |
| `focus` | `#fabd2f` | Focus-visible ring/indicator |

### Contrast rule

- Use `text` or `text-strong` for normal-size readable copy and links.
- Orange/red may label large bold headings or act as non-text indicators, fills, icons, and underlines.
- Do not use dark orange or red for small body text. A small link should stay cream and gain an orange underline or adjacent indicator.
- Never communicate status by color alone.

## Typography

- Preferred interface face: `ProFontIIx`, `ui-monospace`, `SFMono-Regular`, monospace.
- Use mono for controls, labels, navigation, metadata, and code.
- Long-form prose may use the project’s established readable body face while retaining mono for interface chrome.
- An ornamental display face such as Arcane Codex’s Eagle Lake is a brand-specific extension, not part of this generic theme.

## Spacing and shape

- Base spacing unit: `8px`; allow `4px` compact internals.
- Radius: `4px` controls and media, `8px` menus/dialogs/contained regions.
- Prefer square or lightly rounded geometry; avoid pills unless semantically required.

## Elevation

- `none`: canvas and main work surface.
- `sm`: move one step along the Gruvbox surface ramp; no shadow.
- `md`: raised surface plus one named shadow for menus/popovers.
- `lg`: raised surface plus one stronger named shadow for dialogs.

Dark-theme hierarchy should come primarily from `canvas → surface → surface-raised → surface-active`, not borders or repeated shadows.

## Interaction

- Hover: cream-to-orange indicator change or one-step surface shift on hover-capable pointers.
- Focus-visible: yellow focus indicator, clearly separated from hover and selection.
- Active: one-step darker/lighter surface shift or brief `scale(.97)` feedback.
- Disabled: remove accent affordance but retain readable cream text where a label must remain legible.
- Motion: direct and restrained, generally 120–200ms; use transform/opacity/color and honor reduced motion.
- A terminal cursor blink or typewriter reveal is allowed only when it supports the product concept, never as a default flourish.

## Avoid

- Pure black backgrounds or pure white text.
- Neon orange/red glow, cyberpunk decoration, scanlines, and fake terminal chrome.
- Using every Gruvbox hue at once; orange remains the product accent.
- Red as the generic accent. Reserve Arcane Codex’s red treatment for an explicitly branded variant.
- Borders around every region, large rounded cards, and shadow texture.
