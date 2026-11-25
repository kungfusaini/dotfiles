# Pure policy compiler. Mako applies criteria in file order, so keep this output
# after presentation settings. Sender identities are routing hints, not security
# principals: any local notification client can claim an app-name.
{ lib, registry, modes }:
let
  entries = lib.concatMap (entry: map (match: { inherit (entry) category; inherit match; }) entry.matches) registry;
  criteria = match: lib.concatStringsSep " " (lib.mapAttrsToList (key: value: "${key}=${builtins.toJSON value}") match);
  keys = map (entry: criteria entry.match) entries;
  validFields = [ "app-name" "desktop-entry" "category" "urgency" ];
  validMatch = match:
    builtins.isAttrs match && match != { }
    && (match ? "app-name" || match ? "desktop-entry")
    && lib.all (key: builtins.elem key validFields && builtins.isString match.${key} && match.${key} != ""
      && builtins.match ".*[\n\r].*" match.${key} == null) (builtins.attrNames match);
  deny = ''
    invisible=true
    history=false
    default-timeout=1
    ignore-timeout=true
  '';
  allow = entry: ''
    invisible=false
    history=${if entry.category == "navigation" then "false" else "true"}
    default-timeout=${if entry.category == "navigation" then "1500" else "5000"}
    ignore-timeout=true
  '';
  section = name: settings: "[${name}]\n${settings}\n";
  rules = mode: allowed: lib.concatMapStrings (entry:
    lib.optionalString (builtins.elem entry.category allowed)
      (section (lib.optionalString (mode != null) "mode=${mode} " + criteria entry.match) (allow entry))
  ) entries;
in
assert lib.assertMsg (lib.all (entry: entry ? category && entry ? matches && entry.matches != [ ]) registry)
  "Notification registrations require a category and nonempty matches";
assert lib.assertMsg (lib.all (entry: builtins.elem entry.category modes.all || entry.category == "muted") registry)
  "Unknown notification category";
assert lib.assertMsg (lib.all (entry: validMatch entry.match) entries)
  "Invalid notification match: use a nonempty explicit app-name or desktop-entry";
assert lib.assertMsg (builtins.length keys == builtins.length (lib.unique keys))
  "Duplicate notification registration";
assert lib.assertMsg (lib.all (mode: lib.all (category: builtins.elem category modes.all) modes.${mode}) (builtins.attrNames modes))
  "Unknown category in notification mode";
# Baseline denies unknown sources even in All. Hidden sources expire immediately
# without history, so changing modes cannot replay suppressed conversations.
section "" deny
+ rules null modes.all
+ section "mode=no-contact" deny
+ rules "no-contact" modes.no-contact
+ section "mode=do-not-disturb" deny
+ rules "do-not-disturb" modes.do-not-disturb
+ lib.concatMapStrings (entry: lib.optionalString (entry.category == "muted") (section (criteria entry.match) deny)) entries
