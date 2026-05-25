"""Activity ``fetch_pr_context`` (story S8).

Fetches the data ``run_review_in_sandbox`` needs to produce a review:
the unified diff of the PR and the optional ``.meow.yml`` at the HEAD
commit. Auth is delegated to ``installation_client`` (S3), which mints a
``contents:read`` installation token for the call.
"""

from __future__ import annotations

from datetime import timedelta

import mistralai.workflows as workflows
from githubkit.exception import RequestFailed

from meow.common.github.auth import installation_client
from meow.common.logging import get_logger
from meow.worker.types import PrContext

logger = get_logger("worker")

_MEOW_YML_PATH = ".meow.yml"


# 30s is enough headroom for a slow PR + a slow .meow.yml on a cold
# connection; anything longer is a GitHub outage we'd rather surface as a
# failure than block on.
@workflows.activity(start_to_close_timeout=timedelta(seconds=30))
async def fetch_pr_context(
    installation_id: int,
    owner: str,
    repo: str,
    pr_number: int,
) -> PrContext:
    async with installation_client(installation_id, permissions={"contents": "read"}) as gh:
        pr_resp = await gh.rest.pulls.async_get(owner, repo, pr_number)
        pr = pr_resp.parsed_data
        base_sha = pr.base.sha
        head_sha = pr.head.sha

        # The typed wrapper insists on JSON; the unified diff endpoint
        # returns text/plain. Go through the raw transport instead.
        diff_resp = await gh.arequest(
            "GET",
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Accept": "application/vnd.github.v3.diff"},
        )
        diff = diff_resp.text

        meow_yml_raw: str | None
        try:
            yml_resp = await gh.arequest(
                "GET",
                f"/repos/{owner}/{repo}/contents/{_MEOW_YML_PATH}",
                params={"ref": head_sha},
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            meow_yml_raw = yml_resp.text
        except RequestFailed as e:
            if e.response.status_code != 404:
                raise
            meow_yml_raw = None

        logger.info(
            "activity.fetch_pr_context.done",
            extra={
                "repo": f"{owner}/{repo}",
                "pr": pr_number,
                "diff_bytes": len(diff),
                "has_meow_yml": meow_yml_raw is not None,
            },
        )
        return PrContext(
            installation_id=installation_id,
            repo_full_name=f"{owner}/{repo}",
            pr_number=pr_number,
            base_sha=base_sha,
            head_sha=head_sha,
            diff=diff,
            meow_yml_raw=meow_yml_raw,
        )
