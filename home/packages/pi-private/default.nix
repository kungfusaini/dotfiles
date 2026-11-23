{ runCommand, replaceVars, python3, bubblewrap, llama-cpp, pi }:
let
  launcher = replaceVars ./launcher.py {
    python = "${python3}/bin/python3";
    bwrap = "${bubblewrap}/bin/bwrap";
    chat = "${./chat.py}";
    pi = "${pi}/bin/pi";
    llama = "${llama-cpp}/bin/llama-server";
  };
in
runCommand "pi-private-0.1.0" { } ''
  mkdir -p "$out/bin" "$out/lib/pi-private"
  cp ${launcher} "$out/bin/pi-private"
  chmod +x "$out/bin/pi-private"
  cp ${./chat.py} "$out/lib/pi-private/chat.py"
''
