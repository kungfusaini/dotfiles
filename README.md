# My Dotfiles

This repository contains my system configuration files, managed with GNU Stow. This approach addresses several common issues:
* Easy recovery from messed up configurations
* Quick experimentation without permanent installation
* Seamless system transitions
* Clean tracking and removal of software

## Setup

I use GNU [Stow](https://www.gnu.org/software/stow/) to manage dotfiles. To set up:
```bash
stow ~/dotfiles --dotfiles
```

While Nix Home Manager is an alternative, I find Stow simpler for managing a focused set of dotfiles.

## Configurations

### Window Manager
- **Aerospace** - Tiling window manager configuration (`dot-config/aerospace/`)

### Development Tools
- **Neovim** - Lua-based configuration with plugins, keybindings, and custom scripts (`dot-config/nvim/`)
- **Git** - Git configuration (`dot-config/git/`)
- **GitHub CLI** - gh configuration and hosts (`dot-config/gh/`)

### Terminal
- **Kitty** - Terminal emulator with themes, shortcuts, and quick access configs (`dot-config/kitty/`)
- **Starship** - Custom prompt configuration (`dot-config/starship/`)
- **ZSH** - Modular shell configuration with aliases, functions, and plugins (`dot-config/zsh/`)
- **Tmux** - Terminal multiplexer with status bar and keybindings (`dot-config/tmux/`)

### Productivity
- **Taskwarrior** - Task management with custom themes and hooks (`dot-config/task/`)
- **Timewarrior** - Time tracking configuration (`dot-config/timewarrior/`)
- **Atuin** - Shell history management (`dot-config/atuin/`)

### Utilities
- **Fastfetch** - System information tool configuration (`dot-config/fastfetch/`)
- **Karabiner-Elements** - Keyboard customization (`dot-config/karabiner/`)
- **Hammerspoon** - macOS automation framework (`dot-config/hammerspoon/`)
- **Raycast** - Launcher extensions (`dot-config/raycast/`)
- **Yazi** - File manager configuration (`dot-config/yazi/`)

### Applications
- **Obsidian** - Note-taking app configuration (`codex/dot-obsidian/`)
- **Sioyek** - PDF viewer preferences (`dot-config/sioyek/`)
- **Spotify Player** - CLI client configuration (`dot-config/spotify-player/`)
- **Stats** - macOS system monitor config (`stats/`)
- **Brave** - Browser bookmarks and extensions (`Library/Application Support/BraveSoftware/`)

### Graphics
- **Inkscape** - Vector graphics editor preferences (`dot-config/inkscape/`)

### Nix
- **Nix** - Declarative package management with flake configuration (`dot-config/nix/`)

### Miscellaneous
- **npm** - Node.js package manager configuration (`dot-config/npm/`)
- **Wallpapers** - Custom wallpaper collection (`wallpapers/`)
