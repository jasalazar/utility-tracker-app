"""
Central configuration — all values come from environment variables (or .env).
Never hard-code secrets here; every sensitive field has no default.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    # APScheduler uses a separate DB index so job metadata never collides
    # with application data.
    redis_scheduler_db: int = 2

    # ------------------------------------------------------------------
    # Google OAuth 2.0 / Gmail API
    # ------------------------------------------------------------------
    google_client_id: str
    google_client_secret: str
    # Must be registered in the Google Cloud Console as an authorised redirect URI.
    google_redirect_uri: str = "http://localhost:8000/auth/callback"

    # Google Cloud Pub/Sub — the topic Gmail push notifications are sent to.
    google_pubsub_topic: str
    # Secret token embedded in the webhook URL to verify calls come from Google.
    pubsub_webhook_token: str

    # ------------------------------------------------------------------
    # Anthropic / Claude
    # ------------------------------------------------------------------
    anthropic_api_key: str
    # Model used for email classification and extraction.
    anthropic_model: str = "claude-opus-4-5"

    # ------------------------------------------------------------------
    # LangSmith observability
    # ------------------------------------------------------------------
    langsmith_api_key: str
    langsmith_project: str = "utility-tracker"
    # LangChain reads LANGCHAIN_* env vars automatically; we mirror them here
    # so they are set before any LangChain import happens.
    langchain_tracing_v2: str = "true"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # ------------------------------------------------------------------
    # JWT session tokens
    # ------------------------------------------------------------------
    jwt_secret: str           # Long, random string — generate with: openssl rand -hex 32
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # ------------------------------------------------------------------
    # Web Push / VAPID (browser + macOS-via-browser notifications)
    # Generate once with: python -c "from pywebpush import Vapid; v=Vapid(); v.generate_keys(); print(v.private_key); print(v.public_key)"
    # ------------------------------------------------------------------
    vapid_private_key: str
    vapid_public_key: str
    # VAPID contact — must be a mailto: or https: URI.
    vapid_email: str = "mailto:admin@example.com"

    # ------------------------------------------------------------------
    # Admin
    # ------------------------------------------------------------------
    # Comma-separated Gmail addresses that receive the admin role on login.
    # Stored as a plain string so Pydantic Settings never tries to JSON-decode
    # it. Parsed into a list at the point of use via settings.admin_email_list.
    # Example: ADMIN_EMAILS=you@gmail.com,other@gmail.com
    admin_emails: str = ""

    @property
    def admin_email_list(self) -> list[str]:
        """Return admin_emails as a lowercase list, safe to call anywhere."""
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_url: str = "http://localhost:8000"
    # Timezone used as the fallback when a user has not set their own.
    default_timezone: str = "America/New_York"


# Singleton — import this everywhere instead of re-instantiating.
settings = Settings()

# Apply LangSmith env vars immediately so LangChain picks them up.
os.environ.setdefault("LANGCHAIN_TRACING_V2", settings.langchain_tracing_v2)
os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key)
os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)
os.environ.setdefault("LANGCHAIN_ENDPOINT", settings.langchain_endpoint)
os.environ.setdefault("ANTHROPIC_API_KEY", settings.anthropic_api_key)
