{ config, pkgs, ... }:

let
  modelDiscovery = pkgs.callPackage ../packages/pi-model-discovery { };
  browserAutomation = pkgs.callPackage ../packages/pi-browser { };
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
  home.packages = [ modelDiscovery browserAutomation pkgs.python3 pkgs.curl ];

  systemd.user.services.pi-model-discovery = {
    Unit.Description = "Check the authenticated Codex model catalog without invoking models";
    Service = {
      Type = "oneshot";
      ExecStart = "${modelDiscovery}/bin/pi-model-discovery check";
      Environment = [
        "XDG_CONFIG_HOME=${config.xdg.configHome}"
        "XDG_STATE_HOME=${config.xdg.stateHome}"
        "PI_CODING_AGENT_DIR=${config.xdg.configHome}/pi/agent"
      ];
      UMask = "0077";
      Nice = 19;
      MemoryMax = "128M";
      TasksMax = 8;
      TimeoutStartSec = 60;
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "strict";
      ProtectHome = "read-only";
      ReadWritePaths = [ "${config.xdg.stateHome}/pi-model-discovery" ];
      RestrictSUIDSGID = true;
      LockPersonality = true;
      RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    };
  };
  systemd.user.timers.pi-model-discovery = {
    Unit.Description = "Check for Codex model catalog changes daily";
    Timer = {
      OnCalendar = "daily";
      Persistent = true;
      RandomizedDelaySec = 300;
      WakeSystem = false;
    };
    Install.WantedBy = [ "timers.target" ];
  };
  systemd.user.tmpfiles.rules = [
    "d ${config.xdg.stateHome}/pi-model-discovery 0700 - - -"
  ];

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
  xdg.configFile."pi/agent/skills/browser/SKILL.md".source = ../config/pi/skills/browser/SKILL.md;
  xdg.configFile."pi/agent/skills/gemini-share-capture/SKILL.md" = {
    source = ../config/pi/skills/gemini-share-capture/SKILL.md;
    force = true; # Replace the pre-existing unmanaged skill during migration.
  };
  xdg.configFile."pi/agent/skills/gemini-share-capture/scripts/extract-gemini-share.py" = {
    source = ../config/pi/skills/gemini-share-capture/scripts/extract-gemini-share.py;
    force = true;
  };
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
