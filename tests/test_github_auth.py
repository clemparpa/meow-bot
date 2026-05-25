"""Tests for ``meow.common.github.auth``.

The ``installation_client`` tests only verify that the auth strategy is
constructed with the expected arguments — no network calls.
``mint_installation_token`` is exercised with an ``httpx.MockTransport``
so we can assert it round-trips through the create-installation-token
REST endpoint and returns the bare token string.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from githubkit.auth import AppInstallationAuthStrategy
from githubkit.utils import UNSET

from meow.common.github import auth as auth_module
from meow.common.github.auth import installation_client, mint_installation_token


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


# --- mint_installation_token ---------------------------------------------


def _mock_token_transport(
    captured: dict[str, Any],
    *,
    token: str = "ghs_minted_token",
) -> httpx.MockTransport:
    """Build a transport that intercepts the access-token POST + JWT auth.

    GitHub's flow is: githubkit attaches a JWT bearer, hits
    ``POST /app/installations/{id}/access_tokens``, and reads
    ``token`` out of the JSON response. We capture the request so the
    test can assert installation_id + permissions made it through.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["auth_header"] = request.headers.get("Authorization", "")
        body = json.loads(request.content) if request.content else {}
        captured["body"] = body
        return httpx.Response(
            201,
            json={
                "token": token,
                "expires_at": "2099-12-31T23:59:59Z",
                "permissions": body.get("permissions", {}),
                "repository_selection": "all",
            },
        )

    return httpx.MockTransport(handler)


async def test_mint_installation_token_returns_token_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    transport = _mock_token_transport(captured, token="ghs_x")

    # Force githubkit to use our MockTransport for both sync and async
    # clients it builds internally.
    original_async = httpx.AsyncClient.__init__

    def patched_async(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_async(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_async)

    token = await mint_installation_token(
        42, permissions={"contents": "read"}
    )

    assert token == "ghs_x"
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/app/installations/42/access_tokens")
    # githubkit attaches the App-level JWT as a Bearer token.
    assert captured["auth_header"].startswith("Bearer ")
    assert captured["body"] == {"permissions": {"contents": "read"}}


async def test_mint_installation_token_omits_permissions_when_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    transport = _mock_token_transport(captured)
    original_async = httpx.AsyncClient.__init__

    def patched_async(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        original_async(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_async)

    _ = await mint_installation_token(7)

    # When no permissions are requested, the POST body must not contain
    # a "permissions" key — sending an empty object would scope the
    # token to *no* permissions, the opposite of "use the App default".
    assert "permissions" not in captured["body"]


async def test_mint_installation_token_is_exported() -> None:
    assert "mint_installation_token" in auth_module.__all__
