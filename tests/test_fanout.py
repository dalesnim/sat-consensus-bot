import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import SecretStr

from bot.config import ModelConfig, RosterConfig
from bot.orchestrator import fanout

IMAGE_URL = "data:image/jpeg;base64,AAAA"
API_KEY = SecretStr("test-secret-key")
BASE_URL = "https://openrouter.ai/api/v1"

VALID_VERDICT_JSON = json.dumps(
    {
        "is_sat_verbal": False,
        "question_count": 0,
        "question_type": None,
        "passage_transcription": "",
        "choice_transcriptions": None,
        "eliminations": [],
        "quantitative_values": None,
        "clause_relationship": None,
        "answer": None,
    }
)

SIX_MODELS = [
    ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="anthropic/claude-sonnet-5", lab="anthropic", reasoning="omit"),
    ModelConfig(id="openai/gpt-6-astra", lab="openai", reasoning="none"),
    ModelConfig(id="openai/gpt-5.6-sol", lab="openai", reasoning="none"),
    ModelConfig(id="google/gemini-3.7-flash", lab="google", reasoning="none"),
    ModelConfig(id="deepseek/deepseek-v4.1-flash", lab="deepseek", reasoning="minimal"),
]

SINGLE_MODEL = ModelConfig(id="anthropic/claude-opus-5", lab="anthropic", reasoning="omit")


def _roster(models: list[ModelConfig]) -> RosterConfig:
    return RosterConfig(models=models, min_distinct_labs=1, max_tokens=2000)


def _chat_response(content: str, *, usage: dict[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return body


async def test_call_one_model_ok_returns_populated_verdict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "ok"
    assert result.verdict is not None
    assert result.verdict.is_sat_verbal is False
    assert result.latency_s > 0


async def test_call_one_model_connect_error_abstains() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason is not None
    assert result.abstain_reason.startswith("transport_error")
    assert result.latency_s > 0


async def test_call_one_model_http_500_abstains() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason == "http_error:500"
    assert result.latency_s > 0


async def test_call_one_model_http_429_abstains() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason == "http_error:429"


async def test_call_one_model_timeout_abstains() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.0)
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=0.05,
        )

    assert result.status == "abstain"
    assert result.abstain_reason == "timeout"
    assert result.latency_s > 0


async def test_call_one_model_empty_body_abstains_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason is not None
    assert result.abstain_reason.startswith("unexpected")


async def test_call_one_model_non_json_body_abstains_without_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all, definitely not")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason is not None
    assert result.abstain_reason.startswith("unexpected")


async def test_call_one_model_repairs_markdown_fenced_json() -> None:
    fenced = f"```json\n{VALID_VERDICT_JSON}\n```"
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(200, json=_chat_response(fenced))
        payload = json.loads(request.content)
        assert "image_url" not in json.dumps(payload)
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "ok"
    assert result.repaired is True
    assert result.raw_first_response == fenced
    assert call_count["n"] == 2


async def test_call_one_model_abstains_after_failed_repair() -> None:
    malformed = "not json at all"
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=_chat_response(malformed))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert result.status == "abstain"
    assert result.abstain_reason == "unparseable_after_repair"
    assert result.raw_first_response == malformed
    assert call_count["n"] == 2


async def test_call_one_model_never_issues_more_than_two_requests() -> None:
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json=_chat_response("still not json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await fanout.call_one_model(
            client,
            SINGLE_MODEL,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            max_tokens=2000,
            per_model_timeout=2.0,
        )

    assert call_count["n"] <= 2


async def test_run_round_returns_six_results_in_roster_order() -> None:
    roster = _roster(SIX_MODELS)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=2.0,
            round_timeout=5.0,
        )

    assert len(results) == 6
    assert [r.model_id for r in results] == [m.id for m in SIX_MODELS]
    assert all(r.status == "ok" for r in results)


async def test_run_round_isolates_single_straggler_under_wall_clock_budget() -> None:
    roster = _roster(SIX_MODELS)
    straggler_id = SIX_MODELS[0].id

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if payload["model"] == straggler_id:
            await asyncio.sleep(5.0)
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    start = time.monotonic()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=0.2,
            round_timeout=5.0,
        )
    elapsed = time.monotonic() - start

    assert elapsed < 1.0
    ok = [r for r in results if r.status == "ok"]
    abstained = [r for r in results if r.status == "abstain"]
    assert len(ok) == 5
    assert len(abstained) == 1
    assert abstained[0].model_id == straggler_id
    assert abstained[0].abstain_reason == "timeout"


async def test_run_round_survives_internal_bug_without_propagating(monkeypatch) -> None:
    roster = _roster(SIX_MODELS)
    buggy_id = SIX_MODELS[2].id
    real_call_one_model = fanout.call_one_model

    async def flaky_call_one_model(client, model, image_data_url, **kwargs):
        if model.id == buggy_id:
            raise RuntimeError("boom")
        return await real_call_one_model(client, model, image_data_url, **kwargs)

    monkeypatch.setattr(fanout, "call_one_model", flaky_call_one_model)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=2.0,
            round_timeout=5.0,
        )

    assert len(results) == 6
    ok = [r for r in results if r.status == "ok"]
    abstained = [r for r in results if r.status == "abstain"]
    assert len(ok) == 5
    assert len(abstained) == 1
    assert abstained[0].model_id == buggy_id
    assert abstained[0].abstain_reason is not None
    assert abstained[0].abstain_reason.startswith("unexpected:RuntimeError")


async def test_run_round_circuit_breaker_when_every_model_hangs() -> None:
    roster = _roster(SIX_MODELS)

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10.0)
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    start = time.monotonic()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=8.0,
            round_timeout=0.3,
        )
    elapsed = time.monotonic() - start

    assert len(results) == 6
    assert all(r.status == "abstain" for r in results)
    assert all(r.abstain_reason == "round_timeout" for r in results)
    assert elapsed < 1.0


async def test_run_round_fires_all_six_concurrently() -> None:
    roster = _roster(SIX_MODELS)
    barrier = asyncio.Barrier(6)
    seen_counter = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_counter["count"] += 1
        await barrier.wait()
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=2.0,
            round_timeout=5.0,
        )

    assert seen_counter["count"] == 6
    assert all(r.status == "ok" for r in results)


async def test_run_round_records_two_requests_for_repaired_model_one_for_clean() -> None:
    fenced = f"```json\n{VALID_VERDICT_JSON}\n```"
    repair_model_id = SIX_MODELS[0].id
    clean_model_id = SIX_MODELS[1].id
    roster = _roster([SIX_MODELS[0], SIX_MODELS[1]])
    call_counts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        model_id = payload["model"]
        call_counts[model_id] = call_counts.get(model_id, 0) + 1
        if model_id == repair_model_id and call_counts[model_id] == 1:
            return httpx.Response(200, json=_chat_response(fenced))
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=API_KEY,
            per_model_timeout=2.0,
            round_timeout=5.0,
        )

    assert call_counts[repair_model_id] == 2
    assert call_counts[clean_model_id] == 1
    by_id = {r.model_id: r for r in results}
    assert by_id[repair_model_id].repaired is True
    assert by_id[clean_model_id].repaired is False


async def test_run_round_logs_no_credential_requirement() -> None:
    """Sanity check: run_round never needs a real API key to complete offline."""
    roster = _roster(SIX_MODELS)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chat_response(VALID_VERDICT_JSON))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await fanout.run_round(
            client,
            roster,
            IMAGE_URL,
            base_url=BASE_URL,
            api_key=SecretStr("not-a-real-key"),
            per_model_timeout=2.0,
            round_timeout=5.0,
        )

    assert len(results) == 6
