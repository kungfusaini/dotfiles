{ pi-coding-agent }:

pi-coding-agent.overrideAttrs (old: {
  # Upstream 0.87.1 reparses streaming Markdown on every delta and redraws
  # long transcripts at up to 60 fps. Bound display-only work to 10 fps.
  # Keyboard input and final messages retain immediate rendering.
  patches = (old.patches or [ ]) ++ [
    ./coalesce-rendering.patch
    ./model-mode-ui.patch
  ];
})
