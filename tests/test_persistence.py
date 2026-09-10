import json
from pathlib import Path

import aiosqlite

from bot.db.attempts import insert_attempts
from bot.db.connection import open_connection
from bot.db.questions import insert_question
from bot.orchestrator.consensus import tally
from tests.test_consensus import make_abstain, make_ok


async def test_open_connection_sets_wal_journal_mode(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("PRAGMA journal_mode") as cursor:
            row = await cursor.fetchone()
        assert row[0] == "wal"
    finally:
        await conn.close()


async def test_open_connection_sets_foreign_keys_on(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("PRAGMA foreign_keys") as cursor:
            row = await cursor.fetchone()
        assert row[0] == 1
    finally:
        await conn.close()


async def test_open_connection_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir" / "a.db"
    conn = await open_connection(nested)
    try:
        assert nested.parent.is_dir()
    finally:
        await conn.close()


async def test_open_connection_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "a.db"
    first = await open_connection(path)
    await first.close()
    second = await open_connection(path)
    try:
        pass
    finally:
        await second.close()


async def test_open_connection_creates_all_four_tables(tmp_path: Path) -> None:
    conn = await open_connection(tmp_path / "a.db")
    try:
        async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cursor:
            rows = await cursor.fetchall()
        names = {row[0] for row in rows}
        assert {"questions", "attempts", "users", "spend_days"} <= names
    finally:
        await conn.close()


async def test_db_fixture_connection_is_aiosqlite(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA journal_mode") as cursor:
        row = await cursor.fetchone()
    assert row[0] == "wal"


async def test_insert_question_returns_id_and_resolved_by_tier_is_single(
    db: aiosqlite.Connection,
) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B"), make_ok("m2", "openai", "B")])
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id="file123",
        user_id=42,
        consensus=consensus,
    )
    assert isinstance(question_id, int)

    async with db.execute(
        "SELECT resolved_by_tier, user_id, image_file_id FROM questions WHERE id = ?",
        (question_id,),
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == "single"
    assert row[1] == 42
    assert row[2] == "file123"


async def test_insert_attempts_writes_one_row_per_result(db: aiosqlite.Connection) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id=None,
        user_id=1,
        consensus=consensus,
    )
    results = [
        make_ok("m1", "anthropic", "B"),
        make_ok("m2", "openai", "B"),
        make_ok("m3", "google", "C"),
        make_ok("m4", "deepseek", "B"),
        make_abstain("m5", "anthropic", "timeout"),
        make_abstain("m6", "openai", "http_error:500"),
    ]
    await insert_attempts(db, question_id, results)

    async with db.execute(
        "SELECT COUNT(*) FROM attempts WHERE question_id = ?", (question_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == 6


async def test_abstain_attempt_stores_reason_in_error_and_null_answer(
    db: aiosqlite.Connection,
) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id=None,
        user_id=1,
        consensus=consensus,
    )
    results = [make_ok("m1", "anthropic", "B"), make_abstain("m2", "openai", "timeout")]
    await insert_attempts(db, question_id, results)

    async with db.execute(
        "SELECT error, answer, raw_json FROM attempts WHERE model_id = 'm2'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == "timeout"
    assert row[1] is None
    envelope = json.loads(row[2])
    assert envelope["verdict"] is None
    assert envelope["raw_first_response"] is None


async def test_ok_attempt_stores_answer_and_serialized_verdict(db: aiosqlite.Connection) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id=None,
        user_id=1,
        consensus=consensus,
    )
    results = [make_ok("m1", "anthropic", "B")]
    await insert_attempts(db, question_id, results)

    async with db.execute(
        "SELECT answer, raw_json, tier, confidence FROM attempts WHERE model_id = 'm1'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row[0] == "B"
    envelope = json.loads(row[1])
    assert envelope["verdict"]["answer"] == "B"
    assert row[2] == "single"
    assert row[3] is None


async def test_every_attempt_row_has_null_confidence_and_tier_single(
    db: aiosqlite.Connection,
) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id=None,
        user_id=1,
        consensus=consensus,
    )
    results = [
        make_ok("m1", "anthropic", "B"),
        make_abstain("m2", "openai", "timeout"),
    ]
    await insert_attempts(db, question_id, results)

    async with db.execute("SELECT confidence, tier FROM attempts") as cursor:
        rows = await cursor.fetchall()
    for row in rows:
        assert row[0] is None
        assert row[1] == "single"


async def test_latency_ms_is_integer_millisecond_rounding(db: aiosqlite.Connection) -> None:
    consensus = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    question_id = await insert_question(
        db,
        phash="",
        image_sha256="deadbeef",
        image_file_id=None,
        user_id=1,
        consensus=consensus,
    )
    results = [make_ok("m1", "anthropic", "B")]
    await insert_attempts(db, question_id, results)

    async with db.execute("SELECT latency_ms FROM attempts WHERE model_id = 'm1'") as cursor:
        row = await cursor.fetchone()
    assert row[0] == 1500


async def test_tally_identical_transcriptions_yields_full_overlap() -> None:
    same = "The passage discusses a historical event in careful detail throughout its length."
    results = [
        make_ok("m1", "anthropic", "B", transcription=same),
        make_ok("m2", "openai", "B", transcription=same),
        make_ok("m3", "google", "B", transcription=same),
    ]
    result = tally(results)
    assert result.min_transcription_overlap == 1.0
    assert result.transcription_divergence is False


async def test_tally_disjoint_transcription_pair_yields_zero_overlap() -> None:
    results = [
        make_ok("m1", "anthropic", "B", transcription="alpha beta gamma delta"),
        make_ok("m2", "openai", "B", transcription="epsilon zeta eta theta"),
        make_ok("m3", "google", "B", transcription="alpha beta gamma delta"),
    ]
    result = tally(results)
    assert result.min_transcription_overlap == 0.0
    assert result.transcription_divergence is True


async def test_tally_single_valid_result_has_no_overlap_score() -> None:
    result = tally([make_ok("m1", "anthropic", "B")], min_valid=1)
    assert result.min_transcription_overlap is None
