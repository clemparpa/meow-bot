"""Tests for ``meow.common.meow_yml.parse_meow_yml`` (story S13).

The parser is meant to be unbreakable: any malformed/wrong-type input
yields defaults + a warning log. Only valid, well-typed YAML mappings
produce non-default ``MeowConfig`` values.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from meow.common.logging import get_logger
from meow.common.meow_yml import parse_meow_yml
from meow.worker.types import MeowConfig


@pytest.fixture(autouse=True)
def _capture_common_logs(caplog: pytest.LogCaptureFixture):
    # ``get_logger`` sets ``propagate=False``, so caplog's root handler never
    # sees these records — attach its handler directly to the meow logger.
    logger = get_logger("common")
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="meow.common")
    yield
    logger.removeHandler(caplog.handler)


def test_parse_none_returns_defaults() -> None:
    assert parse_meow_yml(None) == MeowConfig()


def test_parse_empty_string_returns_defaults() -> None:
    assert parse_meow_yml("") == MeowConfig()


def test_parse_whitespace_only_returns_defaults() -> None:
    assert parse_meow_yml("   \n\t\n  ") == MeowConfig()


def test_parse_malformed_yaml_warns_and_returns_defaults(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Unclosed bracket — yaml.safe_load raises yaml.YAMLError.
    assert parse_meow_yml("model: [unclosed") == MeowConfig()
    assert [r.message for r in caplog.records] == ["config.meow_yml.parse_failed"]
    assert hasattr(caplog.records[0], "error")


def test_parse_non_mapping_root_returns_defaults(caplog: pytest.LogCaptureFixture) -> None:
    # A YAML list is valid YAML but not a config mapping.
    assert parse_meow_yml("- one\n- two\n") == MeowConfig()
    assert [r.message for r in caplog.records] == ["config.meow_yml.not_a_mapping"]
    record: Any = caplog.records[0]
    assert record.root_type == "list"


def test_parse_full_valid_yaml() -> None:
    raw = (
        "model: mistral-large-2.6\n"
        "max_turns: 5\n"
        "max_price_usd: 1.25\n"
        "language: fr\n"
        "agents_md_path: docs/AGENTS.md\n"
        "exclude_paths:\n"
        "  - vendor/**\n"
        "  - '**/*.lock'\n"
    )
    cfg = parse_meow_yml(raw)
    assert cfg.model == "mistral-large-2.6"
    assert cfg.max_turns == 5
    assert cfg.max_price_usd == 1.25
    assert cfg.language == "fr"
    assert cfg.agents_md_path == "docs/AGENTS.md"
    assert cfg.exclude_paths == ["vendor/**", "**/*.lock"]


def test_parse_partial_overrides_only_named_keys() -> None:
    # Only ``model`` overridden — every other field falls back to default.
    cfg = parse_meow_yml("model: mistral-small-3.2\n")
    defaults = MeowConfig()
    assert cfg.model == "mistral-small-3.2"
    assert cfg.max_turns == defaults.max_turns
    assert cfg.max_price_usd == defaults.max_price_usd
    assert cfg.language == defaults.language
    assert cfg.agents_md_path == defaults.agents_md_path
    assert cfg.exclude_paths == defaults.exclude_paths


def test_parse_wrong_type_falls_back_to_defaults(caplog: pytest.LogCaptureFixture) -> None:
    # max_turns expects an int, gets a string — pydantic ValidationError.
    cfg = parse_meow_yml("max_turns: lots\n")
    assert cfg == MeowConfig()
    assert [r.message for r in caplog.records] == ["config.meow_yml.invalid"]
    record: Any = caplog.records[0]
    assert isinstance(record.errors, list)
    assert record.errors


def test_parse_constraint_violation_falls_back(caplog: pytest.LogCaptureFixture) -> None:
    # max_price_usd has gt=0 constraint — 0 must be rejected.
    cfg = parse_meow_yml("max_price_usd: 0\n")
    assert cfg == MeowConfig()
    assert [r.message for r in caplog.records] == ["config.meow_yml.invalid"]


def test_parse_unknown_keys_are_accepted_and_ignored() -> None:
    # Pydantic by default ignores extra keys — forward compat with future
    # schema additions. The known keys must still apply.
    cfg = parse_meow_yml("model: mistral-medium-3.5\nfuture_key: hello\n")
    assert cfg.model == "mistral-medium-3.5"
