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

from datetime import timedelta

import mistralai.workflows as workflows

from meow.worker.models import PrSandboxSpec, VibeResult, VibeTask
from meow.worker.sandbox.builder import (
    WORKING_DIR,
    SandboxBuilder,
    SandboxBuilderConfig,
)

__all__ = ["run_vibe"]

# Activity covers clone + checkout + pr_diff + memory + vibe + cleanup.
_ACTIVITY_TIMEOUT = timedelta(minutes=15)

# Per-exec ceiling for the vibe phase only. Distinct from the activity
# timeout so a stuck vibe surfaces as a clean RuntimeError rather than a
# generic ActivityTimeout swallowed upstream.
_VIBE_EXEC_TIMEOUT = 60 * 12  # 12 minutes

# Slightly longer than the activity timeout so Koyeb's auto-delete net
# catches us if both the activity and __aexit__ fail.
_DELETE_AFTER_DELAY = 60 * 20


@workflows.activity(start_to_close_timeout=_ACTIVITY_TIMEOUT)
async def run_vibe(task: VibeTask, sandbox_spec: PrSandboxSpec) -> VibeResult:
    """Run ``vibe`` inside a freshly-built PR-review sandbox.

    The sandbox is always deleted on exit. Exceptions are re-raised so
    the workflow framework applies its retry policy.
    """
    builder = (
        SandboxBuilder(
            config=SandboxBuilderConfig(delete_after_delay=_DELETE_AFTER_DELAY)
        )
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
    async with builder as sandbox:
        run = await sandbox.exec(
            task.build_command(),
            cwd=WORKING_DIR,
            timeout=_VIBE_EXEC_TIMEOUT,
        )
        return VibeResult.from_exec(
            exit_code=run.exit_code,
            stdout=run.stdout or "",
            stderr=run.stderr or "",
        )
