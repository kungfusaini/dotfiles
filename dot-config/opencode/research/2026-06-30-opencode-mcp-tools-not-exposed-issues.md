# opencode MCP connected but tools not exposed: issue/PR research

Date: 2026-06-30

## Question

Inspect GitHub issues/PRs related to opencode MCP servers that show as connected but whose tools are not exposed or usable: #33027, #26357, #16491, #28177, #13763, #31312. Determine whether fixes/workarounds are mentioned in threads, comments, and linked PRs, especially for current-chat hot attach, permissions/tool filters, version upgrades, MCP server naming, or config changes.

## Executive summary

- #33027 and #26357 are still open reports with no concrete fix in the visible thread. Both describe MCP servers connecting, but tools not being available to the model. #33027 used opencode 1.17.8; #26357 was opencode-desktop on macOS. Sources: https://github.com/anomalyco/opencode/issues/33027, https://github.com/anomalyco/opencode/issues/26357
- Related fixes solve narrower failure modes: #30529 is merged for child-session permission overwrites; #32084 is merged for stale/dead MCP clients after transport close; #30288/#33160 are open for subagent MCP allow inheritance; #32582 is open for MCP permission prompts using `*` instead of the real tool key. Sources: https://github.com/anomalyco/opencode/pull/30529, https://github.com/anomalyco/opencode/pull/32084, https://github.com/anomalyco/opencode/pull/30288, https://github.com/anomalyco/opencode/pull/33160, https://github.com/anomalyco/opencode/pull/32582
- Current docs say MCP tools are automatically available once added, but `enabled:false`, tool filters, and permission filters can hide/block them. MCP tool IDs are prefixed with the server name and can be matched by globs such as `mymcpservername_*`. Sources: https://opencode.ai/docs/mcp-servers/, https://opencode.ai/docs/tools/, https://opencode.ai/docs/permissions/
- Current dev code builds MCP tools from live connected clients when resolving tools for a model request. Interpretation: hot attach should take effect on the next turn/request in the same chat, not in an already in-flight request. Sources: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/tools.ts, https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/mcp/index.ts

## Sources

- #33027 `[BUG] MCP tools connected but not exposed to agent`: https://github.com/anomalyco/opencode/issues/33027
- #26357 Docker MCP gateway connects but LLM cannot recognize/invoke tools: https://github.com/anomalyco/opencode/issues/26357
- #16491 Subagents cannot execute MCP tools: https://github.com/anomalyco/opencode/issues/16491
- #28177 Config precedence ignored: https://github.com/anomalyco/opencode/issues/28177
- #13763 Disabling MCPs does not persist across sessions: https://github.com/anomalyco/opencode/issues/13763
- #31312 auto-reconnect MCP clients on unexpected close: https://github.com/anomalyco/opencode/pull/31312
- #32084 merged follow-up, clear closed MCP clients: https://github.com/anomalyco/opencode/pull/32084
- #30529 merged, merge per-call tool rules into session permission: https://github.com/anomalyco/opencode/pull/30529
- #30288 open, inherit MCP tool allow permissions in subagents: https://github.com/anomalyco/opencode/pull/30288
- #33160 open, OpenAI-compatible MCP null params + subagent MCP allow inheritance: https://github.com/anomalyco/opencode/pull/33160
- #32582 open, pass MCP tool name/args to permission ask: https://github.com/anomalyco/opencode/pull/32582
- #33967 open, scope subagent permission inheritance: https://github.com/anomalyco/opencode/pull/33967
- Official config docs: https://opencode.ai/docs/config/
- Official MCP docs: https://opencode.ai/docs/mcp-servers/
- Official tools docs: https://opencode.ai/docs/tools/
- Official permissions docs: https://opencode.ai/docs/permissions/
- Current dev `session/tools.ts`: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/tools.ts
- Current dev `mcp/index.ts`: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/mcp/index.ts

## Detailed notes

### #33027: connected but not exposed to agent

Confirmed facts: The reporter says a custom Python stdio MCP `pdfrag` connects, `opencode mcp list` shows connected, `tools/list` returns six valid tools, but the tools do not appear in the agent's available tool list. Environment says OpenCode 1.17.8 on macOS. The issue page shows no visible workaround beyond direct CLI/Python calls and no linked PR in the metadata. Source: https://github.com/anomalyco/opencode/issues/33027

Interpretation: Because #33027 is open and lacks a maintainer diagnosis, treat it as unresolved. Check tool filters and permissions first, then upgrade/retest because several MCP fixes landed or are pending after the reporter's version.

### #26357: Docker MCP gateway connected but invisible in desktop

Confirmed facts: The reporter configures a local Docker MCP gateway command in opencode-desktop on macOS. The MCP connection succeeds, but the LLM cannot see/invoke Docker gateway tools; non-Docker MCP servers work. No visible workaround or linked fix appears in the thread. Source: https://github.com/anomalyco/opencode/issues/26357

Interpretation: This may be a desktop + Docker/gateway-specific discovery/stdio issue. Use terminal CLI (`opencode mcp list`, `opencode debug config`) and a non-desktop run to isolate desktop packaging from MCP config.

### #16491 and linked subagent permission PRs

Confirmed facts: #16491 reports that parent agents can use MCP tools, but subagents spawned via Task can see MCP tools and then hit permission denial because subagent sessions lack MCP tool permissions. Source: https://github.com/anomalyco/opencode/issues/16491

Confirmed facts: #30288 proposes copying parent `allow` rules whose permission key contains `_` or is `*`, because MCP tools are named as `sanitize(clientName) + "_" + sanitize(toolName)` such as `context7_resolve-library-id`. The PR is open. Source: https://github.com/anomalyco/opencode/pull/30288

Confirmed facts: #30529 is merged and fixes a broader session-permission overwrite bug: per-call `tools` rules were replacing `session.permission`, dropping inherited rules. The fix merges per-call rules on top of existing session permission. Source: https://github.com/anomalyco/opencode/pull/30529

Confirmed facts: #33160 is open. It primarily fixes OpenAI-compatible provider schema sanitization/null args for MCP tools, and also says it inherits MCP tool allow permissions in subagent sessions. Source: https://github.com/anomalyco/opencode/pull/33160

Actionable implication: If the MCP works in the parent chat but not in a Task subagent, upgrade to a build containing #30529 and track/apply #30288/#33160. Until then, explicitly grant the subagent/agent permission for the relevant MCP tool glob if supported by your config, e.g. `permission: { "server_*": "allow" }` or agent-level equivalent.

### #31312 and #32084: stale MCP connections after transport close

Confirmed facts: #31312 proposed auto-reconnecting MCP clients on unexpected close. It describes stale connected state with stale tool definitions after an MCP process dies or HTTP transport drops. The PR is open and references #17099. Source: https://github.com/anomalyco/opencode/pull/31312

Confirmed facts: #32084 is merged as a narrower follow-up. It observes MCP client closure, marks unexpectedly closed clients failed, removes cached tools, and publishes a tool catalog change. It explicitly says it does not automatically reconnect or replay failed tool calls. Source: https://github.com/anomalyco/opencode/pull/32084

Actionable implication: Upgrade to a build containing #32084 if the UI still says connected after a server died, or if dead tools remain exposed. If the server dies, manually reconnect/restart opencode; automatic reconnection is not merged.

### #28177: config precedence ignored

Confirmed facts: #28177 reports that global config disabled `chrome-devtools_*` tools and project config tried to re-enable them, but `opencode debug config --pure` still showed global `enabled: false` and `tools` false on version 1.15.4. Source: https://github.com/anomalyco/opencode/issues/28177

Confirmed facts: Current docs state config files are merged, later configs override earlier conflicting keys, and project config is higher priority than global config among standard files. Source: https://opencode.ai/docs/config/

Actionable implication: Verify effective config with `opencode debug config --pure`. If a global `tools`/`permission` deny or `enabled:false` wins unexpectedly, either upgrade or remove the global deny instead of relying on project override.

### #13763: TUI disabling MCPs does not persist

Confirmed facts: #13763 says toggling MCPs via `/mcps` disables during the session but after restart they are enabled again. The issue remains open in visible metadata. Source: https://github.com/anomalyco/opencode/issues/13763

Confirmed facts: Current docs say to disable persistently, set the MCP config entry's `enabled` to `false`. Source: https://opencode.ai/docs/mcp-servers/

Actionable implication: Do not rely on `/mcps` toggle for persistent defaults. Put `"enabled": false` in config and enable per project/config when needed.

### Hot attach / current chat behavior

Confirmed facts from current dev source: `MCP.connect(name)` calls `createAndStore(name, { ...mcp, enabled: true })`, which stores the connected client and cached tool definitions. `MCP.tools()` returns tools from currently connected clients whose status is `connected`. `SessionTools.resolve(...)` calls `mcp.tools()` while preparing the tool map for a model request. Sources: https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/mcp/index.ts, https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/session/tools.ts

Interpretation: Hot attaching an MCP server in the current chat should expose tools on the next turn/request after connection, because the tool map is resolved per request from live MCP state. It will not affect a request already in flight. If tools still do not show on the next turn, suspect filters/permissions, failed tool discovery, provider schema incompatibility, or stale/old version.

### Naming and filters

Confirmed facts: Official docs state MCP tools are registered with the server name as prefix and recommend `"mymcpservername_*": false` to disable all tools for a server. They also show per-agent re-enabling with `agent.<name>.tools`. Sources: https://opencode.ai/docs/mcp-servers/, https://opencode.ai/docs/tools/

Confirmed facts: Permissions docs say legacy `tools` boolean config is deprecated as of v1.1.1 but still supported; current control is through `permission`, where MCP tools can be matched by wildcards like `"mymcp_*": "ask"`. Source: https://opencode.ai/docs/permissions/

Actionable implication: Server name matters. If your server is named `pdfrag`, expect tool IDs like `pdfrag_<tool>`. Avoid global filters like `"pdfrag*": false`, `"*_search": false`, or agent `tools` maps that do not re-enable the MCP glob.

## Tradeoffs

- Persistent `enabled:false` is reliable, but requires config edits. The TUI toggle is convenient but currently not persistent per #13763.
- Broad `permission: { "server_*": "allow" }` is the fastest workaround for subagent permission denial, but it grants all tools for that server. Prefer narrower globs if the server exposes write-capable tools.
- Upgrading can pick up merged fixes (#30529, #32084), but pending fixes (#30288, #32582, #33160, #33967) may still require local patches or waiting for merge/release.
- Hot attach should work on the next turn in current code, but not mid-request. Restarting opencode is the blunt fallback when debugging old versions or desktop-specific state.

## Recommendations

1. Run `opencode debug config --pure` and inspect `mcp`, `tools`, `permission`, and agent-specific `tools`/`permission` entries. Remove or override filters matching `server_*`.
2. Use stable MCP names with simple characters and refer to prefixed tool IDs/globs (`server_*`). If renaming a server, update filters and agent permissions.
3. For persistent opt-in MCPs, set global `enabled:false`, then project `enabled:true`; do not expect `/mcps` toggles to survive restart.
4. If tools attach during a chat, send a new turn after the MCP reports connected. Do not expect the in-flight model request to see newly connected tools.
5. Upgrade to a build containing #30529 and #32084. For subagent MCP permission denial, track/apply #30288 or #33160 if not yet merged in your installed version.
6. For Docker MCP gateway/desktop invisibility (#26357), test the same config in terminal opencode. If terminal works but desktop fails, prefer terminal or a non-gateway MCP command until upstream fixes it.

## Open questions

- #33027 and #26357 do not yet have visible maintainer root-cause comments or merged fixes.
- Release/tag mapping was not established in this pass; merged-to-`dev` dates are known, but the exact first released opencode version containing #30529/#32084 should be verified against release notes or installed changelog.
- #30288, #32582, #33160, and #33967 are open as of 2026-06-30, so their exact final behavior may change before merge.
