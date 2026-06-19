"""Fluent async-context-manager builder for the meow review sandbox.

Steps are queued synchronously via :py:meth:`SandboxBuilder.with_meow_secrets`
and :py:meth:`with_clone`, then executed in order inside ``__aenter__``.
On exit — normal or via exception — the sandbox is always deleted, so
an activity that crashes mid-review can't strand Koyeb compute.
``delete_after_delay`` on the underlying sandbox is a second safety net
for the case where the worker itself dies before ``__aexit__`` runs.

Typical use::

    async with (
        SandboxBuilder()
          .with_meow_secrets(installation_id=42, repo_full_name="o/r")
          .with_clone(repo_full_name="o/r", ref="main", target_dir="/work/repo")
    ) as sandbox:
        exit_code, stdout, stderr = await exec_polling(
            sandbox, "...", cwd="/work/repo", timeout=60
        )
"""

from __future__ import annotations

import asyncio
import shlex
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self
from uuid import uuid4

from koyeb import AsyncSandbox
from pydantic import BaseModel, PositiveInt

from meow.common.config import Settings
from meow.common.github.auth import AppPermissionsType, github_installation_auth
from meow.common.logging import get_logger

__all__ = [
    "MEMORY_FILE",
    "REPORT_FILE",
    "REPORT_PATH",
    "SandboxBuilder",
    "SandboxBuilderConfig",
    "SandboxExecTimeout",
    "WORKING_DIR",
    "exec_polling",
    "feature_branch_name",
    "pr_ref_name",
    "read_file_or_empty",
]

logger = get_logger("worker")


# Poll backoff for exec_polling. Start fast so short prep commands finish
# without noticeable latency, then back off to a cap so a long vibe run
# borrows a worker thread for only milliseconds per poll (the rest is
# ``await asyncio.sleep``, which frees both the event loop and the executor
# thread pool — so one sandbox's command never queues another's launch).
_POLL_START_INTERVAL = 0.1
_POLL_MAX_INTERVAL = 3.0


class SandboxExecTimeout(RuntimeError):
    """A polled command did not complete within its deadline."""

    def __init__(self, timeout: int) -> None:
        super().__init__(f"command exceeded {timeout}s deadline")
        self.timeout = timeout


async def _safe_kill(sandbox: AsyncSandbox, pid: str) -> None:
    try:
        await sandbox.kill_process(pid)
    except Exception as exc:  # best-effort; the sandbox is torn down anyway
        logger.warning("sandbox.kill_failed", extra={"pid": pid, "error": str(exc)})


async def read_file_or_empty(sandbox: AsyncSandbox, path: str) -> str:
    """Read a sandbox file, returning ``""`` if it is missing.

    The output files may be absent if the process died before the shell's
    ``exec`` redirect created them — treat that as no output rather than
    failing the whole run. Shared with ``run_vibe``, which reuses it to read
    the agent's output report file back out of the sandbox.
    """
    try:
        info = await sandbox.filesystem.read_file(path)
    except Exception:
        return ""
    content = info.content
    return content if isinstance(content, str) else content.decode("utf-8", "replace")


async def exec_polling(
    sandbox: AsyncSandbox,
    cmd: str,
    *,
    cwd: str | None = None,
    timeout: int,
    poll_max_interval: float = _POLL_MAX_INTERVAL,
) -> tuple[int, str, str]:
    """Run ``cmd`` as a background process and poll until it completes.

    A blocking ``sandbox.exec`` is a single long-held HTTP request that
    Koyeb's edge kills with a 504 once it exceeds the gateway timeout. Here
    we ``launch_process`` and poll a sentinel file instead: every HTTP call
    is short, so neither the event loop nor a thread is held for the duration
    of the command — concurrent sandbox launches never block.

    Completion is detected by a shell-written ``.code`` sentinel file (see the
    ``trap`` below), not by Koyeb's ``list_processes`` ``exit_code``/``status``
    fields, which are unreliable. ``stdout``/``stderr`` are captured via a
    shell ``exec`` redirect (robust to compound commands, heredocs and
    subshells, unlike a trailing ``>``) and read back once the process exits.

    Returns ``(exit_code, stdout, stderr)``. Raises :class:`SandboxExecTimeout`
    if the command has not finished within ``timeout`` seconds (the process
    is killed first).
    """
    run_id = uuid4().hex
    out_path = f"/tmp/meow-{run_id}.out"  # noqa: S108 - sandbox-local scratch
    err_path = f"/tmp/meow-{run_id}.err"  # noqa: S108 - sandbox-local scratch
    code_path = f"/tmp/meow-{run_id}.code"  # noqa: S108 - sandbox-local scratch

    # Capture the exit code ourselves instead of trusting Koyeb's
    # `list_processes` bookkeeping: that field is racy in both directions —
    # `status` flips to "completed" before `exit_code` populates, and
    # `exit_code` is sometimes never backfilled at all, so a finished command
    # (e.g. `gh auth setup-git`) hangs the poll until the deadline. A shell
    # `trap ... EXIT` writes the real status to a sentinel file on *any* exit,
    # including an explicit `exit N` (so `verify_head`'s `exit 1` is captured,
    # not swallowed). The file's existence is the completion signal.
    wrapped = (
        f"trap 'rc=$?; echo \"$rc\" >{shlex.quote(code_path)}' EXIT\n"
        f"exec >{shlex.quote(out_path)} 2>{shlex.quote(err_path)}\n"
        f"{cmd}"
    )

    pid = await sandbox.launch_process(wrapped, cwd=cwd)

    deadline = time.monotonic() + timeout
    interval = _POLL_START_INTERVAL
    while True:
        await asyncio.sleep(interval)
        code_str = (await read_file_or_empty(sandbox, code_path)).strip()
        if code_str:
            try:
                exit_code = int(code_str)
                logger.info("sandbox.exec.completed", extra={"exit_code": exit_code})
                break
            except ValueError:
                # Sentinel caught mid-write; treat as not-yet-complete and
                # re-poll — the next read sees the full line.
                pass
        if time.monotonic() >= deadline:
            await _safe_kill(sandbox, pid)
            raise SandboxExecTimeout(timeout)
        interval = min(interval * 2, poll_max_interval)

    stdout = await read_file_or_empty(sandbox, out_path)
    stderr = await read_file_or_empty(sandbox, err_path)
    return exit_code, stdout, stderr


# Where with_clone drops the repo inside the sandbox. The factory in
# meow.worker.vibe_tasks.pr_review imports this so the prompt and the
# clone path can't drift.
WORKING_DIR = "/work/repo"

# Default scratchpad with_memory writes at the repo root. Factories that
# mention the file in their prompt import this so the path stays in sync.
MEMORY_FILE = "meow-bot-memory.md"

# Default file an agent writes its final markdown deliverable to. The prompt
# tells the agent to write here (via its write_file tool) and run_vibe reads it
# back instead of scraping vibe's stdout transcript. The path a given task
# expects lives on its VibeTask.report_path; this is just the default the
# factories wire in. Lives at the repo root and is git-ignored (with_memory)
# so it never looks like part of the PR.
REPORT_FILE = "meow-output.md"
REPORT_PATH = f"{WORKING_DIR}/{REPORT_FILE}"


def pr_ref_name(pr_number: int) -> str:
    """Local ref name with_pr_diff fetches the PR head into.

    Exposed so factories can refer to it in prompts (``git log pr-N``)
    without re-deriving the convention.
    """
    return f"pr-{pr_number}"


def feature_branch_name(issue_number: int) -> str:
    """Branch the implementation flow lands its commit on.

    One deterministic branch per issue so re-runs force-update the same branch
    (and update the same PR) instead of stacking duplicates. Shared by the
    ``commit_changeset`` activity (creates/force-updates it via the Git Data
    API) and the ``open_pull_request`` activity (uses it as the PR head).
    """
    return f"meow/issue-{issue_number}"


class SandboxBuilderConfig(BaseModel):
    """Timeouts and lifecycle settings for a builder-managed sandbox."""

    delete_after_delay: PositiveInt = 1200
    clone_timeout: PositiveInt = 120
    checkout_timeout: PositiveInt = 60


@dataclass(frozen=True, slots=True)
class _Step:
    name: str
    run: Callable[[AsyncSandbox], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class _PrepStep:
    name: str
    run: Callable[[], Awaitable[None]]


class SandboxBuilder:
    # Image built and published by .github/workflows/sandbox-image.yml.
    # `:latest` is intentional for now — when the workflow starts pinning
    # tags, swap this for the resolved SHA tag.
    _SANDBOX_IMAGE = "clemparpa/meow-sandbox:latest"
    # `gh auth setup-git` is a one-shot config write; 30s is generous and
    # distinguishes "command hung" from "command crashed".
    _GH_AUTH_TIMEOUT = 30

    # Minimum scope the sandbox needs: clone the repo, read diffs. Callers
    # that need broader gh-CLI usage (e.g. `gh pr comment`) pass their own
    # permissions through `with_meow_secrets(..., permissions=...)`.
    _DEFAULT_TOKEN_PERMISSIONS: AppPermissionsType = {"contents": "read"}

    def __init__(self, config: SandboxBuilderConfig | None = None) -> None:
        self._config = config or SandboxBuilderConfig()
        self._env: dict[str, str] = {}
        self._prep_steps: list[_PrepStep] = []
        self._steps: list[_Step] = []
        self._sandbox: AsyncSandbox | None = None

    def with_meow_secrets(
        self,
        *,
        installation_id: int,
        repo_full_name: str,
        permissions: AppPermissionsType | None = None,
    ) -> Self:
        settings = Settings()  # ty: ignore[missing-argument]
        # The sandbox runs nothing but `vibe`, so the in-sandbox
        # `MISTRAL_API_KEY` (read by ~/.vibe/config.toml) carries the *inference*
        # key — the cheaper subscription `MISTRAL_VIBE_API_KEY` when set,
        # otherwise the standard key. The worker's own `MISTRAL_API_KEY` keeps
        # its separate role (Mistral Workflows workspace + receiver SDK) and is
        # never shipped into the sandbox.
        self._env["MISTRAL_API_KEY"] = settings.vibe_api_key

        async def set_gh_token() -> None:
            async with github_installation_auth(
                installation_id=installation_id,
                repositories=[repo_full_name],
                permissions=permissions if permissions else self._DEFAULT_TOKEN_PERMISSIONS,
            ) as gh:
                token = await gh.token()

            self._env["GH_TOKEN"] = token

        async def setup_git(sb: AsyncSandbox) -> None:
            await self._run(
                sb,
                "gh auth setup-git",
                timeout=self._GH_AUTH_TIMEOUT,
                fail_msg="gh auth setup-git failed",
            )

        self._prep_steps.append(_PrepStep(name="mint_gh_token", run=set_gh_token))
        self._steps.append(_Step(name="gh_auth_setup_git", run=setup_git))
        return self

    def with_clone(
        self,
        *,
        repo_full_name: str,
        ref: str,
    ) -> Self:
        """Clone ``repo_full_name`` into ``target_dir`` and checkout ``ref``.

        ``ref`` may be a branch name or a commit SHA — the same
        ``git checkout`` handles both. Private repos require a prior
        :py:meth:`with_meow_secrets` call.
        """
        clone_cmd = f"git clone https://github.com/{repo_full_name}.git {shlex.quote(WORKING_DIR)}"
        checkout_cmd = f"git checkout {shlex.quote(ref)}"
        clone_timeout = self._config.clone_timeout
        checkout_timeout = self._config.checkout_timeout

        async def step(sb: AsyncSandbox) -> None:
            await self._run(
                sb,
                clone_cmd,
                timeout=clone_timeout,
                fail_msg=f"git clone {repo_full_name} failed",
            )
            await self._run(
                sb,
                checkout_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg=f"git checkout {ref} failed",
            )

        self._steps.append(_Step(name="clone_and_checkout", run=step))
        return self

    def with_pr_diff(
        self,
        *,
        pr_number: int,
        base_sha: str,
        head_sha: str,
    ) -> Self:
        """Turn an already-cloned repo into the PR diff view.

        Must run after :py:meth:`with_clone`. Fetches the PR head into the
        ``pr-<n>`` ref, verifies it matches the webhook's ``head_sha`` (a
        mismatch means a new push landed between the webhook firing and this
        clone — we fail loudly rather than review a stale state), detaches
        HEAD onto it, then soft-resets HEAD to ``base_sha``.

        ``base_sha`` comes straight from the webhook payload and is exactly
        the base GitHub diffs the PR against, so we reset onto it directly —
        no ``git merge-base`` needed. Net effect: the working tree holds the
        PR content but ``git status`` / ``git diff`` show it as uncommitted
        changes. PR commits stay reachable via ``pr-<n>`` for ``git log pr-<n>``.
        """
        pr_ref = pr_ref_name(pr_number)
        pr_ref_q = shlex.quote(pr_ref)
        base_sha_q = shlex.quote(base_sha)
        head_sha_q = shlex.quote(head_sha)

        fetch_pr = f"git fetch origin {shlex.quote(f'pull/{pr_number}/head:{pr_ref}')}"
        # Fail if the fetched head isn't what the webhook promised.
        verify_head = (
            f'GOT="$(git rev-parse {pr_ref_q})"; '
            f'test "$GOT" = {head_sha_q} '
            f'|| {{ echo "head mismatch: fetched $GOT, webhook said {head_sha}" >&2; exit 1; }}'
        )
        checkout_cmd = f"git checkout --detach {pr_ref_q}"
        reset_cmd = f"git reset --mixed {base_sha_q}"

        fetch_timeout = self._config.checkout_timeout
        checkout_timeout = self._config.checkout_timeout

        async def step(sb: AsyncSandbox) -> None:
            await self._run(
                sb,
                fetch_pr,
                cwd=WORKING_DIR,
                timeout=fetch_timeout,
                fail_msg=f"fetch PR #{pr_number} head failed",
            )
            await self._run(
                sb,
                verify_head,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg=f"PR #{pr_number} head SHA mismatch (stale webhook?)",
            )
            await self._run(
                sb,
                checkout_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg=f"detached checkout of {pr_ref} failed",
            )
            await self._run(
                sb,
                reset_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg=f"soft reset to base {base_sha} failed",
            )

        self._steps.append(_Step(name="pr_diff", run=step))
        return self

    def with_memory(
        self,
        *,
        pr_number: int,
        base_sha: str,
        head_sha: str,
        repo_full_name: str,
        filename: str = MEMORY_FILE,
    ) -> Self:
        """Drop a memory file at the repo root for the agent to consult.

        SHAs come from the webhook payload and are interpolated directly. The
        file is git-ignored locally (via ``.git/info/exclude``) so it never
        shows up in the agent's ``git status`` / ``git diff`` and can't be
        mistaken for part of the PR. The report file is a separate concern —
        :py:meth:`with_report` git-ignores it — so a use case can have one
        without the other.
        """
        fname_q = shlex.quote(filename)

        body = (
            f"# meow-bot memory\n\n"
            f"Working notes for this review session. Not part of the PR.\n\n"
            f"- repo: {repo_full_name}\n"
            f"- pr_number: {pr_number}\n"
            f"- base_sha: {base_sha}\n"
            f"- head_sha: {head_sha}\n\n"
            f"## Notes\n\n"
            f"(scratch space — record anything worth keeping across steps)\n"
        )
        # Single-quote the heredoc delimiter so the shell does no expansion:
        # the body is literal, nothing inside gets interpreted.
        write_cmd = f"cat > {fname_q} <<'MEOW_EOF'\n{body}MEOW_EOF"
        exclude_cmd = self._git_exclude_cmd(filename)

        checkout_timeout = self._config.checkout_timeout

        async def step(sb: AsyncSandbox) -> None:
            await self._run(
                sb,
                write_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg="write memory file failed",
            )
            await self._run(
                sb,
                exclude_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg="git-ignore memory file failed",
            )

        self._steps.append(_Step(name="memory", run=step))
        return self

    def with_report(self, *, report_filename: str = REPORT_FILE) -> Self:
        """Git-ignore the agent's report file via ``.git/info/exclude``.

        The agent writes its deliverable to this file (its ``write_file``
        tool) and the ``run_*_vibe`` activity reads it back; excluding it
        keeps the file out of the agent's ``git status`` / ``git diff`` so it
        is never mistaken for repo content. Both the PR-review and
        feature-scope sandboxes call this — it is independent of
        :py:meth:`with_memory` (the PR scratchpad), so a use case can take the
        report exclusion without a PR-scoped memory file. Excluding the path
        before the file exists is harmless.
        """
        exclude_cmd = self._git_exclude_cmd(report_filename)
        checkout_timeout = self._config.checkout_timeout

        async def step(sb: AsyncSandbox) -> None:
            await self._run(
                sb,
                exclude_cmd,
                cwd=WORKING_DIR,
                timeout=checkout_timeout,
                fail_msg="git-ignore report file failed",
            )

        self._steps.append(_Step(name="report", run=step))
        return self

    @staticmethod
    def _git_exclude_cmd(*paths: str) -> str:
        """Shell snippet that appends each path to ``.git/info/exclude`` once.

        Idempotent: ``grep -qxF`` skips paths already excluded, so re-running
        never duplicates lines. Shared by ``with_memory`` and ``with_report``
        so the exclude idiom lives in one place.
        """
        return "\n".join(
            f"grep -qxF {q} .git/info/exclude 2>/dev/null || echo {q} >> .git/info/exclude"
            for q in (shlex.quote(p) for p in paths)
        )

    async def __aenter__(self) -> AsyncSandbox:
        for prep in self._prep_steps:
            logger.info("sandbox.builder.prep", extra={"step": prep.name})
            await prep.run()

        settings = Settings()  # ty: ignore[missing-argument]
        sandbox = await AsyncSandbox.create(
            image=self._SANDBOX_IMAGE,
            wait_ready=True,
            env=self._env,
            delete_after_delay=self._config.delete_after_delay,
            api_token=settings.koyeb_api_token,
        )
        self._sandbox = sandbox
        try:
            for step in self._steps:
                logger.info("sandbox.builder.step", extra={"step": step.name})
                await step.run(sandbox)
        except BaseException:
            # Setup failed → tear down before the exception escapes.
            # __aexit__ only runs if __aenter__ returned successfully,
            # so we have to clean up ourselves here.
            await self._safe_delete()
            raise
        return sandbox

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._safe_delete()

    async def _safe_delete(self) -> None:
        sandbox = self._sandbox
        if sandbox is None:
            return
        self._sandbox = None
        try:
            await sandbox.delete()
        except Exception as exc:
            # delete_after_delay catches stragglers — don't mask the
            # original error path with a cleanup-side failure.
            logger.warning(
                "sandbox.builder.delete_failed",
                extra={
                    "sandbox_id": getattr(sandbox, "id", None),
                    "error": str(exc),
                },
            )

    @staticmethod
    async def _run(
        sandbox: AsyncSandbox,
        cmd: str,
        *,
        cwd: str | None = None,
        timeout: int,
        fail_msg: str,
    ) -> None:
        # Prep steps run via the same non-blocking polling path as the vibe
        # run, so a slow clone never holds a worker thread and stalls another
        # review's sandbox launch.
        try:
            exit_code, stdout, stderr = await exec_polling(sandbox, cmd, cwd=cwd, timeout=timeout)
        except SandboxExecTimeout as exc:
            raise RuntimeError(f"{fail_msg} (timeout after {exc.timeout}s)") from exc
        if exit_code != 0:
            err = (stderr or stdout or "").strip()
            raise RuntimeError(f"{fail_msg} (exit={exit_code}): {err[:1000]}")
