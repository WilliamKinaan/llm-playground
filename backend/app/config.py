"""Central app configuration, loaded from environment variables / .env.

Every feature module should read model names and API keys from `settings`
(see `get_settings()`) rather than hardcoding them, so there is exactly one
place to change credentials or swap models.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mistral_api_key: str
    mistral_base_url: str = "https://api.mistral.ai/v1"
    mistral_chat_model: str = "ministral-8b-latest"
    mistral_moderation_model: str = "mistral-moderation-latest"

    # Model Evaluation feature: logs test-suite runs to a Phoenix Cloud space
    # (https://app.phoenix.arize.com) as Experiments, so accuracy can be
    # tracked run-over-run. No default - the app should fail fast rather than
    # silently pointing at nothing.
    phoenix_api_key: str
    phoenix_base_url: str
    # The Phoenix project that experiment runs land traces in (visible in the
    # Phoenix UI under Tracing). Used to build a standing "see live accuracy"
    # spans link that's shown regardless of whether a run has ever kicked
    # off. Not secret on its own (meaningless without the space in
    # phoenix_base_url, which stays out of committed files), so it's fine as
    # a plain default here.
    phoenix_project_id: str = "UHJvamVjdDo0"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env is only read once per process)."""
    return Settings()
