# Vivaldi native input

`hosts/kirax1/modules/desktop/vivaldi.nix` uses Nixpkgs' supported
`commandLineArgs` override to enable native Wayland input for ordinary Vivaldi:

- `--ozone-platform=wayland`
- `--enable-wayland-ime`
- `--wayland-text-input-version=3`

System desktop actions and Home Manager consumers share this configured package.
Existing wrapper arguments and managed Google search policies are preserved.
No profile, startup-page or session-restoration preference is changed.

Flags take effect only for a newly started browser process. Forwarding a new
window request to an old process does not enable them. Deployment must not restart
Vivaldi automatically; agree a safe normal restart after saving ongoing work.
This package policy does not deploy the separate tablet-shell prototype or enable
its cold/first-window startup. Browser session restoration remains desktop-first.

Headless package/module contract check:

```sh
nix build --impure --no-link --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/vivaldi-startup.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```

The check preserves prior wrapper arguments/search policy and verifies that all
ordinary desktop actions reference the configured binary and its native flags.
The exact configured package was additionally exercised in Tablet Mode's isolated
native Vivaldi/Squeekboard regression, without fixture-injected IME flags; no live
browser/profile was used. Physical-device acceptance follows a separately agreed
normal browser restart.
