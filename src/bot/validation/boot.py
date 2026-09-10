import json

import httpx

from bot.config import RosterConfig


class BootValidationError(RuntimeError):
    pass


def _local_roster_problems(roster: RosterConfig, *, min_valid_responses: int) -> list[str]:
    problems: list[str] = []

    bad_cost_ids = [m.id for m in roster.models if m.est_cost_usd <= 0]
    if bad_cost_ids:
        problems.append(f"missing a positive est_cost_usd: {', '.join(bad_cost_ids)}")

    reduced_labs = {m.lab for m in roster.reduced_models}
    if len(reduced_labs) < roster.min_distinct_labs:
        problems.append(
            f"reduced set spans only {len(reduced_labs)} distinct labs "
            f"({', '.join(sorted(reduced_labs))}), minimum is {roster.min_distinct_labs}"
        )

    if len(roster.reduced_models) < min_valid_responses:
        problems.append(
            f"reduced set has only {len(roster.reduced_models)} members, "
            f"minimum is {min_valid_responses}"
        )

    return problems


async def validate_roster(
    roster: RosterConfig,
    *,
    base_url: str,
    client: httpx.AsyncClient,
    min_valid_responses: int = 3,
) -> None:
    local_problems = _local_roster_problems(roster, min_valid_responses=min_valid_responses)
    if local_problems:
        raise BootValidationError("; ".join(local_problems))

    try:
        response = await client.get(f"{base_url}/models", timeout=15.0)
        response.raise_for_status()
        catalog = response.json()
    except httpx.HTTPError as exc:
        raise BootValidationError(
            f"could not reach OpenRouter model catalog at {base_url}/models: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise BootValidationError(
            f"OpenRouter model catalog response was not valid JSON: {exc}"
        ) from exc

    entries = {entry["id"]: entry for entry in catalog.get("data", [])}

    missing_ids: list[str] = []
    no_image_ids: list[str] = []
    no_structured_output_ids: list[str] = []

    for model in roster.models:
        entry = entries.get(model.id)
        if entry is None:
            missing_ids.append(model.id)
            continue
        architecture = entry.get("architecture")
        input_modalities = architecture.get("input_modalities", []) if architecture else []
        if "image" not in input_modalities:
            no_image_ids.append(model.id)
        supported_parameters = entry.get("supported_parameters", [])
        if "structured_outputs" not in supported_parameters:
            no_structured_output_ids.append(model.id)

    problems: list[str] = []
    if missing_ids:
        problems.append(f"absent from OpenRouter catalog: {', '.join(missing_ids)}")
    if no_image_ids:
        problems.append(f"do not advertise image input support: {', '.join(no_image_ids)}")
    if no_structured_output_ids:
        problems.append(
            f"missing structured_outputs support: {', '.join(no_structured_output_ids)}"
        )

    labs = {m.lab for m in roster.models}
    if len(labs) < roster.min_distinct_labs:
        problems.append(
            f"roster spans only {len(labs)} distinct labs ({', '.join(sorted(labs))}), "
            f"minimum is {roster.min_distinct_labs}"
        )

    if problems:
        raise BootValidationError("; ".join(problems))
