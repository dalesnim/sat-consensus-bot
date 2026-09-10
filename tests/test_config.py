from pathlib import Path

import pytest
from pydantic import ValidationError

from bot.config import Settings, load_roster, load_settings

MODELS_YAML = Path("models.yaml")

VALID_YAML = """
min_distinct_labs: 4
max_tokens: 2000
models:
  - id: anthropic/claude-opus-5
    lab: anthropic
    reasoning: omit
  - id: openai/gpt-6-astra
    lab: openai
    reasoning: none
"""

MISSING_LAB_YAML = """
min_distinct_labs: 4
max_tokens: 2000
models:
  - id: anthropic/claude-opus-5
    reasoning: omit
"""

BAD_REASONING_YAML = """
min_distinct_labs: 4
max_tokens: 2000
models:
  - id: anthropic/claude-opus-5
    lab: anthropic
    reasoning: high
"""


def test_load_roster_returns_six_models() -> None:
    roster = load_roster(MODELS_YAML)
    assert len(roster.models) == 6


def test_load_roster_ids_in_order() -> None:
    roster = load_roster(MODELS_YAML)
    ids = [m.id for m in roster.models]
    assert ids == [
        "anthropic/claude-opus-5",
        "anthropic/claude-sonnet-5",
        "openai/gpt-6-astra",
        "openai/gpt-5.6-sol",
        "google/gemini-3.7-flash",
        "mistralai/mistral-large-2512",
    ]


def test_anthropic_entries_omit_reasoning() -> None:
    roster = load_roster(MODELS_YAML)
    anthropic_models = [m for m in roster.models if m.lab == "anthropic"]
    assert len(anthropic_models) == 2
    assert all(m.reasoning == "omit" for m in anthropic_models)


def test_no_entry_has_unset_reasoning() -> None:
    roster = load_roster(MODELS_YAML)
    assert all(m.reasoning is not None for m in roster.models)


def test_load_roster_raises_on_missing_lab(tmp_path: Path) -> None:
    bad_file = tmp_path / "models.yaml"
    bad_file.write_text(MISSING_LAB_YAML)
    with pytest.raises(ValidationError):
        load_roster(bad_file)


def test_load_roster_raises_on_invalid_reasoning(tmp_path: Path) -> None:
    bad_file = tmp_path / "models.yaml"
    bad_file.write_text(BAD_REASONING_YAML)
    with pytest.raises(ValidationError):
        load_roster(bad_file)


def test_load_settings_raises_without_telegram_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError):
        load_settings()


def test_load_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    settings = load_settings()
    assert settings.per_model_timeout_seconds == 22
    assert settings.round_timeout_seconds == 26


def test_load_settings_reads_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setenv("OPENROUTER_API_KEY", "y")
    monkeypatch.setenv("PER_MODEL_TIMEOUT_SECONDS", "5")
    settings = load_settings()
    assert settings.per_model_timeout_seconds == 5


def test_settings_repr_never_leaks_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "super-secret-token")
    monkeypatch.setenv("OPENROUTER_API_KEY", "super-secret-key")
    settings = Settings()
    rendered = repr(settings)
    assert "super-secret-token" not in rendered
    assert "super-secret-key" not in rendered


def test_env_example_documents_openrouter_key_with_no_real_values() -> None:
    content = Path(".env.example").read_text()
    assert "OPENROUTER_API_KEY" in content
    for line in content.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition("=")
        if "TOKEN" in key or "KEY" in key:
            assert len(value.strip()) <= 20
