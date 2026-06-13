"""Generic ``run_vibe`` activity.

One activity per vibe invocation: spin up a Koyeb sandbox configured by
:class:`SandboxBuilder`, run the prompt + agent encoded in the
:class:`VibeTask`, and capture stdout/stderr as a :class:`VibeResult`.
Per-use-case prompts/agents are picked by the workflow via factories
(``meow.worker.vibe_tasks.*``). Post-vibe actions (posting a PR comment,
opening an issue, …) live in separate activities so their retry
boundary stays distinct from the expensive vibe run.

The sandbox is always torn down via :py:meth:`SandboxBuilder.__aexit__`
— including on exceptions — so a misbehaving review can't strand
Koyeb compute.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta

import mistralai.workflows as workflows

from meow.common.logging import get_logger
from meow.worker.models import PrSandboxSpec, VibeResult, VibeTask
from meow.worker.sandbox.builder import (
    REVIEW_REPORT_PATH,
    WORKING_DIR,
    SandboxBuilder,
    SandboxBuilderConfig,
    SandboxExecTimeout,
    exec_polling,
    read_file_or_empty,
)

__all__ = ["run_vibe"]

logger = get_logger("worker")

# Activity covers clone + checkout + pr_diff + memory + vibe + cleanup.
_ACTIVITY_TIMEOUT = timedelta(minutes=15)

# Per-exec ceiling for the vibe phase only. Distinct from the activity
# timeout so a stuck vibe surfaces as a clean terminated-early result
# rather than a generic ActivityTimeout swallowed upstream.
_VIBE_EXEC_TIMEOUT = 60 * 12  # 12 minutes

# Slightly longer than the activity timeout so Koyeb's auto-delete net
# catches us if both the activity and __aexit__ fail.
_DELETE_AFTER_DELAY = 60 * 20

# A background task heartbeats for the WHOLE activity — clone + sandbox
# create + vibe — so Temporal can detect a dead worker within
# _HEARTBEAT_TIMEOUT instead of the 15-minute start_to_close. The interval
# is comfortably below the timeout so a single slow poll never trips it.
_HEARTBEAT_INTERVAL = 10  # seconds
_HEARTBEAT_TIMEOUT = timedelta(seconds=30)


async def _heartbeat_loop() -> None:
    while True:
        await asyncio.sleep(_HEARTBEAT_INTERVAL)
        workflows.activity_heartbeat()


@workflows.activity(
    start_to_close_timeout=_ACTIVITY_TIMEOUT,
    heartbeat_timeout=_HEARTBEAT_TIMEOUT,
)
async def run_vibe(task: VibeTask, sandbox_spec: PrSandboxSpec) -> VibeResult:
    """Run ``vibe`` inside a freshly-built PR-review sandbox.

    The sandbox is always deleted on exit. A deadline overrun returns a
    terminated-early result (so the workflow still posts a comment); other
    exceptions are re-raised so the framework applies its retry policy.
    """
    builder = (
        SandboxBuilder(config=SandboxBuilderConfig(delete_after_delay=_DELETE_AFTER_DELAY))
        .with_meow_secrets(
            installation_id=sandbox_spec.installation_id,
            repo_full_name=sandbox_spec.repo_full_name,
        )
        .with_clone(
            repo_full_name=sandbox_spec.repo_full_name,
            ref=sandbox_spec.base_sha,
        )
        .with_pr_diff(
            pr_number=sandbox_spec.pr_number,
            base_sha=sandbox_spec.base_sha,
            head_sha=sandbox_spec.head_sha,
        )
        .with_memory(
            pr_number=sandbox_spec.pr_number,
            base_sha=sandbox_spec.base_sha,
            head_sha=sandbox_spec.head_sha,
            repo_full_name=sandbox_spec.repo_full_name,
        )
    )
    heartbeat = asyncio.create_task(_heartbeat_loop())
    try:
        async with builder as sandbox:
            try:
                exit_code, stdout, stderr = await exec_polling(
                    sandbox,
                    task.build_command(),
                    cwd=WORKING_DIR,
                    timeout=_VIBE_EXEC_TIMEOUT,
                )
            except SandboxExecTimeout as exc:
                return VibeResult(
                    body=None,
                    terminated_early=True,
                    stop_reason=f"vibe exceeded {exc.timeout}s budget",
                )
            # The deliverable is the agent's report file, not the stdout
            # transcript (which is its full thinking/monologue). Read it back
            # while the sandbox is still alive; from_exec falls back to a
            # terminated-early banner when it's missing.
            report = await read_file_or_empty(sandbox, REVIEW_REPORT_PATH)
            logger.info(
                "run_vibe.completed",
                extra={
                    "exit_code": exit_code,
                    "report_bytes": len(report),
                    "stdout_bytes": len(stdout),
                },
            )
            return VibeResult.from_exec(
                exit_code=exit_code,
                report=report,
                stderr=stderr,
            )
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
