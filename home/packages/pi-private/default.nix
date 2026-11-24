{ runCommand, replaceVars, python3, bubblewrap, llama-cpp, stable-diffusion-cpp, mesa, pi }:
let
  # A dedicated variant: the normal Pi package and its interface are untouched.
  nativePi = pi.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [ ./native-chat.patch ];
  });
  imagePython = python3.withPackages (ps: [ ps.pillow ]);
  imageHelper = replaceVars ./image.py {
    sdServer = "${stable-diffusion-cpp.override { vulkanSupport = true; }}/bin/sd-server";
  };
  imageExtension = replaceVars ./private-image.ts {
    python = "${imagePython}/bin/python3";
    inherit imageHelper;
  };
  chat = replaceVars ./chat.py { inherit imageExtension; };
  launcher = replaceVars ./launcher.py {
    python = "${python3}/bin/python3";
    bwrap = "${bubblewrap}/bin/bwrap";
    inherit chat;
    pi = "${nativePi}/bin/pi";
    llama = "${llama-cpp.override { vulkanSupport = true; }}/bin/llama-server";
    intelVulkanIcd = "${mesa}/share/vulkan/icd.d/intel_icd.x86_64.json";
  };
in
runCommand "pi-private-0.1.0" { } ''
  mkdir -p "$out/bin" "$out/lib/pi-private"
  cp ${launcher} "$out/bin/pi-private"
  chmod +x "$out/bin/pi-private"
  cp ${chat} "$out/lib/pi-private/chat.py"
  cp ${imageHelper} "$out/lib/pi-private/image.py"
  cp ${imageExtension} "$out/lib/pi-private/private-image.ts"
''
