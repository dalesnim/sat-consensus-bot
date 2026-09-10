import copy
import json
from pathlib import Path

import httpx
import pytest

from bot.config import ModelConfig, RosterConfig
from bot.validation.boot import BootValidationError, validate_roster

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "openrouter_models.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text())

VALID_ROSTER = RosterConfig(
    models=[
        ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit"),
        ModelConfig(id="anthropic/claude-sonnet-5", lab="anthropic", reasoning="omit"),
        ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none"),
        ModelConfig(id="openai/gpt-5.6-sol", lab="openai", reasoning="none"),
        ModelConfig(id="google/gemini-3.7-flash", lab="google", reasoning="none"),
        ModelConfig(id="deepseek/deepseek-v4.1-flash", lab="deepseek", reasoning="minimal"),
    ],
    min_distinct_labs=4,
    max_tokens=2000,
)


def _client_for(catalog: dict | None, *, status_code: int = 200, body: bytes | None = None) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if body is not None:
            return httpx.Response(status_code, content=body)
        return httpx.Response(status_code, json=catalog)

    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


async def test_validate_roster_passes_with_valid_catalog() -> None:
    async with _client_for(FIXTURE) as client:
        result = await validate_roster(
            VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
        )
    assert result is None


async def test_missing_id_names_offending_model() -> None:
    catalog = copy.deepcopy(FIXTURE)
    catalog["data"] = [e for e in catalog["data"] if e["id"] != "openai/gpt-6-astra"]
    async with _client_for(catalog) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
    assert "openai/gpt-6-astra" in str(exc_info.value)


async def test_missing_image_modality_names_offending_model() -> None:
    catalog = copy.deepcopy(FIXTURE)
    for entry in catalog["data"]:
        if entry["id"] == "deepseek/deepseek-v4.1-flash":
            entry["architecture"]["input_modalities"] = ["text"]
    async with _client_for(catalog) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
    assert "deepseek/deepseek-v4.1-flash" in str(exc_info.value)


async def test_missing_structured_outputs_names_offending_model() -> None:
    catalog = copy.deepcopy(FIXTURE)
    for entry in catalog["data"]:
        if entry["id"] == "openai/gpt-6-astra":
            entry["supported_parameters"] = ["response_format"]
    async with _client_for(catalog) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
    message = str(exc_info.value)
    assert "structured_outputs" in message
    assert "openai/gpt-6-astra" in message


async def test_missing_architecture_key_treated_as_no_image_support() -> None:
    catalog = copy.deepcopy(FIXTURE)
    for entry in catalog["data"]:
        if entry["id"] == "google/gemini-3.7-flash":
            del entry["architecture"]
    async with _client_for(catalog) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
    assert "google/gemini-3.7-flash" in str(exc_info.value)


async def test_three_lab_roster_lists_labs_present() -> None:
    three_lab_roster = RosterConfig(
        models=[
            ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit"),
            ModelConfig(id="anthropic/claude-sonnet-5", lab="anthropic", reasoning="omit"),
            ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none"),
            ModelConfig(id="openai/gpt-5.6-sol", lab="openai", reasoning="none"),
            ModelConfig(id="google/gemini-3.7-flash", lab="google", reasoning="none"),
            ModelConfig(id="deepseek/deepseek-v4.1-flash", lab="google", reasoning="minimal"),
        ],
        min_distinct_labs=4,
        max_tokens=2000,
    )
    async with _client_for(FIXTURE) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                three_lab_roster, base_url="https://openrouter.ai/api/v1", client=client
            )
    message = str(exc_info.value)
    assert "anthropic" in message
    assert "openai" in message
    assert "google" in message


async def test_two_bad_ids_both_named_in_one_message() -> None:
    catalog = copy.deepcopy(FIXTURE)
    catalog["data"] = [
        e for e in catalog["data"] if e["id"] not in ("openai/gpt-6-astra", "google/gemini-3.7-flash")
    ]
    async with _client_for(catalog) as client:
        with pytest.raises(BootValidationError) as exc_info:
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
    message = str(exc_info.value)
    assert "openai/gpt-6-astra" in message
    assert "google/gemini-3.7-flash" in message


async def test_http_500_raises_boot_validation_error() -> None:
    async with _client_for(None, status_code=500, body=b"internal error") as client:
        with pytest.raises(BootValidationError):
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )


async def test_non_json_body_raises_boot_validation_error() -> None:
    async with _client_for(None, status_code=200, body=b"not json at all") as client:
        with pytest.raises(BootValidationError):
            await validate_roster(
                VALID_ROSTER, base_url="https://openrouter.ai/api/v1", client=client
            )
