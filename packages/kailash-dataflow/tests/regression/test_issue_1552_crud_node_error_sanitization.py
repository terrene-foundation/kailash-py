"""Regression for issue #1552 — CRUD-node handlers leak raw driver error text
(``DETAIL: Key(col)=(value)`` / ``Duplicate entry 'value' for key``) into ERROR
logs + the returned ``{"success": False, "error": ...}`` dict.

DML sibling of the already-shipped #1550 DDL fix. #1550 closed the eager/lazy
DDL-executor leak (``CREATE UNIQUE INDEX`` over duplicate data). The CRUD
operation handlers in ``dataflow/core/nodes.py`` were a different, pre-existing
code path #1550 never touched: a constraint-violating INSERT / bulk write raises
a driver error carrying a real column VALUE (potential PII), and the handlers
rendered ``str(e)`` verbatim into:

* ``create`` (async path) — the ``original_error`` that flows to the
  param-mismatch ``error_msg`` AND the else-branch ``nodes.create_operation_failed``
  ERROR log + returned ``error``;
* ``bulk_create`` / ``bulk_update`` / ``bulk_delete`` / ``bulk_upsert`` — each
  ``except Exception`` handler's ``nodes.bulk_*_operation_failed`` ERROR log +
  returned ``error``.

Log aggregators typically have broader access than the DB
(``observability.md`` Rule 8; ``security.md`` § no-secrets-in-logs), so the raw
value MUST NOT reach the log line or the returned error string. The fix routes
every direct render through the shared
``dataflow.core.exceptions.sanitize_db_error`` (PG ``DETAIL:`` / ``Key(col)=(value)``
and MySQL ``Duplicate entry 'value' for key`` redaction), preserving the
diagnostic shape (constraint / column names, the conflict-target classifier
text) while replacing the value payload with ``[REDACTED]``.

Four parts (mirroring the #1550 test structure):

* **Part A (Tier-2, requires_postgres):** real PostgreSQL, a genuine
  duplicate-VALUE INSERT / bulk write driven through the DataFlow node path
  (the code path that hits the nodes.py handlers) — neither the returned
  ``error`` nor the ERROR log may contain the duplicated value. The database is
  never mocked; this is the issue's acceptance criterion.
* **Part B (Tier-1, deterministic):** the ``sanitize_db_error`` call is
  load-bearing — a crafted value-bearing driver error injected at the CRUD
  path's own seam (``AsyncSQLDatabaseNode.async_run`` for create;
  ``BulkOperations.bulk_create`` / ``bulk_upsert`` for the bulk paths) MUST
  render as ``[REDACTED]`` in BOTH the returned ``error`` dict AND the ERROR
  log, proving the redaction ran rather than passing vacuously because a
  particular driver happened to omit the value. Runs WITHOUT postgres.
* **Part C (structural invariant):** no DML handler renders raw ``str(e)`` into
  its return/log — a source-level guard that fails loudly if a future edit
  re-inlines the leak (``refactor-invariants.md``). Precise enough to exclude
  the two out-of-scope raw-render sites (the DDLFailedError-propagation log,
  already sanitized at source by #1550, and the TDD-connection-parse log, not a
  driver constraint error).
* **Part D (consumer-safety):** ``is_conflict_target_error`` is called on the
  RAW exception, and its match text survives ``sanitize_db_error`` — so
  sanitizing the returned/logged error does NOT break conflict-target
  classification.

Round-1 red team found the DML driver-error leak class is BROADER than the
nodes.py create+bulk handlers; the following parts close the WHOLE class:

* **Part E (FIX 2 — sanitize_db_error newline bypass):** a ``Key (col)=(value)``
  value spanning a NEWLINE (a unique/PK TEXT column) was truncated by the
  ``DETAIL:`` regex running first; reordering ``_KEY_VALUES_RE`` before
  ``_DETAIL_RE`` redacts the whole multi-line value.
* **Part F (FIX 1, HIGH — trust-audit persistence):** the single-record
  create/update/delete/upsert failure paths funnel through
  ``express._trust_record_failure`` → ``record_query_failure``, which PERSISTS
  the error verbatim (``result=f"failure:{error}"``) into the audit store (a
  broader-access surface). The single point now sanitizes; Part F proves it for
  the PG / MySQL / multi-line shapes and pins the four-mutation wiring.
* **Part G (FIX 3 — feature write-paths):** ``derived.py`` (RefreshResult.error +
  meta.last_error + log), ``retention.py`` (RetentionResult.error + log), and
  ``transactions.py`` (rollback log) each rendered raw driver errors; all now
  route through ``sanitize_db_error``.
* **Part H (FIX 4 + FIX 8, defense-in-depth):** the dead DML-capable adapter
  methods (``execute_insert`` / ``execute_bulk_insert`` — FIX 4; ``execute_query``
  / ``execute_transaction`` — FIX 8) on mysql / postgresql / sqlite render into a
  log + a raised ``*Error``; sanitized so a future wiring cannot reintroduce the
  leak (structural guard — no callers on the DataFlow hot path today).

Round-2 red team found a HIGH on a live public path plus redactor residuals:

* **Part E extension (FIX 7 — sanitize_db_error root cause):** the single-line
  ``DETAIL:[^\\n]*`` regex leaked value-bearing DETAIL content spanning a newline
  in two shapes — MED-1 (a ``Key (col)=(value)`` value with an embedded ``)`` +
  newline) and MED-2 (``DETAIL: Failing row contains (…)`` from CHECK / NOT-NULL
  / exclusion violations, which dump the WHOLE row). ``_DETAIL_RE`` now block-
  redacts the ENTIRE DETAIL clause up to the next PG structured-field marker
  (HINT/CONTEXT/…) or EOS — fail-closed, byte-identical on every single-line case.
* **Part I (FIX 5, HIGH):** ``express.import_file`` (public API returning
  ``{"imported": int, "errors": [...]}``) rendered the raw re-raised driver error
  from its per-record ``upsert`` / ``bulk_create`` into the RETURNED ``errors``
  list — the #1552 returned-error surface on a live public path (SQLite is
  value-less, which is why no earlier test caught it). Both renders now sanitize.

Permanent regression tests — NEVER delete (``rules/testing.md`` Regression).
"""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

import pytest

from dataflow import DataFlow

# Distinctive so its ABSENCE from any log / returned-error surface is
# unambiguous. Shaped like an email so a PG unique-violation DETAIL carries it.
SECRET_VALUE = "leak-secret-DO-NOT-LEAK-7f3a9c@corp.example"

_NODES_LOGGER = "dataflow.core.nodes"

# A value-bearing driver error in the canonical PostgreSQL unique-violation
# shape. The DETAIL clause embeds SECRET_VALUE, exactly as asyncpg surfaces it.
_VALUE_BEARING_ERROR = (
    'duplicate key value violates unique constraint "acct_email_key"\n'
    f"DETAIL:  Key (email)=({SECRET_VALUE}) already exists."
)

# The MySQL/MariaDB errno-1062 shape (``Duplicate entry 'value' for key 'name'``).
# A real MySQL container is not available in this Tier-1 env; injecting the exact
# driver-error STRING is the honest substitute — it proves the handler redacts the
# MySQL shape end-to-end (the value is gone from both the returned error and log),
# exactly as it would for a real MySQL duplicate-key failure.
_MYSQL_VALUE_BEARING_ERROR = (
    f"(1062, \"Duplicate entry '{SECRET_VALUE}' for key 'accts.email_uniq'\")"
)

# A driver error whose ``Key (col)=(value)`` value spans a NEWLINE (a unique/PK
# TEXT column — notes/address/bio). Pre-FIX-2 the ``DETAIL:`` regex (``[^\n]*``)
# ran first and truncated at the newline, leaking the post-newline remainder.
_MULTILINE_SECRET_L1 = "line1-secret-DO-NOT-LEAK-a1"
_MULTILINE_SECRET_L2 = "line2-secret-DO-NOT-LEAK-b2"
_MULTILINE_VALUE_BEARING_ERROR = (
    'duplicate key value violates unique constraint "acct_notes_key"\n'
    f"DETAIL:  Key (notes)=({_MULTILINE_SECRET_L1}\n{_MULTILINE_SECRET_L2}) already exists."
)


def _rendered(records) -> str:
    """Flatten captured log records into one searchable string, including the
    structured ``extra`` fields (where the CRUD error text lives)."""
    parts = []
    for r in records:
        parts.append(r.getMessage())
        for attr in ("error", "error_message", "statement"):
            val = getattr(r, attr, None)
            if isinstance(val, str):
                parts.append(val)
    return "\n".join(parts)


def _make_node(db: DataFlow, node_name: str):
    """Instantiate a generated CRUD node bound to ``db`` (mirrors
    ``features/express.py::_create_node``). Sets the express-precheck sentinel
    so protection prechecks don't intercept the write on this direct path."""
    node = db._nodes[node_name]()
    node.dataflow_instance = db
    node._express_protection_precheck_done = True
    return node


# --------------------------------------------------------------------------
# Part A — Tier-2, real PostgreSQL (acceptance criterion)
# --------------------------------------------------------------------------


@pytest.fixture
async def test_suite():
    """Real PostgreSQL integration suite (shared infra)."""
    from tests.infrastructure.test_harness import IntegrationTestSuite

    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


def _pg_model(db: DataFlow, cls_name: str):
    """Register a model with a UNIQUE email index so a duplicate-email write
    genuinely fails with a value-bearing driver DETAIL on PostgreSQL."""
    ns = {
        "__annotations__": {"id": str, "email": str, "name": str},
        "__dataflow__": {"indexes": [{"fields": ["email"], "unique": True}]},
    }
    model_cls = type(cls_name, (), ns)
    return db.model(model_cls)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_create_node_does_not_leak_duplicate_value(test_suite, caplog):
    """`create` handler: a real duplicate-VALUE INSERT through the generated
    CreateNode MUST NOT surface the value in the returned error or the log.

    Pre-fix this FAILS (the raw ``DETAIL: Key (email)=(<value>)`` reaches the
    returned ``error`` + ERROR log); post-fix it PASSES (redacted)."""
    cls = f"AcctC{uuid.uuid4().hex[:8]}"
    db = DataFlow(test_suite.config.url, auto_migrate=True)
    _pg_model(db, cls)

    node_name = f"{cls}CreateNode"
    try:
        seed = await _make_node(db, node_name).async_run(
            id="c1", email=SECRET_VALUE, name="seed"
        )
        assert seed.get("success") is not False, seed

        with caplog.at_level(logging.ERROR):
            result = await _make_node(db, node_name).async_run(
                id="c2", email=SECRET_VALUE, name="dup"
            )

        blob = _rendered(caplog.records)
        returned_error = (result or {}).get("error") or ""
        assert result.get("success") is False, result
        assert (
            SECRET_VALUE not in returned_error
        ), "issue #1552: duplicate value leaked into the returned create error"
        assert (
            SECRET_VALUE not in blob
        ), "issue #1552: duplicate value leaked into the create ERROR log"
        assert "[REDACTED]" in (
            returned_error + "\n" + blob
        ), "sanitize_db_error did not run on the create path"
    finally:
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_bulk_create_node_does_not_leak_duplicate_value(test_suite, caplog):
    """`bulk_create` handler: a real duplicate-VALUE bulk INSERT MUST NOT
    surface the value in the returned error or the ERROR log."""
    cls = f"AcctBC{uuid.uuid4().hex[:8]}"
    db = DataFlow(test_suite.config.url, auto_migrate=True)
    _pg_model(db, cls)

    node_name = f"{cls}BulkCreateNode"
    try:
        seed = await _make_node(db, node_name).async_run(
            data=[{"id": "b1", "email": SECRET_VALUE, "name": "seed"}]
        )
        assert seed.get("success") is not False, seed

        with caplog.at_level(logging.ERROR):
            result = await _make_node(db, node_name).async_run(
                data=[{"id": "b2", "email": SECRET_VALUE, "name": "dup"}]
            )

        blob = _rendered(caplog.records)
        returned_error = (result or {}).get("error") or ""
        assert result.get("success") is False, result
        assert (
            SECRET_VALUE not in returned_error
        ), "issue #1552: duplicate value leaked into the returned bulk_create error"
        assert (
            SECRET_VALUE not in blob
        ), "issue #1552: duplicate value leaked into the bulk_create ERROR log"
        assert "[REDACTED]" in (
            returned_error + "\n" + blob
        ), "sanitize_db_error did not run on the bulk_create path"
    finally:
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.postgresql
async def test_bulk_upsert_node_does_not_leak_duplicate_value(test_suite, caplog):
    """`bulk_upsert` handler: an upsert whose conflict target (`id`) does NOT
    cover the violated UNIQUE constraint (`email`) raises a real duplicate-VALUE
    driver error; neither the returned error nor the ERROR log may leak it."""
    cls = f"AcctBU{uuid.uuid4().hex[:8]}"
    db = DataFlow(test_suite.config.url, auto_migrate=True)
    _pg_model(db, cls)

    node_name = f"{cls}BulkUpsertNode"
    try:
        seed = _make_node(db, node_name)
        seed.conflict_columns = ["id"]
        seed_res = await seed.async_run(
            data=[{"id": "u1", "email": SECRET_VALUE, "name": "seed"}]
        )
        assert seed_res.get("success") is not False, seed_res

        with caplog.at_level(logging.ERROR):
            node = _make_node(db, node_name)
            node.conflict_columns = ["id"]  # NOT the violated (email) constraint
            result = await node.async_run(
                data=[{"id": "u2", "email": SECRET_VALUE, "name": "dup"}]
            )

        blob = _rendered(caplog.records)
        returned_error = (result or {}).get("error") or ""
        assert result.get("success") is False, result
        assert (
            SECRET_VALUE not in returned_error
        ), "issue #1552: duplicate value leaked into the returned bulk_upsert error"
        assert (
            SECRET_VALUE not in blob
        ), "issue #1552: duplicate value leaked into the bulk_upsert ERROR log"
        assert "[REDACTED]" in (
            returned_error + "\n" + blob
        ), "sanitize_db_error did not run on the bulk_upsert path"
    finally:
        res = db.close()
        if res is not None and hasattr(res, "__await__"):
            await res


# --------------------------------------------------------------------------
# Part B — Tier-1, deterministic injected driver error (sanitize is load-bearing)
# --------------------------------------------------------------------------
#
# The value-bearing DETAIL leak fires only for genuine constraint violations,
# which do not naturally occur on every backend/path. The ONLY injection
# permitted (mirroring #1550's fault-injection contract) is the driver error
# RAISED at the CRUD path's own seam — the database itself is never mocked; we
# exercise the handler's error-rendering branch with a controlled value-bearing
# input, on BOTH the returned-error surface AND the ERROR-log surface.


@pytest.fixture
def sqlite_db():
    """File-backed SQLite DataFlow with a unique-email model. Yields the db."""
    with tempfile.TemporaryDirectory() as tmp:
        db = DataFlow(
            f"sqlite:///{tmp}/issue_1552_{uuid.uuid4().hex}.db", auto_migrate=True
        )

        class Acct:
            __annotations__ = {"id": str, "email": str, "name": str}
            __dataflow__ = {"indexes": [{"fields": ["email"], "unique": True}]}

        db.model(Acct)
        db._ensure_connected()
        try:
            yield db
        finally:
            db.close()


@pytest.mark.regression
async def test_injected_create_error_is_sanitized(sqlite_db, monkeypatch, caplog):
    """The `create` handler's else-branch routes the value-bearing driver error
    through ``sanitize_db_error`` → ``[REDACTED]`` in BOTH the returned ``error``
    dict AND the ``nodes.create_operation_failed`` ERROR log."""
    db = sqlite_db
    from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

    # Seed the table (so the failing create's ensure_table short-circuits and
    # does not itself touch the patched async_run).
    await _make_node(db, "AcctCreateNode").async_run(
        id="s1", email="seed@corp.example", name="seed"
    )

    async def _boom(self, *a, **k):
        raise RuntimeError(_VALUE_BEARING_ERROR)

    monkeypatch.setattr(AsyncSQLDatabaseNode, "async_run", _boom)

    with caplog.at_level(logging.ERROR, logger=_NODES_LOGGER):
        result = await _make_node(db, "AcctCreateNode").async_run(
            id="s2", email="dup@corp.example", name="dup"
        )

    returned_error = (result or {}).get("error") or ""
    assert result.get("success") is False, result
    # Returned-error surface
    assert SECRET_VALUE not in returned_error
    assert (
        "[REDACTED]" in returned_error
    ), "create returned-error not redacted — sanitize is not load-bearing"
    # Log surface
    rec = next(
        (
            r
            for r in caplog.records
            if r.getMessage() == "nodes.create_operation_failed"
        ),
        None,
    )
    assert rec is not None, "nodes.create_operation_failed was not logged"
    log_error = getattr(rec, "error", "")
    assert SECRET_VALUE not in log_error
    assert "[REDACTED]" in log_error, "create ERROR log not redacted"


@pytest.mark.regression
@pytest.mark.parametrize(
    "op,node_name,seam,log_event,err",
    [
        # All four bulk handlers, PG value-bearing shape.
        (
            "bulk_create",
            "AcctBulkCreateNode",
            "bulk_create",
            "nodes.bulk_create_operation_failed",
            _VALUE_BEARING_ERROR,
        ),
        (
            "bulk_update",
            "AcctBulkUpdateNode",
            "bulk_update",
            "nodes.bulk_update_operation_failed",
            _VALUE_BEARING_ERROR,
        ),
        (
            "bulk_delete",
            "AcctBulkDeleteNode",
            "bulk_delete",
            "nodes.bulk_delete_operation_failed",
            _VALUE_BEARING_ERROR,
        ),
        (
            "bulk_upsert",
            "AcctBulkUpsertNode",
            "bulk_upsert",
            "nodes.bulk_upsert_operation_failed",
            _VALUE_BEARING_ERROR,
        ),
        # MySQL errno-1062 shape through bulk_create (real MySQL unavailable —
        # injected-string substitute; proves the handler redacts the MySQL shape).
        (
            "bulk_create",
            "AcctBulkCreateNode",
            "bulk_create",
            "nodes.bulk_create_operation_failed",
            _MYSQL_VALUE_BEARING_ERROR,
        ),
    ],
)
async def test_injected_bulk_error_is_sanitized(
    sqlite_db, monkeypatch, caplog, op, node_name, seam, log_event, err
):
    """Each bulk handler's ``except`` branch routes the value-bearing driver
    error through ``sanitize_db_error`` → ``[REDACTED]`` in BOTH the returned
    ``error`` dict AND the ``nodes.bulk_*_operation_failed`` ERROR log — for the
    PostgreSQL DETAIL shape AND the MySQL ``Duplicate entry`` shape."""
    db = sqlite_db

    async def _boom(*a, **k):
        raise RuntimeError(err)

    # Inject at the CRUD path's own seam: the bulk handler delegates to
    # ``self.dataflow_instance.bulk.<op>(...)``.
    monkeypatch.setattr(db.bulk, seam, _boom)

    node = _make_node(db, node_name)
    if op == "bulk_upsert":
        node.conflict_columns = ["id"]

    with caplog.at_level(logging.ERROR, logger=_NODES_LOGGER):
        result = await node.async_run(
            data=[{"id": "x1", "email": SECRET_VALUE, "name": "x"}]
        )

    returned_error = (result or {}).get("error") or ""
    assert result.get("success") is False, result
    # Returned-error surface
    assert SECRET_VALUE not in returned_error
    assert (
        "[REDACTED]" in returned_error
    ), f"{op} returned-error not redacted — sanitize is not load-bearing"
    # Log surface
    rec = next((r for r in caplog.records if r.getMessage() == log_event), None)
    assert rec is not None, f"{log_event} was not logged"
    log_error = getattr(rec, "error", "")
    assert SECRET_VALUE not in log_error
    assert "[REDACTED]" in log_error, f"{op} ERROR log not redacted"


# --------------------------------------------------------------------------
# Part C — structural invariant (guards against a future re-inline regression)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_no_dml_handler_renders_raw_error_text():
    """Every DML CRUD handler routes its error render through
    ``sanitize_db_error``. A raw ``"error": str(e)`` / ``extra={"error": str(e)}``
    render at these sites is the exact #1552 leak shape — assert none remain, so
    a future edit that re-inlines a raw render fails this test loudly
    (``refactor-invariants.md``).

    Precise so it does NOT flag the two OUT-OF-SCOPE raw-render sites that are
    legitimately raw ``str(e)``:
      * the ``DDLFailedError``-propagation log (``model_name`` + ``error``) —
        the exception text is already sanitized at source by #1550;
      * the ``failed_to_extract_tdd_connection_info`` log — a connection-parse
        error, not a driver constraint error (outside the leak class).
    """
    nodes_src = (
        Path(__file__).resolve().parents[2] / "src" / "dataflow" / "core" / "nodes.py"
    ).read_text()

    # The 6 fixed renders (create source + create else + 4 bulk) all sanitize
    # at the source. Re-inlining any one drops the count below 6.
    assert nodes_src.count("sanitize_db_error(str(e))") >= 6, (
        "a DML handler stopped routing its driver error through "
        "sanitize_db_error — #1552 leak re-inlined"
    )
    # The 4 bulk handlers log + return the SANITIZED value.
    assert (
        nodes_src.count('extra={"error": sanitized}') >= 4
    ), "a bulk handler's ERROR log no longer uses the sanitized value"
    assert (
        nodes_src.count('"error": sanitized,') >= 4
    ), "a bulk handler's returned error dict no longer uses the sanitized value"
    # The create else-branch computes one sanitized value for both surfaces.
    assert (
        "sanitized_error = sanitize_db_error(str(e))" in nodes_src
    ), "the create else-branch no longer sanitizes str(e)"
    # Guard against re-inlining the raw bulk-return leak shape: post-fix the ONLY
    # remaining ``"error": str(e),`` render is the out-of-scope DDLFailedError
    # propagation log (its exception text is sanitized at source by #1550).
    assert nodes_src.count('"error": str(e),') <= 1, (
        'a raw `"error": str(e),` render re-appeared at a DML handler — '
        "#1552 leak re-inlined (only the DDLFailedError-propagation site is "
        "allowed this raw shape)"
    )
    # And the ONLY remaining ``extra={"error": str(e)}`` is the out-of-scope
    # TDD-connection-parse log (not a driver constraint error).
    assert nodes_src.count('extra={"error": str(e)}') <= 1, (
        'a raw `extra={"error": str(e)}` render re-appeared at a DML handler — '
        "#1552 leak re-inlined (only the TDD-connection log is allowed this shape)"
    )


# --------------------------------------------------------------------------
# Part D — consumer-safety (redaction does NOT break conflict-target classification)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_conflict_target_classification_survives_sanitization():
    """``is_conflict_target_error`` is called on the RAW exception
    (``nodes.py`` ~L3649, ``_is_conflict_target_error(str(exec_err))``), NOT on
    the returned/logged dict. Its match text is NOT redacted by
    ``sanitize_db_error`` — so sanitizing the returned/logged error does NOT
    break conflict-target classification.
    """
    from dataflow.core.exceptions import (
        is_conflict_target_error,
        sanitize_db_error,
    )

    # The two canonical conflict-target driver messages (PostgreSQL + SQLite).
    pg_msg = (
        "there is no unique or exclusion constraint matching the ON CONFLICT "
        "specification"
    )
    sqlite_msg = (
        "ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint"
    )
    for msg in (pg_msg, sqlite_msg):
        assert is_conflict_target_error(msg) is True, msg
        # Classification must survive redaction (idempotent — no value payload).
        assert is_conflict_target_error(sanitize_db_error(msg)) is True, (
            "sanitize_db_error broke conflict-target classification: "
            f"{sanitize_db_error(msg)!r}"
        )

    # A conflict-target error that ALSO carries a value-bearing DETAIL: the
    # DETAIL value is redacted, but the classifier text still matches.
    combined = f"{pg_msg}\nDETAIL:  Key (email)=({SECRET_VALUE}) already exists."
    sanitized = sanitize_db_error(combined)
    assert SECRET_VALUE not in sanitized
    assert "[REDACTED]" in sanitized
    assert is_conflict_target_error(sanitized) is True


# --------------------------------------------------------------------------
# Part E — FIX 2: newline-truncation bypass (multi-line constraint value)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_sanitize_db_error_redacts_multiline_value():
    """FIX 2: a ``Key (col)=(value)`` value spanning a NEWLINE (a unique/PK TEXT
    column — notes/address/bio) MUST be redacted IN FULL. Pre-fix, ``_DETAIL_RE``
    (``[^\\n]*``) ran first and truncated at the newline, leaking the post-newline
    remainder. Post-fix ``_KEY_VALUES_RE`` (``[^)]*`` spans newlines) runs first."""
    from dataflow.core.exceptions import sanitize_db_error

    out = sanitize_db_error(_MULTILINE_VALUE_BEARING_ERROR)
    assert _MULTILINE_SECRET_L1 not in out, "first line of multi-line value leaked"
    assert (
        _MULTILINE_SECRET_L2 not in out
    ), "post-newline remainder of multi-line value leaked (FIX 2 regression)"
    assert "[REDACTED]" in out

    # The single-line PG shape and MySQL shape remain correct after the reorder.
    single = sanitize_db_error(_VALUE_BEARING_ERROR)
    assert SECRET_VALUE not in single and "[REDACTED]" in single
    mysql = sanitize_db_error(_MYSQL_VALUE_BEARING_ERROR)
    assert SECRET_VALUE not in mysql and "[REDACTED]" in mysql


@pytest.mark.regression
def test_sanitize_db_error_redacts_embedded_paren_multiline_value():
    """FIX 7 (MED-1): a ``Key (col)=(value)`` value that contains an embedded
    ``)`` AND a newline. ``_KEY_VALUES_RE``'s ``[^)]*`` stops at the embedded
    ``)``; the old single-line ``DETAIL:[^\\n]*`` then collapsed only to the
    newline, leaking the post-newline tail. The block ``_DETAIL_RE`` redacts the
    whole DETAIL clause."""
    from dataflow.core.exceptions import sanitize_db_error

    tail = "TAILSECRET-DO-NOT-LEAK-c3"
    raw = (
        'insert or update violates constraint "c"\n'
        f"DETAIL: Key (bio)=({SECRET_VALUE}) leaked\n{tail}) already exists."
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "embedded-paren value head leaked"
    assert tail not in out, "post-newline tail leaked (FIX 7 MED-1 regression)"
    assert "[REDACTED]" in out


@pytest.mark.regression
def test_sanitize_db_error_redacts_failing_row_contains_multiline():
    """FIX 7 (MED-2): PG ``DETAIL: Failing row contains (…)`` (CHECK / NOT-NULL /
    exclusion violations dump the WHOLE row) spanning a newline. This shape has NO
    ``Key (col)=(value)`` clause, so ``_KEY_VALUES_RE`` never matches it; the old
    single-line ``DETAIL:`` missed the continuation. The block ``_DETAIL_RE``
    redacts the entire row dump. This shape IS reachable — Part A proves a PG
    DETAIL reaches ``str(e)`` on DataFlow's path."""
    from dataflow.core.exceptions import sanitize_db_error

    row_tail = "ROWSECRET-DO-NOT-LEAK-d4"
    raw = (
        'null value in column "x" violates not-null constraint\n'
        f"DETAIL: Failing row contains (1, {SECRET_VALUE}, multi\n{row_tail}).\n"
        "HINT: provide a value."
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "Failing-row value leaked"
    assert row_tail not in out, "Failing-row post-newline tail leaked (FIX 7 MED-2)"
    assert "[REDACTED]" in out
    # The trailing structured HINT: field is preserved (block stops before it).
    assert (
        "HINT: provide a value." in out
    ), "block redaction over-consumed the HINT field"


# --------------------------------------------------------------------------
# Part F — FIX 1 (HIGH): single-record update/delete/upsert trust-audit leak
# --------------------------------------------------------------------------
#
# express._trust_record_failure passes the driver error to
# record_query_failure, which persists it verbatim as result=f"failure:{error}"
# into the audit store (a broader-access surface than the DB). The
# create/update/delete/upsert failure paths all funnel through this ONE point.


class _CaptureTrustExecutor:
    """Deterministic fault-injection sink: captures the ``error`` kwarg that
    _trust_record_failure forwards to record_query_failure (the value persisted
    into the audit store). NOT a DB mock — it is the audit-boundary capture."""

    def __init__(self):
        self.captured_error = None

    async def record_query_failure(self, **kwargs):
        self.captured_error = kwargs.get("error")


@pytest.mark.regression
@pytest.mark.parametrize(
    "raw_error",
    [_VALUE_BEARING_ERROR, _MYSQL_VALUE_BEARING_ERROR, _MULTILINE_VALUE_BEARING_ERROR],
)
async def test_trust_record_failure_sanitizes_persisted_error(sqlite_db, raw_error):
    """FIX 1: the value forwarded to record_query_failure (persisted verbatim in
    the audit store as ``failure:{error}``) MUST be redacted — for the PG,
    MySQL, and multi-line driver-error shapes."""
    db = sqlite_db
    capture = _CaptureTrustExecutor()
    db._trust_executor = capture
    assert db.express._trust_enabled() is True

    await db.express._trust_record_failure(
        "Acct", "update", None, RuntimeError(raw_error), query_params={"id": "x"}
    )

    persisted = capture.captured_error or ""
    assert SECRET_VALUE not in persisted
    assert _MULTILINE_SECRET_L2 not in persisted
    assert (
        "[REDACTED]" in persisted
    ), "the persisted trust-audit error was not redacted (FIX 1 not load-bearing)"


@pytest.mark.regression
def test_trust_record_failure_wiring_is_sanitized_and_shared():
    """Structural: express._trust_record_failure sanitizes at the ONE audit point,
    and every single-record mutation (create/update/delete/upsert) routes its
    driver exception through it — so the single-point fix covers all four."""
    express_src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "features"
        / "express.py"
    ).read_text()
    assert (
        "error=sanitize_db_error(str(error))" in express_src
    ), "the trust-audit failure point no longer sanitizes the driver error"
    # All four single-record mutations funnel through _trust_record_failure.
    assert (
        express_src.count("await self._trust_record_failure(") >= 4
    ), "create/update/delete/upsert must all route through _trust_record_failure"


# --------------------------------------------------------------------------
# Part G — FIX 3: feature write-paths render raw driver errors (same class)
# --------------------------------------------------------------------------


@pytest.mark.regression
async def test_derived_refresh_sanitizes_returned_error_and_status_and_log(
    sqlite_db, monkeypatch, caplog
):
    """FIX 3: DerivedModelEngine.refresh runs SQL against source/derived models;
    a value-bearing driver failure MUST be redacted in the returned
    RefreshResult.error, the persisted meta.last_error (read by
    db.derived_model_status()), AND the ERROR log."""
    from dataflow.features.derived import DerivedModelEngine, DerivedModelMeta

    db = sqlite_db
    engine = DerivedModelEngine(db)
    meta = DerivedModelMeta(
        model_name="Summary",
        sources=["Acct"],
        refresh="manual",
        schedule=None,
        compute_fn=lambda sources: [],
    )
    engine.register(meta)

    async def _boom(*a, **k):
        raise RuntimeError(_VALUE_BEARING_ERROR)

    # refresh() queries sources first via db.express.list — inject there.
    monkeypatch.setattr(db.express, "list", _boom)

    with caplog.at_level(logging.ERROR, logger="dataflow.features.derived"):
        result = await engine.refresh("Summary")

    blob = _rendered(caplog.records)
    for surface, label in (
        (result.error or "", "returned RefreshResult.error"),
        (meta.last_error or "", "persisted meta.last_error"),
        (blob, "ERROR log"),
    ):
        assert SECRET_VALUE not in surface, f"derived refresh leaked value into {label}"
    assert "[REDACTED]" in (
        result.error or ""
    ), "derived RefreshResult.error not redacted"
    assert "[REDACTED]" in (
        meta.last_error or ""
    ), "derived meta.last_error not redacted"
    assert "[REDACTED]" in blob, "derived ERROR log not redacted"


@pytest.mark.regression
async def test_retention_run_sanitizes_returned_error_and_log(
    sqlite_db, monkeypatch, caplog
):
    """FIX 3: RetentionEngine.run runs DELETE/UPDATE SQL; a value-bearing driver
    failure MUST be redacted in the returned RetentionResult.error AND the log."""
    from dataflow.features.retention import RetentionEngine, RetentionPolicy

    db = sqlite_db
    engine = RetentionEngine(db)
    engine.register(
        RetentionPolicy(
            model_name="Acct", table_name="accts", policy="delete", after_days=30
        )
    )

    async def _boom(*a, **k):
        raise RuntimeError(_VALUE_BEARING_ERROR)

    monkeypatch.setattr(engine, "_execute_policy", _boom)

    with caplog.at_level(logging.ERROR, logger="dataflow.features.retention"):
        results = await engine.run()

    result = results["Acct"]
    blob = _rendered(caplog.records)
    assert SECRET_VALUE not in (
        result.error or ""
    ), "retention leaked value into result"
    assert SECRET_VALUE not in blob, "retention leaked value into ERROR log"
    assert "[REDACTED]" in (
        result.error or ""
    ), "retention RetentionResult.error not redacted"
    assert "[REDACTED]" in blob, "retention ERROR log not redacted"


@pytest.mark.regression
def test_transactions_rollback_log_sanitizes():
    """FIX 3: the transaction-rollback ERROR log routes the (possibly
    value-bearing) driver error through sanitize_db_error before logging; the
    re-raise below it preserves the caller's raw exception. Structural — the
    rollback path requires a live pool/connection failure to drive behaviorally."""
    txn_src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "features"
        / "transactions.py"
    ).read_text()
    assert (
        "sanitize_db_error(str(e))" in txn_src
    ), "transactions.py rollback log no longer sanitizes the driver error"
    assert (
        'extra={"error": str(e)}' not in txn_src
    ), "transactions.py re-inlined a raw error render in the rollback log"


# --------------------------------------------------------------------------
# Part H — FIX 4 + FIX 8 (defense-in-depth): dead DML-capable adapter methods
# --------------------------------------------------------------------------
#
# adapters/{mysql,postgresql,sqlite}.py execute_insert / execute_bulk_insert
# (FIX 4) and execute_query / execute_transaction (FIX 8) render the raw driver
# error into a log + a raised *Error. They have ZERO callers on the DataFlow hot
# path today (which uses AsyncSQLDatabaseNode), so a behavioral test is not
# meaningful; this structural guard ensures the render stays sanitized so a future
# wiring cannot reintroduce the leak. create_table/drop_table/get_table_schema are
# intentionally left raw (DDL/introspection — no row VALUES; #1550 owns DDL).


@pytest.mark.regression
@pytest.mark.parametrize("adapter", ["mysql", "postgresql", "sqlite"])
def test_adapter_dml_methods_sanitize(adapter):
    """Each adapter's DML-capable renders (execute_insert + execute_bulk_insert +
    execute_query + execute_transaction) redact the driver error at the render
    (log extra where present + the raised *Error message)."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "adapters"
        / f"{adapter}.py"
    ).read_text()
    # Robust to import formatting (single-line vs parenthesized multi-line).
    assert (
        "core.exceptions import" in src and "sanitize_db_error" in src
    ), f"{adapter}.py must import the shared redactor"
    # FIX 4 (execute_insert + execute_bulk_insert) + FIX 8 (execute_query +
    # execute_transaction) each compute a sanitized value at the source. sqlite's
    # execute_query is raise-only (no log line), so it inlines sanitize in the
    # raise rather than a `safe_error =` assignment — count the union of forms.
    sanitize_calls = src.count("sanitize_db_error(str(e))")
    assert (
        sanitize_calls >= 4
    ), f"{adapter}.py must sanitize all 4 DML-capable renders (got {sanitize_calls})"
    # The raised INSERT QueryError messages use the sanitized value, not raw {e}.
    assert (
        'raise QueryError(f"Insert failed: {safe_error}")' in src
    ), f"{adapter}.py execute_insert raises a raw QueryError message"
    assert (
        'raise QueryError(f"Bulk insert failed: {safe_error}")' in src
    ), f"{adapter}.py execute_bulk_insert raises a raw QueryError message"
    # FIX 8: execute_query + execute_transaction no longer raise a raw {e}.
    assert (
        'raise QueryError(f"Query execution failed: {e}")' not in src
    ), f"{adapter}.py execute_query re-inlined a raw QueryError message (FIX 8)"
    assert (
        'raise TransactionError(f"Transaction failed: {e}")' not in src
    ), f"{adapter}.py execute_transaction re-inlined a raw TransactionError (FIX 8)"


# --------------------------------------------------------------------------
# Part I — FIX 5 (HIGH): express.import_file returned-`errors`-list leak
# --------------------------------------------------------------------------
#
# import_file is a public API returning {"imported": int, "errors": [...]}. It
# calls self.upsert(...) per record (or self.bulk_create) and RENDERS the raw
# re-raised driver error into the RETURNED errors list — the #1552 returned-error
# surface on a live public path. SQLite constraint errors carry no value, which
# is why no earlier test caught it; a crafted value-bearing driver error injected
# at the upsert/bulk_create seam proves the sanitize is load-bearing on the
# returned surface.


def _write_csv(dir_path: str) -> str:
    import os

    fp = os.path.join(dir_path, "import.csv")
    with open(fp, "w") as fh:
        fh.write("id,email,name\nr1,a@x.com,Alice\n")
    return fp


@pytest.mark.regression
@pytest.mark.parametrize(
    "upsert,seam,raw_error",
    [
        (True, "upsert", _VALUE_BEARING_ERROR),
        (True, "upsert", _MYSQL_VALUE_BEARING_ERROR),
        (False, "bulk_create", _VALUE_BEARING_ERROR),
    ],
)
async def test_import_file_sanitizes_returned_errors(
    sqlite_db, monkeypatch, upsert, seam, raw_error
):
    """FIX 5: a value-bearing driver error raised at the per-record upsert seam
    (or the bulk_create seam) MUST be redacted in the RETURNED ``errors`` list —
    for the PG DETAIL shape AND the MySQL shape."""
    import tempfile

    db = sqlite_db

    async def _boom(*a, **k):
        raise RuntimeError(raw_error)

    # Inject at import_file's own seam: it calls self.upsert / self.bulk_create.
    monkeypatch.setattr(db.express, seam, _boom)

    with tempfile.TemporaryDirectory() as tmp:
        fp = _write_csv(tmp)
        result = await db.express.import_file("Acct", fp, upsert=upsert)

    errors = result.get("errors") or []
    assert result.get("imported") == 0, result
    assert errors, "import_file reported no errors despite the injected failure"
    blob = "\n".join(errors)
    assert SECRET_VALUE not in blob, (
        "issue #1552 (FIX 5): the raw driver VALUE leaked into import_file's "
        "returned errors list"
    )
    assert (
        "[REDACTED]" in blob
    ), "import_file returned-errors not redacted — sanitize is not load-bearing"


@pytest.mark.regression
def test_import_file_error_renders_are_sanitized_structural():
    """Structural guard: both import_file error renders route through
    ``sanitize_db_error`` — a raw ``f"...: {exc}"`` render at either site is the
    exact FIX-5 leak shape."""
    express_src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "features"
        / "express.py"
    ).read_text()
    assert (
        'f"Upsert failed for record: {sanitize_db_error(str(exc))}"' in express_src
    ), "import_file upsert-branch error render no longer sanitizes"
    assert (
        'f"Bulk create failed: {sanitize_db_error(str(exc))}"' in express_src
    ), "import_file bulk_create-branch error render no longer sanitizes"
    # The raw shapes must be gone.
    assert 'f"Upsert failed for record: {exc}"' not in express_src
    assert 'f"Bulk create failed: {exc}"' not in express_src


# --------------------------------------------------------------------------
# Part J — FIX 9: transaction node wrappers bake the raw driver error into a
# user-facing NodeExecutionError message + ERROR log
# --------------------------------------------------------------------------
#
# Round-3 red team found the DML leak class also reaches the transaction NODE
# layer: TransactionCommitNode (registered + reachable via a workflow) commits
# the active transaction, and a COMMIT of DEFERRED constraints raises a
# value-bearing driver error. Both the per-op ERROR log (extra={"error": str(e)})
# AND the raised ``NodeExecutionError(f"... {e}")`` message rendered that value
# verbatim. The raw exception is preserved as ``__cause__`` (``from e``); only the
# message string + the log field are sanitized.


class _FailingCommitTxn:
    """A fake transaction whose ``commit()`` raises a value-bearing PG driver
    error — the deferred-constraint-at-COMMIT failure mode."""

    async def commit(self):
        raise RuntimeError(_VALUE_BEARING_ERROR)


@pytest.mark.regression
async def test_transaction_commit_node_sanitizes_message_and_log(caplog):
    """A value-bearing COMMIT failure MUST NOT leak the column value into the
    raised ``NodeExecutionError`` message OR the ERROR log; the raw error
    survives only as ``__cause__``."""
    from kailash.sdk_exceptions import NodeExecutionError

    from dataflow.nodes.transaction_nodes import TransactionCommitNode

    node = TransactionCommitNode()
    node.set_workflow_context("active_transaction", _FailingCommitTxn())
    node.set_workflow_context("transaction_context_manager", None)
    node.set_workflow_context("transaction_id", "txn-probe")

    with caplog.at_level(logging.ERROR, logger="dataflow.nodes.transaction_nodes"):
        with pytest.raises(NodeExecutionError) as exc_info:
            await node.async_run()

    message = str(exc_info.value)
    assert SECRET_VALUE not in message, (
        "issue #1552: the raw duplicate value leaked into the "
        "NodeExecutionError message on the transaction-commit node path"
    )
    assert "[REDACTED]" in message
    # Raw error preserved for traceback-only diagnosability (not user-facing).
    assert exc_info.value.__cause__ is not None
    assert SECRET_VALUE in str(exc_info.value.__cause__)
    # The ERROR log MUST NOT carry the value either.
    blob = _rendered(caplog.records)
    assert (
        SECRET_VALUE not in blob
    ), "issue #1552: transaction-commit ERROR log leaked the duplicate value"
    assert "[REDACTED]" in blob


@pytest.mark.regression
def test_no_transaction_node_render_leaks_raw_driver_error():
    """Structural invariant: every raw-exception render in transaction_nodes.py
    (the ERROR-log ``extra={"error": str(e)}`` sites AND the
    ``NodeExecutionError(f"... {e}")`` raises) routes through
    ``sanitize_db_error``. A future re-inline of a raw ``str(e)`` / ``{e}`` render
    fails this test loudly (``refactor-invariants.md``)."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / "transaction_nodes.py"
    ).read_text()
    # All 8 driver-error renders (3 ERROR logs + 5 NodeExecutionError messages)
    # sanitize; none render a raw value.
    assert src.count("sanitize_db_error(str(e))") == 8, (
        "expected all 8 transaction_nodes driver-error renders to sanitize; "
        "a raw render was re-inlined"
    )
    assert '"error": str(e)}' not in src, "raw ERROR-log render re-inlined"
    assert 'NodeExecutionError(f"Failed to begin transaction: {e}")' not in src
    assert 'NodeExecutionError(f"Failed to commit transaction: {e}")' not in src
    assert 'NodeExecutionError(f"Failed to rollback transaction: {e}")' not in src
    assert 'NodeExecutionError(f"Failed to create savepoint: {e}")' not in src
    assert 'NodeExecutionError(f"Failed to rollback to savepoint: {e}")' not in src


# --------------------------------------------------------------------------
# Part J — FIX 11 (HIGH): BulkCreatePoolNode leaks raw driver VALUE
# --------------------------------------------------------------------------
#
# BulkCreatePoolNode is @register_node() (reachable via
# workflow.add_node("BulkCreatePoolNode", ...)) and runs REAL batch INSERTs via
# AsyncSQLDatabaseNode. A duplicate-value INSERT raises a driver error carrying
# DETAIL: Key(col)=(value). Three raw render sites (raised NodeExecutionError +
# two returned-`errors`-list appends) are the exact #1552 class.


@pytest.mark.regression
@pytest.mark.parametrize(
    "raw_error", [_VALUE_BEARING_ERROR, _MYSQL_VALUE_BEARING_ERROR]
)
async def test_bulk_create_pool_node_sanitizes_returned_errors(monkeypatch, raw_error):
    """FIX 11: a value-bearing driver error raised at the batch-INSERT seam
    (AsyncSQLDatabaseNode.async_run) MUST be redacted in the RETURNED
    ``errors`` list — for the PG DETAIL shape AND the MySQL shape."""
    import tempfile

    from dataflow.nodes.bulk_create_pool import BulkCreatePoolNode
    from kailash.nodes.data import async_sql as _asql

    async def _boom(self, *a, **k):
        raise RuntimeError(raw_error)

    monkeypatch.setattr(_asql.AsyncSQLDatabaseNode, "async_run", _boom)

    with tempfile.TemporaryDirectory() as tmp:
        node = BulkCreatePoolNode(
            table_name="accts",
            database_type="sqlite",
            connection_string=f"sqlite:///{tmp}/t.db",
            conflict_resolution="error",
        )
        result = await node.async_run(
            data=[{"id": "1", "email": SECRET_VALUE, "name": "A"}]
        )

    errors = result.get("errors") or []
    assert errors, "BulkCreatePoolNode reported no errors despite the injected failure"
    blob = "\n".join(str(e) for e in errors)
    assert SECRET_VALUE not in blob, (
        "issue #1552 (FIX 11): the raw driver VALUE leaked into "
        "BulkCreatePoolNode's returned errors list"
    )
    assert (
        "[REDACTED]" in blob
    ), "BulkCreatePoolNode returned-errors not redacted — sanitize not load-bearing"


@pytest.mark.regression
def test_bulk_create_pool_node_renders_are_sanitized_structural():
    """Structural: all 3 BulkCreatePoolNode driver-error renders (the raised
    NodeExecutionError + the two returned-``errors`` appends) route through
    ``sanitize_db_error``; no raw ``str(e)`` render remains."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / "bulk_create_pool.py"
    ).read_text()
    assert (
        "core.exceptions import" in src and "sanitize_db_error" in src
    ), "bulk_create_pool.py must import the shared redactor"
    assert src.count("sanitize_db_error(str(e))") >= 3, (
        "expected all 3 BulkCreatePoolNode renders to sanitize; a raw render "
        "was re-inlined (#1552 FIX 11)"
    )
    # The exact pre-fix raw leak shapes must be gone.
    assert 'NodeExecutionError(f"Bulk create operation failed: {str(e)}")' not in src
    assert "f\"Batch {results['batches']} error: {str(e)}\"" not in src
    assert "errors.append(str(e))" not in src
    # The raise preserves the raw exception as __cause__ (from e).
    assert (
        ") from e" in src
    ), "the sanitized NodeExecutionError raise must keep `from e`"


# --------------------------------------------------------------------------
# Part K — FIX 12 + FIX-6-sweep: coordinator + standalone bulk-upsert nodes
# --------------------------------------------------------------------------
#
# The transaction-coordinator wrapper nodes render str(e) of delegated
# participant/DB-operation errors (a constraint-violating participant op can
# propagate a raw asyncpg error) into returned dicts — defense-in-depth parity
# with core/nodes.py. The standalone DataFlowBulkUpsertNode (FIX-6 sweep) runs
# real upserts; two of its renders were raw.


@pytest.mark.regression
@pytest.mark.parametrize(
    "module,expected_count",
    [
        ("transaction_manager", 9),
        ("two_phase_commit_coordinator", 5),
        ("saga_coordinator", 4),
    ],
)
def test_coordinator_nodes_sanitize_participant_errors(module, expected_count):
    """FIX 12: every coordinator render of a delegated participant/DB-operation
    error routes through ``sanitize_db_error``; no raw ``str(e)`` render remains."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / f"{module}.py"
    ).read_text()
    assert (
        "core.exceptions import" in src and "sanitize_db_error" in src
    ), f"{module}.py must import the shared redactor"
    assert src.count("sanitize_db_error(str(e))") == expected_count, (
        f"{module}.py: expected {expected_count} sanitized renders "
        f"(got {src.count('sanitize_db_error(str(e))')}) — a raw render remains"
    )
    # No raw `str(e)` render survives (every str(e) is wrapped).
    import re

    raw_unwrapped = re.findall(r"(?<!error\()str\(e\)", src)
    assert not raw_unwrapped, f"{module}.py has {len(raw_unwrapped)} raw str(e) renders"


@pytest.mark.regression
def test_bulk_upsert_node_renders_are_sanitized_structural():
    """FIX-6 sweep: the standalone DataFlowBulkUpsertNode's returned-dict error
    and raised NodeExecutionError both sanitize (it already sanitized its
    batch-error path; the outer/execute renders were raw)."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / "bulk_upsert.py"
    ).read_text()
    assert 'return {"success": False, "error": str(e), "rows_affected": 0}' not in src
    assert 'NodeExecutionError(f"Database upsert error: {str(e)}")' not in src
    assert "_sanitize_db_error(str(e))" in src


# --------------------------------------------------------------------------
# Part L — FIX 13: 2PC concurrent prepare/commit path renders the raw gather
# exception via ``str(result)`` (NOT ``str(e)``) into the returned dict
# --------------------------------------------------------------------------
#
# ``asyncio.gather(..., return_exceptions=True)`` surfaces a participant-prepare
# DRIVER error as an element of ``results``; the concurrent branch rendered it
# raw (``str(result)``) while the sequential sibling already sanitized. The
# ``str(e)`` sweeps could not see ``str(result)`` — this closes the last shape.


@pytest.mark.regression
async def test_two_phase_commit_concurrent_prepare_sanitizes_gather_error(
    monkeypatch,
):
    """The concurrent (``synchronous_prepare=False``) prepare path drives the
    real ``_prepare_phase`` gather branch; a value-bearing participant-prepare
    driver error MUST NOT reach the returned ``failed_participants`` /
    ``failure_reasons`` raw."""
    from dataflow.nodes.two_phase_commit_coordinator import (
        DataFlowTwoPhaseCommitNode,
    )

    # The node's __init__ reads ``self.node_id`` (injected by the runtime at
    # add_node time); provide a class-attr fallback so a direct unit construction
    # of the node under test succeeds.
    monkeypatch.setattr(
        DataFlowTwoPhaseCommitNode, "node_id", "tpc_test", raising=False
    )
    node = DataFlowTwoPhaseCommitNode()

    async def _raise_value_bearing(participant, transaction_state, latencies):
        raise RuntimeError(_VALUE_BEARING_ERROR)

    # Patch the per-participant async prepare to raise a value-bearing driver
    # error — it propagates uncaught into asyncio.gather(return_exceptions=True),
    # exactly the reachable failure mode.
    monkeypatch.setattr(node, "_prepare_participant_async", _raise_value_bearing)

    transaction_state = {
        "participants": [{"id": "p1", "name": "acct-writer"}],
        "failed_participants": [],
        "prepared_participants": [],
        "data": {},
    }
    failure_reasons: list = []

    prepared_ok = await node._prepare_phase(
        transaction_state,
        synchronous=False,
        latencies={},
        failure_reasons=failure_reasons,
    )

    assert prepared_ok is False
    blob = str(transaction_state["failed_participants"]) + " ".join(failure_reasons)
    assert SECRET_VALUE not in blob, (
        "issue #1552: the concurrent 2PC prepare gather path leaked the driver "
        "value into the returned failed_participants / failure_reasons"
    )
    assert "[REDACTED]" in blob


@pytest.mark.regression
def test_no_two_phase_commit_gather_render_leaks_raw_driver_error():
    """Structural invariant: every ``str(result)`` render from the 2PC
    ``asyncio.gather`` branches (prepare + commit) routes through
    ``sanitize_db_error``. A raw ``str(result)`` in a returned-dict / reason
    render is the FIX-13 leak shape."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / "two_phase_commit_coordinator.py"
    ).read_text()
    assert src.count("sanitize_db_error(str(result))") == 4, (
        "expected all 4 gather-exception renders (2 prepare + 2 commit) to "
        "sanitize; a raw str(result) render was re-inlined"
    )
    assert '"error": str(result)}' not in src
    assert "error: {str(result)}" not in src
