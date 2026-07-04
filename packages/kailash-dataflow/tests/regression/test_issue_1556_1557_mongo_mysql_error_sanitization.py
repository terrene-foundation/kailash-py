"""Regression: issues #1556 + #1557 — extend the #1552 driver-error VALUE-leak
class through ``sanitize_db_error``.

#1557 (MySQL): ``_MYSQL_DUP_ENTRY_RE`` used a LAZY ``.*?`` anchored on the FIRST
``' for key`` occurrence, so a value that literally CONTAINS the substring
``' for key`` leaked its tail. The fix greedily anchors on the FINAL
``' for key '<name>'`` structured suffix while preserving the key NAME.

#1556 (MongoDB): ``nodes/mongodb_nodes.py`` rendered raw ``str(e)`` of pymongo
errors. A MongoDB E11000 duplicate-key error carries the offending value in a
``dup key: { field: "value" }`` payload none of the SQL redaction shapes target,
so the value survived. The fix adds ``_MONGO_DUP_KEY_RE`` and routes all 8
MongoDB node error handlers through ``sanitize_db_error``.

Parts:
  A — #1557 MySQL regex unit tests (adversarial ``' for key`` edge, keyname
      preservation, errno-1061 tolerance, keyname-less fallback).
  B — #1556 Mongo redactor unit tests (canonical E11000, pymongo full-error
      suffix, compound index).
  C — #1556 injected driver-error through a REAL DocumentInsertNode handler
      (honest substitute; a real MongoDB container is not available in this
      Tier-1 env — the injected E11000 STRING proves the handler redacts the
      Mongo shape end-to-end, on BOTH the returned-error AND the ERROR-log
      surface, mirroring #1552 Part B's MySQL injected-string contract).
  D — #1556 structural invariant (no raw ``str(e)`` render remains — guards a
      future re-inline regression, per ``refactor-invariants.md``).
  E — #1556 Tier-2 real MongoDB (skipped cleanly when no container is present).
"""

import logging
from pathlib import Path

import pytest

from dataflow.core.exceptions import sanitize_db_error

# Distinctive so its ABSENCE from any log / returned-error surface is
# unambiguous. Shaped like an email so it reads as a real leaked value.
SECRET_VALUE = "leak-secret-DO-NOT-LEAK-7f3a9c@corp.example"

_MONGO_LOGGER = "dataflow.nodes.mongodb_nodes"

# A MongoDB E11000 duplicate-key error in the exact shape pymongo renders via
# ``str(e)`` on the insert/bulk-insert/update paths. The offending value lives in
# the ``dup key: { field: "value" }`` payload.
_MONGO_E11000_ERROR = (
    "E11000 duplicate key error collection: appdb.users index: email_1 "
    f'dup key: {{ email: "{SECRET_VALUE}" }}'
)


# --------------------------------------------------------------------------
# Part A — #1557: MySQL ``Duplicate entry '...' for key '...'`` regex edge
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_mysql_dup_entry_adversarial_for_key_substring_redacts_tail():
    """#1557 core: a value that literally CONTAINS the substring ``' for key``
    MUST be redacted IN FULL. Pre-fix, the lazy ``.*?`` anchored on the FIRST
    ``' for key`` and leaked the tail after it."""
    injected_tail = "INJECTED-TAIL-DO-NOT-LEAK-9c2f"
    raw = (
        f"(1062, \"Duplicate entry '{SECRET_VALUE}' for key '{injected_tail}' "
        "for key 'accts.email_uniq'\")"
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "value head leaked"
    assert (
        injected_tail not in out
    ), "post-``' for key`` tail leaked — #1557 lazy-anchor regression"
    assert "[REDACTED]" in out
    # The trailing key NAME is schema shape, preserved (matches PG ``Key (col)``).
    assert "accts.email_uniq" in out, "key name over-redacted (#1550 contract)"


@pytest.mark.regression
def test_mysql_dup_entry_preserves_keyname():
    """A benign single-value 1062 error redacts the value, keeps the key name."""
    raw = f"(1062, \"Duplicate entry '{SECRET_VALUE}' for key 'accts.email_uniq'\")"
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out and "[REDACTED]" in out
    assert "accts.email_uniq" in out


@pytest.mark.regression
def test_mysql_dup_key_name_1061_tolerance_preserved():
    """The benign errno-1061 ``Duplicate key name 'idx_email'`` shape lacks the
    ``Duplicate entry '`` prefix, so it MUST pass through untouched (the #1550
    keyname-tolerance contract the greedy fix must not break)."""
    raw = "Duplicate key name 'idx_email'"
    assert sanitize_db_error(raw) == raw


@pytest.mark.regression
def test_mysql_dup_entry_keyname_less_still_redacts():
    """A truncated ``Duplicate entry 'v' for key`` with no ``'<name>'`` suffix
    MUST still redact the value (optional keyname group)."""
    raw = f"Duplicate entry '{SECRET_VALUE}' for key"
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out and "[REDACTED]" in out


@pytest.mark.regression
def test_mysql_dup_entry_newline_in_value_redacts():
    """#1556 red-team: a column VALUE containing a literal newline MUST still be
    redacted. Without ``re.DOTALL`` the greedy ``.*`` pins to the first line, the
    ``' for key`` anchor sits on line 2, the match fails, and the tail leaks."""
    val = f"line1-{SECRET_VALUE}\nline2-POST-NEWLINE-DO-NOT-LEAK"
    raw = f"(1062, \"Duplicate entry '{val}' for key 'accts.email_uniq'\")"
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "value head leaked"
    assert "POST-NEWLINE-DO-NOT-LEAK" not in out, "post-newline tail leaked (DOTALL)"
    assert "[REDACTED]" in out and "accts.email_uniq" in out


# --------------------------------------------------------------------------
# Part B — #1556: MongoDB E11000 ``dup key: { field: "value" }`` redactor
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_mongo_e11000_redacts_dup_key_payload():
    """The E11000 ``dup key: { field: "value" }`` payload is redacted; the
    ``collection:`` and ``index:`` names before it are preserved."""
    out = sanitize_db_error(_MONGO_E11000_ERROR)
    assert SECRET_VALUE not in out, "Mongo dup-key value leaked (#1556)"
    assert "dup key: { [REDACTED] }" in out
    # Diagnostic shape preserved (collection + index names).
    assert "collection: appdb.users" in out
    assert "index: email_1" in out


@pytest.mark.regression
def test_mongo_e11000_full_error_suffix_redacts_all_occurrences():
    """pymongo can append ``, full error: {...}`` that echoes the value a second
    time inside ``errmsg``/``keyValue``. Greedy-to-final-``}`` folds the whole
    tail into the redaction so NO occurrence survives."""
    raw = (
        "E11000 duplicate key error collection: appdb.users index: email_1 "
        f'dup key: {{ email: "{SECRET_VALUE}" }}, full error: {{"index": 0, '
        f'"code": 11000, "errmsg": "... dup key: {{ email: {SECRET_VALUE} }}", '
        f'"keyValue": {{"email": "{SECRET_VALUE}"}}}}'
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "value leaked via the full-error suffix (#1556)"
    assert "[REDACTED]" in out


@pytest.mark.regression
def test_mongo_e11000_compound_index_redacts():
    """A compound-index dup key ``{ a: 1, b: "value" }`` is redacted in full."""
    raw = (
        "E11000 duplicate key error collection: appdb.orders index: a_1_b_1 "
        f'dup key: {{ a: 1, b: "{SECRET_VALUE}" }}'
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out and "dup key: { [REDACTED] }" in out


@pytest.mark.regression
def test_mongo_bulk_write_error_redacts_all_occurrences():
    """A real pymongo ``BulkWriteError`` (from ``insert_many``) nests the value in
    a ``writeErrors`` array: the ``errmsg`` ``dup key: {...}``, ``keyValue``, AND
    ``op`` all echo it. Greedy + DOTALL folds every occurrence after the first
    ``dup key: {`` into the redaction. (Shape captured from a real pymongo
    BulkWriteError against MongoDB 7.)"""
    raw = (
        "batch op errors occurred, full error: {'writeErrors': [{'index': 0, "
        "'code': 11000, 'errmsg': 'E11000 duplicate key error collection: "
        f'appdb.users index: email_1 dup key: {{ email: "{SECRET_VALUE}" }}\', '
        f"'keyPattern': {{'email': 1}}, 'keyValue': {{'email': '{SECRET_VALUE}'}}, "
        f"'op': {{'email': '{SECRET_VALUE}', '_id': 'x'}}}}], "
        "'writeConcernErrors': [], 'nInserted': 0}"
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "BulkWriteError leaked the value (writeErrors)"
    assert "[REDACTED]" in out


@pytest.mark.regression
def test_mongo_e11000_newline_in_value_redacts():
    """#1556 red-team: a real pymongo ``DuplicateKeyError`` renders an embedded
    newline in the value LITERALLY. Without ``re.DOTALL`` the greedy ``.*`` stops
    at the newline, the closing ``}`` sits on line 2, the match fails, and the
    value leaks. DOTALL folds the newline-spanning payload into the redaction."""
    raw = (
        "E11000 duplicate key error collection: appdb.users index: bio_1 "
        f'dup key: {{ bio: "line1-{SECRET_VALUE}\nline2-POST-NEWLINE-DO-NOT-LEAK" }}'
    )
    out = sanitize_db_error(raw)
    assert SECRET_VALUE not in out, "value head leaked"
    assert "POST-NEWLINE-DO-NOT-LEAK" not in out, "post-newline tail leaked (DOTALL)"
    assert "dup key: { [REDACTED] }" in out
    assert "collection: appdb.users" in out  # shape before dup key preserved


# --------------------------------------------------------------------------
# Part C — #1556: injected driver error through a real DocumentInsertNode
# --------------------------------------------------------------------------
#
# The value-bearing E11000 fires only on a genuine unique-index violation, which
# does not occur on every path/backend. The ONLY injection permitted (mirroring
# #1552 Part B's contract) is the driver error RAISED at the node's own adapter
# seam — the database is never mocked. ``_FailingMongoAdapter`` is a real
# ``MongoDBAdapter`` subclass with deterministic output (raises the E11000
# string): a Protocol-Satisfying Deterministic Adapter, NOT a mock
# (``testing.md`` § Tier-1 exception).


class _StubDataFlow:
    def __init__(self, adapter):
        self.adapter = adapter


@pytest.mark.regression
async def test_injected_mongo_insert_error_is_sanitized(caplog):
    """The ``DocumentInsertNode`` handler routes the value-bearing E11000 error
    through ``sanitize_db_error`` → ``[REDACTED]`` in BOTH the returned ``error``
    dict AND the ``mongodb_nodes.document_insert_failed`` ERROR log."""
    from dataflow.adapters.mongodb import MongoDBAdapter
    from dataflow.nodes.mongodb_nodes import DocumentInsertNode

    # A real MongoDBAdapter subclass with deterministic output (raises the E11000
    # driver string): passes the node's isinstance(MongoDBAdapter) gate without
    # opening a real connection. A Protocol-Satisfying Deterministic Adapter, NOT
    # a mock (``testing.md`` § Tier-1 exception).
    class _FailingMongoAdapter(MongoDBAdapter):
        def __init__(self):  # no real connection
            pass

        async def insert_one(self, collection, document, **options):
            raise RuntimeError(_MONGO_E11000_ERROR)

    node = DocumentInsertNode()
    node.dataflow_instance = _StubDataFlow(_FailingMongoAdapter())

    with caplog.at_level(logging.ERROR, logger=_MONGO_LOGGER):
        result = await node.async_run(
            collection="users", document={"email": SECRET_VALUE}
        )

    assert result.get("success") is False, result
    returned_error = result.get("error") or ""
    # Returned-error surface
    assert SECRET_VALUE not in returned_error, "returned error leaked the value"
    assert "[REDACTED]" in returned_error, (
        "DocumentInsertNode returned-error not redacted — sanitize is not "
        "load-bearing on the Mongo path (#1556)"
    )
    # Log surface
    rec = next(
        (
            r
            for r in caplog.records
            if r.getMessage() == "mongodb_nodes.document_insert_failed"
        ),
        None,
    )
    assert rec is not None, "mongodb_nodes.document_insert_failed was not logged"
    log_error = getattr(rec, "error", "")
    assert SECRET_VALUE not in log_error, "ERROR log leaked the value"
    assert "[REDACTED]" in log_error, "DocumentInsertNode ERROR log not redacted"


@pytest.mark.regression
@pytest.mark.parametrize(
    "node_cls, seam_methods, run_kwargs, log_event",
    [
        # update-with-upsert can raise E11000 on a unique-index collision.
        (
            "DocumentUpdateNode",
            ("update_one", "update_many"),
            {
                "collection": "users",
                "filter": {"email": SECRET_VALUE},
                "update": {"$set": {"email": SECRET_VALUE}},
            },
            "mongodb_nodes.document_update_failed",
        ),
        # bulk insert surfaces E11000 for a duplicate document.
        (
            "BulkDocumentInsertNode",
            ("insert_many",),
            {"collection": "users", "documents": [{"email": SECRET_VALUE}]},
            "mongodb_nodes.bulk_document_insert_failed",
        ),
    ],
)
async def test_injected_mongo_dupkey_capable_handlers_sanitize(
    caplog, node_cls, seam_methods, run_kwargs, log_event
):
    """The other two dup-key-capable MongoDB handlers — update-with-upsert and
    bulk-insert — MUST redact the E11000 value on BOTH the returned dict AND the
    ERROR log (behavioral coverage beyond the Part D structural guard)."""
    import dataflow.nodes.mongodb_nodes as mn
    from dataflow.adapters.mongodb import MongoDBAdapter

    async def _boom(self, *a, **k):
        raise RuntimeError(_MONGO_E11000_ERROR)

    class _FailingMongoAdapter(MongoDBAdapter):
        def __init__(self):  # no real connection
            pass

    for method in seam_methods:
        setattr(_FailingMongoAdapter, method, _boom)

    node = getattr(mn, node_cls)()
    node.dataflow_instance = _StubDataFlow(_FailingMongoAdapter())

    with caplog.at_level(logging.ERROR, logger=_MONGO_LOGGER):
        result = await node.async_run(**run_kwargs)

    returned_error = (result or {}).get("error") or ""
    assert SECRET_VALUE not in returned_error, f"{node_cls} returned error leaked value"
    assert "[REDACTED]" in returned_error, f"{node_cls} returned error not redacted"

    rec = next((r for r in caplog.records if r.getMessage() == log_event), None)
    assert rec is not None, f"{node_cls}: {log_event} was not logged"
    log_error = getattr(rec, "error", "")
    assert SECRET_VALUE not in log_error, f"{node_cls} ERROR log leaked value"
    assert "[REDACTED]" in log_error, f"{node_cls} ERROR log not redacted"


# --------------------------------------------------------------------------
# Part D — #1556: structural invariant (no raw ``str(e)`` render remains)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_no_mongodb_handler_renders_raw_error_text():
    """Every MongoDB node error handler routes its render through
    ``sanitize_db_error``. A raw ``"error": str(e)`` / ``extra={"error": str(e)}``
    render is the exact #1556 leak shape — assert none remain, so a future edit
    that re-inlines a raw render fails this test loudly."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "nodes"
        / "mongodb_nodes.py"
    ).read_text()

    # The 8 handlers each compute one sanitized value at the top of their except.
    assert src.count("sanitized = sanitize_db_error(str(e))") >= 8, (
        "a MongoDB handler stopped routing its driver error through "
        "sanitize_db_error — #1556 leak re-inlined"
    )
    # Each handler uses the sanitized value on BOTH surfaces (8 log + 8 return).
    assert (
        src.count('"error": sanitized') >= 16
    ), "a MongoDB handler's log/return no longer uses the sanitized value"
    # No raw ``str(e)`` render may remain at any handler surface.
    assert src.count('"error": str(e)') == 0, (
        'a raw `"error": str(e)` render re-appeared at a MongoDB handler — '
        "#1556 leak re-inlined"
    )


# --------------------------------------------------------------------------
# Part E — #1556: Tier-2 real MongoDB (skipped cleanly when unavailable)
# --------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.regression
async def test_mongo_dup_key_real_infra_redacted(caplog):
    """Tier-2: drive a real duplicate-key violation through a real MongoDB and
    assert the value is redacted on EVERY surface — the node's returned dict AND
    the ADAPTER's own ``mongodb.failed_to_insert_document_into`` ERROR log (the
    adapter renders ``str(e)`` at its DML seam BEFORE re-raising to the node;
    scanner-surface symmetry per ``zero-tolerance.md`` Rule 1a). Skipped when no
    MongoDB is reachable (Part C is the honest Tier-1 substitute)."""
    pymongo = pytest.importorskip("pymongo")
    pytest.importorskip(
        "motor"
    )  # DataFlow's MongoDBAdapter uses the async motor driver
    import os

    mongo_url = os.environ.get("MONGODB_TEST_URL", "mongodb://localhost:27017")
    try:
        client = pymongo.MongoClient(mongo_url, serverSelectionTimeoutMS=800)
        client.admin.command("ping")
    except Exception:
        pytest.skip(f"no reachable MongoDB at {mongo_url}")

    from dataflow.adapters.mongodb import MongoDBAdapter
    from dataflow.nodes.mongodb_nodes import DocumentInsertNode

    dbname = "dataflow_issue_1556"
    coll = "users_uniq_1556"
    # A newline-bearing value: a real pymongo DuplicateKeyError renders the LF
    # LITERALLY, so this drives the #1556 red-team DOTALL case through real infra.
    nl_value = f"{SECRET_VALUE}\nREAL-NEWLINE-TAIL-DO-NOT-LEAK"
    client[dbname][coll].drop()
    client[dbname][coll].create_index("email", unique=True)
    client[dbname][coll].insert_one({"email": nl_value})

    adapter = MongoDBAdapter(connection_string=mongo_url, database_name=dbname)
    await adapter.connect()
    node = DocumentInsertNode()
    node.dataflow_instance = _StubDataFlow(adapter)
    try:
        with caplog.at_level(logging.ERROR):
            result = await node.async_run(collection=coll, document={"email": nl_value})
    finally:
        await adapter.disconnect()
        client[dbname][coll].drop()

    # Node returned-error surface — both the value head AND the post-newline tail
    # MUST be gone.
    assert result.get("success") is False
    assert SECRET_VALUE not in (result.get("error") or "")
    assert "REAL-NEWLINE-TAIL-DO-NOT-LEAK" not in (result.get("error") or "")
    assert "[REDACTED]" in (result.get("error") or "")

    # Adapter ERROR-log surface (mongodb.py::insert_one renders str(e) BEFORE
    # re-raising — it MUST be redacted too).
    adapter_rec = next(
        (
            r
            for r in caplog.records
            if r.getMessage() == "mongodb.failed_to_insert_document_into"
        ),
        None,
    )
    assert adapter_rec is not None, "adapter insert-failure was not logged"
    adapter_err = getattr(adapter_rec, "error", "")
    assert SECRET_VALUE not in adapter_err, (
        "adapter ERROR log leaked the dup-key value — #1556 adapter-layer "
        "scanner-surface-symmetry regression (zero-tolerance Rule 1a)"
    )
    assert (
        "REAL-NEWLINE-TAIL-DO-NOT-LEAK" not in adapter_err
    ), "adapter ERROR log leaked the post-newline tail — DOTALL regression"
    assert "[REDACTED]" in adapter_err, "adapter ERROR log not redacted"

    # No captured record on EITHER logger may carry the raw value.
    assert not any(
        SECRET_VALUE in getattr(r, "error", "") for r in caplog.records
    ), "a captured log record leaked the dup-key value"


# --------------------------------------------------------------------------
# Part F — #1556: adapter-layer structural invariant (mongodb.py)
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_no_mongodb_adapter_renders_raw_error_text():
    """The ``mongodb.py`` ADAPTER renders ``str(e)`` at its DML seams (insert /
    insert_many / update / upsert / find_one_and_*) BEFORE re-raising to the
    node. Every such render MUST route through ``sanitize_db_error`` so the
    dup-key value cannot leak at the adapter log surface (the deeper instance of
    the #1556 leak). Assert no raw ``"error": str(e)`` render remains."""
    src = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "dataflow"
        / "adapters"
        / "mongodb.py"
    ).read_text()

    assert src.count('"error": str(e)') == 0, (
        'a raw `"error": str(e)` render re-appeared in the MongoDB adapter — '
        "#1556 adapter-layer leak re-inlined"
    )
    # Every error render routes through the redactor (defense-in-depth; the
    # redactor is a no-op on non-value connection/health errors).
    assert (
        src.count("sanitize_db_error(str(e))") >= 21
    ), "a MongoDB adapter error render stopped routing through sanitize_db_error"
