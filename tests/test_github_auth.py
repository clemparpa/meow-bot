"""Tests for ``meow.common.github.auth.installation_client``.

These tests only verify that the auth strategy is constructed with the
expected arguments — no network calls, no GitHub API mocking. The
network-bound paths (JWT exchange, token fetch) are exercised at the
integration level in v0.1.0 S8.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from githubkit.auth import AppInstallationAuthStrategy
from githubkit.utils import UNSET

from meow.common.github.auth import installation_client


@pytest.fixture
def rsa_pem(tmp_path: Path) -> Path:
    """Generate a throwaway 2048-bit RSA key on disk for the App PEM."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "github-app.pem"
    path.write_bytes(pem)
    return path


@pytest.fixture(autouse=True)
def _auth_env(monkeypatch: pytest.MonkeyPatch, rsa_pem: Path) -> None:
    monkeypatch.setenv("MEOW_DOMAIN", "meow.test")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY_PATH", str(rsa_pem))


async def test_installation_client_default_constructs_auth() -> None:
    async with installation_client(123) as gh:
        auth = gh.auth
        assert isinstance(auth, AppInstallationAuthStrategy)
        assert auth.app_id == "12345"
        assert auth.installation_id == 123
        assert auth.permissions is UNSET
        assert auth.repositories is UNSET


async def test_installation_client_passes_permissions() -> None:
    async with installation_client(123, permissions={"contents": "read"}) as gh:
        auth = gh.auth
        assert isinstance(auth, AppInstallationAuthStrategy)
        assert auth.permissions == {"contents": "read"}


async def test_installation_client_passes_repositories() -> None:
    async with installation_client(123, repositories=["foo/bar"]) as gh:
        auth = gh.auth
        assert isinstance(auth, AppInstallationAuthStrategy)
        assert auth.repositories == ["foo/bar"]
