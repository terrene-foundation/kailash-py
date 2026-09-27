"""Trust decisions retain raw inputs while automatic diagnostics remain inert."""

import json
from types import SimpleNamespace

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.runtime.trust.context import RuntimeTrustContext
from kailash.runtime.trust.verifier import TrustVerifier, TrustVerifierConfig
from kailash.workflow import Workflow

pytestmark = pytest.mark.regression


class RecordingBackend:
    """Deterministic unit-test backend; the production TrustVerifier runs normally."""

    def __init__(self, reason, *, valid=False, fail=False):
        self.reason = reason
        self.valid = valid
        self.fail = fail
        self.calls = []

    async def verify(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError(self.reason)
        return SimpleNamespace(
            valid=self.valid,
            reason=self.reason,
            effective_constraints=[],
            capability_used=None,
        )


def trust_records(caplog):
    return [
        record
        for record in caplog.records
        if record.name in {"kailash.runtime.base", "kailash.runtime.trust.verifier"}
    ]


def assert_inert(records, secret):
    assert records
    for record in records:
        text = record.getMessage()
        assert all(character.isprintable() for character in text), repr(text)
        assert len(text) < 2400
        assert secret not in text
        assert record.exc_info is None


@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
@pytest.mark.parametrize(
    "surface,field",
    [("workflow", field) for field in ("workflow_id", "agent_id", "reason")]
    + [("node", field) for field in ("node_id", "node_type", "agent_id", "reason")],
)
@pytest.mark.parametrize(
    "shape", ["controls", "credentials", "json_credentials", "oversize"]
)
@pytest.mark.asyncio
async def test_denial_fields_are_log_only_transforms(
    caplog, mode, surface, field, shape
):
    secret = "trust-credential-canary-823791"
    values = dict(
        workflow_id="workflow-1",
        node_id="node-1",
        node_type="PythonCode",
        agent_id="agent-1",
        reason="policy denied",
    )
    payloads = {
        "controls": "caller\nERROR forged\r\x00\x1b[31m\u2028\u202e",
        "credentials": f"https://user:{secret}@example.invalid/path?token={secret}",
        "json_credentials": json.dumps({"password": secret, "message": "denied"}),
        "oversize": "prefix-" + "z" * 12000,
    }
    values[field] = payloads[shape]
    backend = RecordingBackend(values["reason"])
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    context = RuntimeTrustContext(delegation_chain=[values["agent_id"]])
    workflow = Workflow(workflow_id=values["workflow_id"], name="trust-log-test")
    with LocalRuntime(trust_verification_mode=mode, trust_verifier=verifier) as runtime:
        caplog.clear()
        if surface == "workflow":
            allowed = await runtime._verify_workflow_trust(workflow, context)
            raw = await verifier.verify_workflow_access(
                values["workflow_id"], values["agent_id"], context
            )
            expected_action = f"execute_workflow:{values['workflow_id']}"
        else:
            allowed = await runtime._verify_node_trust(
                values["node_id"], values["node_type"], context
            )
            raw = await verifier.verify_node_access(
                values["node_id"], values["node_type"], values["agent_id"], context
            )
            expected_action = f"execute_node:{values['node_type']}:{values['node_id']}"
        assert allowed is (mode == "permissive")
        assert raw.allowed is False
        assert raw.reason == values["reason"]
        assert len(backend.calls) == 1
        assert backend.calls[0]["action"] == expected_action
        assert backend.calls[0]["agent_id"] == values["agent_id"]
        assert backend.calls[0]["context"]["delegation_chain"] == [values["agent_id"]]
        records = trust_records(caplog)
        assert len(records) == 3
        assert {record.name for record in records} == {
            "kailash.runtime.base",
            "kailash.runtime.trust.verifier",
        }
        assert_inert(records, secret)
        assert "Trust verification" in records[-1].getMessage()


@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
@pytest.mark.parametrize("surface", ["workflow", "node", "resource"])
@pytest.mark.parametrize("fail", [False, True])
@pytest.mark.asyncio
async def test_real_verifier_denial_and_failure_siblings(caplog, mode, surface, fail):
    secret = "backend-credential-canary-643127"
    payload = f"https://user:{secret}@example.invalid/?token={secret}\nforged\x1b"
    backend = RecordingBackend(payload, fail=fail)
    verifier = TrustVerifier(
        backend, TrustVerifierConfig(mode=mode, fallback_allow=False)
    )
    if surface == "workflow":
        result = await verifier.verify_workflow_access(payload, payload)
    elif surface == "node":
        result = await verifier.verify_node_access(payload, payload, payload)
    else:
        result = await verifier.verify_resource_access(payload, payload, payload)
    assert result.allowed is (mode == "permissive")
    assert payload in result.reason
    assert backend.calls[0]["agent_id"] == payload
    assert_inert(trust_records(caplog), secret)
    if fail:
        assert any("RuntimeError@" in r.getMessage() for r in trust_records(caplog))
    if mode == "permissive":
        assert any(
            "allowing denied operation" in r.getMessage() for r in trust_records(caplog)
        )


@pytest.mark.parametrize("surface", ["workflow", "node"])
@pytest.mark.parametrize(
    "mode,valid", [("disabled", False), ("enforcing", True), ("permissive", True)]
)
@pytest.mark.asyncio
async def test_allowed_and_disabled_paths_preserve_behavior(
    caplog, surface, mode, valid
):
    backend = RecordingBackend("unused", valid=valid)
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    workflow = Workflow(workflow_id="normal", name="normal")
    with LocalRuntime(trust_verification_mode=mode, trust_verifier=verifier) as runtime:
        caplog.clear()
        if surface == "workflow":
            allowed = await runtime._verify_workflow_trust(workflow)
        else:
            allowed = await runtime._verify_node_trust("node", "PythonCode")
        assert allowed is True
        assert len(backend.calls) == (0 if mode == "disabled" else 1)
        assert not trust_records(caplog)


@pytest.mark.asyncio
async def test_revocation_log_preserves_raw_cache_identity(caplog):
    secret = "revoke-credential-canary-918273"
    agent = f"https://user:{secret}@example.invalid/\nforged"
    verifier = TrustVerifier(config=TrustVerifierConfig(mode="enforcing"))
    await verifier.verify_workflow_access("wf", agent)
    caplog.clear()
    with caplog.at_level("INFO", logger="kailash.runtime.trust.verifier"):
        assert verifier.invalidate_agent(agent) == 1
    assert_inert(trust_records(caplog), secret)
    assert verifier.invalidate_agent(agent) == 0


def test_log_field_handles_hostile_string_conversion():
    from kailash.runtime.trust.verifier import _safe_trust_log_field

    class HostileText(str):
        def __str__(self):
            raise AssertionError("must use builtin string normalization")

        def __len__(self):
            return 0

    class Unprintable:
        def __str__(self):
            raise ValueError("cannot render")

    secret = "subclass-credential-canary-291836"
    value = HostileText(f"https://user:{secret}@example.invalid/\n" + "a" * 12000)
    output = _safe_trust_log_field(value)
    assert secret not in output
    assert output.isprintable()
    assert len(output) <= 1024
    assert _safe_trust_log_field(Unprintable()) == "<unrepresentable>"


@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
@pytest.mark.parametrize("surface", ["workflow", "node", "resource"])
@pytest.mark.asyncio
async def test_opaque_exception_provenance_survives_cache_and_permissive(
    caplog, mode, surface
):
    from kailash.runtime.trust.verifier import _safe_trust_log_reason

    secret = "opaque-private-canary-735198"
    backend = RecordingBackend(secret, fail=True)
    verifier = TrustVerifier(
        backend, TrustVerifierConfig(mode=mode, fallback_allow=False)
    )

    async def operation():
        if surface == "workflow":
            return await verifier.verify_workflow_access("wf", "agent")
        if surface == "node":
            return await verifier.verify_node_access("node", "PythonCode", "agent")
        return await verifier.verify_resource_access("resource", "read", "agent")

    result = await operation()
    cached = await operation()
    assert len(backend.calls) == 1
    assert result.allowed is (mode == "permissive")
    assert cached.allowed is (mode == "permissive")
    assert (
        cached.reason
        == ("PERMISSIVE: " if mode == "permissive" else "")
        + f"Verification unavailable: {secret}"
    )
    assert result.reason == cached.reason
    for value in (result, cached):
        assert secret in value.to_dict()["reason"]
        assert "_log_reason" not in value.to_dict()
        assert "_log_reason" not in repr(value)
        assert "RuntimeError@" in _safe_trust_log_reason(value)
        assert secret not in _safe_trust_log_reason(value)
    assert_inert(trust_records(caplog), secret)


@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
@pytest.mark.parametrize("surface", ["workflow", "node"])
@pytest.mark.asyncio
async def test_opaque_exception_provenance_reaches_runtime_on_cached_access(
    caplog, mode, surface
):
    secret = "opaque-private-canary-735198"
    backend = RecordingBackend(secret, fail=True)
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    workflow = Workflow(workflow_id="wf", name="opaque-log-test")
    with LocalRuntime(trust_verification_mode=mode, trust_verifier=verifier) as runtime:
        caplog.clear()
        for _ in range(2):
            if surface == "workflow":
                allowed = await runtime._verify_workflow_trust(workflow)
            else:
                allowed = await runtime._verify_node_trust("node", "PythonCode")
            assert allowed is (mode == "permissive")
        assert len(backend.calls) == 1
        records = trust_records(caplog)
        assert (
            len(records) == 5
        )  # Backend failure, two verifier and two runtime denials.
        assert sum(r.name == "kailash.runtime.base" for r in records) == 2
        assert all("RuntimeError@" in r.getMessage() for r in records)
        assert_inert(records, secret)


def test_explicit_denial_reason_is_not_classified_by_prefix():
    from kailash.runtime.trust.verifier import (
        VerificationResult,
        _safe_trust_log_reason,
    )

    reason = "Verification unavailable: explicit policy diagnostic"
    result = VerificationResult(allowed=False, reason=reason)
    assert _safe_trust_log_reason(result) == reason


@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
@pytest.mark.parametrize("surface", ["workflow", "node", "resource"])
@pytest.mark.asyncio
async def test_cached_denial_preserves_mode_and_audit(caplog, mode, surface):
    backend = RecordingBackend("explicit policy denial")
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode=mode))
    args = {
        "workflow": ("wf", "agent"),
        "node": ("node", "PythonCode", "agent"),
        "resource": ("resource", "read", "agent"),
    }[surface]
    operation = getattr(verifier, f"verify_{surface}_access")
    first = await operation(*args)
    caplog.clear()
    cached = await operation(*args)
    assert first.allowed is cached.allowed is (mode == "permissive")
    assert first.reason == cached.reason
    assert (
        cached.reason
        == ("PERMISSIVE: " if mode == "permissive" else "") + backend.reason
    )
    assert len(backend.calls) == 1
    assert any(
        "Trust verification DENIED" in r.getMessage() for r in trust_records(caplog)
    )
    assert backend.calls[0]["agent_id"] == "agent"
