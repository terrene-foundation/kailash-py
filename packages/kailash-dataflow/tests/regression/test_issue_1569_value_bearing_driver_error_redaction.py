"""Regression: issue #1569 — value-bearing NON-dup-key driver errors MUST redact
through ``sanitize_db_error`` (``dataflow.core.exceptions``).

Cross-SDK (``cross-sdk``, ``security``): sibling of the #1552 / #1567 driver-error
redaction workstream. The four pre-#1569 regexes covered only the duplicate-key /
constraint shapes (PG ``Key (col)=(value)`` + ``DETAIL:``, MySQL ``Duplicate entry
'v' for key 'n'``, MongoDB ``dup key: {...}``). ANY OTHER value-bearing driver
error — a truncated/wrong value (MySQL errno 1292/1366), a failed type cast or
out-of-range value (PostgreSQL) — rendered the offending user VALUE verbatim into
logs / node-return dicts. Surfaced as an adjacent out-of-scope gap in the #1567
red-team; the ``1292`` leak was empirically confirmed with a canary in that run.

FAIL-CLOSED DESIGN DECISION LOCKED HERE (issue #1569 AC #3) — the fix is
DIALECT-SCOPED FAMILY redaction, NOT per-errno whack-a-mole and NOT a blanket
quoted-literal sweep:
  * One regex per dialect covers that dialect's whole value-echoing FAMILY
    (``_MYSQL_INCORRECT_VALUE_RE`` for the ``Incorrect/Truncated <type> value``
    family; ``_PG_QUOTED_VALUE_RE`` for the ``invalid input …`` / ``… out of
    range`` family), so the NEXT errno in the family redacts without a new regex.
  * The value is redacted while the diagnostic SHAPE (the ``<type>`` word + any
    trailing ``for column '<col>'`` schema name) is PRESERVED — the same contract
    the dup-key redactors hold. A blanket quoted-literal sweep would destroy those
    schema names, so it was rejected.
  * Column-name-ONLY errno shapes that echo NO user value (MySQL 1264 ``Out of
    range value for column``, 1406 ``Data too long for column``, 1265 ``Data
    truncated for column``) MUST pass through UNCHANGED — asserted below so a
    future over-broadening that starts redacting schema names fails loudly.

Cross-SDK parity: the equivalent Rust SDK redactor has the same pre-#1569 design
scope; broadening it is tracked on the Rust SDK (filed as its cross-SDK sibling).
This file locks the Python family-redaction invariant; a refactor that narrows
``sanitize_db_error`` back to dup-key-only fails these tests loudly.

The redaction chokepoint is a single helper; every DataFlow node handler + adapter
routes ``str(e)`` through it (routing invariants proven in
``test_issue_1552_crud_node_error_sanitization.py``), so covering the helper
covers every surface that renders a value-bearing ``DataFlowError``.
"""

import pytest

from dataflow.core.exceptions import sanitize_db_error

# A canary that is unmistakably user data / PII — MUST NOT survive on any surface.
PII = "SECRET-PII-o'brien@x.com-2020❤"


# (label, raw_driver_error_template, schema_tokens_that_MUST_survive)
# Each template embeds {pii}; the rendered string is passed to sanitize_db_error.
_REDACT_CASES = [
    # --- MySQL errno 1292 ER_TRUNCATED_WRONG_VALUE family (AC #1) ---
    (
        "mysql-1292-datetime-no-column",
        "(1292, \"Incorrect datetime value: '{pii}'\")",
        ["Incorrect datetime value", "(1292,"],
    ),
    (
        "mysql-1292-datetime-with-column",
        "(1292, \"Incorrect datetime value: '{pii}' for column 'created_at' at row 1\")",
        ["Incorrect datetime value", "created_at", "at row 1"],
    ),
    (
        "mysql-1292-integer",
        "(1292, \"Incorrect integer value: '{pii}' for column 'age' at row 3\")",
        ["Incorrect integer value", "age"],
    ),
    (
        "mysql-1292-truncated-double",
        "(1292, \"Truncated incorrect DOUBLE value: '{pii}'\")",
        ["Truncated incorrect DOUBLE value"],
    ),
    (
        "mysql-1292-truncated-decimal-column",
        "(1292, \"Truncated incorrect DECIMAL value: '{pii}' for column 'amount' at row 2\")",
        ["Truncated incorrect DECIMAL value", "amount"],
    ),
    # --- MySQL errno 1366 ER_TRUNCATED_WRONG_VALUE_FOR_FIELD (AC #2) ---
    (
        "mysql-1366-string-with-column",
        "(1366, \"Incorrect string value: '\\xF0{pii}' for column 'name' at row 1\")",
        ["Incorrect string value", "name", "at row 1"],
    ),
    # --- PostgreSQL value-bearing family (completeness — same class, other dialect) ---
    (
        "pg-invalid-input-integer",
        'invalid input syntax for type integer: "{pii}"',
        ["invalid input syntax for type integer"],
    ),
    (
        "pg-invalid-input-timestamp",
        'invalid input syntax for type timestamp: "{pii}"',
        ["invalid input syntax for type timestamp"],
    ),
    (
        "pg-invalid-input-enum",
        'invalid input value for enum mood: "{pii}"',
        ["invalid input value for enum mood"],
    ),
    (
        "pg-datetime-out-of-range",
        'date/time field value out of range: "{pii}"',
        ["date/time field value out of range"],
    ),
    (
        "pg-invalid-input-with-hint-continuation",
        'invalid input syntax for type integer: "{pii}"\nHINT: use a whole number',
        ["invalid input syntax for type integer", "HINT: use a whole number"],
    ),
    # --- PG numeric-overflow: value BEFORE the descriptor (errcode 22003, empirically
    #     confirmed against real PG; the colon-anchored PG family regex cannot reach it) ---
    (
        "pg-value-out-of-range-integer",
        'value "{pii}" is out of range for type integer',
        ["value ", "is out of range for type integer"],
    ),
    (
        "pg-value-out-of-range-smallint",
        'value "{pii}" is out of range for type smallint',
        ["is out of range for type smallint"],
    ),
    # --- PG malformed array/range literal (value-echoing, empirically confirmed);
    #     the trailing "\nDETAIL: ..." is redacted by _DETAIL_RE running first ---
    (
        "pg-malformed-array-literal",
        'malformed array literal: "{pii}"\nDETAIL:  Array value must start with brace.',
        ["malformed array literal"],
    ),
    (
        "pg-malformed-range-literal",
        'malformed range literal: "{pii}"\nDETAIL:  Unexpected end of input.',
        ["malformed range literal"],
    ),
    # --- adversarial: value embeds a quote AND a newline (DOTALL + greedy-to-suffix) ---
    (
        "mysql-embedded-quote-and-newline",
        "(1292, \"Incorrect datetime value: 'ab'c\\n{pii}' for column 'ts' at row 1\")",
        ["Incorrect datetime value", "ts", "at row 1"],
    ),
]


@pytest.mark.regression
@pytest.mark.parametrize(
    "label,template,survive", _REDACT_CASES, ids=[c[0] for c in _REDACT_CASES]
)
def test_value_bearing_driver_error_value_is_redacted(label, template, survive):
    """The user VALUE is gone; the redaction sentinel is present; the diagnostic
    schema tokens (error code, type word, column name) survive."""
    raw = template.format(pii=PII)
    out = sanitize_db_error(raw)

    # The whole PII canary AND its distinctive fragments MUST be absent.
    assert PII not in out, f"{label}: full PII survived: {out!r}"
    assert "o'brien@x.com" not in out, f"{label}: PII fragment survived: {out!r}"
    assert "REDACTED" in out, f"{label}: no redaction sentinel emitted: {out!r}"

    # Diagnostic shape preserved — an operator can still triage.
    for token in survive:
        assert token in out, f"{label}: schema token {token!r} lost: {out!r}"


# Column-name-ONLY errno shapes that echo NO user value — MUST pass through
# byte-identical (guards the fail-closed decision from over-broadening into the
# schema-name-preservation contract the dup-key redactors hold).
_UNCHANGED_CASES = [
    (
        "mysql-1264-out-of-range-no-value",
        "(1264, \"Out of range value for column 'age' at row 1\")",
    ),
    (
        "mysql-1406-data-too-long-no-value",
        "(1406, \"Data too long for column 'bio' at row 1\")",
    ),
    (
        "mysql-1265-data-truncated-no-value",
        "(1265, \"Data truncated for column 'pct' at row 1\")",
    ),
    (
        "mysql-1061-duplicate-key-name-schema-only",
        "(1061, \"Duplicate key name 'idx_email'\")",
    ),
    ("pg-value-too-long-type-only", "value too long for type character varying(10)"),
    ("benign-prose-no-driver-shape", "could not connect to server: connection refused"),
]


@pytest.mark.regression
@pytest.mark.parametrize(
    "label,raw", _UNCHANGED_CASES, ids=[c[0] for c in _UNCHANGED_CASES]
)
def test_column_name_only_errors_pass_through_unchanged(label, raw):
    """Errors that echo only a schema column name (no user value) MUST NOT be
    touched — over-redaction of schema names is a diagnostic regression."""
    assert sanitize_db_error(raw) == raw, f"{label}: over-redacted a value-less error"


@pytest.mark.regression
def test_existing_dupkey_redaction_unaffected():
    """The #1569 broadening MUST NOT regress the pre-existing dup-key redactors
    (disjoint preambles, order-independent)."""
    mysql_dup = "(1062, \"Duplicate entry 'alice@x.com' for key 'idx_email'\")"
    out = sanitize_db_error(mysql_dup)
    assert "alice@x.com" not in out
    assert "idx_email" in out  # key NAME preserved
    assert "[REDACTED]" in out

    pg_detail = (
        "duplicate key value violates unique constraint\n"
        "DETAIL: Key (email)=(alice@x.com) already exists."
    )
    out = sanitize_db_error(pg_detail)
    assert "alice@x.com" not in out
    assert "[REDACTED]" in out
