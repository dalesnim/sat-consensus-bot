from datetime import UTC, datetime

import aiosqlite
from pydantic import BaseModel

from bot.orchestrator.contract import ConsensusResult


class CachedQuestion(BaseModel):
    id: int
    consensus_json: str
    image_sha256: str


class QuestionRow(BaseModel):
    id: int
    phash: str
    image_sha256: str
    image_file_id: str | None
    created_at: str
    question_type: str | None
    consensus_answer: str | None
    consensus_state: str
    resolved_by_tier: str
    ground_truth: str | None
    user_id: int
    consensus_json: str
    served_from_cache: bool
    source_question_id: int | None
    reduced_model_set: bool
    transcription_divergence: bool
    min_transcription_overlap: float | None


async def insert_question(
    conn: aiosqlite.Connection,
    *,
    phash: str,
    image_sha256: str,
    image_file_id: str | None,
    user_id: int,
    consensus: ConsensusResult,
    served_from_cache: bool = False,
    source_question_id: int | None = None,
    reduced_model_set: bool = False,
) -> int:
    created_at = datetime.now(UTC).isoformat()
    question_type = consensus.question_type.value if consensus.question_type else None
    cursor = await conn.execute(
        """
        INSERT INTO questions (
            phash, image_sha256, image_file_id, created_at, question_type,
            consensus_answer, consensus_state, resolved_by_tier, user_id,
            consensus_json, served_from_cache, source_question_id,
            reduced_model_set, transcription_divergence, min_transcription_overlap
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            phash,
            image_sha256,
            image_file_id,
            created_at,
            question_type,
            consensus.winning_letter,
            consensus.tier,
            'single',
            user_id,
            consensus.model_dump_json(),
            int(served_from_cache),
            source_question_id,
            int(reduced_model_set),
            int(consensus.transcription_divergence),
            consensus.min_transcription_overlap,
        ),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


async def find_cached_question(conn: aiosqlite.Connection, phash: str) -> CachedQuestion | None:
    cursor = await conn.execute(
        """
        SELECT id, consensus_json, image_sha256 FROM questions
        WHERE phash = ? AND served_from_cache = 0 AND consensus_state != 'insufficient'
        ORDER BY id DESC LIMIT 1
        """,
        (phash,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return CachedQuestion(id=row[0], consensus_json=row[1], image_sha256=row[2])
