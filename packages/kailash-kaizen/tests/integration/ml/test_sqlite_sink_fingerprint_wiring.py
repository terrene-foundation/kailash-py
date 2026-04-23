# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 — ``SQLiteSink`` persists the N4 canonical fingerprint.

Spec ``kaizen-ml-integration.md §5`` mandates that the SQLite sink
persists the cross-SDK N4 canonical fingerprint unchanged — the
single-filter-point discipline at the ``TraceExporter`` layer means
the sink MUST NOT re-compute. This test proves:

    1. The schema (``_kml_agent_runs`` + ``_kml_agent_events``) is
       created against a real SQLite file.
    2. A ``TraceEvent`` routed through the sink creates a row pair
       linked by ``trace_id``.
    3. The fingerprint persisted in ``_kml_agent_events.fingerprint``
       matches ``compute_trace_event_fingerprint(event)`` — byte-for-byte.
    4. ``_kml_agent_runs.run_id`` preserves the ambient ``km.track()``
       run_id supplied at sink construction (spec §5.4 — dashboard
       join surface).

No mocks — real SQLite file in ``tmp_path``.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

import pytest

from kailash.diagnostics.protocols import (
    TraceEvent,
    TraceEventStatus,
    TraceEventType,
    compute_trace_event_fingerprint,
)


@pytest.mark.integration
def test_sqlite_sink_creates_kml_agent_tables(tmp_path) -> None:
    """Spec §5.2 — both tables and their indexes exist after init."""
    from kaizen.ml import SQLiteSink

    db_path = tmp_path / "ml.db"
    sink = SQLiteSink(db_path=db_path)
    try:
        with sqlite3.connect(str(db_path)) as inspect_conn:
            rows = inspect_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
            tables = {r[0] for r in rows}
        assert "_kml_agent_runs" in tables
        assert "_kml_agent_events" in tables
    finally:
        sink.close()


@pytest.mark.integration
def test_sqlite_sink_persists_canonical_fingerprint(tmp_path) -> None:
    """Spec §5 — persisted fingerprint MUST equal the canonical digest.

    The canonical digest is produced by
    ``kailash.diagnostics.protocols.compute_trace_event_fingerprint``
    (N4 canonical — byte-identical with kailash-rs v3.17.1+). If the
    sink re-hashes, drifts, or truncates, this test fails loudly.
    """
    from kaizen.ml import SQLiteSink

    db_path = tmp_path / "ml.db"
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    trace_id = f"trace-{uuid.uuid4().hex[:8]}"

    event = TraceEvent(
        event_id=uuid.uuid4().hex,
        event_type=TraceEventType.AGENT_RUN_START,
        timestamp=datetime(2026, 4, 23, 12, 0, 0, tzinfo=timezone.utc),
        run_id=run_id,
        agent_id="sink-agent",
        cost_microdollars=500,
        trace_id=trace_id,
        tenant_id=None,
        status=TraceEventStatus.OK,
    )
    expected_fingerprint = compute_trace_event_fingerprint(event)

    sink = SQLiteSink(db_path=db_path, run_id=run_id, agent_id="sink-agent")
    try:
        sink.export(event, expected_fingerprint)
    finally:
        sink.close()

    with sqlite3.connect(str(db_path)) as inspect_conn:
        run_row = inspect_conn.execute(
            "SELECT trace_id, run_id, agent_id, status, cost_microdollars "
            "FROM _kml_agent_runs WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
        event_row = inspect_conn.execute(
            "SELECT event_id, trace_id, seq, event_type, event_status, "
            "fingerprint FROM _kml_agent_events WHERE event_id = ?",
            (event.event_id,),
        ).fetchone()

    # Spec §5.4 — the sink stamped the ambient run_id on the trace row.
    assert run_row is not None, "trace row missing from _kml_agent_runs"
    assert run_row[0] == trace_id
    assert run_row[1] == run_id
    assert run_row[2] == "sink-agent"
    assert run_row[3] == "RUNNING"
    assert run_row[4] == 500

    # Spec §5 — persisted fingerprint is byte-identical to canonical.
    assert event_row is not None, "event row missing from _kml_agent_events"
    assert event_row[0] == event.event_id
    assert event_row[1] == trace_id
    assert event_row[2] == 1  # monotone seq starts at 1
    assert event_row[3] == TraceEventType.AGENT_RUN_START.value
    assert event_row[4] == TraceEventStatus.OK.value
    assert event_row[5] == expected_fingerprint


@pytest.mark.integration
def test_sqlite_sink_finalize_trace_rejects_legacy_status(tmp_path) -> None:
    """Spec §5.3 — legacy status values BLOCKED."""
    from kaizen.ml import SQLiteSink, SQLiteSinkError

    sink = SQLiteSink(db_path=tmp_path / "ml.db")
    try:
        # First, seed a trace row so finalize has something to touch.
        event = TraceEvent(
            event_id=uuid.uuid4().hex,
            event_type=TraceEventType.AGENT_RUN_START,
            timestamp=datetime.now(timezone.utc),
            run_id="finalize-run",
            agent_id="finalize-agent",
            cost_microdollars=0,
            trace_id="finalize-trace",
            status=TraceEventStatus.OK,
        )
        fingerprint = compute_trace_event_fingerprint(event)
        sink.export(event, fingerprint)

        # Spec §5.3 — only RUNNING / FINISHED / FAILED / KILLED allowed.
        with pytest.raises(SQLiteSinkError):
            sink.finalize_trace("finalize-trace", status="COMPLETED")
        with pytest.raises(SQLiteSinkError):
            sink.finalize_trace("finalize-trace", status="SUCCESS")

        # But FINISHED is accepted — and the row transitions.
        sink.finalize_trace("finalize-trace", status="FINISHED")
    finally:
        sink.close()

    with sqlite3.connect(str(tmp_path / "ml.db")) as inspect_conn:
        status = inspect_conn.execute(
            "SELECT status FROM _kml_agent_runs WHERE trace_id = ?",
            ("finalize-trace",),
        ).fetchone()[0]
    assert status == "FINISHED"


@pytest.mark.integration
def test_sqlite_sink_default_path_is_kml_db() -> None:
    """Spec §5.1 default — ``~/.kailash_ml/ml.db``.

    Structural assertion only (we don't WRITE to the user's home —
    we only verify the computed path). ``tmp_path`` isolation is
    handled by other tests; this test guards against a refactor that
    silently changes the default away from the shared ML store.
    """
    from pathlib import Path

    from kaizen.ml import default_ml_db_path

    expected = Path.home() / ".kailash_ml" / "ml.db"
    assert default_ml_db_path() == expected
