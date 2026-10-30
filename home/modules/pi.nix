{ pkgs, ... }:

let
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
  xdg.configFile."pi/agent/extensions/chatid.ts".source = ../config/pi/extensions/chatid.ts;
  xdg.configFile."pi/agent/extensions/codex-imagegen.ts".source = ../config/pi/extensions/codex-imagegen.ts;
  xdg.configFile."pi/agent/extensions/nanogpt.ts".source = ../config/pi/extensions/nanogpt.ts;
  xdg.configFile."pi/agent/extensions/review.ts".source = ../config/pi/extensions/review.ts;
  xdg.configFile."pi/agent/skills/nanogpt/SKILL.md".source = ../config/pi/skills/nanogpt/SKILL.md;

  xdg.configFile."pi/agent/settings.json".text = builtins.toJSON {
    lastChangelogVersion = "0.87.1";
    theme = "dark";
    defaultProvider = "openai-codex";
    defaultModel = "gpt-5.6-sol";
    packages = [
      "npm:pi-web-access"
    ];
  };
}
