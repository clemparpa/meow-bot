"""Smoke test for :mod:`meow.common.logging`."""

from __future__ import annotations

import json
import logging

import pytest

from meow.common.logging import get_logger


@pytest.fixture(autouse=True)
def _reset_meow_loggers() -> None:
    """Reset loggers under the ``meow.`` namespace between tests."""
    manager = logging.Logger.manager
    for name in list(manager.loggerDict):
        if name.startswith("meow."):
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
            logger.propagate = True
            logger.setLevel(logging.NOTSET)


def test_get_logger_emits_json_with_svc_event_and_extras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = get_logger("receiver")
    logger.info("webhook.received", extra={"delivery": "abcd-1234"})

    out = capsys.readouterr().out.strip()
    record = json.loads(out)
    assert record["svc"] == "receiver"
    assert record["event"] == "webhook.received"
    assert record["delivery"] == "abcd-1234"
