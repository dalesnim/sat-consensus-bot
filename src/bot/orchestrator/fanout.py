import asyncio
import json
import logging
import time

import httpx
from pydantic import SecretStr, ValidationError

from bot.config import ModelConfig, RosterConfig
from bot.orchestrator.client import build_payload, build_repair_payload, call_model
from bot.orchestrator.contract import AttemptResult, Verdict

logger = logging.getLogger(__name__)


def _abstain_for_exception(
    exc: Exception,
    model: ModelConfig,
    latency_s: float,
    raw_first_response: str | None = None,
) -> AttemptResult:
    if isinstance(exc, TimeoutError):
        reason = "timeout"
    elif isinstance(exc, httpx.HTTPStatusError):
        reason = f"http_error:{exc.response.status_code}"
    elif isinstance(exc, httpx.HTTPError):
        reason = f"transport_error:{type(exc).__name__}"
    else:
        logger.warning("unexpected error calling %s: %s", model.id, exc)
        reason = f"unexpected:{type(exc).__name__}"
    return AttemptResult.abstain(model.id, model.lab, reason, latency_s, raw_first_response)


async def call_one_model(
    client: httpx.AsyncClient,
    model: ModelConfig,
    image_data_url: str,
    *,
    base_url: str,
    api_key: SecretStr,
    max_tokens: int,
    per_model_timeout: float,
) -> AttemptResult:
    """Never raises. Always returns an AttemptResult, either ok or abstained."""
    started = time.monotonic()

    try:
        payload = build_payload(model, image_data_url, max_tokens=max_tokens)
        first = await asyncio.wait_for(
            call_model(client, model, payload, base_url=base_url, api_key=api_key),
            timeout=per_model_timeout,
        )
    except Exception as exc:  # noqa: BLE001
        return _abstain_for_exception(exc, model, time.monotonic() - started)

    try:
        verdict = Verdict.model_validate_json(first.text)
    except (ValidationError, json.JSONDecodeError):
        raw_first_response = first.text

        try:
            repair_payload = build_repair_payload(
                model, raw_first_response, max_tokens=max_tokens
            )
            repaired = await asyncio.wait_for(
                call_model(client, model, repair_payload, base_url=base_url, api_key=api_key),
                timeout=per_model_timeout,
            )
        except Exception as exc:  # noqa: BLE001
            return _abstain_for_exception(
                exc, model, time.monotonic() - started, raw_first_response
            )

        try:
            repaired_verdict = Verdict.model_validate_json(repaired.text)
        except (ValidationError, json.JSONDecodeError):
            return AttemptResult.abstain(
                model.id,
                model.lab,
                "unparseable_after_repair",
                time.monotonic() - started,
                raw_first_response,
            )

        return AttemptResult.ok(
            model.id,
            model.lab,
            repaired_verdict,
            time.monotonic() - started,
            prompt_tokens=repaired.prompt_tokens,
            completion_tokens=repaired.completion_tokens,
            cost_usd=repaired.cost_usd,
            raw_first_response=raw_first_response,
            repaired=True,
        )

    return AttemptResult.ok(
        model.id,
        model.lab,
        verdict,
        time.monotonic() - started,
        prompt_tokens=first.prompt_tokens,
        completion_tokens=first.completion_tokens,
        cost_usd=first.cost_usd,
    )


async def run_round(
    client: httpx.AsyncClient,
    roster: RosterConfig,
    image_data_url: str,
    *,
    base_url: str,
    api_key: SecretStr,
    per_model_timeout: float,
    round_timeout: float,
) -> list[AttemptResult]:
    """Fire every model in the roster concurrently, one round, no cascade.

    Collecting exceptions from the inner gather is a backstop against a programming
    bug inside call_one_model, never the primary error-handling mechanism —
    call_one_model is contractually forbidden from raising.
    """
    started = time.monotonic()
    tasks = [
        call_one_model(
            client,
            model,
            image_data_url,
            base_url=base_url,
            api_key=api_key,
            max_tokens=roster.max_tokens,
            per_model_timeout=per_model_timeout,
        )
        for model in roster.models
    ]

    try:
        raw_results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=round_timeout
        )
    except TimeoutError:
        elapsed = time.monotonic() - started
        logger.info(
            "round complete models=%d ok=0 abstain=%d elapsed_s=%.2f",
            len(roster.models),
            len(roster.models),
            elapsed,
        )
        return [
            AttemptResult.abstain(model.id, model.lab, "round_timeout", elapsed)
            for model in roster.models
        ]

    results: list[AttemptResult] = []
    for model, raw in zip(roster.models, raw_results, strict=True):
        if isinstance(raw, AttemptResult):
            results.append(raw)
        else:
            results.append(
                _abstain_for_exception(raw, model, time.monotonic() - started)
                if isinstance(raw, Exception)
                else AttemptResult.abstain(
                    model.id,
                    model.lab,
                    f"unexpected:{type(raw).__name__}",
                    time.monotonic() - started,
                )
            )

    ok_count = sum(1 for r in results if r.status == "ok")
    logger.info(
        "round complete models=%d ok=%d abstain=%d elapsed_s=%.2f",
        len(roster.models),
        ok_count,
        len(results) - ok_count,
        time.monotonic() - started,
    )
    return results
