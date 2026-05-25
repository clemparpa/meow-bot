"""Unit tests for ``meow.worker.sandbox.vibe`` (story S12).

We test the pure pieces (prompt building, JSON parsing) directly and use
fakes for ``AsyncDaytona`` to exercise ``run_vibe_review``'s
orchestration + cleanup-on-error behaviour without hitting the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from meow.worker.sandbox import vibe as vibe_module
from meow.worker.sandbox.vibe import (
    _build_prompt,
    _build_runner_script,
    _parse_runner_output,
    run_vibe_review,
)
from meow.worker.types import MeowConfig, PrContext, ReviewReport


def _ctx() -> PrContext:
    return PrContext(
        installation_id=99,
        repo_full_name="octocat/hello",
        pr_number=42,
        base_sha="b" * 40,
        head_sha="h" * 40,
        diff="diff --git a/x b/x\n",
    )


# --- pure helpers --------------------------------------------------------


def test_build_prompt_embeds_diff_and_repo_coords() -> None:
    prompt = _build_prompt(_ctx(), MeowConfig(), "FILTERED_DIFF_CONTENT")
    assert "octocat/hello#42" in prompt
    assert "FILTERED_DIFF_CONTENT" in prompt
    assert "/work/repo" in prompt


def test_build_prompt_uses_agents_md_path() -> None:
    cfg = MeowConfig(agents_md_path="docs/AGENTS.md")
    prompt = _build_prompt(_ctx(), cfg, "")
    assert "docs/AGENTS.md" in prompt


def test_build_prompt_language_auto_vs_explicit() -> None:
    auto_prompt = _build_prompt(_ctx(), MeowConfig(language="auto"), "")
    assert "language of the diff" in auto_prompt
    fr_prompt = _build_prompt(_ctx(), MeowConfig(language="fr"), "")
    assert "in fr" in fr_prompt


def test_build_runner_script_has_correct_vibe_invocation() -> None:
    """Guards against regressions on the exact ``run_programmatic`` call shape.

    The runner script can't be unit-tested by execution — vibe isn't a
    local dep — so we assert on its source text instead. If any of these
    strings drift, the smoke run in the real sandbox will fail.
    """
    cfg = MeowConfig(model="m1", max_turns=3, max_price_usd=0.12)
    script = _build_runner_script("HI", cfg)

    # Imports — including the partial-message recovery exception.
    assert "from vibe.core.programmatic import run_programmatic" in script
    assert "from vibe.core.config import VibeConfig" in script
    assert "from vibe.core.utils.concurrency import ConversationLimitException" in script

    # Working dir set BEFORE the vibe imports so its tools see /work/repo.
    assert "os.chdir('/work/repo')" in script
    assert script.index("os.chdir") < script.index("from vibe.core.programmatic")

    # VibeConfig.load uses the model from MeowConfig + the READ_ONLY profile.
    assert "active_model='m1'" in script
    assert "['read_file', 'grep', 'bash']" in script

    # run_programmatic(config, prompt=..., max_turns=3, max_price=0.12).
    # ``config`` is positional — the function rejects ``config=`` kwarg.
    assert "run_programmatic(\n        config," in script
    assert "prompt='HI'" in script
    assert "max_turns=3" in script
    assert "max_price=0.12" in script

    # ConversationLimitException is caught so terminated_early survives.
    assert "except ConversationLimitException" in script
    assert "terminated_early = True" in script


def test_build_runner_script_is_syntactically_valid() -> None:
    """The runner is pure Python — parse it as a guard against f-string typos."""
    import ast

    cfg = MeowConfig()
    script = _build_runner_script("a normal prompt", cfg)
    ast.parse(script)


def test_build_runner_script_escapes_prompt_safely() -> None:
    """Prompts contain user-controlled content from PR diffs — must not break the script."""
    import ast

    cfg = MeowConfig()
    nasty = 'I\'ll "break" your script\nwith \\backslashes'
    script = _build_runner_script(nasty, cfg)
    # repr() produces a fully-escaped Python literal — the script stays parseable.
    assert repr(nasty) in script
    ast.parse(script)


def test_parse_runner_output_happy_path() -> None:
    stdout = '{"body": "hello", "terminated_early": false}\n'
    report = _parse_runner_output(stdout)
    assert report == ReviewReport(body="hello", terminated_early=False)


def test_parse_runner_output_picks_last_json_line() -> None:
    stdout = 'progress: step 1\nprogress: step 2\n{"body": "final", "terminated_early": true}\n'
    report = _parse_runner_output(stdout)
    assert report.body == "final"
    assert report.terminated_early is True


def test_parse_runner_output_raises_when_no_json() -> None:
    with pytest.raises(RuntimeError, match="no JSON"):
        _parse_runner_output("just text\nno json here\n")


# --- run_vibe_review orchestration --------------------------------------


class _FakeExec:
    def __init__(self, exit_code: int = 0, result: str = "") -> None:
        self.exit_code = exit_code
        self.result = result


class _FakeProcess:
    def __init__(self, *, code_run_result: _FakeExec | None = None) -> None:
        self.exec_calls: list[tuple[str, dict[str, Any]]] = []
        self.code_run_calls: list[str] = []
        self._code_run_result = code_run_result or _FakeExec(
            result='{"body": "ok", "terminated_early": false}',
        )

    async def exec(self, command: str, **kwargs: Any) -> _FakeExec:
        self.exec_calls.append((command, kwargs))
        return _FakeExec()

    async def code_run(self, code: str) -> _FakeExec:
        self.code_run_calls.append(code)
        return self._code_run_result


class _FakeSandbox:
    def __init__(self, *, code_run_result: _FakeExec | None = None) -> None:
        self.process = _FakeProcess(code_run_result=code_run_result)
        self.id = "sb-fake-1"
        self.deleted = False

    async def delete(self) -> None:
        self.deleted = True


class _FakeDaytona:
    def __init__(self, sandbox: _FakeSandbox) -> None:
        self._sandbox = sandbox
        self.create_calls: list[Any] = []

    async def create(self, params: Any) -> _FakeSandbox:
        self.create_calls.append(params)
        return self._sandbox


@pytest.fixture
def patch_daytona(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``AsyncDaytona`` so no network/auth happens."""
    sandbox = _FakeSandbox()
    fake = _FakeDaytona(sandbox)
    monkeypatch.setattr(vibe_module, "AsyncDaytona", lambda _cfg: fake)
    return {"daytona": fake, "sandbox": sandbox}


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEOW_DOMAIN", "meow.test")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")


async def test_run_vibe_review_clones_checks_out_and_runs(
    patch_daytona: dict[str, Any],
) -> None:
    report = await run_vibe_review(_ctx(), MeowConfig(), "TKN", "DIFF")

    sandbox: _FakeSandbox = patch_daytona["sandbox"]
    # 1st exec: clone with the embedded token. 2nd: checkout the head SHA.
    assert "git clone" in sandbox.process.exec_calls[0][0]
    assert "x-access-token:TKN@github.com/octocat/hello.git" in sandbox.process.exec_calls[0][0]
    assert f"git checkout {'h' * 40}" in sandbox.process.exec_calls[1][0]
    # And the runner script was code_run.
    assert len(sandbox.process.code_run_calls) == 1
    assert "run_programmatic" in sandbox.process.code_run_calls[0]
    assert report == ReviewReport(body="ok", terminated_early=False)


async def test_run_vibe_review_deletes_sandbox_on_success(
    patch_daytona: dict[str, Any],
) -> None:
    await run_vibe_review(_ctx(), MeowConfig(), "TKN", "DIFF")
    assert patch_daytona["sandbox"].deleted is True


async def test_run_vibe_review_deletes_sandbox_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # code_run returns non-zero → activity raises → sandbox must still
    # get deleted.
    failing = _FakeSandbox(
        code_run_result=_FakeExec(exit_code=1, result="boom"),
    )
    fake = _FakeDaytona(failing)
    monkeypatch.setattr(vibe_module, "AsyncDaytona", lambda _cfg: fake)
    monkeypatch.setenv("MEOW_DOMAIN", "meow.test")
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test")
    monkeypatch.setenv("DAYTONA_API_KEY", "daytona-test")
    monkeypatch.setenv("DEPLOYMENT_NAME", "meow-bot-test")

    with pytest.raises(RuntimeError, match="vibe runner failed"):
        await run_vibe_review(_ctx(), MeowConfig(), "TKN", "DIFF")

    assert failing.deleted is True


async def test_run_vibe_review_uses_meow_base_snapshot(
    patch_daytona: dict[str, Any],
) -> None:
    await run_vibe_review(_ctx(), MeowConfig(), "TKN", "DIFF")
    create_call = patch_daytona["daytona"].create_calls[0]
    assert create_call.snapshot == "meow-base"


async def test_run_vibe_review_injects_mistral_api_key_via_env_vars(
    patch_daytona: dict[str, Any],
) -> None:
    """``code_run`` has no per-call env arg, so the key must ride on create()."""
    await run_vibe_review(_ctx(), MeowConfig(), "TKN", "DIFF")
    create_call = patch_daytona["daytona"].create_calls[0]
    # ``mistral-test`` is the value the autouse env fixture sets.
    assert create_call.env_vars == {"MISTRAL_API_KEY": "mistral-test"}


async def test_clone_failure_scrubs_token_from_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """git can echo the failing URL in its diag — the token must not leak."""

    class _FailingProcess(_FakeProcess):
        async def exec(self, command: str, **kwargs: Any) -> _FakeExec:
            self.exec_calls.append((command, kwargs))
            # Mimic git's stderr: it tends to repeat the failing URL verbatim.
            return _FakeExec(exit_code=1, result=f"fatal: could not read: {command}")

    sandbox = _FakeSandbox()
    sandbox.process = _FailingProcess()
    fake = _FakeDaytona(sandbox)
    monkeypatch.setattr(vibe_module, "AsyncDaytona", lambda _cfg: fake)

    with pytest.raises(RuntimeError) as excinfo:
        await run_vibe_review(_ctx(), MeowConfig(), "SECRET_TOKEN", "DIFF")

    msg = str(excinfo.value)
    assert "SECRET_TOKEN" not in msg
    assert "x-access-token:***@" in msg
    # And the sandbox was still cleaned up on the way out.
    assert sandbox.deleted is True
