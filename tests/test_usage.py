from datetime import datetime, timedelta, timezone

from src.usage import ACTIVE_WINDOW, COOLDOWN_WINDOW, evaluate_usage


NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def test_fresh_window_starts_on_first_request():
    status = evaluate_usage(None, None, NOW)
    assert status.allowed and status.starts_on_first_request
    assert status.remaining == ACTIVE_WINDOW


def test_active_window_expires_to_cooldown():
    status = evaluate_usage(NOW - ACTIVE_WINDOW - timedelta(seconds=1), None, NOW)
    assert not status.allowed and status.state == "cooldown"
    assert status.remaining == COOLDOWN_WINDOW


def test_cooldown_is_enforced():
    status = evaluate_usage(NOW - timedelta(hours=9), NOW + timedelta(hours=3), NOW)
    assert not status.allowed and status.remaining == timedelta(hours=3)
