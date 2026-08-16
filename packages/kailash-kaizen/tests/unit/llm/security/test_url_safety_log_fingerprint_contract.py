# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""The rejection log carries a fingerprint, never a URL — and joins the exception.

Pins the fix for CodeQL `py/clear-text-logging-sensitive-data` (HIGH) on
`kaizen/llm/url_safety.py`. The alert was a naming artifact rather than a
leak: the value reaching `logger.warning` was already 8 hex characters of a
non-reversible BLAKE2b digest, but it came from a callee named
`fingerprint_secret`, and CodeQL classifies the result of any call whose
name matches `secret` as sensitive data — interprocedurally, so a local
wrapper does not clear it. The fix names the canonical helper for what it
produces (`fingerprint_value`) instead of suppressing the finding.

Three properties have to survive that rename, and each is asserted here:

1. `fingerprint_value` and `fingerprint_secret` are byte-identical, so tags
   emitted through either name still correlate in one forensic query.
2. `url_safety`'s log tag still equals `errors._fingerprint`'s exception
   tag — the log-line-to-exception join this module exists to support.
3. No raw URL, host, or query string ever reaches the log record.
"""

from __future__ import annotations

import ast
import inspect
import logging

import pytest

from kailash.utils.url_credentials import fingerprint_secret, fingerprint_value
from kaizen.llm import url_safety
from kaizen.llm.errors import InvalidEndpoint, _fingerprint

# A URL that is rejected offline, carrying a credential-shaped query param so
# a regression that logs the raw URL is caught by the leak assertion below.
_REJECTED = "https://10.0.0.1/v1/chat?api-key=sk-super-secret-value"


# ---------------------------------------------------------------------------
# 1. The two helper names are one implementation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["", "sk-1234567890abcdef", "https://api.openai.com/v1", "a" * 4096, "ünïcødé"],
)
def test_fingerprint_value_is_byte_identical_to_fingerprint_secret(value: str) -> None:
    assert fingerprint_value(value) == fingerprint_secret(value)


@pytest.mark.parametrize("length", [1, 4, 8, 16, 32, 64])
def test_the_two_names_agree_at_every_length(length: int) -> None:
    raw = "https://myfoundry.services.ai.azure.com"
    assert fingerprint_value(raw, length=length) == fingerprint_secret(
        raw, length=length
    )
    assert len(fingerprint_value(raw, length=length)) == length


# ---------------------------------------------------------------------------
# 2. The log-to-exception join still holds.
# ---------------------------------------------------------------------------


def test_log_fingerprint_matches_the_exception_fingerprint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The whole point of the tag: one query joins the WARN to the raise."""
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.url_safety"):
        with pytest.raises(InvalidEndpoint) as exc_info:
            url_safety.check_url(_REJECTED, resolve_dns=False)

    records = [r for r in caplog.records if r.message == "url_safety.rejected"]
    assert len(records) == 1, f"expected exactly one WARN, got {len(records)}"
    assert records[0].url_fingerprint == _fingerprint(_REJECTED)
    assert records[0].url_fingerprint in str(exc_info.value)
    assert records[0].reason == "private_ipv4"


def test_kaizen_specific_scheme_check_logs_through_the_same_site(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`_reject` (HTTPS-only) and the shared guard emit the identical line."""
    url = "http://api.openai.com/v1"
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.url_safety"):
        with pytest.raises(InvalidEndpoint):
            url_safety.check_url(url, resolve_dns=False)

    records = [r for r in caplog.records if r.message == "url_safety.rejected"]
    assert len(records) == 1
    assert records[0].reason == "scheme"
    assert records[0].url_fingerprint == _fingerprint(url)


# ---------------------------------------------------------------------------
# 3. No raw URL material in the log record.
# ---------------------------------------------------------------------------


def test_no_raw_url_material_reaches_the_log_record(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.url_safety"):
        with pytest.raises(InvalidEndpoint):
            url_safety.check_url(_REJECTED, resolve_dns=False)

    records = [r for r in caplog.records if r.message == "url_safety.rejected"]
    assert len(records) == 1
    rendered = records[0].getMessage() + repr(records[0].__dict__)
    for leaked in ("sk-super-secret-value", "10.0.0.1", "api-key", _REJECTED):
        assert leaked not in rendered, f"{leaked!r} leaked into the log record"


# ---------------------------------------------------------------------------
# 4. Source-level pin on the CodeQL class itself.
# ---------------------------------------------------------------------------


def _called_and_imported_names(module) -> set[str]:
    """Every name this module CALLS or IMPORTS — prose excluded.

    Walks the AST rather than grepping the source so the module docstring may
    explain the CodeQL rule (and name `fingerprint_secret` while doing so)
    without the pin matching its own rationale.
    """
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def test_module_does_not_route_a_log_through_a_secret_named_callee() -> None:
    """The alert class, pinned at the source level.

    `py/clear-text-logging-sensitive-data` fires on a `*secret*`-named callee
    reaching a logging sink. `url_safety` logs a fingerprint on every
    rejection path, so any reintroduction of `fingerprint_secret` here
    reintroduces the HIGH alert.

    SCOPE, stated precisely because the CodeQL flow is interprocedural and
    this pin is not: it covers `url_safety`'s OWN calls and imports, one hop.
    `errors._fingerprint` still calls `fingerprint_secret` and that is
    correct — its input is credential-adjacent and its output reaches an
    exception message, not a log sink. A future `logger.*(str(exc))`
    anywhere would put that hop on a logging path and is NOT caught here.
    """
    names = _called_and_imported_names(url_safety)
    offenders = sorted(n for n in names if "secret" in n.lower())
    assert not offenders, (
        f"url_safety calls/imports {offenders}; it logs a fingerprint on "
        "every rejection path, so a `secret`-named callee reinstates CodeQL "
        "py/clear-text-logging-sensitive-data (HIGH). Use fingerprint_value "
        "— byte-identical."
    )
    assert "fingerprint_value" in names


def test_exactly_one_rejection_logging_site() -> None:
    """Two copies of the WARN drift, and each is its own CodeQL sink."""
    src = inspect.getsource(url_safety)
    assert src.count("url_safety.rejected") == 1, (
        "url_safety must have exactly ONE rejection-logging site; "
        "_reject routes through _rejecting_error_factory"
    )
