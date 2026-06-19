"""Activity ``commit_changeset``.

Turns the agent's :class:`Changeset` (extracted from the read-only sandbox) into
a real commit on a feature branch, entirely through the GitHub Git Data API —
no git runs in the sandbox and no write token ever reaches the agent. Auth is
delegated to ``github_installation_auth`` with ``contents:write``.

Builds one atomic commit on top of the base branch: a tree layered over the base
tree where each changed file's text goes inline in the entry's ``content`` field
(GitHub writes the blob) and deletions are entries with ``sha=None``; then a
commit, then create-or-force-update the branch ref. Force-update makes a
re-trigger on the same issue land on the same branch (and refresh the open PR)
instead of stacking duplicates.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import mistralai.workflows as workflows
from githubkit.exception import RequestFailed
from githubkit.versions.latest.types import (
    ReposOwnerRepoGitTreesPostBodyPropTreeItemsType as TreeItem,
)

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.models import Changeset

logger = get_logger("worker")

# Regular, non-executable file. The executable bit is not preserved in v1 —
# every committed file lands as 100644. Typed as a Literal so it satisfies the
# tree item's `mode` field (a Literal of the allowed git modes).
_FILE_MODE: Literal["100644"] = "100644"


@workflows.activity(start_to_close_timeout=timedelta(seconds=60))
async def commit_changeset(
    installation_id: int,
    repo_full_name: str,
    base_branch: str,
    branch: str,
    commit_message: str,
    changeset: Changeset,
) -> str:
    if repo_full_name.count("/") != 1:
        raise ValueError(f"repo_full_name must be 'owner/repo', got {repo_full_name!r}")
    if changeset.is_empty:
        raise ValueError("commit_changeset called with an empty changeset")
    owner, repo = repo_full_name.split("/", 1)

    async with github_installation_auth(
        installation_id,
        permissions={"contents": "write"},
        repositories=[repo_full_name],
    ) as gh:
        git = gh.client.rest.git

        # Base commit + its tree to layer the new tree on top of.
        base_ref = await git.async_get_ref(owner, repo, f"heads/{base_branch}")
        base_commit_sha = base_ref.parsed_data.object_.sha
        base_commit = await git.async_get_commit(owner, repo, base_commit_sha)
        base_tree_sha = base_commit.parsed_data.tree.sha

        # One tree entry per changed file. An add/modify carries its text inline
        # in `content` (GitHub writes the blob); a deletion is `sha=None`.
        # `content` and `sha` are mutually exclusive, so each entry sets exactly
        # one.
        tree: list[TreeItem] = []
        for change in changeset.files:
            if change.content is None:
                tree.append(TreeItem(path=change.path, mode=_FILE_MODE, type="blob", sha=None))
            else:
                tree.append(
                    TreeItem(path=change.path, mode=_FILE_MODE, type="blob", content=change.content)
                )

        new_tree = await git.async_create_tree(owner, repo, base_tree=base_tree_sha, tree=tree)
        new_commit = await git.async_create_commit(
            owner,
            repo,
            message=commit_message,
            tree=new_tree.parsed_data.sha,
            parents=[base_commit_sha],
        )
        new_commit_sha = new_commit.parsed_data.sha

        # Create the branch ref, or force-update it if a previous run made it.
        try:
            await git.async_create_ref(owner, repo, ref=f"refs/heads/{branch}", sha=new_commit_sha)
            created = True
        except RequestFailed as e:
            if e.response.status_code != 422:
                raise
            await git.async_update_ref(
                owner, repo, f"heads/{branch}", sha=new_commit_sha, force=True
            )
            created = False

        logger.info(
            "activity.commit_changeset.done",
            extra={
                "repo": repo_full_name,
                "branch": branch,
                "commit": new_commit_sha,
                "files": len(changeset.files),
                "ref_created": created,
            },
        )
        return new_commit_sha
