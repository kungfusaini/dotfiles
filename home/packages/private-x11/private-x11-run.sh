# Run GUI probes without sharing the desktop's filesystem or abstract X sockets.
# This is test isolation, not an authorization or hostile-code security boundary.
if [[ $# -eq 0 ]]; then
  echo 'Usage: private-x11-run COMMAND [ARG ...]' >&2
  exit 2
fi
cache="${XDG_CACHE_HOME:-$HOME/.cache}/private-x11"
mkdir -p -- "$cache"
run=$(mktemp -d "$cache/run.XXXXXXXX")
chmod 700 "$run"
mkdir -m 700 "$run/home" "$run/runtime"
echo "private-x11-run: retained test artifacts: $run (inside: /tmp/work)" >&2
# --clearenv removes DISPLAY, Wayland/Hyprland tokens, session buses, audio
# routing and app-specific environment. No unsafe non-isolated fallback.
exec bwrap --die-with-parent --new-session --unshare-all \
  --ro-bind / / --proc /proc --dev /dev \
  --tmpfs /tmp --tmpfs /run/user --tmpfs /run/dbus \
  --bind "$run" /tmp/work --chdir "$PWD" --clearenv \
  --setenv PATH "$PATH" --setenv HOME /tmp/work/home \
  --setenv XDG_RUNTIME_DIR /tmp/work/runtime \
  --setenv XDG_CONFIG_HOME /tmp/work/home/.config \
  --setenv XDG_DATA_HOME /tmp/work/home/.local/share \
  --setenv XDG_STATE_HOME /tmp/work/home/.local/state \
  --setenv XDG_CACHE_HOME /tmp/work/home/.cache \
  --setenv TMPDIR /tmp --setenv LANG C.UTF-8 \
  --setenv QT_QPA_PLATFORM xcb --setenv GSETTINGS_BACKEND memory \
  dbus-run-session -- xvfb-run --server-args='-screen 0 1600x1000x24 -nolisten tcp' "$@"
