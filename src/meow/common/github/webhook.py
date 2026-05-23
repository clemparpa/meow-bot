"""HMAC-SHA256 verification for GitHub webhook deliveries.

Uses githubkit's native verification as per SPEC §15.2.
Replaces the hand-rolled implementation from v0.0.x.
"""

from __future__ import annotations

from githubkit.webhooks import verify as gh_verify

__all__ = ["InvalidSignature", "verify_signature"]


class InvalidSignature(Exception):
    """Raised when a webhook signature header is missing or does not match."""


def verify_signature(header: str | None, body: bytes, secret: str) -> None:
    """Verify a GitHub ``X-Hub-Signature-256`` header using githubkit.

    Parameters
    ----------
    header:
        Raw value of the ``X-Hub-Signature-256`` header, expected to start
        with ``sha256=`` followed by the hex digest. ``None`` is rejected.
    body:
        Exact raw request body bytes that GitHub signed.
    secret:
        Shared webhook secret configured on the GitHub App.

    Raises
    ------
    InvalidSignature
        If the header is missing, malformed, or does not match the
        HMAC-SHA256 digest of ``body`` keyed by ``secret``.
    """
    if header is None:
        raise InvalidSignature("missing X-Hub-Signature-256 header")

    try:
        if not gh_verify(secret, body, header):
            raise InvalidSignature("signature mismatch")
    except AttributeError as e:
        # githubkit's verify() calls .split("=") on the header and raises
        # AttributeError when the prefix is missing or the value is not a str.
        raise InvalidSignature(f"malformed signature header: {e}") from e
