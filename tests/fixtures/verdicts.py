import json


def valid_verdict_json(answer: str = "B") -> str:
    eliminations = [
        {
            "choice": letter,
            "verdict": "selected" if letter == answer else "eliminated",
            "reason": f"Reason for {letter}.",
        }
        for letter in ("A", "B", "C", "D")
    ]
    return json.dumps(
        {
            "is_sat_verbal": True,
            "question_count": 1,
            "question_type": "central_ideas_details",
            "passage_transcription": "The passage discusses a historical event.",
            "choice_transcriptions": {
                "A": "First choice text.",
                "B": "Second choice text.",
                "C": "Third choice text.",
                "D": "Fourth choice text.",
            },
            "eliminations": eliminations,
            "quantitative_values": None,
            "clause_relationship": None,
            "answer": answer,
        }
    )


def abstaining_verdict_json() -> str:
    return json.dumps(
        {
            "is_sat_verbal": False,
            "question_count": 1,
            "question_type": None,
            "passage_transcription": "",
            "choice_transcriptions": None,
            "eliminations": [],
            "quantitative_values": None,
            "clause_relationship": None,
            "answer": None,
        }
    )


def multi_question_verdict_json() -> str:
    return json.dumps(
        {
            "is_sat_verbal": True,
            "question_count": 2,
            "question_type": None,
            "passage_transcription": "Two questions appear in this image.",
            "choice_transcriptions": None,
            "eliminations": [],
            "quantitative_values": None,
            "clause_relationship": None,
            "answer": None,
        }
    )
