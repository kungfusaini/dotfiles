{ pkgs }:

# Final, reviewed images are permanent repository sources, not remote fetches.
# See home/config/pegasus/ARTWORK.md for provenance and update instructions.
pkgs.runCommand "pegasus-curated-artwork" { } ''
  mkdir -p "$out"
  cp -r ${../config/pegasus/media}/. "$out/"
''
