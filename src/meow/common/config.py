"""Application settings loaded from environment / `.env` file.

Centralises the runtime configuration described in spec §15.3.  All required
fields raise :class:`pydantic.ValidationError` at startup when missing — this
gives us a fail-fast guarantee instead of discovering the issue mid-request.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the meow services.

    Field names map case-insensitively to the env vars listed in spec §15.3:

    - ``MEOW_DOMAIN``
    - ``GITHUB_APP_ID``
    - ``GITHUB_WEBHOOK_SECRET``
    - ``MISTRAL_API_KEY``
    - ``DAYTONA_API_KEY``
    - ``GITHUB_APP_PRIVATE_KEY_PATH`` (defaults to ``/secrets/github-app.pem``)
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    meow_domain: str
    github_app_id: str
    github_webhook_secret: str
    mistral_api_key: str
    daytona_api_key: str
    github_app_private_key_path: str = "/secrets/github-app.pem"
