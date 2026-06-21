"""The ``run_*_vibe`` activities.

One activity per use case: spin up a Koyeb sandbox configured by
:class:`SandboxBuilder`, run the prompt + agent encoded in the
:class:`VibeTask`, and capture stdout/stderr as a :class:`VibeResult`.
``run_pr_review_vibe`` overlays the PR diff + a PR scratchpad;
``run_feature_scope_vibe`` runs on a plain default-branch clone;
``run_feature_implement_vibe`` runs on a **read-only** clone and extracts the
agent's :class:`Changeset` (the actual writes happen worker-side via
``commit_changeset`` — the sandbox never holds a write token). They share the
run/teardown core (:func:`_vibe_session`) and differ only in how they wire the
builder and what they do with the live sandbox. Per-use-case prompts/agents are
picked by the workflow via factories (``meow.worker.vibe_tasks.*``). Post-vibe
actions (committing, posting a comment, …) live in separate activities so their
retry boundary stays distinct from the expensive vibe run.

The sandbox is always torn down via :py:meth:`SandboxBuilder.__aexit__`
— including on exceptions — so a misbehaving run can't strand Koyeb compute.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta

import mistralai.workflows as workflows
from koyeb import AsyncSandbox
from koyeb.sandbox import FileInfo

from meow.common.logging import get_logger
from meow.worker.models import (
    Changeset,
    CloneSandboxSpec,
    FileChange,
    ImplementResult,
    PrSandboxSpec,
    VibeResult,
    VibeTask,
)
from meow.worker.sandbox.builder import (
    WORKING_DIR,
    SandboxBuilder,
    SandboxBuilderConfig,
    SandboxExecTimeout,
    exec_polling,
    read_file_or_empty,
)

__all__ = ["run_feature_implement_vibe", "run_feature_scope_vibe", "run_pr_review_vibe"]

logger = get_logger("worker")

# Activity covers clone + checkout + pr_diff + memory + vibe + cleanup.
_ACTIVITY_TIMEOUT = timedelta(minutes=15)

# Per-exec ceiling for the vibe phase only. Distinct from the activity
# timeout so a stuck vibe surfaces as a clean terminated-early result
# rather than a generic ActivityTimeout swallowed upstream.
_VIBE_EXEC_TIMEOUT = 60 * 12  # 12 minutes

# Implementation runs are heavier than a review/scope (write code + tests),
# so they get a longer budget on both the activity and the vibe exec.
_IMPL_ACTIVITY_TIMEOUT = timedelta(minutes=25)
_IMPL_VIBE_EXEC_TIMEOUT = 60 * 20  # 20 minutes

# Slightly longer than the activity timeout so Koyeb's auto-delete net
# catches us if both the activity and __aexit__ fail.
_DELETE_AFTER_DELAY = 60 * 20
_IMPL_DELETE_AFTER_DELAY = 60 * 30

# Ceiling for the read-only `git status` used to extract the changeset.
_GIT_READ_TIMEOUT = 60

# Cap on the UTF-8 bytes of an implementation changeset. The changeset crosses
# the workflow boundary, so an over-large diff would blow the payload limit — we
# drop it and let the workflow post a comment instead of committing a partial
# tree.
_MAX_CHANGESET_BYTES = 1_200_000

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


@asynccontextmanager
async def _vibe_session(
    builder: SandboxBuilder,
    task: VibeTask,
    *,
    vibe_exec_timeout: int = _VIBE_EXEC_TIMEOUT,
) -> AsyncIterator[tuple[AsyncSandbox, VibeResult]]:
    """Build the sandbox, run ``vibe``, and yield ``(sandbox, VibeResult)``.

    Shared core of the ``run_*_vibe`` activities — they differ only in how they
    wire the :class:`SandboxBuilder` and what they do with the live sandbox
    inside the ``with`` block (an activity may read extra state, e.g. the
    implementation changeset, before the context exits). A background heartbeat
    runs for the whole session and the sandbox is always deleted on exit —
    normal or via exception. A deadline overrun yields a terminated-early result
    (so the caller can still post a comment) rather than raising.
    """
    heartbeat = asyncio.create_task(_heartbeat_loop())
    try:
        async with builder as sandbox:
            try:
                exit_code, stdout, stderr = await exec_polling(
                    sandbox,
                    task.build_command(),
                    cwd=WORKING_DIR,
                    timeout=vibe_exec_timeout,
                )
            except SandboxExecTimeout as exc:
                yield (
                    sandbox,
                    VibeResult(
                        body=None,
                        terminated_early=True,
                        stop_reason=f"vibe exceeded {exc.timeout}s budget",
                    ),
                )
                return
            # The deliverable is the agent's report file (declared by the
            # task), not the stdout transcript (its full thinking/monologue).
            # Read it back while the sandbox is still alive; from_exec falls
            # back to a terminated-early banner when it's missing. Tasks with
            # no file deliverable leave report_path None — nothing to read.
            report = (
                await read_file_or_empty(sandbox, task.report_path)
                if task.report_path is not None
                else ""
            )
            logger.info(
                "run_vibe.completed",
                extra={
                    "exit_code": exit_code,
                    "report_bytes": len(report),
                    "stdout_bytes": len(stdout),
                },
            )
            yield sandbox, VibeResult.from_exec(exit_code=exit_code, report=report, stderr=stderr)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


@workflows.activity(
    start_to_close_timeout=_ACTIVITY_TIMEOUT,
    heartbeat_timeout=_HEARTBEAT_TIMEOUT,
)
async def run_pr_review_vibe(task: VibeTask, sandbox_spec: PrSandboxSpec) -> VibeResult:
    """Run ``vibe`` inside a freshly-built PR-review sandbox.

    The sandbox is configured by :py:meth:`PrSandboxSpec.configure_builder`
    which wires up ``with_pr_diff`` (the PR overlay), ``with_memory`` (the
    PR-scoped scratchpad), and ``with_report`` (git-ignored output file).
    See :func:`_vibe_session` for the run/teardown semantics.
    """
    builder = sandbox_spec.configure_builder(
        SandboxBuilder(config=SandboxBuilderConfig(delete_after_delay=_DELETE_AFTER_DELAY))
    )
    async with _vibe_session(builder, task) as (_sandbox, result):
        return result


@workflows.activity(
    start_to_close_timeout=_ACTIVITY_TIMEOUT,
    heartbeat_timeout=_HEARTBEAT_TIMEOUT,
)
async def run_feature_scope_vibe(task: VibeTask, sandbox_spec: CloneSandboxSpec) -> VibeResult:
    """Run ``vibe`` inside a feature-scoping sandbox.

    A plain clone of the default branch — no PR diff to overlay. The sandbox
    is configured by :py:meth:`CloneSandboxSpec.configure_builder`. See
    :func:`_vibe_session` for the run/teardown semantics.
    """
    builder = sandbox_spec.configure_builder(
        SandboxBuilder(config=SandboxBuilderConfig(delete_after_delay=_DELETE_AFTER_DELAY))
    )
    async with _vibe_session(builder, task) as (_sandbox, result):
        return result


async def _read_text(sandbox: AsyncSandbox, path: str) -> str | None:
    """Read a sandbox file as UTF-8 text, or ``None`` if it isn't text.

    koyeb's executor returns a file's content as a JSON string (it decodes the
    bytes server-side), so the default ``encoding="utf-8"`` hands us that ``str``
    directly — accents and emoji included. We deliberately avoid
    ``encoding="base64"``: that koyeb path ``b64decode``s the raw text and raises
    ``string argument should contain only ASCII characters`` on the first
    non-ASCII byte.

    A binary file can't be committed inline through the Git Data API's ``content``
    field anyway, so we return ``None`` — and the caller drops the whole changeset
    — when the read fails or the content isn't valid UTF-8. Binary detection is
    best-effort: koyeb usually hands us an already-decoded ``str`` (it decodes
    server-side), so the strict decode only catches a binary that came back as raw
    ``bytes``; faithful detection would need the raw bytes (a base64 transport).
    """
    try:
        info: FileInfo = await sandbox.filesystem.read_file(path)
    except Exception:
        logger.warning("run_feature_implement_vibe.unreadable_file", extra={"path": path})
        return None
    content = info.content
    try:
        text = content if isinstance(content, str) else content.decode("utf-8", "strict")
    except UnicodeDecodeError:
        logger.warning("run_feature_implement_vibe.binary_file", extra={"path": path})
        return None
    return text


async def _extract_changeset(sandbox: AsyncSandbox) -> Changeset:
    """Read the agent's working-tree changes out of the read-only sandbox.

    Uses ``git status`` (read-only) to find what changed, then reads each
    surviving file's text for a worker-side commit. Returns an empty changeset
    (so the workflow posts a comment instead of opening a PR) when nothing
    changed, when the diff exceeds :data:`_MAX_CHANGESET_BYTES`, or when a file
    isn't text (see :func:`_read_text`) — we commit text inline via the Git Data
    API's ``content`` field, so a binary file can't be represented and we bail
    rather than push a partial PR. Module-level so it's unit-testable against a
    fake sandbox.
    """
    # `--untracked-files=all` lists every new file individually — without it git
    # collapses a brand-new directory into a single ``?? dir/`` entry and we'd
    # miss its files (and try to read a directory as a file). It's the `git add
    # .` recursion we need. `--no-renames` keeps every entry a plain ``XY
    # <path>`` (a rename becomes a delete + an untracked add) so there's no
    # second NUL field to parse — and ``-z`` means paths are never quoted. Each
    # entry: two status chars, a space, then the path; a ``D`` in either status
    # column is a deletion.
    exit_code, stdout, stderr = await exec_polling(
        sandbox,
        "git status --porcelain=v1 -z --no-renames --untracked-files=all",
        cwd=WORKING_DIR,
        timeout=_GIT_READ_TIMEOUT,
    )
    if exit_code != 0:
        err = (stderr or stdout or "").strip()
        raise RuntimeError(f"git status failed (exit={exit_code}): {err[:1000]}")

    files: list[FileChange] = []
    total = 0
    for entry in stdout.split("\0"):
        if len(entry) < 4:  # skip the trailing empty field (and any malformed bit)
            continue
        status, path = entry[:2], entry[3:]
        if "D" in status:
            files.append(FileChange(path=path, content=None))
            continue
        text = await _read_text(sandbox, f"{WORKING_DIR}/{path}")
        if text is None:  # binary or unreadable → never ship a partial PR
            return Changeset(files=[])
        total += len(text.encode("utf-8"))
        if total > _MAX_CHANGESET_BYTES:
            logger.warning(
                "run_feature_implement_vibe.changeset_too_large",
                extra={"bytes": total, "limit": _MAX_CHANGESET_BYTES},
            )
            return Changeset(files=[])
        files.append(FileChange(path=path, content=text))
    return Changeset(files=files)


@workflows.activity(
    start_to_close_timeout=_IMPL_ACTIVITY_TIMEOUT,
    heartbeat_timeout=_HEARTBEAT_TIMEOUT,
)
async def run_feature_implement_vibe(
    task: VibeTask, sandbox_spec: CloneSandboxSpec
) -> ImplementResult:
    """Run ``vibe`` to implement a feature on a **read-only** sandbox.

    The agent edits the working tree of a plain default-branch clone; it gets a
    ``contents: read`` token only (``with_meow_secrets`` default) so it cannot
    push, and it runs no git itself. The sandbox is configured by
    :py:meth:`CloneSandboxSpec.configure_builder`. After the vibe exits we
    extract its changeset (read-only ``git status`` + file reads) and return it
    — the commit happens worker-side in ``commit_changeset``. A terminated-early
    run yields an empty changeset (we don't trust partial edits), so the
    workflow posts a comment.
    """
    builder = sandbox_spec.configure_builder(
        SandboxBuilder(config=SandboxBuilderConfig(delete_after_delay=_IMPL_DELETE_AFTER_DELAY))
    )
    async with _vibe_session(builder, task, vibe_exec_timeout=_IMPL_VIBE_EXEC_TIMEOUT) as (
        sandbox,
        result,
    ):
        if result.terminated_early:
            return ImplementResult(vibe=result, changeset=Changeset(files=[]))
        changeset = await _extract_changeset(sandbox)
        return ImplementResult(vibe=result, changeset=changeset)
