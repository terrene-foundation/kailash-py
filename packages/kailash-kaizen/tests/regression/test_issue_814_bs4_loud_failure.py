"""Regression test for issue #814 — bs4 silent-degradation -> loud failure.

Pre-fix (silent):
    `WebFetchTool._extract_text(html)` swallowed `ImportError` and returned
    the raw HTML with only a `logger.warning(...)` line. The caller passed
    `extract_text=True` and got back un-extracted HTML — invisible to the
    LLM, the user, and any downstream consumer that branched on
    "is this extracted text?".

Post-fix (loud):
    `_extract_text` raises a typed `ImportError` with an actionable
    install hint when beautifulsoup4 is missing. `WebFetchTool.execute(..., extract_text=True)`
    catches the ImportError at the call site and returns
    `NativeToolResult.from_error(...)` to the LLM caller. The error message
    points at the `kailash-kaizen[web-search]` extra.

This test MUST fail on the pre-fix code (raw HTML returned) and pass
post-fix (ImportError raised with the right message).
"""

from __future__ import annotations

import pytest

from kaizen.tools.native import search_tools
from kaizen.tools.native.search_tools import WebFetchTool


@pytest.mark.regression
def test_issue_814_extract_text_raises_when_bs4_missing(monkeypatch):
    """Behavior: _extract_text raises ImportError with install hint when
    beautifulsoup4 is not installed. No silent fallback to raw HTML."""
    monkeypatch.setattr(search_tools, "_BeautifulSoup", None)

    tool = WebFetchTool()

    with pytest.raises(ImportError, match=r"kailash-kaizen\[web-search\]"):
        tool._extract_text("<html><body>some content</body></html>")


@pytest.mark.regression
def test_issue_814_extract_text_message_directs_to_extras(monkeypatch):
    """The error message MUST point users at the optional extras group, not
    at a bare `pip install beautifulsoup4` (the pre-fix wording)."""
    monkeypatch.setattr(search_tools, "_BeautifulSoup", None)

    tool = WebFetchTool()

    with pytest.raises(ImportError) as exc_info:
        tool._extract_text("<html/>")

    msg = str(exc_info.value)
    assert "kailash-kaizen[web-search]" in msg
    assert "extract_text=False" in msg, (
        "Error message MUST tell users how to fall back to raw HTML "
        f"if they cannot install the extra; got: {msg!r}"
    )


@pytest.mark.regression
def test_issue_814_extract_text_succeeds_when_bs4_present():
    """Pre-fix sanity: when bs4 IS installed, _extract_text strips tags as
    documented. Confirms the loud-failure path does not regress the
    happy path."""
    if search_tools._BeautifulSoup is None:
        pytest.skip("beautifulsoup4 not installed in this venv")

    tool = WebFetchTool()
    extracted = tool._extract_text(
        "<html><body><p>hello</p><script>x</script></body></html>"
    )

    assert "hello" in extracted
    assert "<p>" not in extracted, "BeautifulSoup MUST strip HTML tags"
    assert (
        "x" not in extracted
    ), "BeautifulSoup MUST decompose <script> blocks before get_text"
