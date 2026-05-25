"""GitHub App installation authentication helpers.

Exposes :func:`installation_client`, an async context manager yielding a
:class:`githubkit.GitHub` authenticated as a specific installation, and
:func:`mint_installation_token`, which returns a raw installation token
string for cases where the token must be embedded in a third-party URL
(e.g. ``git clone https://x-access-token:TOKEN@github.com/...`` from
inside a Daytona sandbox). JWT minting, installation-token exchange, and
token caching are delegated to ``githubkit``'s auth strategies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from githubkit import GitHub
from githubkit.auth import AppAuthStrategy, AppInstallationAuthStrategy
from githubkit.utils import UNSET
from githubkit.versions.latest.types import AppPermissionsType

from meow.common.config import Settings

__all__ = ["AppPermissionsType", "installation_client", "mint_installation_token"]


@asynccontextmanager
async def installation_client(
    installation_id: int,
    *,
    permissions: AppPermissionsType | None = None,
    repositories: Sequence[str] | None = None,
) -> AsyncIterator[GitHub]:
    """Yield a githubkit ``GitHub`` client authenticated as an installation.

    Parameters
    ----------
    installation_id:
        Numeric installation ID, as found in the webhook payload or via
        ``GET /app/installations``.
    permissions:
        Optional mapping such as ``{"contents": "read"}`` used to
        down-scope the minted installation token. When omitted the token
        carries the App's full installed permissions.
    repositories:
        Optional list of ``owner/repo`` names further restricting the
        token to specific repositories.

    Yields
    ------
    GitHub
        A configured githubkit client. Tokens are minted lazily and
        cached internally by ``AppInstallationAuthStrategy``.
    """
    settings = Settings()  # ty: ignore[missing-argument]
    pem = Path(settings.github_app_private_key_path).read_text()

    auth = AppInstallationAuthStrategy(
        app_id=settings.github_app_id,
        private_key=pem,
        installation_id=installation_id,
        permissions=permissions if permissions is not None else UNSET,
        repositories=list(repositories) if repositories is not None else UNSET,
    )

    async with GitHub(auth) as gh:
        yield gh


async def mint_installation_token(
    installation_id: int,
    *,
    permissions: AppPermissionsType | None = None,
) -> str:
    """Mint a raw installation access token for embedding in URLs.

    Use this when the calling code needs the bare bearer string — typically
    to pass to a subprocess (``git clone``, ``gh``) that cannot share the
    httpx client. For in-process REST calls prefer
    :func:`installation_client`, which keeps the token inside githubkit.

    The token is the same one ``installation_client`` would acquire on its
    first authenticated request — valid for ~1h, scoped down to
    ``permissions`` if provided, otherwise carrying the App's full
    installed permissions.
    """
    settings = Settings()  # ty: ignore[missing-argument]
    pem = Path(settings.github_app_private_key_path).read_text()

    auth = AppAuthStrategy(app_id=settings.github_app_id, private_key=pem)
    async with GitHub(auth) as gh:
        resp = await gh.rest.apps.async_create_installation_access_token(
            installation_id,
            permissions=permissions if permissions is not None else UNSET,
        )
        return resp.parsed_data.token
