# Installation contract: immutable companion/host, unchanged normal browser and
# legacy entry routes until explicit native acceptance. No browser is opened.
{ pkgs, homeConfig, expectedBrowser }:
let
  lib = pkgs.lib;
  extension = homeConfig.xdg.dataFile."tablet-media-companion".source;
  manifest = homeConfig.xdg.configFile."vivaldi/NativeMessagingHosts/org.machine.tablet_media.json".source;
  watcher = builtins.head (builtins.filter (p: p.name == "tablet-fold-watch") homeConfig.home.packages);
in
assert !homeConfig.programs.tablet-native.automatic;
assert toString pkgs.vivaldi == toString expectedBrowser;
assert lib.hasInfix "tablet-chat start-home" homeConfig.xdg.desktopEntries.tablet-workspace.exec;
assert builtins.any (p: p.name == "tablet-native") homeConfig.home.packages;
pkgs.runCommand "tablet-native-install-contract" { nativeBuildInputs = [ pkgs.python3 ]; } ''
  python3 - ${extension}/manifest.json ${manifest} <<'PY'
import base64, hashlib, json, sys
extension = json.load(open(sys.argv[1]))
host = json.load(open(sys.argv[2]))
key = hashlib.sha256(base64.b64decode(extension['key'])).hexdigest()[:32]
identity = "".join(chr(ord('a') + int(c, 16)) for c in key)
assert identity == 'cfepbdnljmjhpbaoephifiehkdahpgll'
assert host['allowed_origins'] == ['chrome-extension://' + identity + '/']
assert host['type'] == 'stdio'
assert set(extension['permissions']) == {'nativeMessaging', 'scripting', 'storage'}
assert set(extension['host_permissions']) == {'http://*/*', 'https://*/*'}
assert extension['version'] == '0.2.0'
assert extension['content_scripts'][1]['matches'] == ['http://*/*', 'https://*/*']
assert extension['content_scripts'][1]['all_frames']
assert extension['content_scripts'][1]['match_origin_as_fallback']
assert extension.get('externally_connectable') is None
PY
  ${pkgs.gnugrep}/bin/grep -Fq -- '-tablet-fold-watch.py' ${watcher}/bin/tablet-fold-watch
  if ${pkgs.gnugrep}/bin/grep -Fq -- 'tablet-native watch-fold' ${watcher}/bin/tablet-fold-watch; then
    echo 'Native routing was enabled before acceptance' >&2
    exit 1
  fi
  touch "$out"
''
