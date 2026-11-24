# grill-me for Pi

Adapted from Matt Pocock's MIT-licensed skills at revision
`abeeaf95660ba9e8b7c753eb38f441ca707a8823`:

- https://github.com/mattpocock/skills/blob/abeeaf95660ba9e8b7c753eb38f441ca707a8823/skills/productivity/grill-me/SKILL.md
- https://github.com/mattpocock/skills/blob/abeeaf95660ba9e8b7c753eb38f441ca707a8823/skills/productivity/grilling/SKILL.md
- Usage guidance: https://www.aihero.dev/skills-grill-me

The upstream entry point calls a Skill tool that Pi does not expose. This
adaptation bundles its companion grilling instructions into an explicitly
invoked skill. Fact-finding uses available read-only tools rather than requiring
a general-purpose sub-agent tool. Statelessness, user-owned scope and prototype
boundaries follow the linked usage guidance; implementation remains subject to
the normal approval rules.

The managed prompt template adds `/grill-me [topic]`; `/skill:grill-me [topic]`
also works. Neither command starts implementation. Prefer a fresh conversation.
The full upstream MIT notice is retained in `LICENSE`.
