{ joycond }:

# Reuse upstream's combining/rumble implementation, but never take over Pro
# Controllers: their native Steam identity and custom mappings must survive.
joycond.overrideAttrs (old: {
  pname = "ashlyn-joycond";
  postPatch = (old.postPatch or "") + ''
    substituteInPlace src/virt_ctlr_combined.cpp \
      --replace-fail 'Nintendo Switch Combined Joy-Cons' "Ashlyn's Joy Cons"
  '';
  # Upstream's custom installPhase does not run postInstall hooks.
  installPhase = old.installPhase + ''
    install -m0644 ${./71-joycond-hidraw.rules} $out/etc/udev/rules.d/71-joycond-hidraw.rules
    install -m0644 ${./72-joycond.rules} $out/etc/udev/rules.d/72-joycond.rules
    install -m0644 ${./89-joycond.rules} $out/etc/udev/rules.d/89-joycond.rules
  '';
  installCheckPhase = ''
    runHook preInstallCheck
    cmp ${./71-joycond-hidraw.rules} $out/etc/udev/rules.d/71-joycond-hidraw.rules
    cmp ${./72-joycond.rules} $out/etc/udev/rules.d/72-joycond.rules
    cmp ${./89-joycond.rules} $out/etc/udev/rules.d/89-joycond.rules
    grep -aF "Ashlyn's Joy Cons" $out/bin/joycond > /dev/null
    runHook postInstallCheck
  '';
})
