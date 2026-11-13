# One-at-a-time Pi branches

The managed `enumerate.ts` extension adds `/enum` and `/next`. It uses Pi's public
command/tree APIs. Each item is a native, labeled conversation branch inheriting
all the effective conversation before the agenda. No extra npm dependency is used.

## Use

1. Discuss the topics, then run **`/enum`**. The current model extracts the agenda
   once from the **full effective active conversation**, including tool evidence.
   Edit the proposed list (one item per line), then confirm. Escape cancels.
   `/enum First topic; Second topic` can also supply an explicit list, but is not
   required for long conversations.
2. Item 1 becomes the focus. Ask questions or authorize work as usual. The widget,
   footer and model context identify the current branch, e.g. **Item 2 of 3:
   Which colour?** `/enum` or `/enum status` displays the queue.
3. **`/next`** simply switches to the next item branch. No model call, transcript
   copying, summary generation or carryover dialog occurs. The full shared
   pre-agenda history stays inherited, just like native `/tree` navigation.
4. The final branch is marked **LAST ITEM** immediately, including single-item
   queues. `/next` there returns to an agenda-rooted main-conversation branch,
   announces completion and turns pacing off. No additional task is invented.

Commands establish focus, but do not trigger an automatic agent turn or authorize
implementation. Type your question/instruction after switching. The model receives
a fresh reminder of its current item on every user turn, even after compaction.
Only the user invoking `/next` advances. Queue navigation is deterministic;
semantic on-topic behavior remains instruction-based, not a security boundary.

`/enum cancel` confirms turning off pacing on the current branch without deleting
anything or changing the filesystem.

## Optional item-specific carryover

Shared pre-agenda history is always inherited; it is never an opt-in copy.
Discussion added within an item stays on that branch unless explicitly carried.
Use **`/next carry`** instead of `/next` when you want carryover choices:

- Between items: a decisions summary, full effective item conversation (including
  earlier carried context, tool details and images), or agenda context only.
- At the final item: summaries from all item branches, selected item summaries,
  or agenda context only. This can gather answers even when earlier `/next`
  switches did not carry them. For the fruit/colour/location story trial, use
  plain `/next` between questions and `/next carry` with all-item summaries at the
  end to bring the three answers into the main conversation for story writing.

Escape from an optional carry dialog stays on the current item. Summary generation
only happens when explicitly selected. Full carry is reference material, not
native replay of assistant/tool message roles. Hidden reasoning, system prompts,
omitted context-edit entries and context-excluded `!!` output are not copied.

## Tree, persistence and limits

Labels are `enum:<queue-id-prefix>:agenda` and
`enum:<queue-id-prefix>:<item-number> <title>`. Branches and raw history are never
deleted. State follows the active branch: `/tree`, resume and reload restore that
branch's item. Revisiting an old item and advancing creates an alternative
progression; it does not mutate the progression you left.

Pi's own effective-history projection, context edits and compaction are honored.
Neither initial extraction nor inherited branch context has the old 180,000-
character carryover cap. There is no recent-only window or silent truncation.
The selected model's context window and Pi's existing compaction still apply;
compacted or abandoned history is not resurrected into active context.

Optional carryover requests remain bounded (180,000 text characters, 8 MB
transcript). Extraction/summary output is limited to 4096 tokens and requests to
120 seconds. Oversized optional carryover or failed requests stop without
navigation. Agendas contain at most 30 items. TUI model requests have an
Escape-cancellable loader; RPC uses native dialogs. Print/JSON modes cannot start
or advance a queue because they lack confirmation UI.

Nested request usage is retained in `enumerate-model-usage` custom entries. Pi's
standard session totals do not include these: the public extension API has no
appendUsage method. The footer is therefore not complete billing for extraction
or explicitly requested summaries.

**Conversation branches are not Git branches/worktrees. Switching items does not
undo, isolate or roll back files, commands or external changes. Existing approval
and safety rules still apply.**

## Verification

```sh
PI_ENUM_SDK=/path/to/pi-monorepo/dist/index.js node --test tests/pi-enumerate*.test.mjs
python3 tests/pi-enumerate-tui.py
```

Synthetic tests cover long-history extraction beyond the old limit, unchanged
shared-history inheritance, model-visible branch identity, processing-free
switches/completion, optional carryover, actual SDK command dispatch/native tree
navigation, projection, persistence, cancellation and races. The hidden PTY test
uses an empty private agent directory and no provider requests. Pass a deployed
extension path to test the installed file.

`PI_ENUM_LIVE=1` opts into a configured-Codex test using a synthetic history longer
than the former limit, the fruit/colour/location agenda, three item answers and
explicit all-item summary collection. Default tests never access real credentials
or call a provider; the opt-in test uses the normal credential API without copying
credentials or sending personal conversation history.

Pi's [session/tree support](https://pi.dev/docs/latest/sessions) and
[extension command APIs](https://pi.dev/docs/latest/extensions) provide the native
mechanisms. [pi-tree-navigator](https://pi.dev/packages/%40cad0p/pi-tree-navigator)
is aimed at agent-controlled rewinds and documents internal reflection. This
workflow instead keeps branch advancement in explicit user commands on public APIs.
