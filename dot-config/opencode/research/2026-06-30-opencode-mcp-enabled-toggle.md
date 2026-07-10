# opencode MCP `enabled` config and TUI toggle

Date: 2026-06-30

## Question

How does opencode's MCP config `enabled` field interact with the TUI MCP toggle? Specifically: does `enabled: false` mean disabled by default but manually toggle-able, does the TUI toggle persist, and how should an MCP be configured so it is available to toggle without being enabled in every chat?

## Executive summary

- Confirmed: `mcp.<name>.enabled: false` keeps the server configured and visible in MCP status, but opencode does not connect/start it on startup. The server can still be connected later through the `/mcp/:name/connect` HTTP API, which is what the TUI toggle calls.
- Confirmed: the TUI toggle is runtime state, not a config edit. It calls connect/disconnect endpoints and refreshes status; the reviewed code does not write back to `opencode.json` or `tui.json`. On restart, `enabled: false` returns to disabled.
- Recommendation: define optional/heavy MCPs globally with full config plus `enabled: false`. Toggle them from the TUI only when needed. If a project should always use one, override that MCP in the project `opencode.json` with `enabled: true`.
- Caveat: while toggled on, MCP tools are available to the running opencode instance/session context like other tools. This is not per-chat persisted state; it is runtime state until disconnected or restart.

## Sources

- Official MCP docs: https://opencode.ai/docs/mcp-servers/
- Official config docs: https://opencode.ai/docs/config/
- opencode source cloned from `https://github.com/anomalyco/opencode`, commit `6387f95`:
  - `packages/opencode/src/mcp/index.ts`
  - `packages/tui/src/component/dialog-mcp.tsx`
  - `packages/tui/src/context/local.tsx`
  - `packages/tui/src/feature-plugins/sidebar/mcp.tsx`
  - `packages/opencode/src/server/routes/instance/httpapi/groups/mcp.ts`
  - `packages/opencode/test/server/httpapi-mcp.test.ts`
- Local config inspected: `dot-config/opencode/opencode.json` has `chrome-devtools` configured with `enabled: false`.

## Detailed notes

### What `enabled: false` means

The official docs say MCP servers are configured under `mcp`, and: “You can also disable a server by setting `enabled` to `false`. This is useful if you want to temporarily disable a server without removing it from your config.” They also list `enabled` as “Enable or disable the MCP server on startup.” https://opencode.ai/docs/mcp-servers/

The source confirms startup behavior. In `packages/opencode/src/mcp/index.ts`, service initialization iterates configured MCPs and, if `mcp.enabled === false`, sets `s.status[key] = { status: "disabled" }` and returns without creating a client. The `create()` helper also immediately returns a disabled result when `mcp.enabled === false`.

Interpretation: `enabled: false` is best read as “do not auto-connect on startup,” not “remove from opencode.”

### Whether disabled MCPs are still toggle-able

Confirmed. The status endpoint includes configured MCPs even when disabled. In `MCP.status()`, opencode iterates current config and returns each configured MCP status, defaulting to `{ status: "disabled" }` when no runtime status exists.

The HTTP API exposes connect/disconnect endpoints at `/mcp/:name/connect` and `/mcp/:name/disconnect` in `packages/opencode/src/server/routes/instance/httpapi/groups/mcp.ts`.

The connect implementation in `packages/opencode/src/mcp/index.ts` does:

```ts
const mcp = yield* requireMcpConfig(name)
yield* createAndStore(name, { ...mcp, enabled: true })
```

So even if the static config has `enabled: false`, manual connect overlays `enabled: true` for the runtime connect attempt.

The test `packages/opencode/test/server/httpapi-mcp.test.ts` configures an MCP with `enabled: false`, verifies status is disabled, then calls `/mcp/demo/connect` and expects success.

### What the TUI MCP toggle does

The TUI MCP dialog lists `sync.data.mcp` entries, so disabled configured MCPs appear in the dialog if they are present in server status. In `packages/tui/src/component/dialog-mcp.tsx`, the action calls `local.mcp.toggle(option.value)`, then refreshes `sdk.client.mcp.status()`.

`packages/tui/src/context/local.tsx` implements `toggle(name)` as: if current status is `connected`, call `sdk.client.mcp.disconnect({ name })`; otherwise call `sdk.client.mcp.connect({ name })`.

No persistence write is present in that TUI path.

The sidebar plugin `packages/tui/src/feature-plugins/sidebar/mcp.tsx` displays statuses including `connected`, `disabled`, `failed`, `needs_auth`, and `needs_client_registration`.

### Does the TUI toggle persist?

Confirmed no file persistence in the source path reviewed. The toggle changes server runtime state through connect/disconnect endpoints. The MCP service stores connected clients/status in instance state, not config. `disconnect()` closes the client and sets runtime status to disabled; `connect()` connects with an in-memory `{ ...mcp, enabled: true }` overlay.

Practical result: with config `enabled: false`, toggling on should last for the current opencode server/TUI runtime. Restarting opencode re-reads config and starts disabled again.

### Local config context

Your current global opencode config has `chrome-devtools` configured as a local MCP with `enabled: false` and an `npx chrome-devtools-mcp@latest` command pointing at Brave. This matches the recommended pattern for an optional, heavyweight MCP: globally available in the TUI, disabled on startup, manually connect when browser tools are needed.

## Tradeoffs

- `enabled: false` avoids startup cost, token/tool clutter, and background local processes. Official docs warn MCPs add context and recommend being careful with which ones are enabled: https://opencode.ai/docs/mcp-servers/
- Manual toggling is convenient but ephemeral. If you need repeatable project behavior, static config is clearer.
- `tools` config is different from MCP `enabled`. MCP `enabled` controls whether the server connects. `tools` controls whether already-registered tools are exposed/allowed globally or per-agent. The docs show using `tools`/agent tool overrides when an MCP is connected but should be hidden except for certain agents: https://opencode.ai/docs/mcp-servers/#manage

## Recommendations

### Optional MCP, available to toggle, not enabled by default

Use this pattern in global config:

```json
{
  "mcp": {
    "chrome-devtools": {
      "type": "local",
      "enabled": false,
      "command": ["npx", "-y", "chrome-devtools-mcp@latest"]
    }
  }
}
```

This should show as disabled in the TUI MCP list/sidebar and can be toggled on when needed.

### Project that should auto-enable it

In that project’s `opencode.json`, override the same MCP name with `enabled: true` and the needed config. Config files are merged, and project config overrides global config per the official config precedence docs: https://opencode.ai/docs/config/#precedence-order

### Connected but not exposed broadly

If the goal is “server connected, but tools only usable by a specific agent,” use `enabled: true` for the MCP plus `tools` disable/agent enable rules as documented. Do not use `enabled: false` for that case, because the server will not be connected until manually toggled.

## Open questions / caveats

- Exact TUI keybinding/menu path can change; the source behavior is stable enough for the conclusion, but this artifact did not document UI navigation.
- The toggle is instance-scoped. In worktree/project stream setups, status may be scoped by the instance/workspace routing used by the TUI/server.
- If an MCP requires OAuth, toggling may move it into `needs_auth` and require the auth flow. Stored OAuth tokens persist separately in opencode’s MCP auth store per official docs, but the enabled/disabled toggle itself still does not persist.
