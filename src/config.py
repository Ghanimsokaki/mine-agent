from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUESTED_HF_MODEL = "hwiiiiiiii/gemby-agent-3b"
NEMOTRON_MODEL = "nvidia/llama-3.1-nemotron-ultra-253b-v1:free"
HF_CHAT_ENDPOINT = "https://router.huggingface.co/v1/chat/completions"
DEFAULT_ADMIN_EMAIL = "emir.erningpraja@gmail.com"


def _nested(source: Mapping[str, Any], section: str, key: str, default: Any = "") -> Any:
    """Read a Streamlit secrets-like nested mapping without leaking values."""
    try:
        group = source.get(section, {})
        if isinstance(group, Mapping):
            return group.get(key, default)
    except (AttributeError, KeyError, TypeError):
        pass
    return default


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    public_url: str
    huggingface_key: str
    huggingface_model: str
    huggingface_endpoint: str
    openrouter_key: str
    nemotron_model: str
    openrouter_site_url: str
    supabase_url: str
    supabase_anon_key: str
    admin_email: str
    google_oauth_enabled: bool
    browser_bridge_enabled: bool
    max_upload_mb: int

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def has_huggingface(self) -> bool:
        return bool(self.huggingface_key)

    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_key)

    @property
    def has_llm(self) -> bool:
        return self.has_huggingface or self.has_openrouter


def load_config(secrets: Mapping[str, Any]) -> AppConfig:
    public_url = str(_nested(secrets, "app", "public_url", "http://localhost:8501")).rstrip("/")
    return AppConfig(
        app_name=str(_nested(secrets, "app", "name", "ForgePilot")),
        public_url=public_url,
        huggingface_key=str(_nested(secrets, "huggingface", "api_key", "")),
        huggingface_model=str(_nested(secrets, "huggingface", "model", REQUESTED_HF_MODEL)),
        huggingface_endpoint=str(_nested(secrets, "huggingface", "chat_endpoint", HF_CHAT_ENDPOINT)),
        openrouter_key=str(_nested(secrets, "openrouter", "api_key", "")),
        nemotron_model=str(_nested(secrets, "openrouter", "nemotron_model", NEMOTRON_MODEL)),
        openrouter_site_url=str(_nested(secrets, "openrouter", "site_url", public_url)),
        supabase_url=str(_nested(secrets, "supabase", "url", "")).rstrip("/"),
        supabase_anon_key=str(_nested(secrets, "supabase", "anon_key", "")),
        admin_email=str(_nested(secrets, "admin", "email", DEFAULT_ADMIN_EMAIL)).strip().lower(),
        google_oauth_enabled=bool(_nested(secrets, "features", "enable_google_oauth", True)),
        browser_bridge_enabled=bool(_nested(secrets, "features", "enable_browser_bridge", True)),
        max_upload_mb=int(_nested(secrets, "features", "max_upload_mb", 25)),
    )
