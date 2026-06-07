"""Application settings loaded from environment / `.env` file.

Centralises the runtime configuration described in spec §15.3.  Required
fields raise :class:`pydantic.ValidationError` at startup when missing **or
empty** — this gives us a fail-fast guarantee instead of discovering the
issue mid-request, and means copying ``.env.example`` to ``.env`` without
filling in any value fails loudly rather than booting a misconfigured stack.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the meow services.

    Field names map case-insensitively to the env vars listed in spec §15.3:

    - ``MEOW_DOMAIN``
    - ``GITHUB_APP_ID``
    - ``GITHUB_WEBHOOK_SECRET``
    - ``MISTRAL_API_KEY``
    - ``KOYEB_API_TOKEN``
    - ``GITHUB_APP_PRIVATE_KEY`` — inline PEM content. Takes precedence
      over ``GITHUB_APP_PRIVATE_KEY_PATH`` when both are set. Handy on
      PaaS hosts (Koyeb, Fly, Render…) where mounting a file is awkward
      but multi-line env vars are first-class.
    - ``GITHUB_APP_PRIVATE_KEY_PATH`` (defaults to ``/secrets/github-app.pem``)
    - ``DEPLOYMENT_NAME`` — Mistral Workflows deployment grouping the
      receiver and worker(s) of one service together (spec §7). Consumed
      by ``mistralai.workflows.run_worker`` at boot.
    - ``MEOW_BOT_LOGIN`` — GitHub login of the bot, used by the self-event
      filter (receiver) and the mention regex (worker). Required: without
      it the bot can neither detect intents nor guard against self-loops.
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
    koyeb_api_token: str = Field(min_length=1)
    github_app_private_key: str | None = Field(default=None)
    github_app_private_key_path: str = Field(default="/secrets/github-app.pem", min_length=1)
    deployment_name: str = Field(min_length=1)
    # Alias to ``MEOW_BOT_LOGIN`` so the env var follows the ``MEOW_*`` prefix
    # convention shared with ``MEOW_DOMAIN``; the Python attribute stays the
    # short ``bot_login`` for ergonomic call sites.
    bot_login: str = Field(
        min_length=1,
        validation_alias="MEOW_BOT_LOGIN",
    )

    def load_github_app_private_key(self) -> str:
        """Return the GitHub App PEM, preferring the inline env var over the file.

        Both sources are kept so self-hosters can pick whichever fits their
        platform: a mounted secret file for bare-metal / docker-compose,
        or a plain env var for PaaS hosts that don't expose filesystem
        secrets. Reading the file is deferred until first use to match the
        previous behaviour — Settings still boots without a PEM present,
        the failure surfaces on the first GitHub call.
        """
        if self.github_app_private_key:
            return self.github_app_private_key
        return Path(self.github_app_private_key_path).read_text()
