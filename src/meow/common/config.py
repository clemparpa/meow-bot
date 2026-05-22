"""Application settings loaded from environment / `.env` file.

Centralises the runtime configuration described in spec §15.3.  Required
fields raise :class:`pydantic.ValidationError` at startup when missing **or
empty** — this gives us a fail-fast guarantee instead of discovering the
issue mid-request, and means copying ``.env.example`` to ``.env`` without
filling in any value fails loudly rather than booting a misconfigured stack.
"""

from __future__ import annotations

from pydantic import Field
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

    meow_domain: str = Field(min_length=1)
    github_app_id: str = Field(min_length=1)
    github_webhook_secret: str = Field(min_length=1)
    mistral_api_key: str = Field(min_length=1)
    daytona_api_key: str = Field(min_length=1)
    github_app_private_key_path: str = Field(default="/secrets/github-app.pem", min_length=1)
