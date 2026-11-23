{ runCommand, replaceVars, python3, bubblewrap, llama-cpp, mesa, pi }:
let
  # A dedicated variant: the normal Pi package and its interface are untouched.
  nativePi = pi.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [ ./native-chat.patch ];
  });
  launcher = replaceVars ./launcher.py {
    python = "${python3}/bin/python3";
    bwrap = "${bubblewrap}/bin/bwrap";
    chat = "${./chat.py}";
    pi = "${nativePi}/bin/pi";
    llama = "${llama-cpp.override { vulkanSupport = true; }}/bin/llama-server";
    intelVulkanIcd = "${mesa}/share/vulkan/icd.d/intel_icd.x86_64.json";
  };
in
runCommand "pi-private-0.1.0" { } ''
  mkdir -p "$out/bin" "$out/lib/pi-private"
  cp ${launcher} "$out/bin/pi-private"
  chmod +x "$out/bin/pi-private"
  cp ${./chat.py} "$out/lib/pi-private/chat.py"
''
