"""The file changes an implementation agent produced, ready for a worker commit.

``run_feature_implement_vibe`` extracts this from a read-only sandbox (the agent
never touches git); the ``commit_changeset`` activity turns it into a commit via
the GitHub Git Data API, feeding each file's text straight into a tree entry's
``content`` field. Contents are plain UTF-8 text (the agent writes code) — a
file that doesn't decode as UTF-8 makes extraction drop the whole changeset. The
set is size-capped upstream to stay under the workflow payload limit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["Changeset", "FileChange"]


class FileChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Repo-relative path of the changed file.
    path: str = Field(min_length=1)
    # New file content as plain UTF-8 text, fed inline to the Git Data API's
    # tree ``content`` field. ``None`` deletes the path.
    content: str | None = None


class Changeset(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Empty ⇒ the agent left the tree untouched (no PR; post a comment instead).
    files: list[FileChange] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.files
