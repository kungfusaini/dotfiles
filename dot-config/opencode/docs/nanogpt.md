# NanoGPT Reference

## Local credentials

Approved local secret keys live in `~/.config/opencode/.env`:

- `NANOGPT_API_KEY`
- `NANOGPT_BASE_URL` (defaults to `https://nano-gpt.com/api/v1`)

Do not print, log, or copy secret values. Prefer reading `~/.config/opencode/.env.example` when only key names are needed.

## Subscription-safe usage

NanoGPT subscription usage should use the subscription API base when the goal is to consume the weekly subscription token pool:

```text
https://nano-gpt.com/api/subscription/v1/chat/completions
```

List subscription models with:

```text
GET https://nano-gpt.com/api/subscription/v1/models
GET https://nano-gpt.com/api/subscription/v1/models?detailed=true
```

Avoid explicit provider selection when staying inside subscription usage. These features can bypass subscription coverage and bill as pay-as-you-go:

- `X-Provider`
- request body `provider`
- provider/routing suffixes such as `:fast`, `:speed`, `:throughput`, `:latency`, `:cheap`, `:price`, and direct provider suffixes

## Website model metrics

The documented `/api/v1/models?detailed=true` endpoint includes model metadata, pricing, capabilities, and subscription fields, but not the website's intelligence/coding/speed benchmark metrics.

The website uses extra endpoints:

```text
GET https://nano-gpt.com/api/explore/text-models
GET https://nano-gpt.com/api/explore/text-model-details?model_ids=<comma-separated-model-ids>
GET https://nano-gpt.com/api/models/benchmark-leaderboard?type=text
```

`text-model-details` returns per-model fields such as:

- `avgTps`
- `avgTtftMs`
- `benchmarkData.intelligence`
- `benchmarkData.coding`
- `benchmarkData.speedTokensPerSecond`
- `benchmarkData.gpqa`, `hle`, `ifbench`, `lcr`, `scicode`, `tau2`, `terminalbenchHard`
- `benchmarkData.lastUpdated`

## Joined subscription model script

Use this helper to join subscription model metadata with website metrics:

```bash
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --limit 20
```

Useful options:

```bash
# Full JSON payload
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --json --output ~/.local/share/opencode/nanogpt-subscription-models.json

# CSV, all rows, sorted by coding score
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --csv --all --sort coding

# Table sorted by speed metrics
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --sort speed --limit 25
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --sort avg-tps --limit 25
~/.config/opencode/scripts/nanogpt-subscription-models.mjs --sort latency --limit 25
```

Supported sort keys:

- `intelligence`
- `coding`
- `math`
- `speed` (`benchmarkData.speedTokensPerSecond`)
- `avg-tps`
- `latency` (lower `avgTtftMs` first)
- `context`
- `output`
- `multiplier` (lower subscription input-token multiplier first)
- `price`
- `name`

The script reads `NANOGPT_API_KEY` from `~/.config/opencode/.env` and never prints the key.
