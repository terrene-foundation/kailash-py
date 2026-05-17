"""Regression: write-protection MUST fire BEFORE field validators on
every Express mutation (issue #1058 Shard 2).

The pre-fix ordering ran ``_validate_if_enabled`` BEFORE the protection
check that lives inside ``ProtectedNode.async_run``. Under that order a
blocked-write attacker could trigger field-validator side effects —
custom validators may log, emit metrics, call external services — even
when the write was about to be rejected. Invariant I2 ("a blocked
write never takes a connection") still held because validation is
in-process, so this was defense-in-depth ordering, not a bypass.
Shard 2 closes the ordering gap by routing every Express mutation
through ``DataFlowExpress._check_protection_if_enabled`` BEFORE the
validator call.

Spec anchor: ``specs/dataflow-protection.md`` §2 path 1 (Express);
``rules/dataflow-classification.md`` validator-side-effect class.

Tier 2 per ``rules/testing.md`` — real backend, no mocking. File-SQLite
chosen because the contract is dialect-independent (the precheck lives
in pure-Python ``express.py`` ahead of any SQL) and the test must run
in any CI lane without the shared Docker stack.
"""

from __future__ import annotations

import tempfile
from typing import Any

import pytest

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import ProtectionViolation
from dataflow.validation.decorators import field_validator

# Module-scope counter the validator increments. A bare list is used (not
# an int) so the closure can mutate it without `nonlocal` ceremony —
# pytest-isolated by being reset inside each test's fixture-free body.
_VALIDATOR_INVOCATIONS: list[Any] = []


def _side_effecting_validator(value: Any) -> bool:
    """A validator with an observable side effect.

    Models the failure mode this rule guards against — a custom
    validator that does work (logs, emits, hits an external service)
    BEFORE the protection block fires. Returns True so validation
    would pass on its own merits if the protection layer ever let
    control reach it.
    """
    _VALIDATOR_INVOCATIONS.append(value)
    return True


@pytest.fixture(autouse=True)
def _reset_validator_counter():
    """Per-test reset of the module-scope validator-invocation log."""
    _VALIDATOR_INVOCATIONS.clear()
    yield
    _VALIDATOR_INVOCATIONS.clear()


def _make_protected_db(tmp_subdir: str) -> ProtectedDataFlow:
    """Construct a ProtectedDataFlow over a fresh file-SQLite DB."""
    tmpdir = tempfile.mkdtemp(prefix=f"issue1058_shard2_{tmp_subdir}_")
    return ProtectedDataFlow(
        database_url=f"sqlite:///{tmpdir}/test.db",
        enable_protection=True,
    )


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_create_protection_fires_before_field_validators():
    """Blocked ``express.create`` MUST raise ``ProtectionViolation``
    WITHOUT invoking any registered field validator.

    Pre-fix sequence (defense-in-depth gap):
      1. ``_validate_if_enabled`` runs → side-effecting validator fires.
      2. ``_trust_check_write`` runs.
      3. ``node.async_run`` runs → ``ProtectionViolation`` raised.

    Post-fix sequence (Shard 2):
      1. ``_check_protection_if_enabled`` runs → ``ProtectionViolation``.
         Validator is NEVER called.
    """
    db = _make_protected_db("create")

    @db.model
    @field_validator("title", _side_effecting_validator)
    class Issue1058Shard2Doc:
        id: str
        title: str

    try:
        await db.initialize()
        db.enable_read_only_mode("issue #1058 Shard 2 ordering guard")

        with pytest.raises(ProtectionViolation):
            await db.express.create(
                "Issue1058Shard2Doc",
                {"id": "doc-1", "title": "blocked-create"},
            )

        # The load-bearing assertion: protection ran AHEAD of validation.
        # If the validator had been invoked, the side-effect log would
        # contain "blocked-create" and the pre-fix ordering would be back.
        assert _VALIDATOR_INVOCATIONS == [], (
            "Field validator fired on a blocked create — protection "
            "precheck regressed behind _validate_if_enabled. See issue "
            "#1058 Shard 2."
        )
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_update_protection_fires_before_field_validators():
    """Blocked ``express.update`` MUST NOT invoke field validators.

    Parallel test to ``create`` — same contract on the update surface
    so a future refactor that moves the precheck on create but forgets
    update fails loudly here.
    """
    db = _make_protected_db("update")

    @db.model
    @field_validator("title", _side_effecting_validator)
    class Issue1058Shard2UpdateDoc:
        id: str
        title: str

    try:
        await db.initialize()
        # Seed a row under permissive protection so update has a real
        # target. The seeding create is allowed; the validator fires
        # legitimately here.
        await db.express.create(
            "Issue1058Shard2UpdateDoc",
            {"id": "doc-1", "title": "original"},
        )
        # Reset the counter AFTER seeding so the assertion isolates the
        # blocked-update behavior, not the seeding side effect.
        _VALIDATOR_INVOCATIONS.clear()

        db.enable_read_only_mode("issue #1058 Shard 2 update ordering guard")

        with pytest.raises(ProtectionViolation):
            await db.express.update(
                "Issue1058Shard2UpdateDoc",
                "doc-1",
                {"title": "blocked-update"},
            )

        assert _VALIDATOR_INVOCATIONS == [], (
            "Field validator fired on a blocked update — protection "
            "precheck regressed behind _validate_if_enabled. See issue "
            "#1058 Shard 2."
        )
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_upsert_protection_fires_before_field_validators():
    """Blocked ``express.upsert`` MUST NOT invoke field validators.

    Third mutation surface — upsert is the failure-mode entry point
    that the audit specifically called out as silently re-opening
    in any future refactor that copies the create/update pattern
    without porting the precheck. The test pins the contract.
    """
    db = _make_protected_db("upsert")

    @db.model
    @field_validator("title", _side_effecting_validator)
    class Issue1058Shard2UpsertDoc:
        id: str
        title: str

    try:
        await db.initialize()
        db.enable_read_only_mode("issue #1058 Shard 2 upsert ordering guard")

        with pytest.raises(ProtectionViolation):
            await db.express.upsert(
                "Issue1058Shard2UpsertDoc",
                {"id": "doc-1", "title": "blocked-upsert"},
            )

        assert _VALIDATOR_INVOCATIONS == [], (
            "Field validator fired on a blocked upsert — protection "
            "precheck regressed behind _validate_if_enabled. See issue "
            "#1058 Shard 2."
        )
    finally:
        db.close()


@pytest.mark.regression
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_allowed_create_does_not_double_check_protection():
    """Happy-path ``express.create`` MUST run the protection check
    exactly ONCE (Express precheck), NOT twice.

    Pin invariant I1 (single check, no double-audit) end-to-end. Pre-
    fix the audit log would have one allow entry per Express mutation
    (from ``ProtectedNode.async_run``). Post-fix with the precheck
    AND no sentinel-skip in ``ProtectedNode.async_run``, the audit
    log would have TWO entries per mutation. The sentinel-skip is
    what keeps the count at one.
    """
    db = _make_protected_db("happy_path")

    @db.model
    class Issue1058Shard2HappyDoc:
        id: str
        title: str

    try:
        await db.initialize()
        # Snapshot the auditor's event log BEFORE the create. Pre-test
        # noise (initialization, seeding) is irrelevant — we measure
        # the delta the single create produces.
        protection_engine = getattr(db, "_protection_engine", None)
        assert (
            protection_engine is not None
        ), "ProtectedDataFlow MUST wire a protection engine"
        before = len(protection_engine.config.auditor.events)

        await db.express.create(
            "Issue1058Shard2HappyDoc",
            {"id": "doc-1", "title": "permitted-create"},
        )

        after = len(protection_engine.config.auditor.events)
        delta = after - before
        assert delta == 1, (
            f"Express create produced {delta} protection-audit events; "
            f"expected exactly 1 (single-check invariant I1). A delta of "
            f"2 indicates the sentinel-skip in ProtectedNode.async_run "
            f"regressed and the Express precheck is double-checking."
        )
    finally:
        db.close()
