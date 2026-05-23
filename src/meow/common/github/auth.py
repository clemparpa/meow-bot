"""GitHub App installation authentication helpers.

Exposes :func:`installation_client`, an async context manager yielding a
:class:`githubkit.GitHub` authenticated as a specific installation. JWT
minting, installation-token exchange, and token caching (~1h TTL) are
delegated to ``githubkit.AppInstallationAuthStrategy``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path

from githubkit import GitHub
from githubkit.auth import AppInstallationAuthStrategy
from githubkit.utils import UNSET
from githubkit.versions.latest.types import AppPermissionsType

from meow.common.config import Settings

__all__ = ["AppPermissionsType", "installation_client"]


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
