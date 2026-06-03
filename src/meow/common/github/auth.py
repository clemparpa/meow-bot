"""GitHub App installation authentication helpers.

Exposes :func:`github_installation_auth`, an async context manager
yielding a :class:`GithubInstallationAuth` that wraps a
:class:`githubkit.GitHub` client authenticated as a specific installation
and can mint a raw installation token on demand (for embedding in third
party URLs, e.g. ``git clone https://x-access-token:TOKEN@github.com/...``
from inside a sandbox). JWT minting, installation-token exchange, and
token caching are delegated to ``githubkit``'s auth strategies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from githubkit import GitHub
from githubkit.auth import AppInstallationAuthStrategy
from githubkit.utils import UNSET
from githubkit.versions.latest.types import AppPermissionsType

from meow.common.config import Settings

__all__ = ["AppPermissionsType", "GithubInstallationAuth", "github_installation_auth"]


@dataclass
class GithubInstallationAuth:
    client: GitHub[AppInstallationAuthStrategy]
    auth: AppInstallationAuthStrategy

    async def token(self) -> str:
        permissions = self.auth.permissions
        installation_id = self.auth.installation_id
        repositories = self.auth.repositories
        # Safe on an AppInstallationAuthStrategy client: githubkit's
        # AppAuth.async_auth_flow automatically swaps to JWT auth for
        # App-level endpoints like this one.
        return (
            await self.client.rest.apps.async_create_installation_access_token(
                installation_id,
                permissions=permissions,
                repositories=list(repositories) if repositories is not UNSET else UNSET,
            )
        ).parsed_data.token


@asynccontextmanager
async def github_installation_auth(
    installation_id: int,
    *,
    permissions: AppPermissionsType | None = None,
    repositories: Sequence[str] | None = None,
) -> AsyncIterator[GithubInstallationAuth]:
    settings = Settings()  # ty: ignore[missing-argument]
    pem = Path(settings.github_app_private_key_path).read_text()

    auth = AppInstallationAuthStrategy(
        app_id=settings.github_app_id,
        private_key=pem,
        installation_id=installation_id,
        permissions=permissions if permissions is not None else UNSET,
        repositories=list(repositories) if repositories is not None else UNSET,
    )

    client = GitHub(auth)
    async with client:
        yield GithubInstallationAuth(client=client, auth=auth)
