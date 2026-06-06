"""End-to-end-ish receiver tests: POST a webhook, assert response + dispatch.

Every Mistral call is intercepted via `app.dependency_overrides` on
`get_workflow_dispatcher`, so this suite has no network and no worker
dependency. New cases land in `tests/integration/cases/`.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.integration.cases import ALL_CASES, WebhookCase
from tests.integration.conftest import WebhookPost


@pytest.mark.parametrize("case", ALL_CASES, ids=lambda c: c.id)
async def test_receiver_dispatch(
    case: WebhookCase,
    webhook_post: WebhookPost,
    dispatcher_spy: AsyncMock,
) -> None:
    response = await webhook_post(
        case.event,
        case.payload_builder(),
        signature_override=case.signature_override,
    )

    assert response.status_code == case.expected_status, (
        f"[{case.id}] expected status {case.expected_status}, "
        f"got {response.status_code} (body={response.text})"
    )

    if case.expected_body is not None:
        assert response.json() == case.expected_body, f"[{case.id}] body mismatch"

    if case.expected_dispatch is None:
        dispatcher_spy.assert_not_called()
    else:
        dispatcher_spy.assert_called_once()
        workflow_id, input_model, ctx = dispatcher_spy.call_args.args
        case.expected_dispatch.check(workflow_id, input_model, ctx)
