# ~/.zshrc
# Auto-attach to Herdr for top-level interactive shells. Keep NO_TMUX_AUTO as a
# compatibility escape hatch while muscle memory/scripts catch up.
if [[ -z $HERDR_ENV && -z $NO_HERDR_AUTO && -z $NO_TMUX_AUTO && -t 1 ]] && command -v herdr >/dev/null 2>&1; then
    exec herdr
fi

# Logo on shell startup.
# Kitty PNG rendering currently fails inside Herdr panes, so only try it outside
# multiplexers or when explicitly forced with ZSH_FORCE_STARTUP_PNG=1.
if [[ -z "$ZSH_ASCII_SHOWN" ]]; then
    logo_png="$ZDOTDIR/assets/led.png"

    if [[ ((-z "$TMUX" && -z "$HERDR_ENV") || -n "$ZSH_FORCE_STARTUP_PNG") && -n "$KITTY_WINDOW_ID" && -r "$logo_png" && $+commands[kitten] -eq 1 ]]; then
        kitten icat --transfer-mode stream --align left --place 36x18@0x0 "$logo_png" 2>/dev/null
        repeat 18 print
    else
        print -r -- "                        ..'"
        print -r -- "                    ,xNMM."
        print -r -- "                  .OMMMMo"
        print -r -- "                  lMM\""
        print -r -- "        .;loddo:.  .olloddol;."
        print -r -- "      cKMMMMMMMMMMNWMMMMMMMMMM0:"
        print -r -- "    .KMMMMMMMMMMMMMMMMMMMMMMMWd."
        print -r -- "    XMMMMMMMMMMMMMMMMMMMMMMMX."
        print -r -- "   ;MMMMMMMMMMMMMMMMMMMMMMMM:"
        print -r -- "   :MMMMMMMMMMMMMMMMMMMMMMMM:"
        print -r -- "   .MMMMMMMMMMMMMMMMMMMMMMMMX."
        print -r -- "    kMMMMMMMMMMMMMMMMMMMMMMMMWd."
        print -r -- "    'XMMMMMMMMMMMMMMMMMMMMMMMMMMk"
        print -r -- "     'XMMMMMMMMMMMMMMMMMMMMMMMMK."
        print -r -- "       kMMMMMMMMMMMMMMMMMMMMMMd"
        print -r -- "        ;KMMMMMMMWXXWMMMMMMMk."
        print -r -- "          \"cooc*\"    \"*coo'\""
    fi

    unset logo_png
    export ZSH_ASCII_SHOWN=1
fi

