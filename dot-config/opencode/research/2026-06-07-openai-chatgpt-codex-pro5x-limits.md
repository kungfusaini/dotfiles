# OpenAI ChatGPT/Codex usage limits relevant to Pro 5x

Date: 2026-06-07

## Question

What public, official information exists on usage-limit differences for OpenAI ChatGPT/Codex models relevant to Pro 5x: `gpt-5.5-fast`, `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.4`, `gpt-5.4-mini`/`nano`, Codex variants, and older GPT-5 models? Are limits published as exact counts or relative/credit based, and does model choice affect a shared quota?

## Executive summary

- **ChatGPT Pro 5x is published mostly as a relative allowance**, not exact per-model message caps: Pro $100/5x has “5x higher usage than Plus”; Pro $200/20x has “20x” ([OpenAI Help: About ChatGPT Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).
- **GPT-5.5 in normal ChatGPT is listed as unlimited for Business and Pro, subject to abuse guardrails**, while Plus/Go have an exact `160 messages / 3 hours` GPT-5.5 cap. GPT-5.5 Pro specifically is limited, but OpenAI does **not** publish an exact Pro-model message count ([OpenAI Help: GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits); [OpenAI Help: Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).
- **Codex is the main place where Pro 5x has model-specific published ranges.** For Pro 5x local messages per 5 hours: `gpt-5.5` 80-400, `gpt-5.4` 100-500, `gpt-5.4-mini` 300-1750, `gpt-5.3-codex` 150-750; `gpt-5.3-codex` cloud tasks 50-300 and code reviews 100-250. These are ranges, not guaranteed exact counts, because consumption varies by task size/complexity ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- **Codex local messages and cloud tasks share a five-hour window**, and Codex usage is shared with other “agentic” features once pricing applies, currently including ChatGPT for Excel on Plus/Pro ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan); [OpenAI Help: Credits for Free/Go/Plus/Pro](https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro)).
- I found **no official `gpt-5.5-fast` model page**. Official ChatGPT names are GPT-5.5 Instant/Thinking/Pro; official API/Codex names include `gpt-5.5`, `gpt-5.5-pro`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano`, and Codex-specific `gpt-5.3-codex`/`gpt-5.3-codex-spark` ([API Models](https://platform.openai.com/docs/models); [Codex Models](https://developers.openai.com/codex/models)).

## Sources

- OpenAI Help, “About ChatGPT Pro tiers” — https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro
- OpenAI Help, “GPT-5.5 in ChatGPT” — https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits
- OpenAI Help, “Using Codex with your ChatGPT plan” — https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- OpenAI Help, “Using Credits for Flexible Usage in ChatGPT (Free/Go/Plus/Pro)” — https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- OpenAI Developers, “Codex Pricing” — https://developers.openai.com/codex/pricing
- OpenAI Developers, “Codex Models” — https://developers.openai.com/codex/models
- OpenAI Developers, “API Models” — https://platform.openai.com/docs/models
- OpenAI Developers, “API Pricing” — https://platform.openai.com/docs/pricing
- OpenCode docs, “Providers” — https://opencode.ai/docs/providers/

## Detailed notes

### ChatGPT Pro 5x / 20x

Confirmed facts:

- OpenAI says both Pro tiers include the same core capabilities; the main difference is allowance: **Pro $100 = 5x higher usage than Plus**, **Pro $200 = 20x higher usage than Plus** ([Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).
- OpenAI says Pro has “unlimited access to GPT-5 as well as our legacy models,” subject to Terms of Use and abuse guardrails ([Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).
- OpenAI separately says **the Pro model has usage limits**, the allowance differs by tier, and if reached ChatGPT will use another available model until reset; exact counts are not published in the help article ([Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).

Interpretation: For normal ChatGPT conversations, Pro 5x should not be treated as “5x the exact Plus count for every model,” because OpenAI publishes exact counts only for some non-Pro tiers and publishes Pro mostly as unlimited-with-guardrails plus a separate undisclosed Pro-model cap.

### GPT-5.5 in ChatGPT

Confirmed facts:

- ChatGPT exposes GPT-5.5 as **Instant**, **Thinking**, and **Pro** in the model picker ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).
- Plus/Go users can send up to **160 GPT-5.5 messages every 3 hours**; after that, chats switch to the mini version until reset ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).
- Manual Thinking usage: Go can send up to **10 messages every 5 hours** after enabling Thinking; Plus/Business can manually select GPT-5.5 Thinking, but the help page does not state an exact Plus/Business Thinking cap. Automatic switching from Instant to Thinking does not count against manual Thinking limits ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).
- Business and Pro have **unlimited access to GPT-5 models, subject to abuse guardrails** ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).
- GPT-5.5 Pro is available only to Pro, Business, Enterprise, and Edu plans, and is described as the highest-capability option for hardest tasks ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).
- GPT-5.5 Pro has limitations beyond usage: Apps, Memory, Canvas, and image generation are not available with Pro ([GPT-5.5 in ChatGPT](https://help.openai.com/en/articles/11909943-chatgpt-plus-and-pro-limits)).

### GPT-5.5 API / `gpt-5.5-pro`

Confirmed facts:

- The API models/pricing pages publish token prices and API rate limits by API usage tier, not ChatGPT subscription message counts ([API Models](https://platform.openai.com/docs/models); [API Pricing](https://platform.openai.com/docs/pricing)).
- API pricing lists: `gpt-5.5` standard short-context $5 input / $0.50 cached / $30 output per 1M tokens; `gpt-5.5-pro` $30 input / no cached discount / $180 output per 1M tokens ([API Pricing](https://platform.openai.com/docs/pricing)).
- `gpt-5.5-pro` API page lists API rate limits by API tier, e.g. Tier 1 50 RPM / 50k TPM and Tier 5 2,000 RPM / 4M TPM, but this applies to API usage tiers, not ChatGPT Pro 5x ([GPT-5.5 pro model](https://platform.openai.com/docs/models/gpt-5.5-pro)).

Interpretation: API usage is token/rate-limit based and separate from ChatGPT/Codex included plan limits unless using ChatGPT sign-in inside Codex rather than an API key.

### GPT-5.4, mini, nano

Confirmed facts:

- API pricing lists `gpt-5.4` at $2.50 input / $0.25 cached / $15 output; `gpt-5.4-mini` at $0.75 / $0.075 / $4.50; `gpt-5.4-nano` at $0.20 / $0.02 / $1.25 per 1M tokens ([API Pricing](https://platform.openai.com/docs/pricing)).
- `gpt-5.4-nano` is described as a simple high-volume model for speed/cost-sensitive tasks; its API page has API-tier rate limits, not ChatGPT Pro limits ([GPT-5.4 nano model](https://platform.openai.com/docs/models/gpt-5.4-nano)).
- Codex pricing includes `gpt-5.4` and `gpt-5.4-mini` in ChatGPT-sign-in local-message limits, but not `gpt-5.4-nano` in the Codex included-limit table ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).

### Codex Pro 5x limits

Confirmed facts from the Codex pricing table ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)):

| Plan/model | Local messages / 5h | Cloud tasks / 5h | Code reviews / 5h |
|---|---:|---:|---:|
| Pro 5x + `gpt-5.5` | 80-400 | Not available | Not available |
| Pro 5x + `gpt-5.4` | 100-500 | Not available | Not available |
| Pro 5x + `gpt-5.4-mini` | 300-1750 | Not available | Not available |
| Pro 5x + `gpt-5.3-codex` | 150-750 | 50-300 | 100-250 |

Additional confirmed Codex facts:

- These are **ranges**, because “the number of Codex messages” varies by model, task size/complexity, and local vs cloud execution. Small scripts may consume a fraction of allowance; large codebases, long-running tasks, or extended sessions use significantly more ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- The table footnote says local messages and cloud tasks share a **five-hour window**, and additional weekly limits may apply ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- Codex cloud tasks and code review run on `gpt-5.3-codex` ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- `gpt-5.3-codex-spark` is Pro-only research preview, unavailable in API at launch, and governed by a **separate usage limit that may adjust based on demand** ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan); [Codex Models](https://developers.openai.com/codex/models)).
- `gpt-5.2` and `gpt-5.3-codex` are deprecated in Codex when signed in with ChatGPT; users should update scripts/configs to recommended models ([Codex Models](https://developers.openai.com/codex/models)).

### Codex credits and shared quota

Confirmed facts:

- Codex usage limits depend on plan and count toward the **agentic usage limit**. Codex, ChatGPT for Excel, and Workspace Agents count toward agentic usage ([Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)).
- For Plus/Pro, ChatGPT for Excel usage counts toward the same agentic usage limit as Codex ([Credits for Free/Go/Plus/Pro](https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro)).
- After plan-included Codex usage is exhausted, eligible Plus/Pro users can buy credits. Credits use token-based rates and work across supported features like Codex and ChatGPT for Excel ([Credits for Free/Go/Plus/Pro](https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro)).
- Codex rate card credits per 1M tokens: `gpt-5.5` 125 input / 12.5 cached / 750 output; `gpt-5.4` 62.5 / 6.25 / 375; `gpt-5.4-mini` 18.75 / 1.875 / 113; `gpt-5.3-codex` 43.75 / 4.375 / 350; `gpt-5.2` 43.75 / 4.375 / 350. GPT-5.5 usage averages **5-45 credits per message** ([Codex Pricing](https://developers.openai.com/codex/pricing#how-do-credits-work)).
- Fast mode consumes credits at a higher rate, so it uses included limits faster; image generation uses included limits around 3-5x faster on average ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).

### OpenCode relevance

Confirmed facts:

- OpenCode supports OpenAI by either ChatGPT Plus/Pro OAuth-style sign-in or manual API key. With ChatGPT Plus/Pro sign-in, “all the OpenAI models should be available” via `/models`; with API key, API billing/rate limits apply ([OpenCode Providers](https://opencode.ai/docs/providers/#openai)).
- OpenCode itself does not publish separate OpenAI ChatGPT/Codex quota counts; it is a client that routes to the selected provider/model ([OpenCode Providers](https://opencode.ai/docs/providers/)).

Interpretation: In OpenCode, using ChatGPT Plus/Pro authentication likely draws from OpenAI’s ChatGPT/Codex-style entitlements; using an OpenAI API key draws from API token billing and API-tier rate limits. Exact behavior for a particular OpenCode model selector should be verified in `/status` or provider usage dashboards.

## Tradeoffs

- **Use `gpt-5.5` in Codex for capability/efficiency**: OpenAI says GPT-5.5 uses fewer tokens to achieve comparable results to GPT-5.4 and supports generous usage despite being more capable ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- **Use `gpt-5.4-mini` for volume**: Pro 5x local-message ranges are much higher for mini (300-1750 / 5h) than `gpt-5.5` (80-400 / 5h), and its credit/token cost is much lower ([Codex Pricing](https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan)).
- **Use API key for deterministic billing, not included ChatGPT allowance**: API pricing/rate limits are exact token/RPM/TPM schedules, but not included in the ChatGPT subscription allowance ([API Pricing](https://platform.openai.com/docs/pricing)).
- **Avoid assuming `gpt-5.5-pro` is unlimited**: Pro model access is explicitly limited by tier, but exact counts are not public ([Pro tiers](https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro)).

## Recommendations

1. For Pro 5x + Codex/OpenCode, treat `gpt-5.5`, `gpt-5.4`, and `gpt-5.4-mini` as spending from the same included Codex/agentic pool, with different consumption rates and model-specific displayed ranges.
2. For routine coding loops, switch to `gpt-5.4-mini` to extend usage; use `gpt-5.5` for harder work; reserve GPT-5.5 Pro for ChatGPT/API tasks where its limits/cost are acceptable.
3. Do not rely on `gpt-5.5-fast` as an official OpenAI model ID without confirming in the model picker or `GET /v1/models`; official docs did not expose that model page.
4. Use Codex Settings > Usage or `/status` during active Codex sessions for actual remaining limit, because public ranges are not exact guarantees.

## Open questions / caveats

- Exact GPT-5.5 Pro ChatGPT message counts for Pro 5x are not published.
- Official docs did not document `gpt-5.5-fast`; it may be an alias/client label rather than a public OpenAI model ID.
- Codex ranges can shift over time, and OpenAI notes separate/weekly limits and demand-adjusted limits for Spark.
- Public help pages can change rapidly; this artifact reflects pages fetched on 2026-06-07.
