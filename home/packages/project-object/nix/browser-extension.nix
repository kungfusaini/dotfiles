{ runCommand }:
runCommand "project-object-browser-extension-1.0.0" {} ''
  mkdir -p "$out"
  cp ${../integrations/browser/manifest.json} "$out/manifest.json"
  cp ${../integrations/browser/background.js} "$out/background.js"
''
