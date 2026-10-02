from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from supabase import Client, create_client

from .files import guessed_mime, sanitize_filename
from .usage import ACTIVE_WINDOW, COOLDOWN_WINDOW, UsageStatus, evaluate_usage


class StoreError(RuntimeError):
    """A safe application-level storage error (without secret details)."""


def _first(data: Any) -> Optional[dict[str, Any]]:
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class BrowserPairing:
    agent_id: str
    secret: str
    project_url: str
    anon_key: str

    def bundle(self) -> dict[str, str | int]:
        return {
            "version": 1,
            "project_url": self.project_url,
            "anon_key": self.anon_key,
            "agent_id": self.agent_id,
            "bridge_secret": self.secret,
        }


class SupabaseStore:
    """User-scoped Supabase access. RLS remains the authorization boundary."""

    def __init__(self, url: str, anon_key: str):
        self.url = url.rstrip("/")
        self.anon_key = anon_key
        self.client: Client = create_client(self.url, self.anon_key)

    def set_session(self, access_token: str, refresh_token: str) -> None:
        try:
            self.client.auth.set_session(access_token, refresh_token)
        except Exception as exc:
            raise StoreError("Your sign-in session could not be restored. Please sign in again.") from exc

    def sign_out(self) -> None:
        try:
            self.client.auth.sign_out()
        except Exception:
            pass

    def _raise(self, message: str, exc: Exception) -> None:
        raise StoreError(message) from exc

    # ---- profile, chats and memory -------------------------------------------------
    def ensure_profile(self, user_id: str, email: str | None) -> None:
        try:
            self.client.table("profiles").upsert(
                {"id": user_id, "email": email or "", "updated_at": _iso_now()}, on_conflict="id"
            ).execute()
        except Exception as exc:
            self._raise("Could not prepare your private workspace.", exc)

    def new_conversation(self, title: str = "New conversation") -> dict[str, Any]:
        try:
            response = self.client.table("conversations").insert({"title": title[:120]}).execute()
            row = _first(response.data)
            if not row:
                raise StoreError("Conversation was not created.")
            return row
        except StoreError:
            raise
        except Exception as exc:
            self._raise("Could not create a conversation.", exc)

    def list_conversations(self) -> list[dict[str, Any]]:
        try:
            response = self.client.table("conversations").select("id,title,updated_at,created_at").order("updated_at", desc=True).limit(30).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load conversations.", exc)

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        try:
            response = self.client.table("messages").select("id,role,content,created_at,model").eq("conversation_id", conversation_id).order("created_at").limit(100).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load messages.", exc)

    def save_message(self, conversation_id: str, role: str, content: str, model: str | None = None) -> None:
        try:
            self.client.table("messages").insert(
                {"conversation_id": conversation_id, "role": role, "content": content, "model": model or ""}
            ).execute()
            self.client.table("conversations").update({"updated_at": _iso_now()}).eq("id", conversation_id).execute()
        except Exception as exc:
            self._raise("Could not save this message.", exc)

    def save_memory(self, content: str, source: str = "chat") -> None:
        text = content.strip()[:2000]
        if not text:
            return
        try:
            self.client.table("memory_items").insert({"content": text, "source": source[:50]}).execute()
        except Exception as exc:
            self._raise("Could not save private memory.", exc)

    def recent_memories(self, limit: int = 6) -> list[dict[str, Any]]:
        try:
            response = self.client.table("memory_items").select("content,source,created_at").order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load private memory.", exc)

    # ---- file vault ----------------------------------------------------------------
    def upload_file(self, user_id: str, filename: str, raw: bytes, mime: str | None = None, kind: str = "reference") -> dict[str, Any]:
        safe = sanitize_filename(filename)
        path = f"{user_id}/{uuid.uuid4().hex}-{safe}"
        content_type = mime or guessed_mime(safe)
        try:
            self.client.storage.from_("agent-files").upload(
                path,
                raw,
                file_options={"content-type": content_type, "upsert": "false"},
            )
            result = self.client.table("file_items").insert(
                {"filename": safe, "storage_path": path, "mime_type": content_type, "size_bytes": len(raw), "kind": kind[:50]}
            ).execute()
            return _first(result.data) or {"filename": safe, "storage_path": path}
        except Exception as exc:
            self._raise("Could not upload this private file.", exc)

    def list_files(self) -> list[dict[str, Any]]:
        try:
            response = self.client.table("file_items").select("id,filename,storage_path,mime_type,size_bytes,kind,created_at").order("created_at", desc=True).limit(100).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load private files.", exc)

    def download_file(self, storage_path: str) -> bytes:
        try:
            return self.client.storage.from_("agent-files").download(storage_path)
        except Exception as exc:
            self._raise("Could not read this private file.", exc)

    # ---- account-wide usage window -------------------------------------------------
    def is_current_admin(self) -> bool:
        """Check the server-side Supabase administrator allow-list for this JWT."""
        try:
            response = self.client.rpc("is_current_admin", {}).execute()
            data = response.data
            if isinstance(data, list):
                data = data[0] if data else False
            return bool(data)
        except Exception as exc:
            self._raise("Could not verify the administrator role.", exc)

    def usage_status(self) -> UsageStatus:
        try:
            response = self.client.table("usage_windows").select("started_at,cooldown_until").maybe_single().execute()
            row = response.data or None
            if not row:
                return evaluate_usage(None, None)
            return evaluate_usage(_parse_timestamp(row.get("started_at")), _parse_timestamp(row.get("cooldown_until")))
        except Exception as exc:
            self._raise("Could not check your usage window.", exc)

    def consume_usage(self) -> UsageStatus:
        """Atomically consume access using the authenticated Supabase user."""
        try:
            response = self.client.rpc("consume_usage_window", {}).execute()
            row = _first(response.data)
            if not row:
                raise StoreError("Usage check did not return a result.")
            return UsageStatus(
                allowed=bool(row.get("allowed")),
                state=str(row.get("state", "cooldown")),
                remaining=timedelta(seconds=max(0, int(row.get("remaining_seconds", 0)))),
                starts_on_first_request=bool(row.get("starts_on_first_request", False)),
            )
        except StoreError:
            raise
        except Exception as exc:
            self._raise("Could not verify the usage limit. Try again shortly.", exc)

    # ---- optional browser bridge ---------------------------------------------------
    def create_browser_agent(self, name: str) -> BrowserPairing:
        agent_id = str(uuid.uuid4())
        bridge_secret = secrets.token_urlsafe(32)
        secret_hash = hashlib.sha256(bridge_secret.encode("utf-8")).hexdigest()
        try:
            self.client.table("browser_agents").insert(
                {"id": agent_id, "name": name.strip()[:80] or "My browser", "secret_hash": secret_hash}
            ).execute()
        except Exception as exc:
            self._raise("Could not create a browser pairing.", exc)
        return BrowserPairing(agent_id, bridge_secret, self.url, self.anon_key)

    def list_browser_agents(self) -> list[dict[str, Any]]:
        try:
            response = self.client.table("browser_agents").select("id,name,created_at,last_seen_at").order("created_at", desc=True).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load paired browsers.", exc)

    def queue_browser_task(self, agent_id: str, actions: list[dict[str, Any]], source: str = "chat") -> dict[str, Any]:
        if not actions:
            raise StoreError("No safe browser actions were supplied.")
        try:
            response = self.client.table("browser_tasks").insert(
                {"agent_id": agent_id, "payload": {"actions": actions, "source": source[:50]}}
            ).execute()
            row = _first(response.data)
            if not row:
                raise StoreError("Browser task was not queued.")
            return row
        except StoreError:
            raise
        except Exception as exc:
            self._raise("Could not queue the browser task.", exc)

    def list_browser_tasks(self, agent_id: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            response = self.client.table("browser_tasks").select("id,status,payload,result,created_at,completed_at").eq("agent_id", agent_id).order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as exc:
            self._raise("Could not load browser task results.", exc)
