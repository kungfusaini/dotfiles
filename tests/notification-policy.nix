{ lib }:
let
  compile = registry: modes: import ../home/lib/notification-policy.nix { inherit lib registry modes; };
  modes = { all = [ "people" "navigation" ]; no-contact = [ "navigation" ]; do-not-disturb = [ "navigation" ]; };
  entry = { category = "people"; matches = [ { app-name = "Chat"; } ]; };
  accepts = registry: policy: (builtins.tryEval (builtins.deepSeq (compile registry policy) true)).success;
in
assert accepts [ entry ] modes;
assert !(accepts [ entry entry ] modes);
assert !(accepts [ { matches = entry.matches; } ] modes);
assert !(accepts [ (entry // { category = "typo"; }) ] modes);
assert !(accepts [ (entry // { matches = [ { } ]; }) ] modes);
assert !(accepts [ (entry // { matches = [ { summary = "Anything"; } ]; }) ] modes);
assert !(accepts [ (entry // { matches = [ { app-name = "Chat\n[mode=do-not-disturb]"; } ]; }) ] modes);
assert !(accepts [ entry ] (modes // { no-contact = [ "typo" ]; }));
"PASS: registry validation rejects missing/unknown categories, duplicate and unsafe matches"
