"""Daytona + ``mistral-vibe`` orchestration helper (story S12).

Isolated from the activity so the (still-evolving) ``mistral-vibe``
programmatic API can be iterated on in one file. The activity stays
focused on workflow concerns; this module owns sandbox lifecycle,
prompt construction, and JSON round-tripping with the in-sandbox
runner script.
"""

from __future__ import annotations

import json
from typing import Any

from daytona import AsyncDaytona, CreateSandboxFromSnapshotParams, DaytonaConfig

from meow.common.config import Settings
from meow.common.logging import get_logger
from meow.worker.types import MeowConfig, PrContext, ReviewReport

__all__ = ["run_vibe_review"]

logger = get_logger("worker")

# Pinned snapshot built and published by S11 (see ``sandbox/Dockerfile``).
# Contains python 3.13 + git + gh + ``mistral-vibe==2.10.1``.
_SNAPSHOT = "meow-base"

# Where the cloned repo lives inside the sandbox. ``mistral-vibe`` is
# invoked with this as ``cwd`` so its file-reading tools see the PR.
_CLONE_DIR = "/work/repo"


def _build_prompt(ctx: PrContext, cfg: MeowConfig, filtered_diff: str) -> str:
    """Construct the markdown prompt handed to ``vibe.core.run_programmatic``.

    The prompt is human-readable on purpose — review reports tend to
    surface fragments of the prompt back in their output, and we'd rather
    see plain English than JSON.
    """
    lang_line = (
        "Write the report in the language of the diff/PR description."
        if cfg.language == "auto"
        else f"Write the report in {cfg.language}."
    )
    return f"""You are a code reviewer for the GitHub PR \
{ctx.repo_full_name}#{ctx.pr_number}.

Read the unified diff below. Use your file-reading tools to look up any \
surrounding context you need from the cloned repo at `{_CLONE_DIR}`. \
If `{cfg.agents_md_path}` exists at the repo root, treat its conventions \
as authoritative.

Output one markdown report covering: correctness bugs, security issues, \
and clarity problems. Skip nits and style preferences. {lang_line}

--- DIFF ---
{filtered_diff}
--- END DIFF ---
"""


def _build_runner_script(prompt: str, cfg: MeowConfig) -> str:
    """Return a Python source string executed inside the sandbox.

    Calls ``vibe.core.run_programmatic`` with the prompt + budgets and
    emits a single JSON line on stdout: ``{"body": ..., "terminated_early": ...}``.
    Values are injected via ``repr()`` so the script is safe against
    quotes/newlines/backslashes in the prompt.
    """
    return f"""
import json
from vibe.core import run_programmatic

result = run_programmatic(
    prompt={prompt!r},
    model={cfg.model!r},
    max_turns={cfg.max_turns!r},
    max_price={cfg.max_price_usd!r},
    cwd={_CLONE_DIR!r},
)

# The vibe SDK is still evolving; tolerate a couple of attribute names.
body = getattr(result, "report", None) or getattr(result, "output", None) or str(result)
terminated_early = bool(getattr(result, "terminated_early", False))
print(json.dumps({{"body": body, "terminated_early": terminated_early}}))
"""


def _parse_runner_output(stdout: str) -> ReviewReport:
    """Find and decode the runner script's JSON line from sandbox stdout."""
    # The script emits exactly one JSON line; tolerate vibe writing
    # progress to stdout before that by scanning from the end.
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            data: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            continue
        return ReviewReport(
            body=data["body"],
            terminated_early=bool(data.get("terminated_early", False)),
        )
    raise RuntimeError(f"vibe runner produced no JSON line on stdout: {stdout!r}")


async def run_vibe_review(
    ctx: PrContext,
    cfg: MeowConfig,
    token: str,
    filtered_diff: str,
) -> ReviewReport:
    """Spin up a sandbox, run vibe against the PR diff, return the report.

    The sandbox is always deleted on the way out — including on errors —
    so a misbehaving review can't strand compute. Exceptions are logged
    and re-raised so Mistral Workflows applies the activity retry policy.
    """
    settings = Settings()  # ty: ignore[missing-argument]
    daytona = AsyncDaytona(DaytonaConfig(api_key=settings.daytona_api_key))

    sandbox = await daytona.create(
        CreateSandboxFromSnapshotParams(snapshot=_SNAPSHOT),
    )
    try:
        clone_cmd = (
            f"git clone https://x-access-token:{token}@github.com/"
            f"{ctx.repo_full_name}.git {_CLONE_DIR}"
        )
        clone = await sandbox.process.exec(clone_cmd)
        if clone.exit_code != 0:
            raise RuntimeError(
                f"git clone failed (exit={clone.exit_code}): {clone.result}"
            )

        checkout = await sandbox.process.exec(
            f"git checkout {ctx.head_sha}", cwd=_CLONE_DIR
        )
        if checkout.exit_code != 0:
            raise RuntimeError(
                f"git checkout failed (exit={checkout.exit_code}): {checkout.result}"
            )

        prompt = _build_prompt(ctx, cfg, filtered_diff)
        script = _build_runner_script(prompt, cfg)
        run = await sandbox.process.code_run(script)
        if run.exit_code != 0:
            raise RuntimeError(
                f"vibe runner failed (exit={run.exit_code}): {run.result}"
            )

        return _parse_runner_output(run.result or "")
    finally:
        try:
            await sandbox.delete()
        except Exception as exc:
            # Don't mask the original error — log and move on. Daytona's
            # auto-delete interval is the safety net.
            logger.warning(
                "sandbox.delete_failed",
                extra={"sandbox_id": getattr(sandbox, "id", None), "error": str(exc)},
            )
