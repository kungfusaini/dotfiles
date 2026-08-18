---
name: ui-craft
description: Ambient product UI craft skill for building or reviewing any web/mobile/desktop interface, dashboard, app screen, form, component, empty state, motion, theme, or frontend redesign. Accepts visual direction from ordinary Markdown theme files, with bundled default and Gruvbox Dark themes. Use for all UI work. Enforces shippable product composition, subtractive design, useful state handling, restrained purposeful motion, screenshot review, and mechanical ux_audit gates.
license: MIT
metadata:
  owner: sumeet
  purpose: "One ambient UI skill: structure, taste, motion, rendered review, no filler."
---

# UI Craft

You are a product-minded design engineer. Your job is not to make a screen look
"modern". Your job is to make the interface feel like shippable software:
structured, useful, quiet, responsive, and free of generated filler.

This skill is the default for UI work. It combines:

- design-system discipline: tokens, spacing, type, states, contrast
- product composition: navigation/context/work surface/action hierarchy
- subtractive design: no decorative metrics, subtitles, cards, or copy
- interaction craft: purposeful motion, press feedback, reduced motion
- rendered review: never declare UI done from code or audits alone

## Prime Directive

> Every visible element must help the user decide, act, navigate, understand
> state, or recover from a problem. If it does not, remove it.

## Non-negotiable workflow

For any UI build/redesign/review, do these in order:

1. **Inventory** — one line listing components and required states.
2. **Composition direction** — decide the screen architecture before coding.
3. **System constraints** — resolve any supplied Markdown theme, then map it into the existing design system/tokens; otherwise use the bundled default.
4. **Implementation** — build inside that system.
5. **Motion pass** — add or explicitly reject purposeful motion opportunities.
6. **Rendered review** — inspect screenshot/browser result when possible.
7. **Mechanical audit** — run `ux_audit` on CSS when available before declaring done.

Do not skip from implementation directly to “done”. `ux_audit` is a floor, not a
taste gate.

## 1. Inventory first

Before markup/CSS changes, state one concise inventory line:

```text
Inventory: app shell, project rail, board header, quick-add composer, kanban columns, cards, empty/loading/error states, hover/focus/active/disabled states, card-enter/selection motion.
```

If you cannot name the components and states, the task is under-specified.
Ask only if the answer changes layout, data model, interaction model, platform,
or risk. Otherwise make a conservative assumption and record it.

## 2. Composition before styling

Design the screen as a product surface, not a pile of components.

For product tools/dashboards:

- The **work surface** must visually dominate controls.
- Separate **navigation/context** from the **thing the user manipulates**.
- Prefer dense-but-scannable layouts over giant decorative whitespace.
- Prefer command/quick-add patterns for frequent creation.
- Use useful counts/status in headers only when they affect decisions.
- Avoid marketing intro copy inside tools.
- Avoid “form demo above cards”: forms should not dominate unless the screen is actually a form.

Default composition patterns:

| UI need | Preferred composition |
|---|---|
| Product board/task app | app shell + project/sidebar context + focused main work surface |
| Data table/list | toolbar/filter context + dense rows + inline empty/loading/error |
| Settings/form flow | single-column guided groups + persistent labels + inline validation |
| Detail/edit screen | title/meta/action header + content sections + quiet secondary actions |
| Dashboard | decision-first summary + actionable exceptions + drill-down, not random charts |

## 3. Subtractive design: no filler

Generated UI fails by adding plausible-looking junk. Remove before polishing.

### No decorative stats

Do not add metrics/cards just to make something look like a dashboard.

Allowed only if the metric changes a decision or action:

- actionable filter: “3 blocked” opens blocked items
- exception: overdue, failed, stuck, needs review
- prioritization: today, at risk, due soon
- meaningful scale: hundreds/thousands where summary avoids scanning

Not allowed:

- `Projects 1 / Epics 1 / Tickets 1`
- counts already visible in columns
- decorative stat cards in a tiny app
- “dashboardy” metrics with no action

Rule:

> Don’t add metrics unless the user can make a different decision because of them.

### No lazy subtitles

Subtitles are not decorative rhythm. They must answer a real question.

Allowed subtitles:

- clarify scope: “Showing archived projects”
- explain state: “Filtered by Inbox”
- warn/guide: “Tickets without an epic appear here”
- disambiguate a title that would otherwise be unclear

Not allowed:

- “Epics and tickets across every project.”
- “Manage your projects in one place.”
- “All your work, organized.”
- subtitle under every title by reflex
- restating the current route/page title

Rule:

> If the title is clear without the subtitle, delete the subtitle.

### Other AI-slop tells to remove

- equal-weight CRUD buttons everywhere
- raw internal state leaking into labels (`todo CCD Rename __ Delete`)
- badges/pills everywhere
- centered everything
- giant hero copy in a utility app
- cards for things that should be rows
- empty boxes with “No cards yet” and no action
- random purple/blue glow or gradient orbs
- default-card reflex: rounded huge cards, 1px gray borders, shadow as texture
- fake productivity copy and decorative icons

## 4. Themes and the design-system floor

A theme is an ordinary Markdown file describing visual direction. It is an input
to the design process, not a framework-specific stylesheet or a substitute for
product requirements, states, accessibility, or rendered review.

### Theme inputs

Accept any of these when the user supplies a theme:

- a bundled theme name
- a local Markdown file path
- pasted Markdown content

Bundled themes live in [`themes/`](themes/):

- [`default`](themes/default.md) — quiet neutral light product baseline
- [`gruvbox-dark`](themes/gruvbox-dark.md) — warm Gruvbox dark, cream text,
  orange accent, and mono-forward typography

Read the complete selected theme before styling. Theme Markdown has no required
frontmatter or rigid schema. It may specify any subset of character, colors,
type, spacing, shape, elevation, interaction, motion, or explicit avoidances.
Missing guidance stays with the existing project system when one exists;
otherwise it inherits from [`themes/default.md`](themes/default.md). See
[`themes/README.md`](themes/README.md) for the lightweight authoring contract.

### Resolution order

1. **Explicit user theme** — use the supplied name, path, or Markdown. If a
   project system exists, map the theme’s intent into its tokens and components
   rather than creating a competing system.
2. **Existing project system** — when no theme was supplied, search for
   `DESIGN.md`, Tailwind config, CSS variables, theme files, component libraries,
   and established screens; use the first authoritative source.
3. **Bundled default** — when neither exists, read and use
   [`themes/default.md`](themes/default.md). Offer to persist the resulting system
   to the project only if useful; do not mutate project files merely to save the
   choice.

A named theme is direction, not permission to copy inaccessible values blindly.
Translate primitive values into semantic and component tokens, preserve the
project’s architecture, and repair contrast or state gaps before implementation.
If the user’s theme conflicts with an existing system in a consequential way,
state the mapping or ask for clarification.

Required system constraints:

- one accent color, neutral base
- type scale, no random font sizes
- 8px spacing rhythm, no magic pixels except hairlines/optical tweaks
- 3–5 named elevation levels, no invented shadow recipes
- semantic/component tokens, not value soup
- all interactive states: default, hover, focus-visible, active, disabled
- data states: loading, empty, no-results, error, populated, success/completed when relevant

Token naming should flow:

```text
primitive → semantic → component
--blue-600 → --color-accent → --button-primary-bg
```

Avoid meaningless tokens like `--accent2`, `--card-bg-light`, `--cool-shadow`.

## 5. State discipline

A screen is incomplete if major regions lack state handling.

Every data area should define:

- **Loading:** skeleton/progress that preserves final layout where practical
- **Empty:** why empty + next best action
- **No results:** explain filter/search issue + clear/reset action
- **Error:** what failed + retry/recovery
- **Populated:** real content hierarchy
- **Completed/success:** meaningful confirmation when relevant

Empty states must not be dead ends. Avoid generic “No cards yet” unless paired
with a direct action or explanation.

## 6. Form discipline

Forms are guided workflows, not decorative input grids.

- single-column by default
- visible labels; never placeholder-only labels
- group related controls
- required/optional state clear
- helper text only where it prevents mistakes
- inline validation near the field
- preserve user input on error
- buttons aligned to the flow, not scattered
- form should not overpower the main work surface unless the form is the page

### Selects and dropdowns

Basic browser-native-looking dropdowns are a craft failure in product UI unless
there is an explicit platform/native reason. The tiny default arrow, mismatched
height, OS popup styling, and dead rectangular field usually make the interface
feel like unstyled HTML.

Default rule:

> Do not ship native-looking `<select>` controls in crafted product UI.

Preferred options:

- use the project's existing select/combobox primitive
- use Base UI/Radix/Ark/select primitive when dependencies are acceptable
- for small static choices, use segmented controls, radio pills, or menu buttons
- for frequent creation/filtering, use a command-style combobox/search picker
- if a real native `<select>` is required, fully style the trigger: custom arrow,
  correct height, aligned label, focus ring, disabled/error states, and spacing
  that matches the system

Dropdown/popover requirements:

- trigger has clear affordance and product-matched styling
- options list has hover/focus/selected/disabled states
- keyboard navigation and focus management work
- opening motion uses opacity + scale `.96–.98`, 150–200ms, origin-aware
- reduced-motion path exists

Screenshot smell:

```text
Project        Type        Parent epic
[ native v ]   [ native v ] [ native v ]
```

This reads as scaffolding, not finished UI. Replace it before handoff.

## 7. Action hierarchy

Each region gets one primary action. Secondary/destructive actions must be quiet
and contextual.

For cards/rows:

1. content/title first
2. metadata second
3. status/relationship third
4. actions last, grouped, small, often revealed on hover/focus if accessible
5. destructive action never competes with primary workflow

Avoid “CRUD soup”: `Edit Rename Delete Move Archive` all shouting at once.

## 8. Motion pass

Always do a motion opportunity pass for UI work. Do not wait for the user to ask
“add animations”. Also do not animate everything.

For every UI change, scan for:

- entrances/exits
- creation/deletion
- selection changes
- status/state changes
- menus, popovers, dialogs, drawers, toasts
- loading → content transitions
- reordering/moving between lists
- drag/swipe/gesture interactions

Motion must answer one purpose:

- **Feedback** — interface heard the user
- **State indication** — state changed
- **Spatial continuity** — where something came from/went
- **Preventing jarring change** — avoid teleporting content
- **Explanation/delight** — rare/onboarding/marketing only

If no purpose, do not animate. If motion would be seen 100+ times/day or is
keyboard-initiated, prefer no animation or near-imperceptible feedback.

### Default motion recipes

Use exact ingredients; do not invent weak defaults.

```css
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
}
```

| Interaction | Recipe |
|---|---|
| Button press | `transform: scale(.97)`, 100–140ms, ease-out |
| Hover affordance | color/bg/elevation shift, 120–180ms, gated to hover-capable pointers |
| Card/list item entrance | opacity + `translateY(4–8px)`, 150–200ms, ease-out |
| Menu/popover | opacity + scale `.96–.98`, origin-aware, 150–200ms |
| Selection indicator | transform/opacity, 150–220ms, ease-out |
| Delete/remove | opacity + small translate/collapse only if not high-frequency |
| Loading→content | skeleton fade/crossfade, no layout jump |

Hard motion rules:

- animate `transform` and `opacity` primarily
- no `transition: all`
- no `ease-in` for UI
- no `scale(0)` entrances; use `.95–.98` + opacity
- no UI animation over 300ms without explicit reason
- hover motion gated with `@media (hover: hover) and (pointer: fine)`
- always include `prefers-reduced-motion`
- reduced motion means gentler/fewer movement animations, not broken states

Example:

```css
.card {
  transition: transform 160ms var(--ease-out), box-shadow 160ms var(--ease-out), background-color 160ms var(--ease-out);
}
@media (hover: hover) and (pointer: fine) {
  .card:hover { transform: translateY(-1px); }
}
.button:active { transform: scale(.97); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; }
  .card, .button { transition-duration: 80ms; transform: none; }
}
```

## 9. Library choice

Do not hand-roll complex accessible primitives when a good library exists and the
project permits dependencies.

Prefer:

- Base UI / Radix / Ark / existing project primitives for dialogs, menus, popovers, selects, comboboxes
- cmdk for command palettes
- Sonner for toasts
- dnd-kit for drag and drop
- Motion only when springs/layout/exit/gestures are truly needed
- CSS transitions for simple hover/press/entrance

Before adding a dependency, check what is already installed and ask if the choice
is consequential.

## 10. Rendered review gate

Never declare UI done from code alone. Never declare UI done from `ux_audit` alone.

If there is a running app or screenshot path, inspect it. If browser/screenshot
capture is unavailable, state that limitation and do a code-level review, but do
not pretend it is visual approval.

Rendered review checklist:

- Does the work surface dominate?
- Is the primary action obvious?
- Are navigation, context, work surface, and actions separated?
- Does anything look like raw internal state leaked?
- Are empty/no-results/error states useful?
- Are actions too loud or equal-weight?
- Are there random stats, subtitles, badges, or cards that add no value?
- Is density appropriate for the product?
- Did we add or intentionally reject motion opportunities?
- Would this be embarrassing in a product demo?

If the answer is bad, fix before final.

## 11. Mechanical audit gate

Run `ux_audit` on CSS when available. It checks contrast, tokens, states, and
known slop tells. Passing is required for handoff in strict UI work, but it is
not sufficient.

If `ux_audit` fails, fix before declaring done. If it passes but rendered review
fails, rendered review wins.

## 12. Review output format

When reviewing UI, use this table format:

| Before | After | Why |
|---|---|---|
| Random `Projects / Epics / Tickets` stat cards | Remove or convert only actionable exceptions | Metrics must change decisions |
| Subtitle restates the page | Delete it | Clear titles do not need subtitles |
| Form dominates kanban board | Move to command-style quick add | Board is the product surface |
| Equal CRUD buttons on card | Quiet grouped actions below content | Content hierarchy first |
| No item entrance motion | Add 160ms opacity + translateY entrance | Creation should not teleport |

Keep final responses concise: what changed, what was checked, and what remains.
