# Pi browser automation

`pi-browser` runs Microsoft's official `@playwright/cli` 0.1.23 with its exact
locked Playwright 1.65.0-alpha-2026-10-30 dependency and Nix-managed Vivaldi.
Upstream: https://github.com/microsoft/playwright-cli (Apache-2.0).
The published CLI pins an alpha Playwright build; upgrades require deliberate
lockfile updates and real-browser acceptance, not floating runtime installs.

## Responsibilities

- **Skill:** command syntax and capabilities across workflows.
- **AGENTS.md:** mode selection, authorization, workspace/focus, login handoff,
  authenticated-session scope, secret handling and cleanup behavior.
- **Wrapper:** Nix runtime defaults, Pi session ownership, private state, command
  serialization and artifact paths. Not a workflow policy or security sandbox.

The original headless-only design conflated these layers. Visible sessions,
persistent profiles and upstream attachment are now available without another
plugin. No browser extension or everyday-browser debugging is enabled by default.

## Modes

```
pi-browser open http://localhost:3000
project-workspace-exec pi-browser open --headed https://example.com
project-workspace-exec pi-browser open --headed --persistent https://example.com
project-workspace-exec pi-browser open --headed --profile=/absolute/profile https://example.com
pi-browser attach --cdp=http://localhost:9222
pi-browser detach
```

The managed default is temporary headless Vivaldi with its Chromium sandbox enabled.
Playwright's engine name remains `chromium`; `executablePath` selects Vivaldi.
Headless Vivaldi requires `--disable-vivaldi` to bypass its UI bootstrap. Headed
sessions keep the real Vivaldi UI, including its extension-backed browser chrome.
No everyday profile is reused and everyday debugging settings remain untouched.

For native UI compatibility the wrapper launches an owned Vivaldi process with an
OS-selected loopback CDP port, then starts the pinned official Playwright daemon
without its implicit first-page snapshot/navigation. It selects the exact created
web target through official CLI commands, rather than capturing or navigating an
unrelated restored tab. This uses version-pinned internal daemon entry points;
upgrades require both native/headless acceptance, not just a package build.
An inert local bootstrap target is created first; the requested URL is navigated
through the official backend only after its file/network policy is configured.
Native startup waits for a rendered web target; completely hidden workspaces can
delay first-frame initialization. Hidden tests keep the target on a separate
virtual output while focus remains elsewhere. Exact per-launch class rules ensure
initial workspace placement, no initial focus and suppressed activation requests;
they are disabled on close/detach. No global focus repair is used.

Process ownership records include PID/start time and endpoint identity. `close`
sends `Browser.close` to the verified owned endpoint before a PID-checked fallback;
`detach` relinquishes ownership without terminating the native browser. Temporary
owned profiles are removed after verified shutdown; persistent and explicit
profiles are retained. The managed default persistent profile is `session/profile`
in both headed and headless modes. `delete-data` removes that default profile,
not explicitly supplied profiles. Active profile locks fail closed.
`--headed` overrides headless mode; `--persistent` and `--profile` use upstream
profile persistence. A human can use the same headed browser to log in, then
hand control back; the agent continues without exporting credentials or cookies.
Workflow and permission rules for doing so live in the canonical Pi `AGENTS.md`.

Explicit `--config` files replace the generated launch defaults and can select
other browser/launch/context options. For the native Vivaldi bridge, supported
launch fields are `executablePath`, `headless`, `chromiumSandbox` and `args`;
unsupported launch fields fail rather than being silently ignored. Native custom
configs are JSON; INI configs are forwarded untouched through upstream, not
silently replaced by managed defaults. Malformed JSON fails before launch. Native
`contextOptions`, `--device`, `--mobile`, `initPage` and `initScript` are rejected:
CDP attaches an existing context, and daemon-wide init callbacks could affect
unrelated restored tabs. These features remain available in headless mode.
Other browsers
and explicit external endpoints retain upstream behavior. Configs must supply a usable executable/channel
when not using the packaged Vivaldi configuration. Config/profile paths resolve
against the invoking shell cwd. Other relative file paths resolve against the
private session directory; absolute paths work for all file arguments.

Upstream `attach`/`detach`, CDP, Playwright server endpoints and extension mode are
exposed. Extension use requires its own installed extension and supported browser;
Vivaldi launch and CDP attachment are tested; extension compatibility is not
established. Attachment retains the external
browser's own scope and ownership and may expose authenticated pages. Detach leaves
the external browser alive. No profile/cookie copying or implicit connection target.

## Session mechanics

`PI_SESSION_ID` (or `PI_SESSION_FILE` fallback) selects a private folder beneath
`$XDG_STATE_HOME/pi-browser/` (default `~/.local/state/pi-browser/`). Different Pi
sessions have different default caches/profiles/artifacts, even in the same repo;
shell cwd changes do not change browser ownership. Explicit profile paths and
attachments deliberately allow reuse beyond these defaults. Concurrent commands
within a Pi session are serialized. Global close/kill commands and runtime install
commands are rejected; per-session `close`, `detach` and `delete-data` are supported.

```
pi-browser snapshot
pi-browser fill e3 'Some text'
pi-browser fill e3 -- '--help'
pi-browser click e4
pi-browser screenshot
pi-browser paths
pi-browser close
```

Snapshots may be inline or files. `paths` reports absolute session, artifact and
temporary directories; reported relative artifact paths resolve against `session`.
Temporary files use short `/run/user/$UID/pib/` paths for Vivaldi/Chromium's Unix socket
length limit. Profiles/artifacts can contain sensitive data. Close does not delete
persistent data. Upstream defaults headless sessions to one hour of inactivity;
headed sessions do not idle-close. An explicit `--idle-timeout` ends the automation
connection in native mode; `close` terminates the owned native Vivaldi process.

The wrapper preserves graphical and project-launch environment for headed routing,
but removes inherited Playwright/MCP connection settings so modes are explicit.
Update checks, browser downloads and Vivaldi's automatic codec download are disabled;
all runtime dependencies are
Nix-store packaged, with no dependency on the checkout. CLI options are forwarded
rather than maintained in a restrictive feature allowlist. Session aliases are
rejected to keep Pi session ownership unambiguous.

## Verification

`python3 -m unittest discover -s tests -v` runs package-level unit checks.
`python3 tests/integration.py /nix/store/.../bin/pi-browser` tests local fixtures,
headless interaction, isolation, persistence and external CDP detach behavior.
`headed_integration.py` reuses the Project Object isolated compositor harness to
exercise native Vivaldi/persistent browsers on a hidden desktop, never the real
desktop. Pass `--browser-class vivaldi --keep-target-visible` plus the documented
executable paths. Set `PI_BROWSER_TEST_TEMPORARY=1` for fresh native-profile and
close-cleanup coverage; the default covers explicit-profile cross-session/mode
reuse and synthetic login continuation. Compositor events check transient focus.
