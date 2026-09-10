import logging
from typing import Any

import httpx
from pydantic import BaseModel, SecretStr

from bot.config import ModelConfig
from bot.orchestrator.contract import Verdict
from bot.prompts import REPAIR_PROMPT_TEMPLATE, SYSTEM_PROMPT, USER_PROMPT

logger = logging.getLogger(__name__)

_VERDICT_SCHEMA = Verdict.model_json_schema()


class ModelCallResult(BaseModel):
    text: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "verdict",
            "strict": True,
            "schema": _VERDICT_SCHEMA,
        },
    }


def _with_reasoning(payload: dict[str, Any], model: ModelConfig) -> dict[str, Any]:
    if model.reasoning != "omit":
        payload["reasoning"] = {"effort": model.reasoning}
    return payload


def build_payload(model: ModelConfig, image_data_url: str, *, max_tokens: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model.id,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ],
        "response_format": _response_format(),
        "max_tokens": max_tokens,
        "stream": False,
    }
    return _with_reasoning(payload, model)


def build_repair_payload(model: ModelConfig, raw: str, *, max_tokens: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model.id,
        "messages": [
            {"role": "user", "content": REPAIR_PROMPT_TEMPLATE.format(raw=raw)},
        ],
        "response_format": _response_format(),
        "max_tokens": max_tokens,
        "stream": False,
    }
    return _with_reasoning(payload, model)


async def call_model(
    client: httpx.AsyncClient,
    model: ModelConfig,
    payload: dict[str, Any],
    *,
    base_url: str,
    api_key: SecretStr,
) -> ModelCallResult:
    response = await client.post(
        f"{base_url}/chat/completions",
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
        },
    )
    response.raise_for_status()
    data = response.json()
    text = data["choices"][0]["message"]["content"]
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    cost_usd = usage.get("cost")
    logger.info(
        "model call complete model=%s prompt_tokens=%s completion_tokens=%s cost_usd=%s",
        model.id,
        prompt_tokens,
        completion_tokens,
        cost_usd,
    )
    return ModelCallResult(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
    )
