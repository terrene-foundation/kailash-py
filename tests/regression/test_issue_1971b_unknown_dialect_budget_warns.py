"""Regression: the unknown-dialect identifier budget must warn at runtime.

#1971b — surfaced by the #1720 forest redteam (R1 adversarial security pass).

``DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH`` is the LOOSEST budget (SQLite's 128)
and is deliberately not safe: a site passing it accepts an identifier
PostgreSQL truncates server-side at 63, silently ALIASING two models onto one
physical table — the exact defect #1971 exists to close.

That hazard was documented only in a source comment, which is invisible at
runtime, while the constant is live on 19 references across 7 modules
(schema_manager, migrations/generator, workflow/dlq, trust/audit_store, and
infrastructure/{task_queue,worker_registry,dlq}) — several of which run against
PostgreSQL. Per ``rules/security.md`` § "Secure-Default For A New Security
Feature", a control whose default makes it inert MUST fail closed OR emit a
loud one-time WARN naming the unprotected surface and its wiring.

Failing closed is not available: the unbound budget is load-bearing for
genuinely dialect-less callers. So the WARN is the required half.
"""

from __future__ import annotations

import logging

import pytest

from kailash.db.dialect import (
    _UNKNOWN_BUDGET_WARNED_SITES,
    DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH,
    POSTGRES_MAX_IDENTIFIER_LENGTH,
    SQLITE_MAX_IDENTIFIER_LENGTH,
    _validate_identifier,
)

_MARKER = "identifier.unknown_dialect_budget"


@pytest.fixture(autouse=True)
def _clear_warn_memo():
    """The memo is process-global; clear it so tests do not mask each other."""
    _UNKNOWN_BUDGET_WARNED_SITES.clear()
    yield
    _UNKNOWN_BUDGET_WARNED_SITES.clear()


@pytest.mark.regression
def test_unknown_budget_emits_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier("users", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)

    assert _MARKER in caplog.text, (
        "the unknown-dialect budget must be visible at runtime, not only in a "
        "source comment"
    )


@pytest.mark.regression
def test_warning_names_the_calling_site_not_the_validator(caplog):
    """Attribution is the point — a warning naming dialect.py is useless.

    The operator needs the site that failed to bind a dialect.
    """
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier("users", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)

    assert (
        __file__.split("/")[-1] in caplog.text
    ), f"warning must name the CALLER, got: {caplog.text!r}"
    assert "db/dialect.py" not in caplog.text


@pytest.mark.regression
def test_repeat_calls_from_one_site_warn_exactly_once(caplog):
    """A migration validating 400 identifiers must not emit 400 lines.

    Log spam is how a real warning gets filtered out and ignored.
    """
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        for _ in range(25):
            _validate_identifier(
                "users", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
            )

    assert caplog.text.count(_MARKER) == 1


@pytest.mark.regression
def test_distinct_sites_each_warn(caplog):
    """Two unbound call sites are two findings; collapsing them hides one."""
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier("a", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)
        _validate_identifier("b", max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH)

    assert caplog.text.count(_MARKER) == 2


@pytest.mark.regression
@pytest.mark.parametrize(
    "label,budget",
    [
        ("postgres", POSTGRES_MAX_IDENTIFIER_LENGTH),
        # SQLITE IS THE DISCRIMINATING CASE and was missing. The unknown budget
        # is numerically EQUAL to SQLite's (both 128), and the trigger used to
        # be a value comparison — so a correctly-bound SQLite caller was
        # indistinguishable from an unbound one and warned on every identifier.
        # Postgres (63) could never expose that: it differs numerically, so it
        # passed either way. The test was cited as the no-false-positive half
        # while being unable to detect the false positive that existed.
        #
        # SQLite is this ecosystem's default store, so the spurious warning
        # fired on the most common configuration.
        ("sqlite", SQLITE_MAX_IDENTIFIER_LENGTH),
    ],
)
def test_a_bound_dialect_budget_is_silent(caplog, label, budget):
    """No-false-positive half.

    A caller that correctly bound its dialect must not be nagged — otherwise
    the warning stops distinguishing wired from unwired sites, and operators
    learn to filter the channel that carries the real signal.
    """
    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier("users", max_length=budget)

    assert _MARKER not in caplog.text, (
        f"a caller correctly bound to {label} was warned as if it had bound "
        f"nothing; the trigger is comparing budget VALUES again rather than "
        f"testing for the _UnknownBudget sentinel"
    )


@pytest.mark.regression
def test_warning_does_not_change_validation_behaviour(caplog):
    """The WARN is observability, not enforcement.

    A 100-char identifier still PASSES under the unknown budget — that is the
    hazard being reported, and silently tightening it here would break the
    dialect-less callers the budget exists for.
    """
    long_name = "a" * 100

    with caplog.at_level(logging.WARNING, logger="kailash.db.dialect"):
        _validate_identifier(
            long_name, max_length=DIALECT_UNKNOWN_MAX_IDENTIFIER_LENGTH
        )

    assert _MARKER in caplog.text
