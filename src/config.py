from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REQUESTED_MODEL = "hwiiiiiiii/gemby-agent-3b:free"
NEMOTRON_MODEL = "nvidia/llama-3.1-nemotron-ultra-253b-v1:free"


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
    openrouter_key: str
    primary_model: str
    nemotron_model: str
    openrouter_site_url: str
    supabase_url: str
    supabase_anon_key: str
    google_oauth_enabled: bool
    browser_bridge_enabled: bool
    max_upload_mb: int

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_anon_key)

    @property
    def has_openrouter(self) -> bool:
        return bool(self.openrouter_key)


def load_config(secrets: Mapping[str, Any]) -> AppConfig:
    return AppConfig(
        app_name=str(_nested(secrets, "app", "name", "ForgePilot")),
        public_url=str(_nested(secrets, "app", "public_url", "http://localhost:8501")).rstrip("/"),
        openrouter_key=str(_nested(secrets, "openrouter", "api_key", "")),
        primary_model=str(_nested(secrets, "openrouter", "primary_model", REQUESTED_MODEL)),
        nemotron_model=str(_nested(secrets, "openrouter", "nemotron_model", NEMOTRON_MODEL)),
        openrouter_site_url=str(_nested(secrets, "openrouter", "site_url", _nested(secrets, "app", "public_url", "http://localhost:8501"))),
        supabase_url=str(_nested(secrets, "supabase", "url", "")).rstrip("/"),
        supabase_anon_key=str(_nested(secrets, "supabase", "anon_key", "")),
        google_oauth_enabled=bool(_nested(secrets, "features", "enable_google_oauth", True)),
        browser_bridge_enabled=bool(_nested(secrets, "features", "enable_browser_bridge", True)),
        max_upload_mb=int(_nested(secrets, "features", "max_upload_mb", 25)),
    )
