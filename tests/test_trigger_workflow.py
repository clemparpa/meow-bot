"""Unit tests for ``trigger_workflow``'s execution_id + 409 dedup handling.

The receiver builds the Mistral ``execution_id`` from the input's
``idempotency_key`` and swallows a 409 ``WF_1101`` ("workflow already started")
as a no-op, so a duplicate delivery (issue opened+labeled) returns 200 instead of
500ing the webhook. We patch the module-level ``client`` to capture/raise.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from mistralai.client.errors import SDKError

from meow.common.webhooks_inputs.base_model import WebhookInput
from meow.receiver import client as cl
from meow.receiver.client import trigger_workflow
from meow.receiver.utils import WebhookContext


class _Input(WebhookInput):
    def idempotency_key(self) -> str:
        return "KEY"


def _patch_client(monkeypatch, execute) -> None:
    fake = SimpleNamespace(workflows=SimpleNamespace(execute_workflow=execute))
    monkeypatch.setattr(cl, "client", fake)


_CTX = WebhookContext(event_name="issues", delivery="deliv-1")


async def test_execution_id_uses_idempotency_key(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    def execute(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(execution_id=kwargs["execution_id"])

    _patch_client(monkeypatch, execute)

    result = await trigger_workflow("FeatureImplementWorkflow", _Input(), _CTX)

    assert captured["execution_id"] == "issues-KEY-FeatureImplementWorkflow"
    assert result == {"queued": True, "execution_id": "issues-KEY-FeatureImplementWorkflow"}


async def test_409_already_started_is_deduplicated(monkeypatch) -> None:
    def execute(**kwargs):
        raise SDKError("already started", httpx.Response(409))

    _patch_client(monkeypatch, execute)

    result = await trigger_workflow("FeatureImplementWorkflow", _Input(), _CTX)

    # 409 → no-op, the webhook still gets a 200.
    assert result == {"deduplicated": True, "execution_id": "issues-KEY-FeatureImplementWorkflow"}


async def test_non_409_sdkerror_propagates(monkeypatch) -> None:
    def execute(**kwargs):
        raise SDKError("server error", httpx.Response(500))

    _patch_client(monkeypatch, execute)

    with pytest.raises(SDKError):
        await trigger_workflow("FeatureImplementWorkflow", _Input(), _CTX)
