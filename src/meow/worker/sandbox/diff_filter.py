"""Filter unified diff hunks by ``.meow.yml`` ``exclude_paths`` globs (S12).

A repo can declare gitignore-style globs (``vendor/**``, ``**/*.lock``)
that the bot should not waste vibe turns reviewing. This module strips
the corresponding ``diff --git`` sections from a unified diff *before*
the diff reaches the sandbox. Pure function, no I/O.
"""

from __future__ import annotations

import re

import pathspec

__all__ = ["filter_diff_by_exclude"]

# Each per-file section in a unified diff starts with ``diff --git a/X b/Y``.
# We extract the ``b/`` path (post-image) since that's what users think of
# as "the file being changed", and what ``exclude_paths`` globs target.
_FILE_HEADER = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+?)$")


def filter_diff_by_exclude(diff: str, exclude_paths: list[str]) -> str:
    """Return ``diff`` with all hunks for paths matching ``exclude_paths`` removed.

    Globs follow gitignore semantics via :mod:`pathspec` — ``vendor/**``,
    ``**/*.lock``, leading-slash anchoring etc. all behave as in
    ``.gitignore``. An empty ``exclude_paths`` is a no-op. Content that
    appears before the first ``diff --git`` header (e.g. a leading commit
    message preamble) is preserved unchanged.
    """
    if not exclude_paths:
        return diff
    if not diff:
        return diff

    spec = pathspec.PathSpec.from_lines("gitignore", exclude_paths)

    out: list[str] = []
    current: list[str] = []
    current_path: str | None = None
    in_section = False

    def _flush() -> None:
        if not in_section:
            # Preamble before the first "diff --git" — preserve as-is.
            out.extend(current)
            return
        assert current_path is not None
        if not spec.match_file(current_path):
            out.extend(current)

    for line in diff.splitlines(keepends=True):
        m = _FILE_HEADER.match(line.rstrip("\r\n"))
        if m:
            _flush()
            current = [line]
            current_path = m.group("b")
            in_section = True
        else:
            current.append(line)

    _flush()
    return "".join(out)
