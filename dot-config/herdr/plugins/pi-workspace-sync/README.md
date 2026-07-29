# Pi Workspace Sync

Durably reconciles Pi projects and Herdr spaces through:

```text
~/.local/share/herdr-pi/workspaces.json
```

Identity is based on the canonical project root path. Pi project ids and Herdr workspace ids are stored as rediscoverable links, so restarts can rebuild the relationship from roots/cwds.

## Herdr workflow

`prefix+shift+s` opens the project-space picker popup.

The picker lets you:

- navigate all currently-open Herdr spaces, including unlinked scratch spaces
- focus an already-open Herdr space for an existing Pi/shared project
- create exactly one Herdr space for a selected existing project
- press `Tab` on a project to expand/collapse its Pi streams underneath
- select project scope or an expanded stream inline
- create a new shared Pi project and open its Herdr space
- create a new unlinked Herdr-only space by name for scratch work

The native Herdr new-space key was moved to `prefix+shift+n` as an escape hatch.

## Herdr plugin actions

```sh
herdr plugin action invoke sumeet.pi-workspace-sync.sync
```

- `sync`: merge Pi registry + currently-open Herdr spaces into the shared registry and report display metadata to Herdr. It does not create missing spaces.

## Pi commands

After Pi reloads extensions:

```text
/workspace-sync
```

The Pi extension also syncs on `session_start` and `agent_start`, and reports workspace metadata for panes running inside Herdr.
