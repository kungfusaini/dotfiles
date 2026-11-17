# Only the native tablet adapter launches this variant. Unmarked instances keep
# upstream desktop behavior; no forked theme engine or duplicate launcher UI.
{ pegasus-frontend }:
pegasus-frontend.overrideAttrs (old: {
  patches = (old.patches or []) ++ [ ./retain-tablet-frontend.patch ];
})
