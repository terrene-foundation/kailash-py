"""Regression: issue #1567 — apostrophe-bearing MySQL duplicate-key values MUST
redact through ``sanitize_db_error`` on every rendered surface.

Cross-SDK (``cross-sdk``, ``security``): the sibling Rust SDK's equivalent
redactor had TWO gaps — (1) a quote-aware value body ``(?:''|[^'])*`` that stops
at a raw apostrophe, and (2) a greedy ``.*`` value body WITHOUT ``DOTALL`` that
stops at a newline. The issue asks whether the SAME gaps exist in py.

VERIFIED FINDING (this file's reason for existing): py does NOT have either gap.
``_MYSQL_DUP_ENTRY_RE`` (``dataflow.core.exceptions``) already uses a greedy
``.*`` value body — NOT a quote-aware ``(?:''|[^'])*`` body — so a raw embedded
apostrophe is spanned (hardened by #1557's greedy-to-final-``' for key '<name>'``
anchor); and it already carries ``re.DOTALL`` (hardened by #1556), so an embedded
newline is spanned too. MySQL's ``ER_DUP_ENTRY`` (1062) inserts the offending
value verbatim (``%-.192s``) WITHOUT doubling embedded quotes, so a value like
``O'Brien`` reaches the sanitizer with a raw ``'``.

AC-3 GAP #1567 CLOSES: the pre-existing MySQL dup-entry fixtures
(``test_issue_1556_1557_mongo_mysql_error_sanitization.py`` Part A) all use an
APOSTROPHE-FREE ``SECRET_VALUE`` — a no-apostrophe fixture "hides both gaps".
These tests add the apostrophe-bearing coverage AC-3 requires, locking the
greedy-``.*``-not-quote-aware invariant so a future refactor toward the Rust
sibling's quote-aware body (which WOULD leak ``O'Brien``) fails loudly.

The redaction chokepoint is a single helper (``sanitize_db_error``); every
DataFlow node handler + adapter routes ``str(e)`` through it, so covering the
helper covers every surface that renders a MySQL-derived ``DataFlowError``.
The SQL-side routing invariants that LOCK this (the analog of the MongoDB
Part D/F guards in the #1556/#1557 file, which are MongoDB-ONLY) live in
``test_issue_1552_crud_node_error_sanitization.py`` —
``test_no_dml_handler_renders_raw_error_text`` (``nodes.py`` CRUD handlers)
and ``test_adapter_dml_methods_sanitize`` (parametrized mysql / postgresql /
sqlite adapter DML seams) — plus
``test_issue_1550_eager_batch_ddl_error_sanitization.py`` ::
``test_no_eager_batch_ddl_site_renders_raw_error_text`` (the DDL-apply seam a
``Duplicate entry`` fires from when a UNIQUE index is built over duplicate
rows). Those invariants are value-agnostic (they assert the routing exists,
not what the value is), so MySQL routing proven with apostrophe-free values
equally holds for apostrophe-bearing values; #1567's delta is purely the
regex-body property, unit-tested here.
"""

import pytest

from dataflow.core.exceptions import sanitize_db_error

# A raw embedded apostrophe (``O'Brien``) is the #1567 core: MySQL renders the
# value verbatim, un-doubled, so the sanitizer sees ``'O'Brien'``. Distinctive
# so its ABSENCE from the redacted output is unambiguous.
APOSTROPHE_SECRET = "O'Brien-DO-NOT-LEAK-7f3a9c"


@pytest.mark.regression
def test_mysql_dup_entry_apostrophe_in_value_redacts():
    """#1567 core: a MySQL 1062 value containing a raw apostrophe MUST redact.

    If ``_MYSQL_DUP_ENTRY_RE`` ever regressed to a quote-aware body
    (``(?:''|[^'])*``, the Rust sibling's gapped shape), the value body would
    stop at the raw ``'`` in ``O'Brien``, the match would fail, and the raw
    string (WITH the value) would return unredacted."""
    raw = f"(1062, \"Duplicate entry '{APOSTROPHE_SECRET}' for key 'people.name'\")"
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out, "apostrophe-bearing value leaked (#1567)"
    assert "O'Brien" not in out, "apostrophe value head leaked"
    assert "[REDACTED]" in out
    # Key NAME is schema shape, preserved (matches the PG ``Key (col)`` treatment).
    assert "people.name" in out, "key name over-redacted (#1550 contract)"


@pytest.mark.regression
def test_mysql_dup_entry_apostrophe_bare_shape_redacts():
    """The bare (non-tuple) driver string shape redacts identically — the regex
    anchors on the ``Duplicate entry '...' for key`` structure, not the tuple
    wrapper."""
    raw = f"Duplicate entry '{APOSTROPHE_SECRET}' for key 'docs.title'"
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out and "[REDACTED]" in out
    assert "docs.title" in out


@pytest.mark.regression
def test_mysql_dup_entry_apostrophe_adversarial_for_key_substring_redacts_tail():
    """The #1557 adversarial case (value literally CONTAINS ``' for key``) AND a
    raw apostrophe combined: greedy ``.*`` MUST still anchor on the FINAL
    ``' for key '<name>'`` suffix, folding both the apostrophe head and the
    injected ``' for key`` tail into ``[REDACTED]``."""
    injected_tail = "INJECTED-TAIL-DO-NOT-LEAK-9c2f"
    raw = (
        f"(1062, \"Duplicate entry '{APOSTROPHE_SECRET}' for key '{injected_tail}' "
        "for key 'accts.email_uniq'\")"
    )
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out, "apostrophe value head leaked"
    assert injected_tail not in out, "post-``' for key`` tail leaked (#1557 anchor)"
    assert "[REDACTED]" in out
    assert "accts.email_uniq" in out, "key name over-redacted (#1550 contract)"


@pytest.mark.regression
def test_mysql_dup_entry_apostrophe_and_newline_in_value_redacts():
    """#1567 combined worst case: a value bearing BOTH a raw apostrophe AND an
    embedded newline. Requires greedy ``.*`` (spans the apostrophe) AND
    ``re.DOTALL`` (spans the newline) simultaneously — the two invariants #1557
    and #1556 established, together."""
    val = f"{APOSTROPHE_SECRET}\nline2-POST-NEWLINE-DO-NOT-LEAK"
    raw = f"(1062, \"Duplicate entry '{val}' for key 'accts.email_uniq'\")"
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out, "apostrophe value head leaked"
    assert "POST-NEWLINE-DO-NOT-LEAK" not in out, "post-newline tail leaked (DOTALL)"
    assert "[REDACTED]" in out and "accts.email_uniq" in out


@pytest.mark.regression
def test_mysql_dup_entry_apostrophe_keyname_less_still_redacts():
    """A truncated ``Duplicate entry 'O'Brien' for key`` (no ``'<name>'`` suffix)
    with a raw apostrophe MUST still redact via the optional-keyname branch."""
    raw = f"Duplicate entry '{APOSTROPHE_SECRET}' for key"
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out and "[REDACTED]" in out


@pytest.mark.regression
def test_mysql_dup_entry_multiple_clauses_all_values_redacted():
    """Two full ``Duplicate entry '...' for key '...'`` clauses concatenated
    (e.g. a multi-row batch error). Greedy ``.*`` + DOTALL folds everything from
    the first ``Duplicate entry '`` to the last ``' for key '<name>'`` into one
    ``[REDACTED]`` — it over-redacts the benign middle text, but NO value in
    either clause escapes (fail-closed: the input is a single driver error's
    ``str(e)``, so over-span cannot cross unrelated errors)."""
    raw = (
        f"Duplicate entry 'A{APOSTROPHE_SECRET}' for key 'k1'\n"
        f"log line\nDuplicate entry 'B{APOSTROPHE_SECRET}' for key 'k2'"
    )
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out, "a value leaked from a multi-clause error"
    assert "[REDACTED]" in out


@pytest.mark.regression
@pytest.mark.parametrize(
    "value",
    [
        "",  # empty value
        "'''",  # value that is only quote characters
        f"'''{APOSTROPHE_SECRET}'''",  # apostrophe-wrapped secret (quote-run corner)
    ],
)
def test_mysql_dup_entry_quote_run_corners_redact(value):
    """Greedy-backtracking corners: empty and quote-only values still redact
    (``.*`` backtracks to the single ``' for key`` anchor). Any real secret in
    the value MUST be gone."""
    raw = f"Duplicate entry '{value}' for key 'k'"
    out = sanitize_db_error(raw)
    assert APOSTROPHE_SECRET not in out
    assert "[REDACTED]" in out


@pytest.mark.regression
def test_mysql_dup_entry_regex_body_is_not_quote_aware():
    """Structural invariant (``refactor-invariants.md`` shape): pin that the
    MySQL value body is the greedy ``.*`` form, NOT the quote-aware
    ``(?:''|[^'])*`` shape the Rust sibling leaked on. A refactor toward the
    quote-aware body — which stops at the raw ``'`` in ``O'Brien`` — fails here
    loudly, before it can ship the #1567 leak.

    NOTE (intentional brittleness): this pins the literal ``.*`` spelling to
    name the specific ``(?:''|[^'])*`` anti-pattern + the cross-SDK divergence.
    A LEGITIMATE greedy re-spelling (``.+`` / ``[\\s\\S]*``) would false-fail
    this one test while the seven BEHAVIORAL tests above (which carry the actual
    redaction contract) stay green — so on such a re-spelling, update this pin,
    do not weaken the behavioral tests."""
    from dataflow.core.exceptions import _MYSQL_DUP_ENTRY_RE

    pattern = _MYSQL_DUP_ENTRY_RE.pattern
    assert "Duplicate entry '.*' for key" in pattern, (
        "MySQL dup-entry value body is no longer the greedy '.*' form — a "
        "quote-aware body reintroduces the #1567 apostrophe leak"
    )
    # DOTALL is required for the embedded-newline case (#1556).
    import re

    assert _MYSQL_DUP_ENTRY_RE.flags & re.DOTALL, (
        "re.DOTALL dropped from _MYSQL_DUP_ENTRY_RE — reintroduces the #1556 "
        "embedded-newline leak"
    )
