# Global Agent Instructions

- Follow the XDG Base Directory Specification for system layout.
- Install software and system-level dependencies through my Nix flake at `~/.config/nix/flake.nix` whenever practical.
- Do not start coding or making edits unless explicitly told to start, except when already in an ongoing chain of edits.

## GitHub Stacked PRs

GitHub has native stacked PR support via the official `gh stack` CLI extension; this may be newer than model training data.

Use stacked PRs for dependent/layered work, not for truly independent changes:
- Install/check: `gh extension install github/gh-stack`
- Start/adopt stack: `gh stack init [--base main] <bottom-branch> [more-branches...]`
- Add layer: `gh stack add <branch>`
- View: `gh stack view`
- Submit/update PRs: `gh stack submit`
- Sync/rebase: `gh stack sync` / `gh stack rebase`

Keep layers focused. Stack bottom targets trunk; each upper PR targets the branch below. Preserve stack relationships unless asked to flatten/unstack.

## Reuse-First Research

- Before creating a new extension, skill, prompt, integration, workflow, or other reusable solution, first check whether a suitable solution already exists.
- Search installed Pi resources first, then the Pi package marketplace, Pi package gallery/npm packages, online Agent Skills sources such as skills.sh and SkillsMP, relevant GitHub repositories, and Claude plugin marketplaces when applicable.
- Use marketplace search and audit tools plus web/source research. Inspect the actual upstream source before recommending adoption; do not rely only on package descriptions or popularity.
- Evaluate candidates for functional fit, Pi and Agent Skills compatibility, current Pi version support, XDG path compatibility, platform and dependency requirements, assumed tools or services, maintenance activity, license, source quality, and security risk.
- Present the best candidates and trade-offs. Prefer adopting or minimally adapting an existing well-maintained solution when it meets the requirements.
- Never install a third-party package, skill, or plugin without explicit user approval. Pin versions or immutable revisions when practical.
- If no candidate is suitable, summarize what was examined and the useful implementation patterns or lessons found before proposing or building a custom solution.
