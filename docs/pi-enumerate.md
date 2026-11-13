# One-at-a-time Pi branches

The managed `enumerate.ts` extension adds `/enum` and `/next`, using Pi's public
command/tree APIs. No extra npm dependency is used.

## Use

1. Discuss the topics, then run **`/enum`**. The current model extracts the agenda
   once from the **full effective active conversation**, including tool evidence.
   It immediately says **“Okay, let's tackle: [first topic]”**. No agenda editor,
   confirmation, menu or custom loading screen.
2. Above the input bar, the only enumeration UI is **`Branch: 1 of 3`**. There is
   no enumeration footer, topic widget or last-item decoration.
3. **`/next`** switches to the next topic branch and acknowledges that topic.
   No model call, transcript copying, summary or dialog occurs between topics.
   Each branch inherits the shared pre-agenda conversation, but not discussion
   added on sibling topic branches.
4. **`/next` on the last topic** automatically brings together the results of
   **all** topic branches in one model-generated summary. It returns to the
   shared main conversation, displays that summary and removes the branch line.
   No extra choice or carryover command is needed.

Commands establish focus; they do not trigger an automatic work turn or authorize
implementation. Ask your question or authorize work after switching. The model
receives a hidden current-item reminder on every turn, including after compaction.
Only `/next` advances. Semantic pacing is instruction-based, not a security boundary.

`/enum First topic; Second topic` optionally supplies an explicit list.
While active, `/enum` repeats the current topic; `/enum status` explicitly shows
the list. `/enum cancel` immediately turns pacing off without deleting branches
or gathering results. `/next carry` and carryover dialogs have been removed.

## Persistence and safeguards

Each topic is a native labeled conversation branch. Labels are
`enum:<queue-id-prefix>:agenda` and `enum:<queue-id-prefix>:<number> <title>`.
State follows the active branch through `/tree`, resume and reload, including
queues created by the earlier extension. Revisiting an old branch and advancing
creates an alternative progression; it does not change the one you left.

Pi's effective-history projection, context edits and compaction are honored.
Collection reads effective item-local histories from the saved topic branches,
not raw omitted messages or reasoning. Effective tools and images are included.
Shared pre-agenda history is not duplicated in the final summary request.

There is no arbitrary 180,000-character limit or silent truncation. The selected
model's context window still applies to extraction and collection. Requests have
a 120-second timeout and 4096-token output limit; agendas have at most 30 items.
A failed collection leaves the last topic active, preserving all branches for a
retry. Busy/queued sessions refuse navigation; stale responses and shutdown
cannot move a changed session. Print/JSON modes cannot start or advance a queue.

Nested usage is saved in `enumerate-model-usage` entries. The standard Pi session
totals do not include it because the public API has no appendUsage method.

**Conversation branches do not isolate, undo or roll back files, commands or
external changes. Existing approval and safety rules still apply.**

## Verification

```sh
PI_ENUM_SDK=/path/to/pi-monorepo/dist/index.js node --test tests/pi-enumerate*.test.mjs
python3 tests/pi-enumerate-tui.py
```

Synthetic tests cover immediate dialog-free startup, exact compact UI, long
history, sibling isolation, automatic all-topic collection, effective projection,
compaction, images/tools, persistence, cancellation/failures, races and actual
SDK dispatch/native navigation. The hidden PTY test uses a private empty agent
directory and synthetic model responses, with no provider requests or visible
windows. Pass the deployed extension path to test the installed file.

`PI_ENUM_LIVE=1` opts into configured Codex extraction and automatic final
collection using only synthetic history longer than the old limit and a
fruit/colour/location agenda with mango/violet/Kyoto answers. Default tests never
access real credentials or providers. The opt-in test uses the normal credential
API without copying credentials or sending personal history.

Pi's [session/tree support](https://pi.dev/docs/latest/sessions) and
[extension APIs](https://pi.dev/docs/latest/extensions) provide the native
branching and above-editor widget mechanisms.
