# Default

A quiet, light product theme for work that has no supplied theme or existing design system. It should feel practical, calm, and finished—not decorative.

## Visual character

- Neutral, daylight surfaces with crisp dark type.
- One clear blue accent used for actions and focus, never as decoration.
- Compact, readable layouts with restrained rounding.
- Hierarchy comes from spacing, typography, and surface shifts before borders or shadows.

## Color tokens

| Token | Value | Use |
|---|---:|---|
| `canvas` | `#f7f7f5` | Page and app background |
| `surface` | `#ffffff` | Primary work surface |
| `surface-raised` | `#ecece8` | Menus, selected rows, quiet grouped regions |
| `surface-active` | `#deded8` | Pressed and active states |
| `text` | `#171714` | Body text and headings |
| `text-secondary` | `#55554f` | Secondary copy that still must remain readable |
| `accent` | `#075fba` | Primary actions, links, selection, focus |
| `accent-strong` | `#064b91` | Hover/active accent state |
| `danger` | `#a52a2a` | Destructive actions and errors only |
| `focus` | `#075fba` | Focus-visible ring/indicator |

Use semantic status colors only when the product genuinely has those states. Do not turn them into decorative accents.

## Typography

- Interface and body: `Inter`, `ui-sans-serif`, `system-ui`, sans-serif.
- Code and machine values: `ui-monospace`, `SFMono-Regular`, monospace.
- Use the project’s existing fonts when present.
- Use a modular type scale and readable line lengths; avoid oversized utility-app headings.

## Spacing and shape

- Base spacing unit: `8px`; use half-steps only for compact control internals or optical correction.
- Radius: `4px` compact controls, `8px` menus/dialogs/contained regions.
- Avoid pill shapes unless the component semantics call for a pill, tag, or status.

## Elevation

- `none`: canvas and ordinary work surfaces.
- `sm`: surface-color shift only; preferred for rows and grouped content.
- `md`: named menu/popover shadow; use only for floating UI.
- `lg`: named dialog shadow; use only for modal UI.

Do not use shadows as texture. Separate with whitespace, then background shift, then elevation; use a border only when the boundary would otherwise be unclear.

## Interaction

- Hover: subtle accent or surface shift on hover-capable pointers.
- Focus-visible: unmistakable accent indicator with sufficient contrast.
- Active: brief surface shift or `scale(.97)` press feedback where appropriate.
- Disabled: preserve legibility while clearly removing affordance.
- Motion: 120–200ms, transform/opacity/color only, with reduced-motion support.

## Avoid

- Gradients, glows, glass effects, ornamental blobs, and decorative dashboards.
- Blue-tinted surfaces everywhere; the accent is for meaning, not atmosphere.
- Large radii, card piles, weak gray borders, and arbitrary shadows.
