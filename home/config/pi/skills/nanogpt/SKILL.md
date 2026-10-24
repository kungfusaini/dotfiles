---
name: nanogpt
description: Use Sumeet's NanoGPT subscription safely for live model discovery, capability-aware model ranking, subscription usage checks, and delegated LLM calls. Use when a task mentions NanoGPT or when selecting or consulting a specialized external model would materially help.
license: MIT
---

# NanoGPT subscription

Use the model-callable `nanogpt_*` tools supplied by the global Pi extension. Do not construct NanoGPT curl requests unless debugging the extension itself.

## Billing boundary

- Use only the dedicated NanoGPT API key configured as **Subscription only** in NanoGPT's API-key billing settings.
- The `/subscription/v1` path filters the model catalogue but is not, by itself, a billing boundary. A subscription-first key can still spend account balance when coverage is unavailable.
- Before inference, the extension checks `/subscription/v1/usage` and proceeds only when `routing.recommendedMode` is `subscription`.
- Never add `X-Provider`, body `provider`, `billing_mode: paygo`, or `X-Billing-Mode: paygo`.
- Never synthesize routing suffixes such as `:fast`, `:speed`, `:throughput`, `:latency`, `:cheap`, `:price`, `:floor`, `:tools`, or provider suffixes.
- Exact IDs returned by the subscription catalogue are allowed, including catalogue-defined IDs such as `:thinking` variants.
- Do not add web-search, memory, redaction, caching, or other paid/enhancement suffixes. Use only an exact catalogue ID.

## Secrets

- Never print, quote, log, commit, or persist `NANOGPT_API_KEY` in plaintext.
- The extension prefers `NANOGPT_API_KEY` when explicitly exported; otherwise it reads the sops-nix secret at `/run/secrets/nanogpt-api-key`.
- Do not read or expose that secret directly. Let the extension resolve it only when a NanoGPT tool executes.
- Model metadata and rankings contain no secret and may be cached.

## Tool workflow

1. Use `nanogpt_rank_models` when choosing a model for a task. State the task and hard requirements such as tools, reasoning, vision, structured output, and minimum context.
2. Use ranking profile `decision` for routing, classification, rubric scoring, or calibrated yes/no judgments. This keeps Decisions-category models available without mixing them into prose-generation rankings.
3. Treat rankings as heuristics. Prefer capability fit first; benchmark fields are incomplete and may be stale.
4. Use `nanogpt_models` for exact-name lookup or detailed filtering.
5. Use `nanogpt_usage` when quota state matters.
6. Use `nanogpt_chat` only with an exact ordinary chat model ID returned by the current subscription catalogue.
7. Use `nanogpt_decide` with an exact Decisions-category model ID. Supply one or more named questions of type `choice`, `score`, or `noul`; consume the returned probabilities rather than asking the model for prose.

`nanogpt_chat` is a delegated text call, not a full autonomous subagent. Give it a self-contained prompt with the necessary context. `nanogpt_decide` is a typed decision call, not a prose generator. Avoid large batches, repeated evaluations, or speculative calls unless the user has approved that level of subscription usage.

## Selection guidance

- Coding: require tool calling only if the delegated call actually needs tools; otherwise rank for coding and reasoning quality.
- Architecture, debugging, and planning: favor reasoning and intelligence.
- Fast bounded work: favor speed and low latency.
- Large documents: set a realistic minimum context rather than choosing the largest context blindly.
- Images: require vision explicitly.
- Machine-readable prose output: require structured output explicitly.
- Classification, routing, scoring, and calibrated yes/no probabilities: use the `decision` profile and `nanogpt_decide`.

The extension uses the direct API host by default:

```text
https://api.nano-gpt.com/api/subscription/v1
```

Discovery and inference must use the same host because NanoGPT's website and direct API catalogues can briefly differ during rollouts.
