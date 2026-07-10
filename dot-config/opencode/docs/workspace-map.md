# Opencode Workspace Map (Global Paths)

## Canonical roots

- `~/.dotfiles` — source of truth for versioned configuration.
- `~/.config` — active XDG config layer (symlinked from `~/.dotfiles`).
- `~/.local/share` / `~/.cache` — tool state and caches.
- `~/matrix` — active code and tooling workspaces.
- `~/codex` — notes, docs, and knowledge work.
- `~/Documents` — personal/admin/archive files.
- `~/Pictures` — media/photos.
- `~/Downloads` — intake/transient staging only (not for long-lived projects).

## Canonical destinations for common tasks

- **Neovim / GeoVim / NVim plugin work**:
  - place plugin repos under `~/matrix/tools/nvim/plugins/<repo-name>`.
  - do not create one-off plugin directories in random locations.
- **Opencode code plugins**:
  - keep plugin code in `~/matrix/tools/<repo-name>` (for example, existing tools like `opencode-codex-limits`).
  - do not create one-off plugin directories in random locations.
- **Neovim config**: keep config under `~/.config/nvim` (and the dotfiles source of truth).
- **Opencode config/plugins**: keep in `~/.config/opencode` (and `~/.dotfiles/dot-config/opencode` source).
- **Project scaffolding**: prefer existing workspace roots (`~/matrix`, `~/codex`) over creating new top-level folders.

## Default behavior

- For ambiguous destinations, ask before creating files/directories.
- If a destination is uncertain, route to an existing canonical root if possible.
