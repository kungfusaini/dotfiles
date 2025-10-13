test -z "$TMUX" && (tmux attach || tmux new-session)

# Run fastfetch only in new tmux windows (not panes)
if [[ -n "$TMUX" ]]; then
    # Check if this is the first pane in the window
    if [[ $(tmux display-message -p '#{window_panes}') -eq 1 ]]; then
        # Check if fastfetch hasn't run in this window yet
        # if [[ -z "$FASTFETCH_RAN" ]]; then
            fastfetch
            # export FASTFETCH_RAN=1
        # fi
    fi
fi

