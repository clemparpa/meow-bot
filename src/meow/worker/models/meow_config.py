from pydantic import BaseModel, Field


class MeowConfig(BaseModel):
    """Parsed ``.meow.json`` — repo-level configuration for the bot (SPEC §10).

    All fields have spec-defined defaults so an unconfigured repo gets a
    sensible review. ``model`` drives the vibe call; ``max_turns`` /
    ``max_price_usd`` are the budget guardrails enforced inside the
    sandbox (SPEC §14).
    """

    model: str = Field(default="mistral-medium-3.5", min_length=1)
    max_turns: int = Field(default=80, ge=1)
    max_price_usd: float = Field(default=0.50, gt=0)
