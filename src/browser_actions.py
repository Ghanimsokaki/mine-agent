from __future__ import annotations

import json
import re
from typing import Any

ALLOWED_ACTIONS = {"read_page", "click", "type", "insert_code", "select", "download_file"}
BLOCKED_TERMS = ("password", "passcode", "one-time", "otp", "credit card", "cvv", "security code")
MAX_ACTIONS = 4
MAX_TEXT_LENGTH = 12_000


def extract_browser_actions(response: str) -> list[dict[str, Any]]:
    """Extract a validated browser-actions JSON fence from a model response.

    We deliberately reject rather than repair malformed tool data. The user can
    still copy normal chat output, while browser automation remains narrow.
    """
    match = re.search(r"```browser-actions\s*\n(.*?)```", response, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    try:
        candidate = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    if isinstance(candidate, dict):
        candidate = candidate.get("actions", [])
    if not isinstance(candidate, list):
        return []

    validated: list[dict[str, Any]] = []
    for action in candidate[:MAX_ACTIONS]:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("action", "")).strip()
        selector = str(action.get("selector", "")).strip()
        description = str(action.get("description", "")).strip()[:300]
        text = str(action.get("text", ""))[:MAX_TEXT_LENGTH]
        value = str(action.get("value", ""))[:MAX_TEXT_LENGTH]
        combined = " ".join((kind, selector, description, text, value)).lower()
        if kind not in ALLOWED_ACTIONS or any(term in combined for term in BLOCKED_TERMS):
            continue
        if kind != "download_file" and not selector:
            continue
        clean: dict[str, Any] = {"action": kind, "description": description or kind.replace("_", " ")}
        if selector:
            clean["selector"] = selector
        if text:
            clean["text"] = text
        if value:
            clean["value"] = value
        if kind == "download_file":
            filename = str(action.get("filename", "forgepilot-output.txt"))
            clean["filename"] = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)[:100] or "forgepilot-output.txt"
            clean["text"] = text
        validated.append(clean)
    return validated


def action_summary(action: dict[str, Any]) -> str:
    label = str(action.get("description") or action.get("action", "action"))
    selector = str(action.get("selector", ""))
    return f"{label}{f' — {selector}' if selector else ''}"
