"""The file changes an implementation agent produced, ready for a worker commit.

``run_feature_implement_vibe`` extracts this from a read-only sandbox (the agent
never touches git); the ``commit_changeset`` activity turns it into a commit via
the GitHub Git Data API. It crosses the workflow boundary, so file contents are
base64-encoded (binary-safe) and the whole set is size-capped upstream to stay
under the workflow payload limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Changeset", "FileChange"]


class FileChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Repo-relative path of the changed file.
    path: str = Field(min_length=1)
    # Base64-encoded new content, or ``None`` to delete the path. Base64 so
    # binary files survive the JSON/workflow round-trip unharmed.
    content_b64: str | None = None


class Changeset(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Empty ⇒ the agent left the tree untouched (no PR; post a comment instead).
    files: list[FileChange] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.files
