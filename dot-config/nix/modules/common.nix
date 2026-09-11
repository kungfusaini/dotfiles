{ pkgs, ... }:

let
  texConf = pkgs.texlive.combine {
    inherit (pkgs.texlive) scheme-small;
    inherit (pkgs.texlive)
      multirow
      latexmk
      contract
      enumitem
      cleveref
      # CV / resume packages
      titlesec
      marvosym
      fontawesome5
      microtype
      ;
  };

  codex-imagegen-cli = pkgs.python3Packages.buildPythonApplication rec {
    pname = "codex-imagegen-cli";
    version = "0.1.0-unstable-2026-06-09";
    pyproject = true;

    patches = [ ../codex-imagegen-style-generate.patch ];

    src = pkgs.fetchFromGitHub {
      owner = "jdmnk";
      repo = "codex-imagegen-cli";
      rev = "a739870aa9d600cfd0c382b6c06f38d0b1f5108b";
      hash = "sha256-uKAJJQ0G/pmAk1WX0w0SWtQv4YS+KoSyVtOl+FTnFFw=";
    };

    build-system = with pkgs.python3Packages; [
      hatchling
    ];

    dependencies = with pkgs.python3Packages; [
      pillow
    ];

    nativeCheckInputs = with pkgs.python3Packages; [
      pytestCheckHook
    ];

    meta = {
      description = "Scriptable image generation CLI using Codex ChatGPT auth";
      homepage = "https://github.com/jdmnk/codex-imagegen-cli";
      license = pkgs.lib.licenses.asl20;
      mainProgram = "codex-imagegen";
    };
  };
in
{
  nixpkgs.config.allowUnfree = true;

  environment.systemPackages = with pkgs; [
    azure-cli
    atuin
    bat
    biome
    bitwarden-desktop
    bun
    cmake
    # Codex is installed only to provide `codex login` auth for codex-imagegen-cli.
    codex
    codex-imagegen-cli
    cowsay
    direnv
    docker_29
    fastfetch
    ffmpeg
    fortune
    fzf
    harper
    htop
    hugo
    kitty
    marksman
    mkcert
    neovim
    netlify-cli
    nil
    nix-direnv
    nix-search-cli
    obsidian
    pdftk
    pyenv
    sioyek
    sox
    spotify
    starship
    stow
    tailscale
    taskwarrior3
    taskwarrior-tui
    telegram-desktop
    terraform
    texConf
    timewarrior
    tldr
    tmux
    tree
    tree-sitter
    unrar
    vscode
    yazi
    zoxide
  ];

  fonts.packages = with pkgs; [
    nerd-fonts.profont
  ];

  nix.settings.experimental-features = "nix-command flakes";
  nix.optimise.automatic = true;

  nix.gc = {
    automatic = true;
    options = "--delete-older-than 30d";
  };

  programs.zsh.enable = true;
  services.openssh.enable = true;
}
