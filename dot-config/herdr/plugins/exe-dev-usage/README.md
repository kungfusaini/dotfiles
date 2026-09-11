# exe.dev Usage

Shows a separate Herdr plugin pane with live exe.dev VM resource usage.

Toggle the panel with `prefix+v` or manually:

```sh
node ~/.config/herdr/plugins/exe-dev-usage/usage.mjs toggle
```

The panel displays:

- actual account usage from `ssh exe.dev billing usage --json`, including pooled billed filesystem disk usage vs included disk quota
- VM count and bandwidth usage vs account limits
- plan limits such as per-VM max CPU/RAM
- current per-VM CPU/RAM/filesystem usage from VM stats

It polls `ssh exe.dev ls --json` plus `ssh exe.dev stat --json <vm>` about once per minute while the panel is open.
