from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

ACTIVE_WINDOW = timedelta(hours=7)
COOLDOWN_WINDOW = timedelta(hours=8)


@dataclass(frozen=True)
class UsageStatus:
    allowed: bool
    state: str  # ready, active, cooldown
    remaining: timedelta
    starts_on_first_request: bool = False


def _utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evaluate_usage(
    started_at: Optional[datetime], cooldown_until: Optional[datetime], now: Optional[datetime] = None
) -> UsageStatus:
    """Evaluate a 7h window + 8h cooldown without mutating storage."""
    now = _utc(now) or datetime.now(timezone.utc)
    started_at = _utc(started_at)
    cooldown_until = _utc(cooldown_until)

    if cooldown_until and now < cooldown_until:
        return UsageStatus(False, "cooldown", cooldown_until - now)
    if not started_at or (cooldown_until and now >= cooldown_until):
        return UsageStatus(True, "ready", ACTIVE_WINDOW, starts_on_first_request=True)

    expires_at = started_at + ACTIVE_WINDOW
    if now < expires_at:
        return UsageStatus(True, "active", expires_at - now)
    return UsageStatus(False, "cooldown", COOLDOWN_WINDOW)


def format_remaining(value: timedelta) -> str:
    seconds = max(0, int(value.total_seconds()))
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes:02d}m"
