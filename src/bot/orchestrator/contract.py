from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

ConsensusTier = Literal["strong", "contested", "unresolved", "insufficient"]


class QuestionType(StrEnum):
    central_ideas_details = "central_ideas_details"
    command_of_evidence_textual = "command_of_evidence_textual"
    command_of_evidence_quantitative = "command_of_evidence_quantitative"
    inferences = "inferences"
    words_in_context = "words_in_context"
    text_structure_purpose = "text_structure_purpose"
    cross_text_connections = "cross_text_connections"
    rhetorical_synthesis = "rhetorical_synthesis"
    transitions = "transitions"
    boundaries = "boundaries"
    form_structure_sense = "form_structure_sense"


class RejectionReason(StrEnum):
    not_sat_verbal = "not_sat_verbal"
    multiple_questions = "multiple_questions"
    unreadable_image = "unreadable_image"
    no_image = "no_image"


class Choices(BaseModel):
    A: str
    B: str
    C: str
    D: str


class ChoiceVerdict(BaseModel):
    choice: Literal["A", "B", "C", "D"]
    verdict: Literal["eliminated", "selected"]
    reason: str


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_sat_verbal: bool
    question_count: int = 0
    question_type: QuestionType | None = None
    passage_transcription: str
    choice_transcriptions: Choices | None = None
    eliminations: list[ChoiceVerdict]
    quantitative_values: str | None = None
    clause_relationship: str | None = None
    answer: Literal["A", "B", "C", "D"] | None = None

    @model_validator(mode="after")
    def _check_elimination_discipline(self) -> "Verdict":
        if not self.is_sat_verbal or self.question_count != 1:
            if self.answer is not None:
                raise ValueError(
                    "answer must be None when the question is not a single SAT verbal item"
                )
            return self

        if len(self.eliminations) != 4:
            raise ValueError("eliminations must contain exactly four entries")

        seen_choices: set[str] = set()
        selected_choices: list[str] = []
        for entry in self.eliminations:
            if entry.choice in seen_choices:
                raise ValueError(f"duplicate choice {entry.choice} in eliminations")
            seen_choices.add(entry.choice)
            if entry.verdict == "selected":
                selected_choices.append(entry.choice)

        if seen_choices != {"A", "B", "C", "D"}:
            raise ValueError("eliminations must cover all four choices A, B, C, D")

        if len(selected_choices) != 1:
            raise ValueError("exactly one choice must be marked selected")

        if self.answer != selected_choices[0]:
            raise ValueError("answer must match the selected choice")

        if (
            self.question_type == QuestionType.command_of_evidence_quantitative
            and not self.quantitative_values
        ):
            raise ValueError(
                "quantitative_values is required for command_of_evidence_quantitative"
            )

        if self.question_type in (QuestionType.transitions, QuestionType.boundaries) and (
            not self.clause_relationship
        ):
            raise ValueError("clause_relationship is required for transitions and boundaries")

        return self


class Position(BaseModel):
    letter: Literal["A", "B", "C", "D"]
    votes: int
    labs: int
    reasoning: list[str]


class ModelVote(BaseModel):
    model_id: str
    lab: str
    letter: Literal["A", "B", "C", "D"] | None


class ConsensusResult(BaseModel):
    tier: ConsensusTier
    winning_letter: Literal["A", "B", "C", "D"] | None
    positions: list[Position]
    model_votes: list[ModelVote] = []
    total_valid: int
    abstentions: int
    labs_in_majority: int
    degraded: bool
    transcription_divergence: bool
    question_type: QuestionType | None


class AttemptResult(BaseModel):
    model_id: str
    lab: str
    status: Literal["ok", "abstain"]
    verdict: Verdict | None = None
    abstain_reason: str | None = None
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    raw_first_response: str | None = None
    repaired: bool = False

    @classmethod
    def ok(
        cls,
        model_id: str,
        lab: str,
        verdict: Verdict,
        latency_s: float,
        **usage: object,
    ) -> "AttemptResult":
        return cls(
            model_id=model_id,
            lab=lab,
            status="ok",
            verdict=verdict,
            latency_s=latency_s,
            **usage,
        )

    @classmethod
    def abstain(
        cls,
        model_id: str,
        lab: str,
        reason: str,
        latency_s: float,
        raw_first_response: str | None = None,
    ) -> "AttemptResult":
        return cls(
            model_id=model_id,
            lab=lab,
            status="abstain",
            abstain_reason=reason,
            latency_s=latency_s,
            raw_first_response=raw_first_response,
        )
