import json

import httpx

from bot.config import RosterConfig


class BootValidationError(RuntimeError):
    pass


async def validate_roster(
    roster: RosterConfig, *, base_url: str, client: httpx.AsyncClient
) -> None:
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
