"""Activity ``fetch_meow_config``.

Reads the optional ``.meow.json`` from the PR's base SHA and parses it
into a :class:`MeowConfig`. Falls back to defaults (``MeowConfig()``)
when the file is absent. Authoring against ``base_sha`` (not ``head``)
so a malicious PR can't raise its own budgets.
"""

from __future__ import annotations

import base64
from datetime import timedelta

import mistralai.workflows as workflows
from githubkit.exception import RequestFailed
from githubkit.rest import ContentFile
from mistralai.workflows.exceptions import WorkflowsException

from meow.common.github.auth import github_installation_auth
from meow.common.logging import get_logger
from meow.worker.models.meow_config import MeowConfig

logger = get_logger("worker")

_MEOW_JSON_PATH = ".meow.json"


@workflows.activity(start_to_close_timeout=timedelta(seconds=30))
async def fetch_meow_config(
    installation_id: int,
    repo_full_name: str,
    base_sha: str,
) -> MeowConfig:
    owner, repo = repo_full_name.split("/", maxsplit=1)

    async with github_installation_auth(
        installation_id,
        permissions={"contents": "read"},
        repositories=[repo_full_name],
    ) as gh:
        try:
            resp = await gh.client.rest.repos.async_get_content(
                owner=owner,
                repo=repo,
                path=_MEOW_JSON_PATH,
                ref=base_sha,
            )
        except RequestFailed as e:
            if e.response.status_code == 404:
                logger.info(
                    "activity.fetch_meow_config.absent",
                    extra={"repo": repo_full_name, "ref": base_sha},
                )
                return MeowConfig()
            raise

    content = resp.parsed_data
    if not isinstance(content, ContentFile):
        raise WorkflowsException(message=f"Config file {_MEOW_JSON_PATH} should be a regular file")

    # GitHub returns ContentFile.content as base64 regardless of file size.
    raw = base64.b64decode(content.content).decode("utf-8")
    cfg = MeowConfig.model_validate_json(raw)
    logger.info(
        "activity.fetch_meow_config.done",
        extra={"repo": repo_full_name, "ref": base_sha, "bytes": len(raw)},
    )
    return cfg
