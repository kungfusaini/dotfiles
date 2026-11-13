# One-at-a-time Pi conversations

The managed `enumerate.ts` extension adds `/enum` and `/next`. It uses Pi's public
command/tree APIs, not a separate session manager or an agent-callable navigation
tool. No extra npm dependency is installed.

## Use

1. Discuss the topics you want to tackle, then run **`/enum`**. The current model
   extracts outstanding topics from the effective active conversation. Edit the
   proposed list (one item per line), then confirm it. Escape cancels.
   Alternatively, `/enum First topic; Second topic` supplies a list without an
   extraction call; it still requires review and confirmation.
2. Item 1 becomes the focus. Ask questions or authorize work as usual. A widget and
   footer show the current position. `/enum` or `/enum status` displays the queue.
3. **`/next`** is the only way to advance. Choose a decisions summary, the full
   effective conversation since the agenda (text, tool details and images), or
   nothing beyond the shared agenda context. Escape stays on the current item.
4. The final item is marked **LAST ITEM** immediately on entry, including a
   single-item queue. `/next` there offers summaries of all items, summaries of
   selected items, or agenda context only. It returns to an agenda-rooted branch,
   announces completion, and disables pacing. It does not invent a next task.

Commands establish focus but do not trigger an automatic agent turn or authorize
implementation. Type your question/instruction after switching. The model receives
a fresh pacing reminder on every user turn, including after compaction. Queue
advancement itself is deterministic; whether a model stays semantically on topic
is still instruction-based, not a topic-classification security boundary.

`/enum cancel` confirms leaving pacing mode on the current branch without deleting
anything or changing the filesystem. Finish normally with `/next` if you want to
return to the shared agenda with selected conclusions.

## Tree and context

Every item starts on its own branch from a labeled agenda state entry. `/next`
handles navigation; manual `/tree` is optional. Labels use
`enum:<queue-id-prefix>:agenda` and `enum:<queue-id-prefix>:<item-number> <title>`.
Branches and raw history are never deleted. State snapshots follow the active
branch, so `/tree`, resume and reload restore the item associated with that branch.
Revisiting an old item and advancing creates an alternative progression, not a
mutation of the progression you left.

Full carryover is a reference copy, not native assistant/tool message replay. It
keeps effective text, tool arguments/results and images, but not hidden reasoning,
system prompts, omitted context-edit entries or context-excluded `!!` output.
Pi's compaction and branch summaries are honored; compacted original messages are
not resurrected. A selected item's effective history may itself contain inherited
context or a compaction summary. "Nothing" means no item carryover; the shared
pre-agenda conversation, project instructions and filesystem state still exist.

Completion can summarize saved earlier item branches even if intervening items
chose no carryover. Metadata stores branch IDs rather than duplicating transcripts.
Summary requests use the currently selected model/provider, send no tools, and do
not execute work. Extraction and summaries are bounded (180,000 text characters,
8 MB transcript, 4096 output tokens, 120 seconds); oversize or failed requests stop
without navigation rather than silently truncating. Keep agendas under 30 items.
TUI generation has an Escape-cancellable loader; RPC uses native dialogs. Print
and JSON modes cannot start or advance queues because they lack confirmation UI.

Nested request usage is recorded in `enumerate-model-usage` custom session entries.
Pi's standard session totals do not include those entries: the public extension
API has no appendUsage method. Do not interpret that footer as complete billing
for extraction/summary calls.

**Conversation branches are not Git branches or worktrees. Switching items does
not undo, isolate or roll back files, commands or external changes.** Existing
approval and safety rules continue to apply within each item.

## Verification

Run against the installed SDK (pass its actual path):

```sh
PI_ENUM_SDK=/path/to/pi-monorepo/dist/index.js node --test tests/pi-enumerate*.test.mjs
python3 tests/pi-enumerate-tui.py
```

The PTY test runs the actual native terminal UI in a hidden pseudo-terminal, using
an empty private agent directory and no model calls. It covers agenda review,
confirmation, Escape, advancement, LAST indication, completion and narrow resize.
Pass a deployed extension path to test the installed file instead of the checkout.

The JavaScript suite uses synthetic data, isolated temporary state, actual Pi session
projection/persistence and native SDK command dispatch/tree navigation. It never
uses real credentials or calls a provider by default. Set `PI_ENUM_LIVE=1` only to
opt into the synthetic live extraction/summary test with the configured Codex
provider. That test uses the existing credential API, not copied credentials.

## Build-versus-adopt

Pi's [native session/tree support](https://pi.dev/docs/latest/sessions) and
[extension command APIs](https://pi.dev/docs/latest/extensions) supply the needed
mechanisms. The existing
[pi-tree-navigator](https://pi.dev/packages/%40cad0p/pi-tree-navigator) is aimed at
agent-callable rewinds and context reduction and documents internal reflection.
That is the opposite advancement authority to this workflow. This small local
extension uses public APIs and keeps advancement in explicit user commands.
