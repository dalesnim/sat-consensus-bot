

def test_pause_switch_round_trips() -> None:
    """Owner controls the bot from Telegram, so no terminal is needed."""
    from bot.runtime_state import is_paused, set_paused

    set_paused(False)
    assert is_paused() is False
    set_paused(True)
    assert is_paused() is True
    set_paused(False)
    assert is_paused() is False
