"""Parser for repo-level ``.meow.yml`` config files (story S13).

The function :func:`parse_meow_yml` is intentionally forgiving: any failure
mode — missing file, empty content, malformed YAML, wrong root type,
schema-level validation error — yields a default :class:`MeowConfig` with
a warning log. A broken config file MUST NOT prevent the bot from
reviewing the PR; defaults are spec-defined and safe.
"""

from __future__ import annotations

import yaml
from pydantic import ValidationError

from meow.common.logging import get_logger
from meow.worker.models import MeowConfig

__all__ = ["parse_meow_yml"]

logger = get_logger("common")


def parse_meow_yml(raw: str | None) -> MeowConfig:
    """Parse a ``.meow.yml`` payload into a :class:`MeowConfig`.

    ``raw`` is the file content as returned by GitHub's contents API (or
    ``None`` if the file doesn't exist on the PR HEAD). All error paths
    log a warning and return ``MeowConfig()`` with full defaults.
    """
    if raw is None or not raw.strip():
        return MeowConfig()

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        logger.warning(
            "config.meow_yml.parse_failed",
            extra={"error": str(exc)[:200]},
        )
        return MeowConfig()

    if not isinstance(data, dict):
        logger.warning(
            "config.meow_yml.not_a_mapping",
            extra={"root_type": type(data).__name__},
        )
        return MeowConfig()

    try:
        return MeowConfig.model_validate(data)
    except ValidationError as exc:
        logger.warning(
            "config.meow_yml.invalid",
            extra={"errors": exc.errors()},
        )
        return MeowConfig()
