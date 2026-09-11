---
name: nanogpt
description: Guidance for safely using Sumeet's NanoGPT subscription from Pi agents and generated tools. Use when the user mentions NanoGPT, nano-gpt, NANOGPT_API_KEY, subscription model discovery, or wants agents/tools to call NanoGPT through the subscription API.
license: MIT
---

# NanoGPT Subscription

Use this skill when the user wants Pi, subagents, or tools/scripts you create to call NanoGPT using Sumeet's subscription rather than pay-as-you-go routing.

## Core policy

- Treat NanoGPT calls as spending a subscription token pool. Ask before running large batches, long evaluations, or repeated agent loops.
- Never print, quote, log, commit, or persist `NANOGPT_API_KEY`.
- Do not read dotenv files unless the user explicitly asks to use NanoGPT or the current task clearly requires `NANOGPT_API_KEY`.
- Prefer environment variables already exported in the current process.
- If credentials are not exported, use the Pi/XDG dotenv at `~/.config/pi/nanogpt.env`; read it only for the current command/script and never echo values.
- Store that dotenv with owner-only permissions: `chmod 600 ~/.config/pi/nanogpt.env`.
- Prefer XDG paths for NanoGPT helpers/cache, e.g. `~/.local/share/pi/nanogpt/` for generated model metadata and `~/.config/pi/agent/skills/nanogpt/` for this skill.

## Subscription-safe endpoints

For subscription usage, use the subscription API base directly:

```text
POST https://nano-gpt.com/api/subscription/v1/chat/completions
GET  https://nano-gpt.com/api/subscription/v1/models
GET  https://nano-gpt.com/api/subscription/v1/models?detailed=true
```

The normal OpenAI-compatible base may also exist:

```text
https://nano-gpt.com/api/v1
```

Do **not** use the normal `/api/v1/chat/completions` endpoint when the task is specifically to consume the subscription pool.

## Avoid bypassing subscription coverage

When staying inside subscription usage, avoid provider/routing controls that can bypass subscription coverage and become pay-as-you-go:

- `X-Provider` header
- request body `provider`
- model suffixes/routing suffixes such as `:fast`, `:speed`, `:throughput`, `:latency`, `:cheap`, `:price`
- direct provider suffixes or explicit provider selection

Use plain subscription-included model IDs returned by `/api/subscription/v1/models`.

## Model discovery

First list subscription models:

```sh
curl -fsS \
  -H "Authorization: Bearer $NANOGPT_API_KEY" \
  -H "Accept: application/json" \
  'https://nano-gpt.com/api/subscription/v1/models?detailed=true'
```

For repeated model discovery, generate or use Pi-native helpers that read `NANOGPT_API_KEY` from the environment or `~/.config/pi/nanogpt.env`, join subscription model metadata with NanoGPT website metrics, and never print the key.

Useful model ranking goals:

- coding work: `--sort coding`
- general intelligence: `--sort intelligence`
- fast iteration: `--sort speed` or `--sort avg-tps`
- low startup latency: `--sort latency`
- large files/context: `--sort context`

## Minimal chat completion request

Use plain OpenAI-compatible chat payloads against the subscription endpoint:

```sh
curl -fsS \
  -H "Authorization: Bearer $NANOGPT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<subscription-model-id>",
    "messages": [
      {"role": "system", "content": "You are a concise coding assistant."},
      {"role": "user", "content": "Say hello."}
    ]
  }' \
  'https://nano-gpt.com/api/subscription/v1/chat/completions'
```

Rules for generated tools:

- Read the API key from `process.env.NANOGPT_API_KEY`, not from hardcoded config.
- Accept `NANOGPT_BASE_URL` only as an override; default subscription tools to `https://nano-gpt.com/api/subscription/v1`.
- Sanitize errors before printing; redact bearer tokens and `sk-*`-style secrets.
- Add clear limits (`--limit`, max inputs, timeouts) to scripts that can make multiple calls.
- Cache model lists in `~/.local/share/pi/nanogpt/` when useful, but never cache secrets.

## Node fetch pattern

```js
const baseUrl = (process.env.NANOGPT_SUBSCRIPTION_BASE_URL ||
  "https://nano-gpt.com/api/subscription/v1").replace(/\/+$/, "")
const apiKey = process.env.NANOGPT_API_KEY
if (!apiKey) throw new Error("NANOGPT_API_KEY is required")

const response = await fetch(`${baseUrl}/chat/completions`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  },
  body: JSON.stringify({
    model: modelId,
    messages,
  }),
})

if (!response.ok) {
  const text = await response.text().catch(() => "")
  throw new Error(`NanoGPT HTTP ${response.status}: ${text.slice(0, 1000)}`)
}

const payload = await response.json()
```

Before emitting errors from real tools, redact secrets:

```js
function redact(text) {
  return String(text || "")
    .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
    .replace(/\bsk-[A-Za-z0-9][A-Za-z0-9._:-]{19,}\b/gi, "[redacted-token]")
}
```

## When building a reusable Pi extension later

Keep this skill as the policy layer. If the user asks for executable NanoGPT capability, build a small Pi extension with tools such as:

- `nanogpt_models`: list subscription models, with optional sort/filter.
- `nanogpt_chat`: call `subscription/v1/chat/completions` with safe defaults.
- `nanogpt_rank_models`: choose likely best model for coding/speed/context from cached metadata.

Never install or publish such an extension without explicit user approval and a security review.
