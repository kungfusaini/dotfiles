# LiteLLM routers for OpenCode

This folder contains a companion LiteLLM setup for exposing two OpenCode-facing
router models:

- `native-router` — LiteLLM's built-in complexity router
- `model-router` — a custom classifier-based router hook

## Files

- `config.yaml` — LiteLLM proxy config
- `hooks/model_router.py` — classifier hook for `model-router`

## Required environment variables

At minimum, set these before starting LiteLLM:

- `LITELLM_MASTER_KEY`
- `OPENCODE_FAST_MODEL`
- `OPENCODE_BALANCED_MODEL`
- `OPENCODE_COMPLEX_MODEL`
- `OPENCODE_REASONING_MODEL`
- `OPENCODE_CLASSIFIER_MODEL`

Example tier choices:

- `OPENCODE_FAST_MODEL=openai/gpt-4.1-mini`
- `OPENCODE_BALANCED_MODEL=openai/gpt-4.1`
- `OPENCODE_COMPLEX_MODEL=anthropic/claude-sonnet-4-20250514`
- `OPENCODE_REASONING_MODEL=openai/o3`
- `OPENCODE_CLASSIFIER_MODEL=openai/gpt-4.1-mini`

Provider credentials should be supplied through the normal LiteLLM provider
environment variables for the models you choose, for example `OPENAI_API_KEY`
and `ANTHROPIC_API_KEY`.

## Start LiteLLM

Run LiteLLM from this directory so the callback module path resolves cleanly:

```bash
litellm --config config.yaml
```

## Connect OpenCode

Point OpenCode at the LiteLLM proxy:

- `LITELLM_BASE_URL=http://127.0.0.1:4000/v1`
- `LITELLM_API_KEY=<your master key or virtual key>`

Then restart OpenCode and select either `litellm/native-router` or
`litellm/model-router` from `/models`.
