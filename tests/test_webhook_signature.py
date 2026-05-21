"""Tests for ``meow.common.github.webhook.verify_signature``."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from meow.common.github.webhook import InvalidSignature, verify_signature

SECRET = "s3cr3t-webhook-key"
BODY = b'{"action":"created","sender":{"login":"alice"}}'


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_verify_signature_accepts_valid_signature() -> None:
    header = _sign(BODY, SECRET)
    # Should not raise.
    verify_signature(header, BODY, SECRET)


def test_verify_signature_rejects_wrong_digest() -> None:
    bad = "sha256=" + "0" * 64
    with pytest.raises(InvalidSignature):
        verify_signature(bad, BODY, SECRET)


def test_verify_signature_rejects_truncated_digest() -> None:
    valid = _sign(BODY, SECRET)
    truncated = valid[:-4]  # chop the tail to break the length
    with pytest.raises(InvalidSignature):
        verify_signature(truncated, BODY, SECRET)


def test_verify_signature_rejects_none_header() -> None:
    with pytest.raises(InvalidSignature):
        verify_signature(None, BODY, SECRET)


def test_verify_signature_rejects_missing_prefix() -> None:
    digest = hmac.new(SECRET.encode("utf-8"), BODY, hashlib.sha256).hexdigest()
    with pytest.raises(InvalidSignature):
        verify_signature(digest, BODY, SECRET)


def test_verify_signature_rejects_wrong_secret() -> None:
    header = _sign(BODY, "not-the-right-secret")
    with pytest.raises(InvalidSignature):
        verify_signature(header, BODY, SECRET)


def test_verify_signature_rejects_tampered_body() -> None:
    header = _sign(BODY, SECRET)
    tampered = BODY + b" "
    with pytest.raises(InvalidSignature):
        verify_signature(header, tampered, SECRET)
