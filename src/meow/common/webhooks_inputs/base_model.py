"""Base model for webhook-input mappers.

Collapses githubkit's UNSET sentinel to None on construction, so input
models can declare optional fields as plain `T | None` without each
field needing its own BeforeValidator annotation.
"""

from typing import Any

from githubkit.utils import UNSET
from pydantic import BaseModel, model_validator


class UnsetAwareModel(BaseModel):
    """BaseModel that transparently treats `UNSET` as `None`."""

    @model_validator(mode="before")
    @classmethod
    def _collapse_unsets(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: (None if v is UNSET else v) for k, v in data.items()}
        return data
