"""Ephemeral, unauthenticated workspace state for a single Streamlit session."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, MutableMapping

from .usage import ACTIVE_WINDOW, COOLDOWN_WINDOW, UsageStatus, evaluate_usage


def _now() -> datetime:
    return datetime.now(timezone.utc)


def initialize_guest(state: MutableMapping[str, Any]) -> None:
    state.setdefault("guest_messages", [])
    state.setdefault("guest_started_at", None)
    state.setdefault("guest_cooldown_until", None)


def usage_status(state: MutableMapping[str, Any]) -> UsageStatus:
    initialize_guest(state)
    return evaluate_usage(state.get("guest_started_at"), state.get("guest_cooldown_until"), _now())


def consume_usage(state: MutableMapping[str, Any]) -> UsageStatus:
    """Apply the product limit locally for an unauthenticated trial session.

    This is intentionally ephemeral and is not a substitute for server-side
    Supabase enforcement, which is used after sign-in.
    """
    initialize_guest(state)
    now = _now()
    status = evaluate_usage(state.get("guest_started_at"), state.get("guest_cooldown_until"), now)
    if status.state == "cooldown":
        # An expired active window needs a concrete cooldown timestamp.
        if state.get("guest_cooldown_until") is None:
            state["guest_cooldown_until"] = now + COOLDOWN_WINDOW
            return evaluate_usage(state.get("guest_started_at"), state["guest_cooldown_until"], now)
        return status
    if status.starts_on_first_request:
        state["guest_started_at"] = now
        state["guest_cooldown_until"] = None
        return UsageStatus(True, "active", ACTIVE_WINDOW, starts_on_first_request=True)
    return status


def new_chat(state: MutableMapping[str, Any]) -> None:
    state["guest_messages"] = []
