{ lib, python3, runCommand, makeWrapper }:
let
  python = python3.withPackages (ps: [ ps.dbus-python ]);
in
runCommand "agent-lid-sleep" {
  nativeBuildInputs = [ makeWrapper ];
  meta.description = "Defer lid-triggered sleep until tracked Pi agents settle";
  meta.platforms = lib.platforms.linux;
} ''
  PYTHONPATH=${./.} ${python}/bin/python -m unittest discover -s ${./tests} -v
  mkdir -p "$out/lib" "$out/bin"
  cp ${./agent_lid_sleep.py} "$out/lib/agent_lid_sleep.py"
  makeWrapper ${python}/bin/python "$out/bin/agent-lid-sleep" \
    --add-flags "$out/lib/agent_lid_sleep.py"
''
