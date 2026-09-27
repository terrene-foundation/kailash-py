"""Real Core decisions keep public semantics while DataFlow logs use safe metadata."""

import logging
from types import SimpleNamespace

import pytest

from dataflow import DataFlow
from dataflow.core.agent_context import async_agent_context
from dataflow.trust.query_wrapper import TrustAwareQueryExecutor

OPAQUE = "opaque-dataflow-canary-628194"
CREDENTIAL = "credential-dataflow-canary-197386"
PAYLOAD = f"https://user:{CREDENTIAL}@example.invalid/?token={CREDENTIAL}\nforged"


class Backend:
    def __init__(self, fail):
        self.fail = fail
        self.calls = []

    async def verify(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError(OPAQUE)
        return SimpleNamespace(
            valid=False, reason=PAYLOAD, effective_constraints=[], capability_used=None
        )


def assert_safe_records(caplog):
    records = [r for r in caplog.records if r.name == "dataflow.trust.query_wrapper"]
    assert records
    for record in records:
        assert record.exc_info is None
        fields = [record.getMessage()] + [
            getattr(record, key)
            for key in ("model", "operation", "agent_id", "reason", "error")
            if hasattr(record, key)
        ]
        for field in fields:
            assert isinstance(field, str)
            assert field.isprintable()
            assert OPAQUE not in field
            assert CREDENTIAL not in field
    return records


@pytest.mark.parametrize("mode", ["disabled", "permissive", "enforcing"])
@pytest.mark.parametrize("surface", ["table", "read", "write"])
@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.asyncio
async def test_core_decision_forwarding_and_cache_diagnostics(
    caplog, mode, surface, fail
):
    from kailash.runtime.trust.verifier import TrustVerifier, TrustVerifierConfig

    backend = Backend(fail)
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    executor = TrustAwareQueryExecutor(None, verifier, enforcement_mode=mode)

    async def call():
        if surface == "table":
            return await executor._verify_table_access(PAYLOAD, "agent", "read")
        if surface == "read":
            return (await executor.check_read_access(PAYLOAD, agent_id="agent")).allowed
        return (
            await executor.check_write_access(PAYLOAD, "create", agent_id="agent")
        ).allowed

    for _ in range(2):
        if mode == "enforcing":
            with pytest.raises(PermissionError) as error:
                await call()
            assert (OPAQUE if fail else PAYLOAD) in str(error.value)
        else:
            assert await call() is True
    assert len(backend.calls) == (0 if mode == "disabled" else 1)
    if mode != "disabled":
        assert backend.calls[0]["resource"] == f"table:{PAYLOAD}"
        assert backend.calls[0]["agent_id"] == "agent"
    if mode == "permissive":
        assert len(assert_safe_records(caplog)) == 2
    else:
        assert not [
            r for r in caplog.records if r.name == "dataflow.trust.query_wrapper"
        ]


@pytest.mark.parametrize("mode", ["disabled", "permissive", "enforcing"])
@pytest.mark.parametrize("operation", ["read", "create"])
@pytest.mark.asyncio
async def test_real_file_express_handoff(tmp_path, caplog, mode, operation):
    from kailash.runtime.trust.verifier import TrustVerifier, TrustVerifierConfig

    db = DataFlow(f"sqlite:///{tmp_path / 'handoff.db'}", trust_enforcement_mode=mode)

    @db.model
    class DiagnosticRecord:
        id: str
        name: str

    try:
        await db.initialize()
        await db.express.create("DiagnosticRecord", {"id": "seed", "name": "seed"})
        backend = Backend(True)
        verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
        db._trust_executor = TrustAwareQueryExecutor(
            db, verifier, enforcement_mode=mode
        )
        async with async_agent_context("agent"):

            async def call():
                if operation == "read":
                    return await db.express.read("DiagnosticRecord", "seed")
                return await db.express.create(
                    "DiagnosticRecord", {"id": "new", "name": "new"}
                )

            if mode == "enforcing":
                with pytest.raises(PermissionError, match=OPAQUE):
                    await call()
            else:
                result = await call()
                assert result["id"] == ("seed" if operation == "read" else "new")
        assert len(backend.calls) == (0 if mode == "disabled" else 1)
        if mode == "permissive":
            assert_safe_records(caplog)
    finally:
        db.close()


class FailureSource:
    async def get_agent_constraints(self, agent_id):
        raise RuntimeError(OPAQUE)

    async def verify_resource_access(self, **kwargs):
        raise RuntimeError(OPAQUE)

    def get_model_columns(self, model_name):
        raise RuntimeError(OPAQUE)

    async def resource_accessed(self, **kwargs):
        raise RuntimeError(OPAQUE)

    def record_query(self, **kwargs):
        raise RuntimeError(OPAQUE)


@pytest.mark.parametrize(
    "surface", ["constraints", "verifier", "columns", "audit", "store"]
)
@pytest.mark.asyncio
async def test_exception_sibling_extras_never_copy_exception_text(caplog, surface):
    source = FailureSource()
    source._audit_store = source
    executor = TrustAwareQueryExecutor(
        source, source, source, enforcement_mode="permissive", audit_generator=source
    )
    with caplog.at_level(logging.DEBUG, logger="dataflow.trust.query_wrapper"):
        if surface == "constraints":
            assert await executor._get_agent_constraints(PAYLOAD) == []
        elif surface == "verifier":
            assert (
                await executor._verify_table_access(PAYLOAD, PAYLOAD, PAYLOAD) is True
            )
        elif surface == "columns":
            assert executor._get_model_columns(PAYLOAD) == []
        elif surface == "audit":
            assert (
                await executor._record_audit(PAYLOAD, PAYLOAD, "failure", PAYLOAD, None)
                is None
            )
        else:
            assert (
                await executor._record_to_audit_store(
                    PAYLOAD, PAYLOAD, "failure", PAYLOAD, None, 0, None
                )
                is None
            )
    records = assert_safe_records(caplog)
    assert all("RuntimeError@" in r.error for r in records)


@pytest.mark.parametrize("mode", ["disabled", "permissive", "enforcing"])
@pytest.mark.asyncio
async def test_constraint_denial_preserves_returned_reason_but_bounds_log_extras(
    caplog, mode
):
    class Constraints:
        async def get_agent_constraints(self, agent_id):
            return [
                SimpleNamespace(constraint_type="action_restriction", value="read_only")
            ]

    executor = TrustAwareQueryExecutor(
        None, trust_operations=Constraints(), enforcement_mode=mode
    )
    if mode == "enforcing":
        with pytest.raises(PermissionError) as error:
            await executor.check_write_access(PAYLOAD, PAYLOAD, PAYLOAD)
        assert PAYLOAD in str(error.value)
    else:
        result = await executor.check_write_access(PAYLOAD, PAYLOAD, PAYLOAD)
        assert result.allowed is True
        if mode == "permissive":
            assert PAYLOAD in result.denied_reason
            assert result.applied_constraints == ["action_restriction:read_only"]
            assert_safe_records(caplog)
        else:
            assert result.denied_reason is None
            assert result.applied_constraints == []
