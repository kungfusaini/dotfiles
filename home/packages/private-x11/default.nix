{ writeShellApplication, bubblewrap, coreutils, dbus, xvfb-run }:
writeShellApplication {
  name = "private-x11-run";
  runtimeInputs = [ bubblewrap coreutils dbus xvfb-run ];
  text = builtins.readFile ./private-x11-run.sh;
}
