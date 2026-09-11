{ self, ... }:

{
  # Reverse SSH tunnel LaunchAgent
  launchd.user.agents.reverse-ssh-tunnel = {
    command = "/usr/bin/ssh -N -R 0.0.0.0:2222:localhost:22 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -i /Users/sumeet/.ssh/id_hetzner root@49.12.43.116";
    serviceConfig = {
      KeepAlive = true;
      RunAtLoad = true;
      StandardOutPath = "/Users/sumeet/.local/share/reverse-tunnel.out.log";
      StandardErrorPath = "/Users/sumeet/.local/share/reverse-tunnel.err.log";
      WorkingDirectory = "/Users/sumeet";
    };
  };

  # Set Git commit hash for darwin-version.
  system.configurationRevision = self.rev or self.dirtyRev or null;

  # Used for backwards compatibility; read the changelog before changing.
  system.stateVersion = 6;

  # Required by Homebrew activation, which runs as root.
  system.primaryUser = "sumeet";

  users.users.sumeet = {
    name = "sumeet";
    home = "/Users/sumeet";
    openssh.authorizedKeys.keys = [
      "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHykhzDDev6Af58WECNPyAs6+5d/CKBAyUg9A80NI2zP kira@flipper"
    ];
  };

  nix-homebrew = {
    enable = true;
    user = "sumeet";
  };

  nixpkgs.hostPlatform = "x86_64-darwin";
}
