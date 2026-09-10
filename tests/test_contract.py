import json

import pytest
from pydantic import ValidationError

from bot.orchestrator.contract import (
    AttemptResult,
    QuestionType,
    Verdict,
)
from bot.prompts import REPAIR_PROMPT_TEMPLATE, SYSTEM_PROMPT
from tests.fixtures.verdicts import (
    abstaining_verdict_json,
    multi_question_verdict_json,
    valid_verdict_json,
)


def test_accepts_well_formed_verdict() -> None:
    verdict = Verdict.model_validate_json(valid_verdict_json(answer="B"))
    assert verdict.answer == "B"


def test_rejects_answer_mismatched_with_selected_choice() -> None:
    payload = json.loads(valid_verdict_json(answer="C"))
    payload["answer"] = "B"
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_only_three_eliminations() -> None:
    payload = json.loads(valid_verdict_json())
    payload["eliminations"] = payload["eliminations"][:3]
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_two_selected_entries() -> None:
    payload = json.loads(valid_verdict_json())
    payload["eliminations"][0]["verdict"] = "selected"
    payload["eliminations"][2]["verdict"] = "selected"
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_duplicate_choice_values() -> None:
    payload = json.loads(valid_verdict_json())
    payload["eliminations"][3]["choice"] = payload["eliminations"][0]["choice"]
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_quantitative_without_values() -> None:
    payload = json.loads(valid_verdict_json())
    payload["question_type"] = "command_of_evidence_quantitative"
    payload["quantitative_values"] = None
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_transitions_without_clause_relationship() -> None:
    payload = json.loads(valid_verdict_json())
    payload["question_type"] = "transitions"
    payload["clause_relationship"] = None
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_rejects_boundaries_without_clause_relationship() -> None:
    payload = json.loads(valid_verdict_json())
    payload["question_type"] = "boundaries"
    payload["clause_relationship"] = None
    with pytest.raises(ValidationError):
        Verdict.model_validate_json(json.dumps(payload))


def test_accepts_not_sat_verbal() -> None:
    verdict = Verdict.model_validate_json(abstaining_verdict_json())
    assert verdict.is_sat_verbal is False
    assert verdict.answer is None
    assert verdict.eliminations == []


def test_accepts_multi_question() -> None:
    verdict = Verdict.model_validate_json(multi_question_verdict_json())
    assert verdict.question_count == 2
    assert verdict.answer is None
    assert verdict.eliminations == []


def test_schema_forbids_additional_properties() -> None:
    schema = Verdict.model_json_schema()
    assert schema["additionalProperties"] is False


def test_attempt_result_ok_and_abstain() -> None:
    verdict = Verdict.model_validate_json(valid_verdict_json())
    ok_result = AttemptResult.ok("model-a", "anthropic", verdict, 1.5)
    assert ok_result.status == "ok"

    abstain_result = AttemptResult.abstain("model-b", "openai", "timeout", 22.0)
    assert abstain_result.status == "abstain"
    assert abstain_result.verdict is None


def test_system_prompt_contains_all_question_types() -> None:
    for question_type in QuestionType:
        assert question_type.value in SYSTEM_PROMPT


def test_repair_prompt_has_no_image_reference() -> None:
    assert "image" not in REPAIR_PROMPT_TEMPLATE.lower()
