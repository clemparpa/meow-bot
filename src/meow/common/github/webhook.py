"""HMAC-SHA256 verification for GitHub webhook deliveries.

Implements the security primitive from spec §12.2: validate the
``X-Hub-Signature-256`` header against the request body using the
shared webhook secret, with a constant-time comparison.
"""

from __future__ import annotations

import hashlib
import hmac

__all__ = ["InvalidSignature", "verify_signature"]

_SIGNATURE_PREFIX = "sha256="


class InvalidSignature(Exception):
    """Raised when a webhook signature header is missing or does not match."""


def verify_signature(header: str | None, body: bytes, secret: str) -> None:
    """Verify a GitHub ``X-Hub-Signature-256`` header.

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
    if header is None or not header.startswith(_SIGNATURE_PREFIX):
        raise InvalidSignature("missing or malformed X-Hub-Signature-256 header")

    provided = header[len(_SIGNATURE_PREFIX) :]
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    # ``hmac.compare_digest`` is timing-safe; it also short-circuits to False
    # when the two strings differ in length, so truncated signatures are
    # rejected here rather than via an explicit length check.
    if not hmac.compare_digest(provided, expected):
        raise InvalidSignature("signature mismatch")
