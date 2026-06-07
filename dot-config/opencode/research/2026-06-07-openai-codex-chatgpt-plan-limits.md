# OpenAI Codex / ChatGPT plan limits for a likely UK user

Date: 2026-06-07

## Question

A user says they have the “plus one for 90 pounds” and wants to understand their usage limits, especially Codex limits, and whether using different models contributes to those limits. Clarify likely plan names/prices in GBP, Codex usage limits, model-specific vs shared limits, and ambiguities, using official OpenAI sources where possible.

## Executive summary

- **Likely plan:** “£90” is more consistent with **ChatGPT Pro $100 / Pro 5x** than with **ChatGPT Plus $20**. OpenAI’s official Codex pricing page lists Plus at **$20/month** and Pro starting at **$100/month**; the Pro help article says **Pro $100 = 5x Plus usage** and **Pro $200 = 20x Plus usage**. The public pages I could fetch did not expose localized GBP prices, so the exact “£90” mapping should be confirmed in the user’s ChatGPT billing page. Sources: https://developers.openai.com/codex/pricing, https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro
- **Codex included limits are not a simple fixed message count.** OpenAI publishes ranges because usage depends on model, task size/complexity, context, and local vs cloud. For Plus, example Codex limits per 5h are GPT-5.5 local **15-80**, GPT-5.4 local **20-100**, GPT-5.4-mini local **60-350**, GPT-5.3-Codex local **30-150**, GPT-5.3-Codex cloud **10-60**, code reviews **20-50**. Pro 5x and Pro 20x scale these ranges up. Source: https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- **Limits are partly shared and partly feature/model-specific.** OpenAI says local messages and cloud tasks share a **five-hour window** and additional weekly limits may apply. Code review has its own published 5h range. Codex usage limits are shared with other agentic features once pricing is effective, currently including ChatGPT for Excel on Plus/Pro. Sources: https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan, https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- **Using smaller/cheaper models can make limits last longer.** OpenAI explicitly recommends switching to a smaller model to extend limits; the Codex rate card shows GPT-5.4-mini consumes fewer credits per token than GPT-5.5, and the Codex pricing page shows larger message ranges for mini. Sources: https://developers.openai.com/codex/pricing#what-can-i-do-to-make-your-usage-limits-last-longer, https://help.openai.com/en/articles/20001106-codex-rate-card

## Sources

- OpenAI Developers, “Codex Pricing”: https://developers.openai.com/codex/pricing
- OpenAI Help, “About ChatGPT Pro tiers”: https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro
- OpenAI Help, “GPT-5.5 in ChatGPT”: https://help.openai.com/en/articles/11909943-chatgpt-pricing-and-limits
- OpenAI Help, “Using Credits for Flexible Usage in ChatGPT (Free/Go/Plus/Pro)”: https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- OpenAI Help, “Codex rate card”: https://help.openai.com/en/articles/20001106-codex-rate-card
- OpenAI ChatGPT pricing page: https://chatgpt.com/pricing

## Detailed notes

### Plan names and likely GBP interpretation

Confirmed facts:

- OpenAI’s Codex pricing page says Codex is included in ChatGPT Free, Go, Plus, Pro, Business, Edu, and Enterprise plans. It lists **Plus at $20/month** and **Pro from $100/month**. https://developers.openai.com/codex/pricing
- OpenAI’s Pro help article says there are two Pro tiers: **Pro $100** unlocks **5x higher usage than Plus**, and **Pro $200** unlocks **20x usage than Plus**. https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro
- The same article says the $200 Pro plan remains the highest usage tier, while $100 is a lower-usage Pro option. https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro

Interpretation:

- If the user’s bill is around **£90/month**, they probably mean **ChatGPT Pro $100 / Pro 5x**, not ChatGPT Plus. “Plus one” may be a misremembering of “Pro 5x” or a localized price label.
- I could not confirm exact GBP pricing from the fetched official pages because the public pricing page output omitted currency amounts for localized UK pricing. The safest advice is to check **ChatGPT → Settings → My Plan / Billing** for the exact plan name and tier.

### ChatGPT conversational model limits

Confirmed facts:

- OpenAI’s GPT-5.5 help article says Plus and Go users can send up to **160 messages with GPT-5.5 every 3 hours**; after that, chats switch to the mini version until reset. https://help.openai.com/en/articles/11909943-chatgpt-pricing-and-limits
- The same article says Go Thinking manually enabled is limited to **10 messages every 5 hours**; for Plus/Business manual Thinking is available, and **automatic switching from GPT-5.5 Instant to GPT-5.5 Thinking does not count toward manual Thinking usage limits**. https://help.openai.com/en/articles/11909943-chatgpt-pricing-and-limits
- For Business and Pro, OpenAI describes GPT-5 access as “unlimited” subject to abuse guardrails, but the Pro help article separately says **Pro-model usage is limited** and differs by $100 vs $200 tier; if a Pro-model limit is reached, ChatGPT uses another available model until reset. https://help.openai.com/en/articles/11909943-chatgpt-pricing-and-limits, https://help.openai.com/en/articles/9793128-what-is-chatgpt-pro

Interpretation:

- General ChatGPT chat limits and Codex limits should not be assumed to be the same bucket. The official sources describe Codex limits separately, with separate ranges and credit mechanics.
- “Unlimited” on Pro does not mean no limits at all; it is subject to abuse guardrails and the Pro model itself has an allowance.

### Codex usage limits by plan/model

Confirmed facts from OpenAI’s Codex pricing page:

- OpenAI says the number of Codex messages depends on “the model used, size and complexity of your coding tasks and whether you run them locally or in the cloud.” Larger codebases, long-running tasks, and extended sessions can consume significantly more of the allowance. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- The page publishes ranges, not fixed counts.
- **Plus / Business per 5h:**
  - GPT-5.5 local messages: **15-80**; no cloud/code review listed for GPT-5.5.
  - GPT-5.4 local messages: **20-100**; no cloud/code review listed for GPT-5.4.
  - GPT-5.4-mini local messages: **60-350**; no cloud/code review listed for GPT-5.4-mini.
  - GPT-5.3-Codex local messages: **30-150**; cloud tasks **10-60**; code reviews **20-50**.
- **Pro 5x per 5h:**
  - GPT-5.5 local: **80-400**.
  - GPT-5.4 local: **100-500**.
  - GPT-5.4-mini local: **300-1750**.
  - GPT-5.3-Codex local: **150-750**; cloud **50-300**; code reviews **100-250**.
- **Pro 20x per 5h:**
  - GPT-5.5 local: **300-1600**.
  - GPT-5.4 local: **400-2000**.
  - GPT-5.4-mini local: **1200-7000**.
  - GPT-5.3-Codex local: **600-3000**; cloud **200-1200**; code reviews **400-1000**.
- The table notes: “The usage limits for local messages and cloud tasks share a five-hour window. Additional weekly limits may apply.” https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- The page says Enterprise/Edu flexible-pricing users have no fixed rate limits because usage scales with credits; Enterprise/Edu without flexible pricing generally have Plus-like per-seat limits. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan

### Do different models contribute to the same limits?

Confirmed facts:

- OpenAI explicitly says Codex usage depends on model and publishes different per-5h ranges by model, so model choice matters. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- OpenAI says **local messages and cloud tasks share a five-hour window**; this means a user should not expect separate local/cloud pools for those categories. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- OpenAI says “Codex usage limits are shared with other agentic features once pricing for those features is effective,” currently including **ChatGPT for Excel on Plus and Pro**. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- The credits article repeats that for Plus and Pro, ChatGPT for Excel usage counts toward the same agentic usage limit as Codex. https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- OpenAI says if you are approaching limits, you can switch to a smaller model to make limits last longer. https://developers.openai.com/codex/pricing#what-happens-when-you-hit-usage-limits

Interpretation:

- The best mental model is **one shared Codex/agentic allowance window with variable drain rates**, not totally independent quotas per model. Model tables describe expected capacity/rate, and smaller models stretch the same included usage further.
- Code reviews are displayed separately as “Code Reviews / 5h,” but reviews outside GitHub count toward general usage limits; GitHub PR review usage is specifically what OpenAI labels Code Review usage. https://developers.openai.com/codex/pricing#what-counts-as-code-review-usage

### Credits and overage usage

Confirmed facts:

- For Plus and Pro, after included Codex limits are hit, users can purchase credits instead of upgrading. Free and Go users are prompted to upgrade to Plus instead of adding Codex credits. https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- Credits are used after included usage first. Credits are flexible across supported features available in the plan, currently Codex and ChatGPT for Excel. https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- Credits expire after 12 months and are generally non-refundable except where required by law. https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro
- Codex credit usage is now token-based for most Plus/Pro/Business/Enterprise/Edu customers. GPT-5.5 rates are **125 credits / 1M input tokens**, **12.50 / 1M cached input tokens**, and **750 / 1M output tokens**; a typical GPT-5.5 Codex task may consume **5-45 credits**. https://help.openai.com/en/articles/20001106-codex-rate-card

## Tradeoffs

- **Higher-capability models vs usage duration:** GPT-5.5 is more capable but has lower published message ranges than GPT-5.4-mini. Use it for hard work; use mini/smaller models for routine edits if trying to stretch limits. https://developers.openai.com/codex/pricing
- **Local vs cloud:** Cloud tasks exist for GPT-5.3-Codex and share the five-hour window with local messages. Cloud tasks are convenient for delegated work but can consume the same included allowance. https://developers.openai.com/codex/pricing#what-are-the-usage-limits-for-my-plan
- **Credits vs plan upgrade:** Plus/Pro users can buy credits after hitting limits, which avoids upgrading but adds variable cost. Heavy consistent usage may make Pro 5x/20x or a business setup more predictable. https://help.openai.com/en/articles/12642688-chatgpt-credits-for-plus-and-pro

## Recommendations

1. Ask the user to confirm the exact label in **ChatGPT → Settings → My Plan**. If it says Pro and the monthly cost is around £90, treat it as likely **Pro 5x**.
2. For Codex planning, use the **Pro 5x** table if the plan is Pro $100-equivalent: GPT-5.5 local **80-400 / 5h**, GPT-5.4-mini local **300-1750 / 5h**, GPT-5.3-Codex cloud **50-300 / 5h**, code reviews **100-250 / 5h**.
3. Use `/status` in an active Codex CLI session or the Codex usage dashboard to see the actual remaining allowance. OpenAI says current limits are visible at https://chatgpt.com/codex/settings/usage and via `/status`. https://developers.openai.com/codex/pricing#where-can-i-see-my-current-usage-limits
4. If limits are tight, reduce injected context, keep AGENTS.md concise/scoped, disable unused MCP servers, and switch to smaller models for routine tasks. https://developers.openai.com/codex/pricing#what-can-i-do-to-make-my-usage-limits-last-longer

## Open questions and ambiguities

- **Exact GBP price:** The official public pages fetched exposed USD pricing but not localized GBP amounts. The user’s billing page is the authoritative source for their plan and taxes/VAT.
- **Exact reset behavior:** OpenAI publishes five-hour windows and says additional weekly limits may apply, but does not publish a simple universal formula for every user/workload.
- **Pro model allowance:** OpenAI confirms Pro-model usage is limited and differs between Pro $100 and $200, but the fetched help article does not disclose exact Pro-model message counts.
- **Future changes:** Plan limits, model names, and rate cards change frequently; OpenAI help articles showed updates within the last few days, so users should re-check the usage dashboard for authoritative live limits.
