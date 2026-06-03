"""Entry point for ``python -m meow.worker``.

Starts a Mistral Workflows worker (spec §7) that registers the workflows
listed in ``_WORKFLOWS`` and polls for tasks. Requires ``MISTRAL_API_KEY``
and ``DEPLOYMENT_NAME`` in the environment.
"""

from __future__ import annotations

import asyncio

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.worker.workflows.pr_review_handler import PrReviewWorkflow

_WORKFLOWS = [PrReviewWorkflow]


def main() -> None:
    logger = get_logger("worker")
    logger.info("worker.started", extra={"workflows": [w.__name__ for w in _WORKFLOWS]})
    asyncio.run(workflows.run_worker(_WORKFLOWS))


if __name__ == "__main__":
    main()
