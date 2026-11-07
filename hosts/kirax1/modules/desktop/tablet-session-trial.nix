{ pkgs, lib, ... }:
let
  trial = pkgs.callPackage ../../packages/tablet-session-trial.nix {};
  controller = "${trial.controller}/bin/tablet-session-trial";
  greetdConfig = (pkgs.formats.toml {}).generate "tablet-trial-greetd.toml" {
    terminal = { vt = 8; switch = true; };
    general = { source_profile = false; runfile = "/run/tablet-session-trial/initial-session"; };
    initial_session = { command = "${trial.session}/bin/tablet-session-trial-session"; user = "tablet-trial"; };
    # Session exit returns to the laptop rather than silently starting another
    # tablet session. The root return unit has a fixed, verified destination.
    default_session = {
      command = "${pkgs.systemd}/bin/systemctl --no-block start tablet-session-trial-return.service; ${pkgs.coreutils}/bin/sleep infinity";
      user = "tablet-trial";
    };
  };
in {
  # Deliberately not a default desktop or a boot-started service. No fold hook.
  users.users.tablet-trial = {
    isNormalUser = true;
    description = "Isolated Plasma Mobile feasibility trial";
    home = "/var/lib/tablet-session-trial-home";
    createHome = true;
    homeMode = "0700";
    hashedPassword = "!";
    extraGroups = [];
    packages = [ trial.environment trial.session ];
  };
  environment.systemPackages = [ trial.controller ];

  systemd.services.tablet-session-trial = {
    description = "Opt-in isolated Plasma Mobile session on tty8";
    # Do not use Conflicts=getty: systemd would stop an occupied login before
    # ExecStartPre could reject it. Both controller and unit preflight refuse it.
    after = [ "systemd-user-sessions.service" ];
    restartIfChanged = false;
    environment.XDG_SESSION_TYPE = "wayland";
    serviceConfig = {
      ExecStartPre = "${controller} check-vt";
      ExecStart = "${pkgs.greetd}/bin/greetd --config ${greetdConfig}";
      ExecStartPost = "${controller} ready";
      ExecStopPost = "${controller} return";
      RuntimeDirectory = "tablet-session-trial";
      RuntimeDirectoryMode = "0700";
      KillMode = "mixed";
      IgnoreSIGPIPE = false;
      SendSIGHUP = true;
      KeyringMode = "shared";
      TimeoutStartSec = 75;
      TimeoutStopSec = 15;
      Restart = "no";
    };
  };
  systemd.services.tablet-session-trial-return = {
    description = "Return to the verified saved laptop session";
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${controller} return";
    };
  };
  # No shell, arbitrary arguments, session ID, unit name or auth bypass is
  # delegated. This account can only request the fixed return operation.
  security.polkit.extraConfig = lib.mkAfter ''
    polkit.addRule(function(action, subject) {
      if (action.id === "org.freedesktop.systemd1.manage-units" &&
          subject.user === "tablet-trial" && subject.local && subject.active &&
          action.lookup("unit") === "tablet-session-trial-return.service" &&
          action.lookup("verb") === "start") {
        return polkit.Result.YES;
      }
    });
  '';
}
