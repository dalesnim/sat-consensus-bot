"""Empirical latency spike: fire every configured model once, for real.

Measures actual wall-clock time and actual completion tokens for the exact
prompt/payload shape the bot sends, using the bot's own `build_payload` and
`call_model`. The result decides whether `max_tokens` stays at 2000 — until
this has run, that value is a research estimate, not a measurement.

Usage:
    python scripts/latency_spike.py --image path/to/question.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import SecretStr, ValidationError

from bot.config import ModelConfig, RosterConfig, load_roster, load_settings
from bot.images.extract import to_data_url
from bot.orchestrator.client import build_payload, call_model
from bot.orchestrator.contract import Verdict

_DEFAULT_OUT = Path(".planning/phases/01-core-inference-loop/SPIKE-RESULTS.md")
_MIN_SUCCESSFUL_MODELS = 4


@dataclass(frozen=True, slots=True)
class ModelMeasurement:
    model_id: str
    lab: str
    reasoning: str
    wall_clock_s: float
    prompt_tokens: int | None
    completion_tokens: int | None
    cost_usd: float | None
    completion_chars: int | None
    parsed_first_try: bool
    error: str | None


async def _measure_one(
    client: httpx.AsyncClient,
    model: ModelConfig,
    image_data_url: str,
    *,
    base_url: str,
    api_key: SecretStr,
    max_tokens: int,
) -> ModelMeasurement:
    """Time exactly one real call to one model.

    Deliberately unbounded — the point of this spike is to see how long a
    model actually takes, including past the bot's own 22-second per-model
    timeout.
    """
    payload = build_payload(model, image_data_url, max_tokens=max_tokens)
    started = time.monotonic()
    try:
        result = await call_model(client, model, payload, base_url=base_url, api_key=api_key)
    except Exception as exc:  # noqa: BLE001
        return ModelMeasurement(
            model_id=model.id,
            lab=model.lab,
            reasoning=model.reasoning,
            wall_clock_s=time.monotonic() - started,
            prompt_tokens=None,
            completion_tokens=None,
            cost_usd=None,
            completion_chars=None,
            parsed_first_try=False,
            error=type(exc).__name__,
        )
    elapsed = time.monotonic() - started

    parsed_first_try = True
    try:
        Verdict.model_validate_json(result.text)
    except (ValidationError, json.JSONDecodeError):
        parsed_first_try = False

    return ModelMeasurement(
        model_id=model.id,
        lab=model.lab,
        reasoning=model.reasoning,
        wall_clock_s=elapsed,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        cost_usd=result.cost_usd,
        completion_chars=len(result.text),
        parsed_first_try=parsed_first_try,
        error=None,
    )


async def _run_spike(
    roster: RosterConfig,
    image_data_url: str,
    *,
    base_url: str,
    api_key: SecretStr,
    max_tokens: int,
) -> list[ModelMeasurement]:
    async with httpx.AsyncClient(timeout=None) as client:
        tasks = [
            _measure_one(
                client,
                model,
                image_data_url,
                base_url=base_url,
                api_key=api_key,
                max_tokens=max_tokens,
            )
            for model in roster.models
        ]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    measurements: list[ModelMeasurement] = []
    for model, raw in zip(roster.models, raw_results, strict=True):
        if isinstance(raw, ModelMeasurement):
            measurements.append(raw)
        else:
            error_name = type(raw).__name__ if isinstance(raw, BaseException) else "unknown"
            measurements.append(
                ModelMeasurement(
                    model_id=model.id,
                    lab=model.lab,
                    reasoning=model.reasoning,
                    wall_clock_s=0.0,
                    prompt_tokens=None,
                    completion_tokens=None,
                    cost_usd=None,
                    completion_chars=None,
                    parsed_first_try=False,
                    error=error_name,
                )
            )
    return measurements


def _fmt(value: float | int | None, *, precision: int | None = None) -> str:
    if value is None:
        return "-"
    if precision is not None and isinstance(value, float):
        return f"{value:.{precision}f}"
    return str(value)


def _ordered(measurements: list[ModelMeasurement]) -> list[ModelMeasurement]:
    return sorted(measurements, key=lambda m: m.wall_clock_s, reverse=True)


def _print_table(measurements: list[ModelMeasurement]) -> None:
    header = (
        f"{'model':<34} {'lab':<10} {'reasoning':<10} {'wall_s':>8} "
        f"{'prompt_tok':>10} {'compl_tok':>10} {'cost_usd':>10} "
        f"{'chars':>7} {'parsed':>7} {'error':<20}"
    )
    print(header)
    print("-" * len(header))
    for m in _ordered(measurements):
        print(
            f"{m.model_id:<34} {m.lab:<10} {m.reasoning:<10} {m.wall_clock_s:>8.2f} "
            f"{_fmt(m.prompt_tokens):>10} {_fmt(m.completion_tokens):>10} "
            f"{_fmt(m.cost_usd, precision=4):>10} {_fmt(m.completion_chars):>7} "
            f"{'yes' if m.parsed_first_try else 'no':>7} {m.error or '':<20}"
        )


def _markdown_table(measurements: list[ModelMeasurement]) -> str:
    header = (
        "| model | lab | reasoning | wall_s | prompt_tok | compl_tok "
        "| cost_usd | chars | parsed_first_try | error |"
    )
    divider = "|---|---|---|---|---|---|---|---|---|---|"
    rows = [header, divider]
    for m in _ordered(measurements):
        rows.append(
            f"| {m.model_id} | {m.lab} | {m.reasoning} | {m.wall_clock_s:.2f} "
            f"| {_fmt(m.prompt_tokens)} | {_fmt(m.completion_tokens)} "
            f"| {_fmt(m.cost_usd, precision=4)} | {_fmt(m.completion_chars)} "
            f"| {'yes' if m.parsed_first_try else 'no'} | {m.error or ''} |"
        )
    return "\n".join(rows)


def _recommended_max_tokens(measurements: list[ModelMeasurement]) -> int:
    observed = [m.completion_tokens for m in measurements if m.completion_tokens is not None]
    if not observed:
        return 2000
    raw = math.ceil(max(observed) * 1.3)
    rounded = math.ceil(raw / 100) * 100
    return min(rounded, 2000)


def _cost_path_line(measurements: list[ModelMeasurement]) -> str:
    if any(m.cost_usd is not None for m in measurements):
        return "cost found at usage.cost"
    return "cost field absent"


def _write_results(
    out_path: Path,
    measurements: list[ModelMeasurement],
    *,
    round_wall_clock_s: float,
    recommended_max_tokens: int,
    cost_path_line: str,
    success_count: int,
) -> None:
    timestamp = datetime.now(UTC).isoformat()
    section = "\n".join(
        [
            f"## Spike run: {timestamp}",
            "",
            _markdown_table(measurements),
            "",
            f"- Round wall clock (max across models): {round_wall_clock_s:.2f}s",
            f"- Models returned successfully: {success_count}/{len(measurements)}",
            f"- {cost_path_line}",
            "",
            "## Decision",
            "",
            f"Recommended `max_tokens`: {recommended_max_tokens} "
            "(ceil(max observed completion_tokens * 1.3), rounded up to the "
            "nearest 100, capped at 2000)",
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        f.write(section + "\n")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fire every configured model once against a real SAT question image "
            "and measure real wall-clock time and completion tokens per model."
        )
    )
    parser.add_argument(
        "--image", required=True, type=Path, help="Path to a real SAT question image"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Override max_tokens for this run (defaults to roster.max_tokens in models.yaml)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help=f"Markdown file to append this run's results to (default: {_DEFAULT_OUT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    if not args.image.is_file():
        print(f"error: image file not found: {args.image}", file=sys.stderr)
        return 1

    try:
        settings = load_settings()
    except ValidationError:
        print(
            "error: OpenRouter/Telegram credentials are not configured.\n"
            "Copy .env.example to .env and fill in OPENROUTER_API_KEY "
            "(and TELEGRAM_BOT_TOKEN) before running the spike. See README.md.",
            file=sys.stderr,
        )
        return 1

    roster = load_roster(settings.models_config_path)
    max_tokens = args.max_tokens if args.max_tokens is not None else roster.max_tokens

    try:
        image_data_url = to_data_url(args.image.read_bytes())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    measurements = asyncio.run(
        _run_spike(
            roster,
            image_data_url,
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            max_tokens=max_tokens,
        )
    )

    _print_table(measurements)

    success_count = sum(1 for m in measurements if m.error is None)
    round_wall_clock_s = max((m.wall_clock_s for m in measurements), default=0.0)
    recommended_max_tokens = _recommended_max_tokens(measurements)
    cost_path_line = _cost_path_line(measurements)
    print(cost_path_line)

    _write_results(
        args.out,
        measurements,
        round_wall_clock_s=round_wall_clock_s,
        recommended_max_tokens=recommended_max_tokens,
        cost_path_line=cost_path_line,
        success_count=success_count,
    )

    if success_count < _MIN_SUCCESSFUL_MODELS:
        print(
            f"error: only {success_count}/{len(measurements)} models returned successfully "
            f"(minimum {_MIN_SUCCESSFUL_MODELS}); refusing to treat this as a valid measurement.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
