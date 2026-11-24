---
name: grill-me
description: A relentless interview to sharpen an idea, plan, or decision. Explicitly invoked with /grill-me or /skill:grill-me.
disable-model-invocation: true
license: MIT
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

This is a stateless conversation. Do not write files or leave a workspace behind. The subject need not be software. If the user has not supplied an idea, ask what they want to explore.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), use available read-only tools to find it; don't ask the user for anything you could look up yourself. Where an authorized read-only exploration agent is available, it may investigate independently. A running exploration is an unsettled prerequisite, so only the questions downstream of it wait; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.

The user owns the scope. Accept pushback and "I don't know" rather than inventing certainty. If a question requires trying something rather than discussing it, flag it as needing a prototype and ask how the user wants to proceed; do not build it during this stateless interview.

The session is done when the frontier is empty: every branch of the agreed scope visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding. Confirmation of understanding is not authorization to implement; follow the normal approval requirements.
