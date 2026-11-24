# Longshot desktop integration

- Pegasus's **PC** collection runs `tablet-game-launch -- longshot-play`, not the update UI.
- The private game stays at `~/matrix/projects/longshot/game`. The entry is hidden if its binary is absent.
- `longshot-play` uses the same AppImage/FHS compatibility path verified with v3.2.0 on the Arc B390. It uses the installed game's binary, not a game in the Nix store.
- Each launch starts a non-blocking oneshot service. It checks the upstream stable-release API at most once per 24 hours, including offline attempts, and notifies once per newer stable version. It never downloads releases, runs remote commands, or rebuilds the game. State is under `$XDG_STATE_HOME/longshot-update-check`.
- **Longshot Launcher** in the applications menu opens the existing game folder for updates. Its signed v1.2.0 seed is copied to writable XDG data on first use so upstream self-updates can be retained. Nothing is installed automatically by the notification checker.
- Save and quit before requesting an update. Upstream rebuilds from the retained local game files, preserves saves/settings, and may prepare shaders again. Do not delete the game's `romfs` or `image.bin` to clean space. Linux saves live under `~/.local/share/longshot`; back them up before updates.
- The initial builder and launcher hashes were checked against upstream's ECDSA-signed SHA256SUMS before packaging. Only redistributable tools enter this repository/store; game files, generated code, saves and downloaded release state do not.
- Controller settings are intentionally untouched. No active game or Pegasus process is restarted by deployment.

Sources: [Longshot](https://git.magicbean.dev/MagicBeanDev/Longshot), [launcher](https://git.magicbean.dev/MagicBeanDev/LongshotLauncher), [updates and saves](https://git.magicbean.dev/MagicBeanDev/Longshot/src/tag/v3.2.0/docs/user/updates-and-saves.md).

Run focused offline tests:

```sh
cd home/packages/longshot
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
```
