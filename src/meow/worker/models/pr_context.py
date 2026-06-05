from __future__ import annotations

from githubkit.rest import PullRequest
from pydantic import BaseModel, Field


class PrContext(BaseModel):
    title: str
    body: str | None = None
    mergeable: bool | None = None
    base_sha: str = Field(min_length=1)
    head_sha: str = Field(min_length=1)

    @classmethod
    def from_pr(cls, pr: PullRequest) -> PrContext:
        return cls(
            title=pr.title,
            body=pr.body,
            mergeable=pr.mergeable,
            base_sha=pr.base.sha,
            head_sha=pr.head.sha,
        )
