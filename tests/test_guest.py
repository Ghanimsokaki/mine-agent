from datetime import timedelta

from src.guest import consume_usage, initialize_guest, usage_status
from src.usage import ACTIVE_WINDOW


def test_guest_starts_only_on_first_request():
    state = {}
    initialize_guest(state)
    assert usage_status(state).starts_on_first_request

    status = consume_usage(state)
    assert status.allowed
    assert status.state == "active"
    assert state["guest_started_at"] is not None


def test_guest_moves_to_cooldown_after_active_window():
    state = {}
    initialize_guest(state)
    consume_usage(state)
    state["guest_started_at"] -= ACTIVE_WINDOW + timedelta(seconds=1)
    status = consume_usage(state)
    assert not status.allowed
    assert status.state == "cooldown"
    assert state["guest_cooldown_until"] is not None
