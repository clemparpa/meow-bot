"""Shared dataclasses for parametrized receiver integration cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from meow.receiver.utils import WebhookContext


@dataclass(frozen=True)
class ExpectedDispatch:
    """Asserts the dispatcher spy was called with the right workflow + input."""

    workflow_id: str
    assert_input: Callable[[Any], None] = field(default=lambda _: None)

    def check(self, workflow_id: str, input_model: Any, ctx: WebhookContext) -> None:
        assert workflow_id == self.workflow_id, (
            f"expected workflow_id={self.workflow_id!r}, got {workflow_id!r}"
        )
        self.assert_input(input_model)


@dataclass(frozen=True)
class WebhookCase:
    """One parametrized case for `test_receiver_dispatch`.

    Either `expected_dispatch` is set (happy path: spy was called) OR it's
    None (the receiver short-circuited via skip or HTTP error).
    """

    id: str
    event: str | None
    payload_builder: Callable[[], dict[str, Any]]
    signature_override: str | None = None
    expected_status: int = 200
    expected_body: dict[str, Any] | None = None
    expected_dispatch: ExpectedDispatch | None = None
