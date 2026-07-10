# opencode MCP hot-attach behavior

Date: 2026-06-30

## Question

Does opencode support hot-attaching MCP tools to an already-open/current chat after toggling an MCP server on in the TUI? Specifically: when is the tool list built for a session/agent request, does runtime MCP connect update available tools for subsequent turns in the same session, and is a new chat required?

## Executive summary

Confirmed from current `anomalyco/opencode` `dev` source and official docs: toggling an MCP on in the UI calls the runtime MCP `connect` API, which creates a client, lists/caches the MCP tool definitions, and stores them in the live MCP service state. The session request path resolves tools immediately before each model request/turn, not once at chat/session creation. Therefore an already-open chat should see newly connected MCP tools on the next submitted turn, without creating a new chat.

Caveat: this does not retrofit tools into a model request that is already in flight. If the assistant is currently generating, that request already has its `tools` payload. Abort/wait, then send another message. Also, a disconnected MCP can make an already-issued tool call stale/unknown if the model tries to use it after the tool set has changed.

## Sources

- Official MCP docs: https://opencode.ai/docs/mcp-servers/
- Official config docs: https://opencode.ai/docs/config/
- Source repo: https://github.com/anomalyco/opencode
- Runtime MCP service: `packages/opencode/src/mcp/index.ts` in `anomalyco/opencode` dev branch
- TUI/app MCP toggle path: `packages/app/src/components/dialog-select-mcp.tsx`, `packages/app/src/context/mcp.ts`, `packages/app/src/context/global-sync/mcp.ts`, `packages/app/src/context/server-sync.tsx`
- Session request/tool resolution paths: `packages/opencode/src/session/prompt.ts`, `packages/opencode/src/session/tools.ts`, `packages/core/src/session/runner/llm.ts`, `packages/core/src/tool/registry.ts`
- HTTP MCP handlers: `packages/opencode/src/server/routes/instance/httpapi/handlers/mcp.ts`

## Detailed notes

### Official docs

The MCP docs say MCP tools are automatically available alongside built-in tools once added: “Once added, MCP tools are automatically available to the LLM alongside built-in tools.” They also document `enabled: false` as disabling a server on startup and list MCP tools as managed like other tools. See https://opencode.ai/docs/mcp-servers/.

The config docs describe `enabled` as “Enable or disable the MCP server on startup,” not as a per-chat/session setting. See https://opencode.ai/docs/config/.

Interpretation: official docs do not explicitly say “same chat hot attach works,” but they frame MCP availability as runtime/config state, not immutable session metadata.

### TUI toggle calls runtime connect/disconnect

Confirmed in source. The MCP picker displays statuses from synced MCP state and toggles the selected server:

- `DialogSelectMcp` calls `toggle.mutate(i.name)` from `useMcpToggle` (`packages/app/src/components/dialog-select-mcp.tsx`).
- `useMcpToggle` uses `sync().mcp.toggle` (`packages/app/src/context/mcp.ts`).
- `toggleMcp` maps `disabled`, `failed`, and `needs_client_registration` to `connect`; `connected` to `disconnect`; `needs_auth` to `authenticate`; then refreshes MCP queries (`packages/app/src/context/global-sync/mcp.ts`).
- `server-sync.tsx` implements connect via `sdk.mcp.connect({ name })` and disconnect via `sdk.mcp.disconnect({ name })`, then refetches MCP status/resources (`packages/app/src/context/server-sync.tsx`).
- HTTP handlers expose `/mcp/{name}/connect` and `/mcp/{name}/disconnect` by calling `mcp.connect(name)` / `mcp.disconnect(name)` (`packages/opencode/src/server/routes/instance/httpapi/handlers/mcp.ts`).

Confirmed fact: toggling in the TUI is a runtime server operation, not “write config then require restart/new chat.”

### Runtime connect updates live MCP state and cached tool definitions

Confirmed in `packages/opencode/src/mcp/index.ts`:

- State keeps `clients`, `defs`, `status`, and `instructions` records.
- `create()` skips only if `mcp.enabled === false`; otherwise it connects local/remote, calls `McpCatalog.defs(...)` to list tools, and returns `defs` and instructions.
- `connect(name)` calls `createAndStore(name, { ...mcp, enabled: true })`.
- `createAndStore()` stores status and, if a client exists, calls `storeClient()`.
- `storeClient()` sets `s.status[name] = { status: "connected" }`, `s.clients[name] = client`, `s.defs[name] = listed`, updates instructions, and watches for tool-list changes.
- `tools()` builds a fresh `Record<string, Tool>` from currently connected `s.clients` and cached `s.defs` each time it is called.
- `disconnect()` closes the client, deletes cached defs/instructions, and marks status disabled.

Confirmed fact: a successful runtime `connect` makes the server's tools available through `mcp.tools()` immediately for later callers in the same opencode process.

### Tool list is built at request/turn time

There are two relevant paths in the current tree.

V1/session prompt path:

- In `packages/opencode/src/session/prompt.ts`, inside the run loop just before `handle.process(...)`, opencode calls `SessionTools.resolve(...)` and passes the resulting `tools` into the model processor.
- In `packages/opencode/src/session/tools.ts`, `resolve(...)` calls `mcp.tools()` near the end and adds each connected MCP tool to the `tools` object.

Confirmed fact for this path: MCP tools are resolved immediately before each model call, based on the live MCP service state at that time.

V2/core runner path:

- In `packages/core/src/session/runner/llm.ts`, each turn attempt calls `tools.materialize(agent.info?.permissions)` immediately before constructing `LLM.request(...)`, then passes `toolMaterialization?.definitions` as `request.tools`.
- In `packages/core/src/tool/registry.ts`, `materialize(...)` snapshots the current registered tool map and returns definitions plus a settlement function. This is a per-request snapshot; later registry changes affect later materializations, not the already-built request.

Confirmed fact for this path: tool definitions are also built per model request/turn. The source inspected did not show MCP-specific registration into the V2 `ApplicationTools` registry in the same way as the V1 `SessionTools.resolve` path, so the V1 path is the stronger direct MCP evidence. The V2 evidence still supports the general “tools are not fixed at chat creation” design.

### In-flight requests do not change

Confirmed from both request-building paths: `tools` is passed into `handle.process(...)` or `LLM.request(...)` as part of a specific provider request. Once that request starts streaming, toggling MCP state cannot change the already-sent `tools` payload. Subsequent continuation/provider requests can re-resolve tools if the loop iterates.

## Tradeoffs

- Hot attach avoids restarting or starting a new chat, which is the useful behavior for optional MCPs.
- Since each provider request receives a snapshot of tool definitions, MCP changes can create stale tool-call edges around an active/in-flight turn. The code has stale/unknown tool handling in registries, but the safest user workflow is to toggle between turns.
- MCP docs warn that MCP tools add context and can exceed context limits: https://opencode.ai/docs/mcp-servers/.

## Recommendations

- To use an MCP in the current chat: toggle it on, wait for status `connected`, then send the next message in the same chat. No new chat should be required.
- If the assistant is already running, stop/wait and send another turn after the MCP is connected.
- Keep optional MCPs disabled until needed because connected MCP tools are included in the tool list/context.

## Open questions

- The exact released binary may differ from `dev` source. The local docs page showed “Last updated: Jun 30, 2026” and GitHub latest release metadata displayed v1.17.11 from Jun 25, 2026; verify against the installed version if behavior differs locally.
- The V2 runner's MCP registration path was not directly identified in this pass; the direct MCP hot-attach conclusion rests primarily on the active opencode session/tool resolution path and runtime MCP service.
