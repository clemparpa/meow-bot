"""Unit tests for ``meow.worker.sandbox.diff_filter`` (story S12)."""

from __future__ import annotations

from meow.worker.sandbox.diff_filter import filter_diff_by_exclude

_HUNK_A = (
    "diff --git a/src/foo.py b/src/foo.py\n"
    "index 1111..2222 100644\n"
    "--- a/src/foo.py\n"
    "+++ b/src/foo.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)
_HUNK_VENDOR = (
    "diff --git a/vendor/lib.js b/vendor/lib.js\n"
    "index 3333..4444 100644\n"
    "--- a/vendor/lib.js\n"
    "+++ b/vendor/lib.js\n"
    "@@ -1 +1 @@\n"
    "-x\n"
    "+y\n"
)
_HUNK_LOCK = (
    "diff --git a/uv.lock b/uv.lock\n"
    "index 5555..6666 100644\n"
    "--- a/uv.lock\n"
    "+++ b/uv.lock\n"
    "@@ -1 +1 @@\n"
    "-a\n"
    "+b\n"
)


def test_empty_diff_passthrough() -> None:
    assert filter_diff_by_exclude("", ["vendor/**"]) == ""


def test_no_exclude_paths_is_noop() -> None:
    diff = _HUNK_A + _HUNK_VENDOR
    assert filter_diff_by_exclude(diff, []) == diff


def test_excludes_single_matching_file() -> None:
    diff = _HUNK_A + _HUNK_VENDOR
    result = filter_diff_by_exclude(diff, ["vendor/**"])
    assert result == _HUNK_A


def test_keeps_files_not_matching_any_glob() -> None:
    diff = _HUNK_A + _HUNK_VENDOR
    # ``src/foo.py`` doesn't match ``vendor/**``, must survive.
    result = filter_diff_by_exclude(diff, ["vendor/**"])
    assert "src/foo.py" in result
    assert "vendor/lib.js" not in result


def test_double_star_glob_matches_nested_paths() -> None:
    nested = _HUNK_VENDOR.replace("vendor/lib.js", "vendor/deeply/nested/lib.js")
    diff = _HUNK_A + nested
    assert filter_diff_by_exclude(diff, ["vendor/**"]) == _HUNK_A


def test_extension_glob() -> None:
    diff = _HUNK_A + _HUNK_LOCK
    # gitignore-style ``**/*.lock`` should match a top-level ``uv.lock``.
    result = filter_diff_by_exclude(diff, ["**/*.lock"])
    assert "uv.lock" not in result
    assert "src/foo.py" in result


def test_multiple_globs_combine() -> None:
    diff = _HUNK_A + _HUNK_VENDOR + _HUNK_LOCK
    result = filter_diff_by_exclude(diff, ["vendor/**", "**/*.lock"])
    assert result == _HUNK_A


def test_excluding_everything_yields_empty() -> None:
    diff = _HUNK_VENDOR + _HUNK_LOCK
    assert filter_diff_by_exclude(diff, ["vendor/**", "**/*.lock"]) == ""


def test_preamble_before_first_diff_is_preserved() -> None:
    # GitHub's diff endpoint doesn't emit preambles, but ``git format-patch``
    # output does. We don't want to drop them silently.
    preamble = "From abc Mon Sep 17 00:00:00 2001\nSubject: [PATCH] x\n\n"
    diff = preamble + _HUNK_A
    result = filter_diff_by_exclude(diff, ["vendor/**"])
    assert result.startswith(preamble)
    assert "src/foo.py" in result


def test_malformed_diff_without_headers_passes_through() -> None:
    # No ``diff --git`` lines at all — there's nothing to filter, so the
    # whole content is treated as preamble and returned as-is.
    junk = "this is not a real diff\nsecond line\n"
    assert filter_diff_by_exclude(junk, ["vendor/**"]) == junk
