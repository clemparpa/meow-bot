"""Base model for webhook-input mappers.

Collapses githubkit's UNSET sentinel to None on construction, so input
models can declare optional fields as plain `T | None` without each
field needing its own BeforeValidator annotation.
"""

from typing import Any

from githubkit.utils import UNSET
from pydantic import BaseModel, Field, model_validator


class UnsetAwareModel(BaseModel):
    """BaseModel that transparently treats `UNSET` as `None`."""

    @model_validator(mode="before")
    @classmethod
    def _collapse_unsets(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if v is UNSET else v) for k, v in data.items()}
        return data


class WebhookInput(UnsetAwareModel):
    """Base for every webhook-driven workflow input.

    Carries the cross-cutting delivery id and the idempotency key folded into
    the Mistral ``execution_id`` (see ``meow.receiver.client.trigger_workflow``).
    """

    delivery: str | None = Field(
        default=None, description="X-GitHub-Delivery — request id, also the default dedup token"
    )

    def idempotency_key(self) -> str:
        """Dedup token for the ``execution_id``.

        Defaults to one execution per webhook delivery. Override to collapse
        several deliveries that mean the same intent (e.g. a GitHub ``opened``
        and ``labeled`` for one issue) onto a single execution.
        """
        return self.delivery or ""
