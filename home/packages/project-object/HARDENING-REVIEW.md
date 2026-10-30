# Hardening Review

## Status

The findings in `INDEPENDENT-REVIEW.md` were addressed in commits `f3e36f3` and `5e82a74`.

Final implementation verdict: **ship**, with the explicitly accepted product constraint that human project names are literal Hyprland workspace names. The system guards collisions with live workspaces only; configured-but-inactive or future global workspace-name collisions remain the user's responsibility by design.

## Review rounds

Local independent read-only reviews were run after implementation. They identified and drove fixes for:

1. an incorrect standalone Home Manager package path;
2. same-root symlink aliases between project UUID homes and session trees;
3. Pi ancestor replacement races while opening `AGENTS.md`;
4. inconsistent Unicode name normalization;
5. post-replacement atomic-write failure semantics;
6. insufficient Home Manager evaluation coverage; and
7. a missing Python build/runtime dependency in the Nix package.

The final technical review found the registry, transaction, descriptor-pinning, tests, and packaging sound. Its only remaining objection was the human workspace-name policy, which is an intentional product decision rather than an unresolved implementation defect.

## Verification

`./scripts/test` passes 27 isolated tests and also:

- compiles all Python entry points;
- builds the Nix package;
- verifies store-pinned Python shebangs;
- evaluates the Home Manager module with the feature enabled; and
- runs Nix and Git whitespace checks.

`./scripts/run-isolated-demo` passes without connecting to live Hyprland or user input.

The complete NixOS system closure builds successfully. Home Manager activation installs immutable store references for:

- the Hyprland terminal command;
- the `Super+P` picker binding; and
- the Pi extension.

The live registry was migrated to remove legacy `projectHome`, and project data/state directories were verified as `0700` with the registry at `0600`.
