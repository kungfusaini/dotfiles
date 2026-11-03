{ pkgs, ... }:

let
  modelModePolicy = builtins.fromJSON (builtins.readFile ../config/pi/model-modes.json);
  defaultModelMode = builtins.head (builtins.filter (mode: mode.id == modelModePolicy.default) modelModePolicy.modes);

  codex-imagegen = pkgs.python3Packages.buildPythonApplication {
    pname = "codex-imagegen-cli";
    version = "0.2.0";
    pyproject = true;

    src = pkgs.fetchFromGitHub {
      owner = "jdmnk";
      repo = "codex-imagegen-cli";
      rev = "bf126f9052723a93ed2dada138df08b66d10d560";
      hash = "sha256-ZnSDWmTCg5jONUz9VoMm51vNGL86nFp8Uya9ob6ezS4=";
    };

    postPatch = ''
      substituteInPlace pyproject.toml \
        --replace-fail 'hatchling>=1.32.0,<1.33' 'hatchling>=1.29.0,<1.33'
    '';

    build-system = [ pkgs.python3Packages.hatchling ];
    dependencies = [ pkgs.python3Packages.pillow ];
  };
in
{
  xdg.configFile."pi/agent/bin/codex".source = "${pkgs.codex}/bin/codex";
  xdg.configFile."pi/agent/bin/codex-imagegen".source = "${codex-imagegen}/bin/codex-imagegen";
  xdg.configFile."pi/agent/AGENTS.md".source = ../config/pi/AGENTS.md;
  xdg.configFile."pi/agent/extensions/chatid.ts".source = ../config/pi/extensions/chatid.ts;
  xdg.configFile."pi/agent/extensions/command-terminal.ts".source = ../config/pi/extensions/command-terminal.ts;
  xdg.configFile."pi/agent/extensions/codex-imagegen.ts".source = ../config/pi/extensions/codex-imagegen.ts;
  xdg.configFile."pi/agent/extensions/model-modes.ts".source = ../config/pi/extensions/model-modes.ts;
  xdg.configFile."pi/agent/extensions/nanogpt.ts".source = ../config/pi/extensions/nanogpt.ts;
  xdg.configFile."pi/agent/extensions/reload-all.ts".source = ../config/pi/extensions/reload-all.ts;
  xdg.configFile."pi/agent/extensions/review.ts".source = ../config/pi/extensions/review.ts;
  xdg.configFile."pi/agent/skills/nanogpt/SKILL.md".source = ../config/pi/skills/nanogpt/SKILL.md;
  xdg.configFile."pi/agent/skills/workstream/SKILL.md".source = ../config/pi/skills/workstream/SKILL.md;
  xdg.configFile."pi/agent/model-modes.json".source = ../config/pi/model-modes.json;

  xdg.configFile."pi/agent/settings.json".text = builtins.toJSON {
    lastChangelogVersion = "0.87.1";
    theme = "dark";
    defaultProvider = defaultModelMode.provider;
    defaultModel = defaultModelMode.model;
    defaultThinkingLevel = defaultModelMode.thinkingLevel;
    packages = [
      "npm:pi-web-access"
    ];
  };
}
