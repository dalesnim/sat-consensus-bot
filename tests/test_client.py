import json

import httpx
import pytest
from pydantic import SecretStr

from bot.config import ModelConfig
from bot.orchestrator.client import build_payload, build_repair_payload, call_model
from bot.orchestrator.contract import Verdict

IMAGE_URL = "data:image/jpeg;base64,AAAA"
API_KEY = SecretStr("test-secret-key")
BASE_URL = "https://openrouter.ai/api/v1"

ANTHROPIC_MODEL = ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit")
OPENAI_MODEL = ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none")
DEEPSEEK_MODEL = ModelConfig(
    id="deepseek/deepseek-v4.1-flash", lab="deepseek", reasoning="minimal"
)


def test_build_payload_omits_reasoning_key_for_anthropic() -> None:
    payload = build_payload(ANTHROPIC_MODEL, IMAGE_URL, max_tokens=2000)
    assert "reasoning" not in payload


def test_build_payload_sets_effort_none_for_openai() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    assert payload["reasoning"] == {"effort": "none"}


def test_build_payload_sets_effort_minimal_for_deepseek() -> None:
    payload = build_payload(DEEPSEEK_MODEL, IMAGE_URL, max_tokens=2000)
    assert payload["reasoning"] == {"effort": "minimal"}


def test_build_payload_never_streams() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    assert payload.get("stream", False) is False


def test_build_payload_sets_max_tokens() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=1234)
    assert payload["max_tokens"] == 1234


def test_build_payload_sets_response_format_from_verdict_schema() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    response_format = payload["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "verdict"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert set(schema["properties"]) == set(Verdict.model_json_schema()["properties"])


def test_build_payload_schema_is_strict_for_every_object() -> None:
    """OpenAI rejects strict schemas whose objects omit additionalProperties: false."""
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    schema = payload["response_format"]["json_schema"]["schema"]

    objects: list[dict[str, object]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and isinstance(node.get("properties"), dict):
                objects.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(schema)
    assert objects, "expected at least one object node in the verdict schema"
    for node in objects:
        assert node["additionalProperties"] is False
        properties = node["properties"]
        assert isinstance(properties, dict)
        assert node["required"] == list(properties)


def test_build_payload_system_message_is_byte_identical_across_models() -> None:
    anthropic_payload = build_payload(ANTHROPIC_MODEL, IMAGE_URL, max_tokens=2000)
    deepseek_payload = build_payload(DEEPSEEK_MODEL, IMAGE_URL, max_tokens=2000)
    assert anthropic_payload["messages"][0]["content"] == deepseek_payload["messages"][0][
        "content"
    ]
    from bot.prompts import SYSTEM_PROMPT

    assert anthropic_payload["messages"][0]["content"] == SYSTEM_PROMPT


def test_build_payload_places_image_as_image_url_part() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    parts = payload["messages"][1]["content"]
    image_parts = [p for p in parts if p["type"] == "image_url"]
    assert len(image_parts) == 1
    assert image_parts[0]["image_url"]["url"] == IMAGE_URL


def test_build_repair_payload_contains_raw_text_no_image_no_system_prompt() -> None:
    raw = "```json\n{}\n```"
    payload = build_repair_payload(OPENAI_MODEL, raw, max_tokens=2000)
    assert "image_url" not in json.dumps(payload)
    assert raw in payload["messages"][0]["content"]
    assert len(payload["messages"]) == 1
    assert payload["messages"][0]["role"] == "user"

    from bot.prompts import SYSTEM_PROMPT

    assert SYSTEM_PROMPT not in json.dumps(payload)


def test_build_payload_never_leaks_api_key() -> None:
    payload = build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000)
    assert API_KEY.get_secret_value() not in str(payload)


async def test_call_model_returns_text_from_choices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello"}}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await call_model(
            client,
            OPENAI_MODEL,
            build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000),
            base_url=BASE_URL,
            api_key=API_KEY,
        )

    assert result.text == "hello"


async def test_call_model_populates_usage_fields_when_present() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.0042},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await call_model(
            client,
            OPENAI_MODEL,
            build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000),
            base_url=BASE_URL,
            api_key=API_KEY,
        )

    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.cost_usd == 0.0042


async def test_call_model_leaves_usage_none_when_absent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await call_model(
            client,
            OPENAI_MODEL,
            build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000),
            base_url=BASE_URL,
            api_key=API_KEY,
        )

    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.cost_usd is None


async def test_call_model_raises_http_status_error_on_500() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "internal"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await call_model(
                client,
                OPENAI_MODEL,
                build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000),
                base_url=BASE_URL,
                api_key=API_KEY,
            )


async def test_call_model_sends_bearer_authorization_header_with_unwrapped_key() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await call_model(
            client,
            OPENAI_MODEL,
            build_payload(OPENAI_MODEL, IMAGE_URL, max_tokens=2000),
            base_url=BASE_URL,
            api_key=API_KEY,
        )

    assert captured["authorization"] == f"Bearer {API_KEY.get_secret_value()}"
