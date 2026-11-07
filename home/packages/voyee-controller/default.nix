{ writeShellApplication, python3 }:
writeShellApplication {
  name = "voyee-controller-setup";
  runtimeInputs = [ python3 ];
  text = ''
    exec python3 ${./setup.py} "$@"
  '';
}
