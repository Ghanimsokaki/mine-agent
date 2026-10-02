from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .store import StoreError, SupabaseStore


@dataclass(frozen=True)
class SignedInUser:
    id: str
    email: str
    provider: str


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def user_from_response(response: Any) -> Optional[SignedInUser]:
    session = _field(response, "session")
    user = _field(response, "user") or _field(session, "user")
    if not user:
        return None
    user_id = _field(user, "id")
    if not user_id:
        return None
    metadata = _field(user, "app_metadata", {}) or {}
    provider = _field(metadata, "provider", "email")
    return SignedInUser(str(user_id), str(_field(user, "email", "")), str(provider))


def remember_session(session_state: dict[str, Any], response: Any) -> Optional[SignedInUser]:
    session = _field(response, "session")
    user = user_from_response(response)
    if not session or not user:
        return None
    access_token = _field(session, "access_token")
    refresh_token = _field(session, "refresh_token")
    if not access_token or not refresh_token:
        return None
    # Kept only in Streamlit's server-side session state, never in a URL or log.
    session_state["auth_tokens"] = {"access_token": access_token, "refresh_token": refresh_token}
    session_state["auth_user"] = user
    return user


def restore_session(store: SupabaseStore, session_state: dict[str, Any]) -> Optional[SignedInUser]:
    tokens = session_state.get("auth_tokens")
    if not isinstance(tokens, dict):
        return None
    try:
        store.set_session(str(tokens["access_token"]), str(tokens["refresh_token"]))
        response = store.client.auth.get_user()
        user = user_from_response(response)
        if user:
            session_state["auth_user"] = user
        return user
    except (StoreError, KeyError, Exception):
        session_state.pop("auth_tokens", None)
        session_state.pop("auth_user", None)
        return None


def begin_oauth(store: SupabaseStore, provider: str, redirect_url: str) -> str:
    try:
        response = store.client.auth.sign_in_with_oauth(
            {"provider": provider, "options": {"redirect_to": redirect_url}}
        )
        url = _field(response, "url")
        if not url:
            raise StoreError("Supabase did not return an OAuth URL.")
        return str(url)
    except StoreError:
        raise
    except Exception as exc:
        raise StoreError(f"Could not start {provider.title()} sign-in. Check the provider setup in Supabase.") from exc


def complete_oauth_callback(store: SupabaseStore, session_state: dict[str, Any], code: str) -> Optional[SignedInUser]:
    try:
        response = store.client.auth.exchange_code_for_session({"auth_code": code})
        return remember_session(session_state, response)
    except Exception as exc:
        raise StoreError("Could not finish sign-in. Try the provider button again.") from exc


def send_email_code(store: SupabaseStore, email: str, redirect_url: str) -> None:
    try:
        store.client.auth.sign_in_with_otp(
            {"email": email, "options": {"email_redirect_to": redirect_url, "should_create_user": True}}
        )
    except Exception as exc:
        raise StoreError("Could not send the email sign-in message. Check Supabase email settings.") from exc


def verify_email_code(store: SupabaseStore, session_state: dict[str, Any], email: str, code: str) -> Optional[SignedInUser]:
    try:
        response = store.client.auth.verify_otp({"email": email, "token": code.strip(), "type": "email"})
        return remember_session(session_state, response)
    except Exception as exc:
        raise StoreError("That email code was not accepted. Request a new sign-in message.") from exc
