"""Shared prompt rendering for vibe task factories.

Each factory under ``meow.worker.vibe_tasks`` ships its prose as a
sibling ``.md`` under :mod:`meow.worker.vibe_tasks.prompts` and pulls
it through :func:`render_prompt`. Centralising the resource lookup
keeps the loader logic (and its ``@cache``) in one place — factories
stay thin and typed.
"""

from __future__ import annotations

from functools import cache
from importlib.resources import files
from string import Template

__all__ = ["render_prompt"]

_PROMPTS_PACKAGE = "meow.worker.vibe_tasks.prompts"


@cache
def _template(name: str) -> Template:
    raw = files(_PROMPTS_PACKAGE).joinpath(name).read_text(encoding="utf-8")
    return Template(raw)


def render_prompt(name: str, /, **kwargs: object) -> str:
    """Render a markdown template by filename, e.g. ``"pr_review.md"``.

    Uses :meth:`string.Template.substitute` (strict): a missing or
    extra placeholder raises ``KeyError`` / ``ValueError`` rather than
    silently rendering ``$varname`` literal in the prompt.
    """
    return _template(name).substitute(**kwargs)
