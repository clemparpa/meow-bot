"""Declarative spec for one ``vibe`` CLI invocation.

Built by per-use-case factories under ``meow.worker.vibe_tasks`` (one
``make_*_task`` per use case) and consumed opaquely by the ``run_vibe``
activity. Frozen so it hashes cleanly for workflow checkpointing.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from meow.worker.models.meow_config import MeowConfig

__all__ = ["VibeTask"]


class VibeTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Fully-rendered markdown prompt — factories own templating.
    prompt: str = Field(min_length=1)

    # Name of an agent shipped in the sandbox image
    # (sandbox_files/.vibe/agents/<agent>.toml). The agent's TOML pins the
    # tool profile, model, and skill set — which is why none of those
    # appear as fields here. None falls back to vibe's default agent.
    agent: str | None = Field(default=None, min_length=1)

    # Budget caps. Map to ``--max-turns`` and ``--max-price`` on the CLI.
    # Defaults match :class:`MeowConfig` so a hand-built task in tests
    # stays sensible; the nominal path is ``from_meow_config``.
    max_turns: int = Field(default=80, ge=1)
    max_price_usd: float = Field(default=0.50, gt=0)

    @classmethod
    def from_meow_config(
        cls,
        *,
        prompt: str,
        agent: str | None,
        cfg: MeowConfig,
    ) -> Self:
        """Build a task whose budgets come from the repo's ``.meow.yml``."""
        return cls(
            prompt=prompt,
            agent=agent,
            max_turns=cfg.max_turns,
            max_price_usd=cfg.max_price_usd,
        )
