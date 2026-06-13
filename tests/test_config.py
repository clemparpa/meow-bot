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
    "MISTRAL_VIBE_API_KEY",
    "KOYEB_API_TOKEN",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_APP_PRIVATE_KEY_PATH",
    "DEPLOYMENT_NAME",
    "MEOW_BOT_LOGIN",
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
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot[bot]")

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
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot[bot]")

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.meow_domain == "meow.example.com"
    assert settings.github_app_id == "42"
    assert settings.github_webhook_secret == "s3cr3t"
    assert settings.mistral_api_key == "mk-test"
    assert settings.koyeb_api_token == "kk-test"
    assert settings.deployment_name == "meow-bot-test"
    assert settings.bot_login == "meow-bot[bot]"
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
        # bot_login surfaces under its validation_alias ("MEOW_BOT_LOGIN")
        # rather than the Python attribute name.
        "MEOW_BOT_LOGIN",
    } <= short_fields


def test_vibe_api_key_falls_back_to_mistral_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Without a dedicated vibe key, the sandbox reuses ``MISTRAL_API_KEY``."""
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _set_minimal_env(monkeypatch)
    # MISTRAL_VIBE_API_KEY intentionally unset.

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.mistral_vibe_api_key is None
    assert settings.vibe_api_key == "mk-test"


def test_vibe_api_key_prefers_dedicated_key(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """A set ``MISTRAL_VIBE_API_KEY`` overrides the standard key for vibe."""
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("MISTRAL_VIBE_API_KEY", "vibe-sub-key")

    settings = Settings()  # ty: ignore[missing-argument]

    # The standard key keeps its workspace/SDK role untouched.
    assert settings.mistral_api_key == "mk-test"
    assert settings.vibe_api_key == "vibe-sub-key"


def test_settings_private_key_path_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setenv("MEOW_DOMAIN", "meow.example.com")
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk-test")
    monkeypatch.setenv("KOYEB_API_TOKEN", "kk-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot[bot]")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", "/tmp/custom.pem")

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.github_app_private_key_path == "/tmp/custom.pem"


def _set_minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate the required env vars with throw-away values."""

    monkeypatch.setenv("MEOW_DOMAIN", "meow.example.com")
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("MISTRAL_API_KEY", "mk-test")
    monkeypatch.setenv("KOYEB_API_TOKEN", "kk-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    monkeypatch.setenv("MEOW_BOT_LOGIN", "meow-bot[bot]")


_FAKE_PEM = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIBOgIBAAJBA...fake-content-for-tests...wIDAQAB\n"
    "-----END RSA PRIVATE KEY-----\n"
)


def test_load_github_app_private_key_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Inline `GITHUB_APP_PRIVATE_KEY` is returned verbatim — no file read."""

    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _set_minimal_env(monkeypatch)
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _FAKE_PEM)
    # Point the path at a nonexistent file to prove it isn't touched.
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(tmp_path / "nope.pem"))

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.load_github_app_private_key() == _FAKE_PEM


def test_load_github_app_private_key_from_file(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Without the inline var, the helper falls back to reading the PEM file."""

    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _set_minimal_env(monkeypatch)

    pem_path = tmp_path / "github-app.pem"
    pem_path.write_text(_FAKE_PEM)
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(pem_path))

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.github_app_private_key is None
    assert settings.load_github_app_private_key() == _FAKE_PEM


def test_load_github_app_private_key_inline_wins_over_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """When both sources are set, the inline env var takes precedence."""

    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)
    _set_minimal_env(monkeypatch)

    file_pem = "-----BEGIN RSA PRIVATE KEY-----\nFILE\n-----END RSA PRIVATE KEY-----\n"
    pem_path = tmp_path / "github-app.pem"
    pem_path.write_text(file_pem)
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(pem_path))
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _FAKE_PEM)

    settings = Settings()  # ty: ignore[missing-argument]

    assert settings.load_github_app_private_key() == _FAKE_PEM
