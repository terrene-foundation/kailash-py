"""Regression for issue #2210 — ``bulk_upsert`` lost the WHOLE batch at 1000 rows.

The report: ``db.express.bulk_upsert`` on SQLite returned
``{"success": False, "created": 0, "total": 0, "error": "... Expression tree is
too large (maximum depth 1000)"}`` and persisted ZERO rows for any batch of
>=1000 rows, with a cliff at exactly 999 ok / 1000 fail.

The report's stated root cause was *"the generated upsert SQL emits one
expression node per row"*. Re-derivation REFUTED that: the INSERT is fine. A
raw multi-row ``INSERT ... VALUES`` of 16383 two-column rows executes without
complaint on this SQLite (3.49.1), and neutralising the pre-count alone makes a
1000-row upsert succeed and persist all 1000 rows. The failing statement is the
ACCOUNTING pre-count in ``BulkOperations._count_existing_conflicts``, which
derives the inserted/updated split for SQLite (which has no ``xmax``) by
emitting one ``("id" = ?)`` clause per row joined by ``OR``. An ``OR`` chain
parses left-deep, so N clauses ARE a tree of depth N, and
``SQLITE_LIMIT_EXPR_DEPTH`` (1000) becomes a flat row ceiling — on a read whose
only job is to COUNT, gating a write that would have succeeded.

Re-derivation also found the relationship to be ADDITIVE in the conflict-target
width, not multiplicative: the measured ceiling is
``MAX_EXPRESSION_DEPTH - len(conflict_columns)``, confirmed at widths 1, 2, 3,
4, 5, 8, 10, 16 and 32 (999, 998, 997, 996, 995, 992, 990, 984, 968). The
report saw a flat ceiling because it varied DATA columns, which do not enter
this expression at all.

Two further same-class defects surfaced and are covered here:

* A SECOND capacity cliff on the WRITE path. A multi-row ``VALUES`` binds
  ``rows * columns`` parameters against ``SQLITE_LIMIT_VARIABLE_NUMBER``
  (32766 here), so a 41-column model at 900 rows — comfortably under the
  999-row expression ceiling — failed with "too many SQL variables" and again
  persisted zero rows. The report missed it by testing at most 30 columns
  (30 * 1000 = 30000, just under the budget).
* ``express.bulk_upsert``'s documented ``batch_size`` kwarg was INERT
  (zero-tolerance Rule 3c). It was assigned as an instance attribute while the
  node resolves the value from ``validate_inputs(**kwargs)``, so the bulk
  engine received the default 1000 for every call — measured at
  ``batch_size=100`` and ``batch_size=400`` alike. The caller's only documented
  escape hatch from the ceiling did nothing.

The fix binds both capacity limits to the DIALECT (``adapters/dialect.py``,
reusing the ``identifier_budget_for`` seam shape from #1971 rather than adding
a parallel one), chunks the pre-count to fit, and clamps the write batch to the
engine's parameter budget.

Tier 2: real SQLite on disk (via ``tmp_path``), no mocking. SQLite IS the
engine whose limits are under test, so substituting anything would remove the
subject of the test.
"""

import uuid
from pathlib import Path

import pytest

import dataflow
from dataflow import DataFlow
from dataflow.adapters.dialect import DialectManager, statement_capacity_for

# Import-path pin (relative to THIS checkout, never a hard-coded worktree path):
# tests/regression/<file> -> tests/ -> kailash-dataflow/ -> src/dataflow.
# An unpinned import silently resolves to an installed copy and produces a FALSE
# GREEN for a fix that is not actually under test.
_CHECKOUT_SRC = Path(__file__).resolve().parents[2] / "src"


def test_dataflow_is_imported_from_this_checkout():
    """Guard: every assertion below is meaningless against a stale install."""
    resolved = Path(dataflow.__file__).resolve()
    assert resolved.is_relative_to(_CHECKOUT_SRC), (
        f"dataflow resolved to {resolved}, not this checkout's {_CHECKOUT_SRC} — "
        f"the suite would be testing an installed copy, not the code under test"
    )


def _fresh_db(tmp_path) -> DataFlow:
    """A real on-disk SQLite DataFlow, isolated per test."""
    return DataFlow(f"sqlite:///{tmp_path}/df_{uuid.uuid4().hex}.db")


# ---------------------------------------------------------------------------
# Behaviour 1 — the reported cliff: >=1000 rows lost the whole batch
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("n_rows", [999, 1000, 1001, 2500])
async def test_bulk_upsert_persists_batches_at_and_above_the_expression_ceiling(
    tmp_path, n_rows
):
    """The reported defect. 999 was the last size that worked; 1000+ wrote zero.

    Asserts on PERSISTED ROWS, not on ``success`` — the reporter's complaint is
    precisely that a caller trusting the summary loses the batch.
    """
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    records = [{"id": f"w{i}", "name": f"n{i}"} for i in range(n_rows)]
    result = await db.express.bulk_upsert("Widget", records, conflict_on=["id"])

    assert (
        result.get("success", True) is not False
    ), f"bulk_upsert of {n_rows} rows reported failure: {result.get('error')!r}"
    assert await db.express.count("Widget") == n_rows
    assert result["created"] == n_rows
    assert result["total"] == n_rows


@pytest.mark.regression
@pytest.mark.asyncio
async def test_inserted_updated_split_is_exact_across_chunk_boundaries(tmp_path):
    """The pre-count is chunked now, so its SUM must equal the true count.

    A wrong split would be the silent way this fix could break: rows land, but
    the reported created/updated breakdown drifts. Uses 2500 rows so the count
    spans three windows, and a mixed third pass whose existing/new boundary
    does NOT align with a window boundary.
    """
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    first = await db.express.bulk_upsert(
        "Widget", [{"id": f"w{i}", "name": "v1"} for i in range(2500)]
    )
    assert (first["created"], first["updated"]) == (2500, 0)

    second = await db.express.bulk_upsert(
        "Widget", [{"id": f"w{i}", "name": "v2"} for i in range(2500)]
    )
    assert (second["created"], second["updated"]) == (0, 2500)
    assert await db.express.count("Widget") == 2500

    # 1200 existing + 1300 new: the split falls mid-window on purpose.
    mixed = [{"id": f"w{i}", "name": "v3"} for i in range(1200)]
    mixed += [{"id": f"fresh{i}", "name": "v3"} for i in range(1300)]
    third = await db.express.bulk_upsert("Widget", mixed)
    assert (third["created"], third["updated"]) == (1300, 1200)
    assert await db.express.count("Widget") == 3800

    # Values really were updated, not merely counted as updates.
    row = await db.express.read("Widget", "w0")
    # read() is Optional-typed; assert presence FIRST so a missing row fails as
    # "w0 was not persisted" rather than as an unactionable TypeError on None.
    assert row is not None, "w0 was not persisted by the upsert under test"
    assert row["name"] == "v3"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_precount_is_exact_for_a_composite_conflict_target(tmp_path):
    """Composite conflict targets exercise the parameter-slicing arithmetic.

    Each ``OR`` clause binds ``len(conflict_columns)`` params, so a window of
    clauses must carry exactly that many times as many params. An off-by-one in
    the slice would bind the wrong values and silently return a wrong count.
    Drives ``_count_existing_conflicts`` directly: it is a ``SELECT COUNT(*)``
    and needs no UNIQUE constraint, so this isolates the arithmetic from the
    native ``ON CONFLICT`` requirement.
    """
    db = _fresh_db(tmp_path)

    @db.model
    class Pair:
        id: str
        sku: str
        region: str

    rows = [
        {"id": f"p{i}", "sku": f"s{i}", "region": "eu" if i % 2 == 0 else "us"}
        for i in range(2200)
    ]
    await db.express.bulk_create("Pair", rows)
    assert await db.express.count("Pair") == 2200

    sql_node = db._get_or_create_async_sql_node("sqlite")
    table = db._models["Pair"].get("table_name") or db._class_name_to_table_name("Pair")

    # Every one of the 2200 keys exists -> the chunked sum must be 2200.
    all_present = await db.bulk._count_existing_conflicts(
        sql_node, table, ["sku", "region"], rows
    )
    assert all_present == 2200, f"chunked pre-count summed to {all_present}, not 2200"

    # Half present, half absent, interleaved so the miss/hit pattern crosses
    # every window boundary rather than sitting in one window.
    interleaved = []
    for i in range(2200):
        interleaved.append(
            rows[i] if i % 2 == 0 else {"sku": f"ghost{i}", "region": "eu"}
        )
    half = await db.bulk._count_existing_conflicts(
        sql_node, table, ["sku", "region"], interleaved
    )
    assert half == 1100, f"chunked pre-count summed to {half}, not 1100"


# ---------------------------------------------------------------------------
# Behaviour 2 — the second cliff: bound-parameter budget on wide models
# ---------------------------------------------------------------------------


def _wide_model(db, n_data_columns: int, name: str):
    """Register a model with ``n_data_columns`` TEXT columns plus ``id``."""
    annotations = {"id": str}
    for i in range(n_data_columns):
        annotations[f"c{i}"] = str
    model = type(name, (), {"__annotations__": annotations})
    db.model(model)
    return model


@pytest.mark.regression
@pytest.mark.asyncio
async def test_wide_model_batch_exceeding_the_bind_budget_still_persists(tmp_path):
    """41 columns x 900 rows = 36900 binds > SQLite's 32766 budget.

    Under the 999-row expression ceiling, so this is a DIFFERENT limit from
    behaviour 1 and fails with "too many SQL variables". Pre-fix: zero rows.
    """
    db = _fresh_db(tmp_path)
    _wide_model(db, 40, "WideWidget")

    records = [
        {"id": f"w{i}", **{f"c{j}": f"v{j}" for j in range(40)}} for i in range(900)
    ]
    result = await db.express.bulk_upsert("WideWidget", records, conflict_on=["id"])

    assert (
        result.get("success", True) is not False
    ), f"wide-model bulk_upsert reported failure: {result.get('error')!r}"
    assert await db.express.count("WideWidget") == 900
    assert result["created"] == 900


@pytest.mark.regression
@pytest.mark.asyncio
async def test_effective_batch_size_is_reported_when_clamped(tmp_path):
    """The clamp is observable, not silent — the result dict reports what ran.

    ``batches`` is derived from the effective size, so reporting the REQUESTED
    size alongside it would be internally inconsistent.
    """
    db = _fresh_db(tmp_path)
    _wide_model(db, 40, "WideReport")
    # The ENGINE surface does not auto-create schema; only the express facade
    # does. Touch the table through express first so the direct engine call
    # below is decided by STATEMENT CAPACITY rather than by "no such table" —
    # a missing table makes the clamp assertion vacuous.
    assert await db.express.count("WideReport") == 0

    records = [
        {"id": f"w{i}", **{f"c{j}": f"v{j}" for j in range(40)}} for i in range(900)
    ]
    engine_result = await db.bulk.bulk_upsert(
        model_name="WideReport",
        data=records,
        conflict_on=["id"],
        conflict_resolution="update",
        batch_size=1000,
    )
    assert engine_result["success"] is True
    capacity = statement_capacity_for("sqlite")
    expected = capacity.max_rows_per_statement(41)
    assert engine_result["batch_size"] == expected, (
        f"result reported batch_size={engine_result['batch_size']}, "
        f"but the statements actually ran at {expected} rows"
    )
    assert engine_result["batch_size"] < 1000


# ---------------------------------------------------------------------------
# Behaviour 3 — the documented batch_size kwarg was inert
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [100, 400])
async def test_express_batch_size_reaches_the_bulk_engine(tmp_path, batch_size):
    """``batch_size`` is a documented kwarg; it MUST affect execution.

    Pre-fix the engine received 1000 no matter what was passed. Observes the
    value at the engine boundary rather than inferring it from timing.
    """
    db = _fresh_db(tmp_path)

    @db.model
    class Widget:
        id: str
        name: str

    seen = []
    original = type(db.bulk).bulk_upsert

    async def recording(self, *args, **kwargs):
        seen.append(kwargs.get("batch_size"))
        return await original(self, *args, **kwargs)

    type(db.bulk).bulk_upsert = recording
    try:
        records = [{"id": f"w{i}", "name": "n"} for i in range(900)]
        await db.express.bulk_upsert(
            "Widget", records, conflict_on=["id"], batch_size=batch_size
        )
    finally:
        type(db.bulk).bulk_upsert = original

    assert seen == [batch_size], (
        f"bulk engine received batch_size={seen}, expected [{batch_size}] — "
        f"the documented kwarg is not plumbed through"
    )
    # And it actually executed: all rows landed.
    assert await db.express.count("Widget") == 900


# ---------------------------------------------------------------------------
# Behaviour 4 — the dialect budgets, pinned to the MEASURED model
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.parametrize(
    "terms_per_row,measured_max_clauses",
    [
        (1, 999),
        (2, 998),
        (3, 997),
        (4, 996),
        (5, 995),
        (8, 992),
        (10, 990),
        (16, 984),
        (32, 968),
    ],
)
def test_sqlite_expression_budget_never_exceeds_the_measured_ceiling(
    terms_per_row, measured_max_clauses
):
    """Pins the ADDITIVE depth model measured against real SQLite 3.49.1.

    A multiplicative model would return 499 clauses where 998 are legal — safe,
    but a 2x over-chunk on every composite conflict target. The budget must sit
    at or below the measured ceiling (a margin is withheld deliberately) and
    must track the ceiling additively, not collapse with width.
    """
    dialect = DialectManager.get_dialect("sqlite")
    budget = dialect.max_terms_per_expression(terms_per_row)
    assert budget <= measured_max_clauses, (
        f"budget {budget} exceeds the measured SQLite ceiling "
        f"{measured_max_clauses} for {terms_per_row} terms/clause — generated "
        f"SQL would be rejected"
    )
    # Additive, not multiplicative: even at width 32 the budget stays close to
    # the ceiling rather than collapsing to ~31.
    assert budget >= measured_max_clauses - 16


@pytest.mark.regression
def test_unknown_engine_falls_back_to_the_tightest_known_budget():
    """Fail-CLOSED for capacity (opposite of ``identifier_budget_for``).

    Over-tight chunking costs round-trips; over-loose chunking costs DATA — the
    statement is rejected and the whole batch is lost.
    """
    unknown = statement_capacity_for("some-future-engine")
    known = [
        DialectManager.get_dialect(name) for name in ("sqlite", "postgresql", "mysql")
    ]
    assert unknown.max_expression_depth == min(d.max_expression_depth for d in known)
    assert unknown.max_bind_parameters == min(d.max_bind_parameters for d in known)


@pytest.mark.regression
def test_bind_parameter_budget_is_bound_per_dialect_not_hardcoded():
    """The SQLite magic numbers live in SQLiteDialect, not in shared code."""
    assert statement_capacity_for("sqlite").max_bind_parameters == 32766
    assert statement_capacity_for("postgresql").max_bind_parameters == 65535
    assert statement_capacity_for("mysql").max_bind_parameters == 65535
    # 41 columns against SQLite's budget -> 799 rows per statement.
    assert statement_capacity_for("sqlite").max_rows_per_statement(41) == 799
