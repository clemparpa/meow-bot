from pydantic import BaseModel, Field


class ReviewReport(BaseModel):
    """Markdown review report produced by the sandbox.

    ``terminated_early`` is set when the sandbox hits ``max_turns`` or
    ``max_price_usd`` (spec §14) so the posting layer can prepend an
    explicit header signalling a truncated review.
    """

    body: str = Field(min_length=1)
    terminated_early: bool = False
