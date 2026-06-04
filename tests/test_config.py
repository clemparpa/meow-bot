"""Tests for :mod:`meow.common.config`."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from meow.common.config import Settings

_REPO_ROOT = Path(__file__).resolve().parent.parent

_REQUIRED_ENV_VARS = (
    "MEOW_DOMAIN",
    "GITHUB_APP_ID",
    "GITHUB_WEBHOOK_SECRET",
    "MISTRAL_API_KEY",
    "KOYEB_API_TOKEN",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "DEPLOYMENT_NAME",
)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure none of the settings vars are inherited from the host shell."""

    for name in _REQUIRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_settings_raises_when_webhook_secret_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    _clear_env(monkeypatch)
    # Move cwd to a directory without a `.env` so the default loader has nothing
    # to fall back to.
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("MEOW_DOMAIN", "example.com")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    # GITHUB_WEBHOOK_SECRET intentionally omitted.
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-key")
    monkeypatch.setenv("KOYEB_API_TOKEN", "koyeb-token")
    monkeypatch.setenv("DEPLOYMENT_NAME", "test-deployment")

    with pytest.raises(ValidationError) as exc_info:
        Settings()  # ty: ignore[missing-argument]

    missing = {
        ".".join(str(loc) for loc in err["loc"])
        for err in exc_info.value.errors()
        if err["type"] == "missing"
    }
    assert "github_webhook_secret" in missing


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("MEOW_DOMAIN", "meow.example.com")
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk-test")
    monkeypatch.setenv("KOYEB_API_TOKEN", "kk-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.meow_domain == "meow.example.com"
    assert settings.github_app_id == "42"
    assert settings.github_webhook_secret == "s3cr3t"
    assert settings.mistral_api_key == "mk-test"
    assert settings.koyeb_api_token == "kk-test"
    assert settings.deployment_name == "meow-bot-test"
    # Default value preserved when env var absent.
    assert settings.github_app_private_key_path == "/secrets/github-app.pem"


def test_env_example_rejected_when_copied_as_is(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """`.env.example` ships with empty values on purpose (template).

    Mirrors the S7 acceptance criterion: copying it to `.env` and loading
    `Settings` must raise — otherwise a self-hoster could boot the stack
    with empty secrets and discover the issue mid-request.
    """
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    env_example = _REPO_ROOT / ".env.example"
    assert env_example.is_file(), "expected .env.example at the repo root"

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=str(env_example))  # ty: ignore[missing-argument,unknown-argument]

    short_fields = {
        ".".join(str(loc) for loc in err["loc"])
        for err in exc_info.value.errors()
        if err["type"] == "string_too_short"
    }
    assert {
        "meow_domain",
        "github_app_id",
        "github_webhook_secret",
        "mistral_api_key",
        "koyeb_api_token",
    } <= short_fields


def test_settings_private_key_path_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("MEOW_DOMAIN", "meow.example.com")
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk-test")
    monkeypatch.setenv("KOYEB_API_TOKEN", "kk-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", "/tmp/custom.pem")

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.github_app_private_key_path == "/tmp/custom.pem"
