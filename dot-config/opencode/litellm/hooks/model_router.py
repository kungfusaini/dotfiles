import json
import os
from typing import Any, Literal

import litellm
from litellm.integrations.custom_logger import CustomLogger


ROUTER_ALIAS = os.getenv("OPENCODE_MODEL_ROUTER_ALIAS", "model-router")
CLASSIFIER_ALIAS = os.getenv("OPENCODE_CLASSIFIER_ALIAS", "opencode-classifier")
DEFAULT_TARGET = os.getenv("OPENCODE_DEFAULT_ROUTE", "opencode-balanced")

TIER_TO_MODEL = {
    "FAST": "opencode-fast",
    "BALANCED": "opencode-balanced",
    "COMPLEX": "opencode-complex",
    "REASONING": "opencode-reasoning",
}

CLASSIFIER_SYSTEM_PROMPT = """You are a strict routing classifier for coding and technical assistant prompts.

Choose exactly one tier:
- FAST: tiny factual asks, short rewrites, simple command help, trivial edits
- BALANCED: normal coding tasks, debugging, medium explanations, common implementation work
- COMPLEX: large design tasks, architecture, deep debugging, multi-file refactors, advanced tool use
- REASONING: prompts explicitly asking for careful reasoning, step-by-step thinking, tradeoff analysis, or complex planning under uncertainty

Return only minified JSON with this schema:
{"tier":"FAST|BALANCED|COMPLEX|REASONING","reason":"<short reason>"}
"""


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            if item.get("type") in {"text", "input_text"} and isinstance(item.get("text"), str):
                parts.append(item["text"])
                continue
            if item.get("type") == "text" and isinstance(item.get("content"), str):
                parts.append(item["content"])
        return "\n".join(part for part in parts if part)
    return ""


def _extract_prompt(data: dict[str, Any]) -> str:
    messages = data.get("messages") or []
    user_messages: list[str] = []

    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        text = _flatten_content(message.get("content"))
        if text.strip():
            user_messages.append(text.strip())

    if not user_messages:
        return ""

    if len(user_messages) == 1:
        return user_messages[0]

    recent = user_messages[-3:]
    return "\n\n".join(f"User turn {idx + 1}: {text}" for idx, text in enumerate(recent))


def _parse_tier(text: str) -> str:
    payload = json.loads(text)
    tier = str(payload.get("tier", "")).strip().upper()
    if tier not in TIER_TO_MODEL:
        raise ValueError(f"Unsupported tier: {tier}")
    return tier


class OpenCodeModelRouter(CustomLogger):
    async def async_pre_call_hook(
        self,
        user_api_key_dict: Any,
        cache: Any,
        data: dict[str, Any],
        call_type: Literal[
            "completion",
            "text_completion",
            "embeddings",
            "image_generation",
            "moderation",
            "audio_transcription",
        ],
    ):
        if call_type != "completion":
            return data

        if data.get("model") != ROUTER_ALIAS:
            return data

        prompt = _extract_prompt(data)
        metadata = data.setdefault("metadata", {})
        metadata["opencode_router"] = ROUTER_ALIAS

        if not prompt:
            data["model"] = DEFAULT_TARGET
            metadata["opencode_router_target"] = DEFAULT_TARGET
            metadata["opencode_router_reason"] = "empty prompt fallback"
            return data

        try:
            response = await litellm.acompletion(
                model=CLASSIFIER_ALIAS,
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                max_tokens=80,
            )
            text = response.choices[0].message.content or ""
            tier = _parse_tier(text)
            target = TIER_TO_MODEL[tier]
            data["model"] = target
            metadata["opencode_router_target"] = target
            metadata["opencode_router_tier"] = tier
            metadata["opencode_router_classifier"] = CLASSIFIER_ALIAS
            return data
        except Exception as exc:
            data["model"] = DEFAULT_TARGET
            metadata["opencode_router_target"] = DEFAULT_TARGET
            metadata["opencode_router_error"] = str(exc)
            return data


proxy_handler_instance = OpenCodeModelRouter()
