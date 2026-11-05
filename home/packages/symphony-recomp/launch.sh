#!@shell@
set -euo pipefail

# All mutable game state stays outside the immutable application closure.
# Override the root for isolated tests or another legally owned disc library.
root="${SYMPHONY_RECOMP_DATA_ROOT:-$HOME/matrix/data/emulation}"
state="$root/games/symphony-recomp"
saves="$root/saves/symphony-recomp"
disc="$root/roms/ps1/Castlevania - Symphony of the Night (USA)/Castlevania - Symphony of the Night (USA).cue"

if [[ ! -f "$disc" ]]; then
    printf 'SymphonyRecomp requires your USA PS1 BIN/CUE dump at:\n%s\n' "$disc" >&2
    exit 1
fi
umask 077
mkdir -p "$state" "$saves"
# Seed once; never replace the player's settings or memory cards.
if [[ ! -e "$state/settings.json" ]]; then
    settings=$(@jq@ -n --arg disc "$disc" --arg saves "$saves" '{
        system: {
            discPath: $disc,
            cardA: {path: ($saves + "/carda.sav"), enabled: true},
            cardB: {path: ($saves + "/cardb.sav"), enabled: true}
        },
        options: {"updates.check_on_startup": false}
    }')
    (set -o noclobber; printf '%s\n' "$settings" > "$state/settings.json")
fi
# Keep the mod cache writable, but pin bundled source directories to this release.
# Never replace a user-installed directory or a link outside our package.
mkdir -p "$state/mods"
for bundled in @app@/mods/*; do
    target="$state/mods/${bundled##*/}"
    if [[ -L "$target" ]]; then
        case "$(readlink "$target")" in
            /nix/store/*/lib/symphony-recomp/mods/*) ln -sfn "$bundled" "$target" ;;
        esac
    elif [[ ! -e "$target" ]]; then
        ln -s "$bundled" "$target"
    fi
done
cd "$state"
exec @dotnet@ @app@/sotn.dll "$@"
