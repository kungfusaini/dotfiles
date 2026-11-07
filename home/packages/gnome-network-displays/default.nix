{ gnome-network-displays, python3 }:

gnome-network-displays.overrideAttrs (old: {
  patches = (old.patches or [ ]) ++ [ ./receiver-first.patch ];
  nativeCheckInputs = (old.nativeCheckInputs or [ ]) ++ [ python3 ];
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 ${./tests/check_receiver_first.py} \
      --source "$NIX_BUILD_TOP/$sourceRoot/src/app/nd-window.c" --probe ${./tests/receiver_first.c}
    runHook postCheck
  '';
  passthru = (old.passthru or { }) // { receiverFirst = true; };
})
