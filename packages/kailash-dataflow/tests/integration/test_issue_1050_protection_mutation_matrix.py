"""Issue #1050 — Per-mutation write-protection enforcement Tier-2 matrix.

Proves the just-merged `ProtectedDataFlow` write-protection wiring
(PR #1057, `protection_middleware.py:316` `async_run` ->
`check_operation` at `:419` before `super().async_run()`) BLOCKS every
mutation surface and does NOT block reads, on REAL infrastructure.

This is the per-mutation Tier-2 matrix the domain spec mandates:
`specs/dataflow-protection.md` §4 ("Conformance to I1–I9 is verified by
... the per-mutation Tier-2 matrix"). AC#1 (block every mutation) +
AC#2 (never block reads) of issue #1050.

Invariants pinned (specs/dataflow-protection.md §3):

- **I7** — read/list/count MUST NOT be write-blocked under read-only /
  production-safe. The `count` case specifically pins the latent
  `count`-over-block regression: `count` was mis-mapped to
  `CUSTOM_QUERY` pre-fix and spuriously blocked under read-only; the
  fix added `"count": OperationType.READ` to
  `protection.py::_operation_mapping`. A regression that reverts that
  mapping fails `test_count_not_blocked_read_only`.
- **I4** — `add_model_protection` / `add_field_protection` enforce
  (i.e. `model_name` reaches `check_operation`). An SQL-string-layer
  check that loses `model_name` does NOT satisfy the contract; the
  model-level + field-level tests fail loudly if it regresses.
- **I9** — a blocked op emits an audit record reachable via
  `db.get_protection_audit_log()` BEFORE the raise.
- **I5** — `ProtectionViolation` propagates to the caller; Express
  surfaces it as an exception, not folded into a result dict.

Tier-2 infrastructure (NO mocking — `rules/testing.md` § Tier 2):

- **file-backed SQLite** (`tempfile`, NOT `:memory:`): DataFlow's
  migration pool opens multiple short-lived connections; bare
  `:memory:` gives each its own DB and breaks the migration handshake
  (see `packages/kailash-dataflow/tests/CLAUDE.md` § Carve-out). Always
  runs.
- **real PostgreSQL** via `IntegrationTestSuite` (port 5434): runs when
  the shared Docker infra is reachable; SKIPPED with an explicit reason
  (NOT mocked, NOT silently passed) when port 5434 is unavailable.

State persistence (`rules/testing.md` § State Persistence): every
blocked write is verified to have NOT persisted (read-back returns
``None`` / unchanged); every write expected to succeed is verified via
read-back.
"""

import socket
import tempfile
import uuid

import pytest

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import ProtectionViolation

# ---------------------------------------------------------------------------
# Dialect parametrization — file-SQLite always; real PostgreSQL infra-gated.
# The PG param is SKIPPED (not mocked) when port 5434 is unreachable so the
# matrix still exercises the full contract on file-SQLite in CI without the
# shared Docker stack, while running both dialects when infra is present.
# ---------------------------------------------------------------------------

PG_HOST = "localhost"
PG_PORT = 5434
PG_URL = f"postgresql://test_user:test_password@{PG_HOST}:{PG_PORT}/kailash_test"


def _postgres_reachable() -> bool:
    """True if the shared test PostgreSQL (port 5434) accepts a TCP connect.

    A real liveness probe against the same endpoint the failing operation
    would target — NOT a documentation/intent proxy
    (`verify-resource-existence.md` MUST-2).
    """
    try:
        with socket.create_connection((PG_HOST, PG_PORT), timeout=1.0):
            return True
    except OSError:
        return False


_PG_AVAILABLE = _postgres_reachable()

DIALECTS = [
    pytest.param("sqlite", id="file-sqlite"),
    pytest.param(
        "postgres",
        id="postgres-5434",
        marks=pytest.mark.skipif(
            not _PG_AVAILABLE,
            reason=(
                "PostgreSQL not reachable on localhost:5434 — start the "
                "shared SDK Docker infra to run the postgres param. NOT "
                "mocked (Tier-2 no-mocking policy); file-sqlite param still "
                "exercises the full contract."
            ),
        ),
    ),
]


def _make_protected_db(dialect: str) -> ProtectedDataFlow:
    """Construct a ProtectedDataFlow on the requested real backend.

    file-SQLite uses ``tempfile.mkdtemp()`` + ``sqlite:///<tmp>/test.db``
    (file-backed, NOT ``:memory:``) per the migration-pool handshake
    constraint documented in
    ``packages/kailash-dataflow/tests/CLAUDE.md``.
    """
    if dialect == "sqlite":
        tmpdir = tempfile.mkdtemp(prefix="issue1050_mutation_matrix_")
        url = f"sqlite:///{tmpdir}/test.db"
    elif dialect == "postgres":
        url = PG_URL
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(f"unknown dialect {dialect!r}")
    return ProtectedDataFlow(database_url=url, enable_protection=True)


def _unique_model_name(prefix: str) -> str:
    """Per-test unique model name — avoids the global node-registry
    collisions DataFlow's generated-node machinery has across tests.
    """
    return f"{prefix}{uuid.uuid4().hex[:10]}"


# Operations the protection wiring MUST block under read-only mode.
# Each maps to the express call that exercises that mutation surface;
# the call MUST raise ProtectionViolation (spec I5 — Express surfaces it
# as an exception, not a result dict).
_BLOCKED_MUTATIONS = [
    "create",
    "update",
    "delete",
    "upsert",
    "bulk_create",
    "bulk_update",
    "bulk_delete",
    "bulk_upsert",
]


@pytest.mark.integration
@pytest.mark.timeout(30)
@pytest.mark.parametrize("dialect", DIALECTS)
class TestIssue1050ProtectionMutationMatrix:
    """Per-mutation enforcement matrix for issue #1050 AC#1 + AC#2."""

    # ------------------------------------------------------------------
    # AC#1 — every mutation surface is BLOCKED under read-only mode.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mutation", _BLOCKED_MUTATIONS)
    async def test_mutation_blocked_under_read_only(self, dialect, mutation):
        """Each write surface raises ProtectionViolation under read-only,
        AND the row is NOT persisted (state-persistence verification).
        """
        db = _make_protected_db(dialect)
        model = _unique_model_name("Mut")

        @db.model  # noqa: B903 - DataFlow model decorator
        class _Doc:
            id: str
            title: str

        # Rebind the dynamically-created class under the unique model name
        # so each parametrized test gets an isolated generated node set.
        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()

            # Seed a baseline row WHILE protection is still permissive so
            # update/delete/bulk_update/bulk_delete have a target and the
            # "row unchanged after blocked write" assertion is meaningful.
            seed = await db.express.create(model, {"id": "seed-1", "title": "original"})
            assert seed["id"] == "seed-1"

            # Engage global read-only protection (BLOCK level — allow READ
            # only). Every mutation below MUST now raise.
            db.enable_read_only_mode("issue #1050 mutation matrix")

            with pytest.raises(ProtectionViolation):
                if mutation == "create":
                    await db.express.create(
                        model, {"id": "blocked-create", "title": "x"}
                    )
                elif mutation == "update":
                    await db.express.update(model, "seed-1", {"title": "MUTATED"})
                elif mutation == "delete":
                    await db.express.delete(model, "seed-1")
                elif mutation == "upsert":
                    await db.express.upsert(model, {"id": "seed-1", "title": "MUTATED"})
                elif mutation == "bulk_create":
                    await db.express.bulk_create(
                        model,
                        [
                            {"id": "bc-1", "title": "a"},
                            {"id": "bc-2", "title": "b"},
                        ],
                    )
                elif mutation == "bulk_update":
                    await db.express.bulk_update(
                        model, [{"id": "seed-1", "title": "MUTATED"}]
                    )
                elif mutation == "bulk_delete":
                    await db.express.bulk_delete(model, ["seed-1"])
                elif mutation == "bulk_upsert":
                    await db.express.bulk_upsert(
                        model, [{"id": "seed-1", "title": "MUTATED"}]
                    )
                else:  # pragma: no cover - parametrization guard
                    raise AssertionError(f"unhandled mutation {mutation!r}")

            # State-persistence verification: the blocked write left the
            # database exactly as it was. Reads are allowed under
            # read-only (I7), so we read back through the same Express
            # surface a user would.
            if mutation in ("create", "bulk_create"):
                # No new rows: the seed row is still the only row.
                assert await db.express.count(model) == 1
                assert await db.express.read(model, "blocked-create") is None
                assert await db.express.read(model, "bc-1") is None
            elif mutation in ("delete", "bulk_delete"):
                # The seed row was NOT deleted.
                survived = await db.express.read(model, "seed-1")
                assert survived is not None
                assert survived["title"] == "original"
            else:
                # update / upsert / bulk_update / bulk_upsert: the seed
                # row's title was NOT mutated.
                unchanged = await db.express.read(model, "seed-1")
                assert unchanged is not None
                assert unchanged["title"] == "original", (
                    f"{mutation} mutated the row despite read-only "
                    f"protection — write-protection bypassed"
                )
        finally:
            db.close()

    # ------------------------------------------------------------------
    # AC#2 — read / list / count are NEVER write-blocked (I7).
    # The `count` case is the explicit regression guard for the latent
    # count-over-block: pre-fix `count` mis-mapped to CUSTOM_QUERY and
    # was spuriously blocked under read-only.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_read_not_blocked_read_only(self, dialect):
        """`read` succeeds under read-only mode (no ProtectionViolation)."""
        db = _make_protected_db(dialect)
        model = _unique_model_name("RdOk")

        @db.model
        class _Doc:
            id: str
            title: str

        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()
            await db.express.create(model, {"id": "r-1", "title": "kept"})
            db.enable_read_only_mode("issue #1050 read allowed")

            got = await db.express.read(model, "r-1")
            assert got is not None
            assert got["title"] == "kept"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_list_not_blocked_read_only(self, dialect):
        """`list` succeeds under read-only mode (no ProtectionViolation)."""
        db = _make_protected_db(dialect)
        model = _unique_model_name("LsOk")

        @db.model
        class _Doc:
            id: str
            title: str

        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()
            await db.express.create(model, {"id": "l-1", "title": "a"})
            await db.express.create(model, {"id": "l-2", "title": "b"})
            db.enable_read_only_mode("issue #1050 list allowed")

            rows = await db.express.list(model)
            assert len(rows) == 2
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_count_not_blocked_read_only(self, dialect):
        """`count` succeeds under read-only mode — pins I7 specifically.

        Regression guard: if `protection.py::_operation_mapping` ever
        loses ``"count": OperationType.READ``, `count` falls through to
        ``CUSTOM_QUERY`` which read-only's allow-list ({READ}) does NOT
        permit, and this raises ProtectionViolation. The fix added the
        explicit `count -> READ` mapping; this test fails loudly if it
        regresses.
        """
        db = _make_protected_db(dialect)
        model = _unique_model_name("CntOk")

        @db.model
        class _Doc:
            id: str
            title: str

        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()
            await db.express.create(model, {"id": "c-1", "title": "a"})
            await db.express.create(model, {"id": "c-2", "title": "b"})
            await db.express.create(model, {"id": "c-3", "title": "c"})
            db.enable_read_only_mode("issue #1050 count allowed")

            # MUST NOT raise — count is a derived-scalar READ.
            n = await db.express.count(model)
            assert n == 3
        finally:
            db.close()

    # ------------------------------------------------------------------
    # I4 — model-level protection enforces (model_name reaches the
    # engine). A write on the protected model is blocked even with NO
    # global read-only mode.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_add_model_protection_blocks_write_on_that_model(self, dialect):
        """`add_model_protection(model, allowed_operations={READ})` blocks
        a write on that model — proves `model_name` reaches
        `check_operation` (spec I4). A second, unprotected model in the
        same DataFlow instance is NOT blocked (the protection is scoped
        to the named model, not global).
        """
        from dataflow.core.protection import OperationType

        db = _make_protected_db(dialect)
        protected = _unique_model_name("ProtMdl")
        free = _unique_model_name("FreeMdl")

        @db.model
        class _Prot:
            id: str
            title: str

        _Prot.__name__ = protected
        _Prot.__qualname__ = protected
        db.model(_Prot)

        @db.model
        class _Free:
            id: str
            title: str

        _Free.__name__ = free
        _Free.__qualname__ = free
        db.model(_Free)

        try:
            await db.initialize()

            # Protect ONLY the `protected` model: READ allowed, writes
            # blocked. No global read-only — the block must come from the
            # model-level rule, which requires model_name to reach the
            # engine (I4).
            db.add_model_protection(protected, allowed_operations={OperationType.READ})

            with pytest.raises(ProtectionViolation):
                await db.express.create(protected, {"id": "p-1", "title": "blocked"})

            # Blocked write did not persist.
            assert await db.express.read(protected, "p-1") is None

            # The unprotected model in the SAME instance is unaffected —
            # confirms the protection is model-scoped (model_name is the
            # discriminator that reached the engine), not global.
            created = await db.express.create(free, {"id": "f-1", "title": "allowed"})
            assert created["id"] == "f-1"
            # Read-back: the write to the free model really persisted.
            back = await db.express.read(free, "f-1")
            assert back is not None
            assert back["title"] == "allowed"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_add_field_protection_blocks_write_on_that_model(self, dialect):
        """`add_field_protection(model, field, ...)` blocks a write on the
        protected model — proves `model_name` reaches `check_operation`
        at the field-protection layer too (spec I4).

        The protection engine resolves a write on a model with a
        BLOCK-level protected field to a violation (the field's
        ``allowed_operations`` defaults to ``{READ}``). This pins that
        ``add_field_protection`` is wired through the same
        ``model_name``-bearing ``check_operation`` path as
        ``add_model_protection``.
        """
        from dataflow.core.protection import OperationType, ProtectionLevel

        db = _make_protected_db(dialect)
        model = _unique_model_name("FldMdl")

        @db.model
        class _Doc:
            id: str
            secret: str

        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()

            db.add_field_protection(
                model,
                "secret",
                protection_level=ProtectionLevel.BLOCK,
                allowed_operations={OperationType.READ},
            )

            with pytest.raises(ProtectionViolation):
                await db.express.create(model, {"id": "fp-1", "secret": "classified"})

            # Blocked write did not persist.
            assert await db.express.read(model, "fp-1") is None
        finally:
            db.close()

    # ------------------------------------------------------------------
    # I9 — a blocked op emits an auditable record reachable via
    # db.get_protection_audit_log() BEFORE the raise.
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_blocked_op_emits_audit_record(self, dialect):
        """After a blocked write, `db.get_protection_audit_log()` contains
        the violation record (spec I9). The record carries the operation
        and the BLOCK level — the security signal an operator monitors.
        """
        db = _make_protected_db(dialect)
        model = _unique_model_name("Audit")

        @db.model
        class _Doc:
            id: str
            title: str

        _Doc.__name__ = model
        _Doc.__qualname__ = model
        db.model(_Doc)

        try:
            await db.initialize()
            db.enable_read_only_mode("issue #1050 audit record")

            with pytest.raises(ProtectionViolation):
                await db.express.create(model, {"id": "a-1", "title": "blocked"})

            events = db.get_protection_audit_log()
            assert len(events) > 0, (
                "no audit events captured — I9 violated (blocked op did "
                "not emit an audit record before the raise)"
            )

            # A violation record (not just an 'allowed' record) MUST be
            # present: it carries `level` + `operation` for the create
            # block. `log_violation` (protection.py) sets these keys;
            # `log_allowed` sets `status: "allowed"` instead.
            violation_records = [
                e
                for e in events
                if e.get("level") is not None and e.get("operation") == "create"
            ]
            assert violation_records, (
                "audit log has no create-violation record with a "
                f"protection level — events seen: {events}"
            )
        finally:
            db.close()
