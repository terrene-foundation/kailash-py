"""Regression: trust dashboard timestamps are escaped on every return path.

CodeQL alert 5149 (``py/bad-tag-filter`` at ``trust/security.py``) was triaged
FALSE POSITIVE on the grounds that its sink escapes via ``html.escape``. The
residual check that triage left open was whether the escaper is applied at EVERY
interpolation site in ``trust/plane/dashboard.py``. It was -- with one exception:
``_format_timestamp`` returned raw text that callers drop straight into markup.

That was not exploitable, because every producer coerces its value through
``datetime.fromisoformat`` first. But the invariant lives in OTHER modules, so
the dashboard's safety depended on an edit elsewhere staying correct -- the
cross-file drift class. These tests pin the escaping locally so the dependency
is gone, and so a future producer that forwards an un-coerced value cannot
silently reopen the hole.
"""

import datetime

import pytest

from kailash.trust.plane.dashboard import _format_timestamp

pytestmark = pytest.mark.regression


class _HostileStrftime:
    """Stands in for a producer that yields markup from strftime()."""

    def strftime(self, fmt: str) -> str:
        return "<script>alert(1)</script>"


class _HostileStr:
    """Stands in for a value with no strftime, taking the fallback path."""

    def __str__(self) -> str:
        return '<img src=x onerror=alert(1)>" autofocus'


def test_strftime_path_is_escaped():
    result = _format_timestamp(_HostileStrftime())
    assert "<script>" not in result
    assert result == "&lt;script&gt;alert(1)&lt;/script&gt;"


def test_fallback_str_path_is_escaped():
    result = _format_timestamp(_HostileStr())
    assert "<" not in result and ">" not in result


def test_fallback_path_escapes_quotes_for_attribute_contexts():
    """html.escape defaults to quote=True; pin it, since quote=False would not.

    A value that keeps its double quote can break out of an HTML attribute even
    with angle brackets escaped.
    """
    result = _format_timestamp(_HostileStr())
    assert '"' not in result
    assert "&quot;" in result


def test_none_is_empty_string():
    assert _format_timestamp(None) == ""


def test_ordinary_timestamp_is_unchanged():
    """Escaping must be invisible for the values this function actually formats."""
    moment = datetime.datetime(2026, 9, 12, 10, 0, 0)
    assert _format_timestamp(moment) == "2026-09-12 10:00:00 UTC"
