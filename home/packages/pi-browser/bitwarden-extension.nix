{ lib, stdenvNoCC, fetchurl, unzip, python3 }:

stdenvNoCC.mkDerivation rec {
  pname = "pi-browser-bitwarden-extension";
  version = "2026.10.2";
  src = fetchurl {
    url = "https://github.com/bitwarden/clients/releases/download/browser-v${version}/dist-chrome-${version}.zip";
    hash = "sha256-LrxhJGouqCplxYm4SE4mpWeCU/pkdMJtxbanp/ysvaQ=";
  };
  nativeBuildInputs = [ unzip python3 ];
  unpackPhase = ''
    mkdir extension
    cd extension
    unzip -q "$src"
  '';
  # The upstream release archive omits the Web Store public key. Restoring that
  # public (not secret) identity keeps the official extension ID across store
  # paths and permits the existing Bitwarden Desktop native-messaging origin.
  buildPhase = ''
    ${python3}/bin/python3 - <<'PY'
    import base64, hashlib, json
    from pathlib import Path
    key = Path('${./bitwarden-public-key.txt}').read_text().strip()
    digest = hashlib.sha256(base64.b64decode(key, validate=True)).hexdigest()[:32]
    extension_id = "".join(chr(ord('a') + int(c, 16)) for c in digest)
    assert extension_id == 'nngceckbapebfimnlniiiahkandclblb', extension_id
    manifest = json.loads(Path('manifest.json').read_text())
    assert manifest['version'] == '${version}'
    assert manifest['manifest_version'] == 3
    assert manifest.get('key', key) == key
    assert 'nativeMessaging' in manifest.get('optional_permissions', [])
    manifest['key'] = key
    Path('manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    PY
  '';
  installPhase = ''
    mkdir -p "$out"
    cp -r . "$out/"
  '';
  meta = {
    description = "Pinned official Bitwarden browser extension for managed Vivaldi";
    homepage = "https://github.com/bitwarden/clients";
    license = [ lib.licenses.gpl3Only lib.licenses.unfree ];
    platforms = lib.platforms.linux;
  };
}
