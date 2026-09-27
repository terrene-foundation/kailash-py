"""Cache identity cannot transfer trust decisions across raw caller fields."""

from types import SimpleNamespace

import pytest

from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
)

PAIRS = {
    "workflow": (("scope\x00user", "principal"), ("scope", "user\x00principal")),
    "node": (
        ("item\x00Kind", "Type", "principal"),
        ("item", "Kind\x00Type", "principal"),
    ),
    "resource": (
        ("resource", "read\x00agent", "other"),
        ("resource", "read", "agent\x00other"),
    ),
}


def request_identity(surface, args):
    if surface == "workflow":
        return {"agent_id": args[1], "action": "execute_workflow:" + args[0]}
    if surface == "node":
        return {
            "agent_id": args[2],
            "action": "execute_node:" + args[1] + ":" + args[0],
        }
    return {"agent_id": args[2], "resource": args[0], "action": args[1]}


class PolicyBackend:
    def __init__(self, permitted=None):
        self.permitted = permitted
        self.calls = []

    async def verify(self, **kwargs):
        self.calls.append(kwargs)
        valid = self.permitted is None or all(
            kwargs.get(k) == v for k, v in self.permitted.items()
        )
        return SimpleNamespace(
            valid=valid,
            reason="allowed identity" if valid else "denied identity",
            effective_constraints=[],
            capability_used=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", PAIRS)
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_real_cache_keeps_nul_delimited_identities_distinct(surface, mode):
    first, second = PAIRS[surface]
    backend = PolicyBackend(request_identity(surface, first))
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode=mode))
    operation = getattr(verifier, "verify_" + surface + "_access")
    allowed = await operation(*first)
    denied = await operation(*second)
    cached_denied = await operation(*second)
    cached_allowed = await operation(*first)
    assert allowed.allowed and cached_allowed.allowed
    assert denied.allowed is cached_denied.allowed is (mode == "permissive")
    assert (
        denied.reason
        == cached_denied.reason
        == ("PERMISSIVE: " if mode == "permissive" else "") + "denied identity"
    )
    assert len(backend.calls) == 2
    for key, value in request_identity(surface, second).items():
        assert backend.calls[1][key] == value
    assert len(verifier._cache) == 2
    assert all(isinstance(key, tuple) for key in verifier._cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", PAIRS)
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_mock_cache_keeps_identity_and_mode_on_repeated_access(surface, mode):
    first, second = PAIRS[surface]
    config = TrustVerifierConfig(mode=mode)
    options = (
        {"denied_nodes": [second[1]]}
        if surface == "node"
        else {"denied_agents": [second[-1]]}
    )
    verifier = MockTrustVerifier(default_allow=True, config=config, **options)
    operation = getattr(verifier, "verify_" + surface + "_access")
    assert (await operation(*first)).allowed
    denied = await operation(*second)
    cached = await operation(*second)
    assert denied.allowed is cached.allowed is (mode == "permissive")
    assert denied.reason == cached.reason
    assert "denied" in denied.reason
    assert len(verifier._cache) == 2
    assert all(isinstance(key, tuple) for key in verifier._cache)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["real", "mock"])
async def test_agent_revocation_matches_complete_agent_field(kind):
    backend = PolicyBackend()
    verifier = (
        TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
        if kind == "real"
        else MockTrustVerifier()
    )
    await verifier.verify_workflow_access("wf", "target")
    await verifier.verify_workflow_access("wf", "other\x00target")
    assert verifier.invalidate_agent("target") == 1
    assert set(verifier._cache) == {("wf", "wf", "other\x00target")}
    assert (await verifier.verify_workflow_access("wf", "other\x00target")).allowed
    assert verifier.invalidate_agent("other\x00target") == 1
    assert not verifier._cache
    if kind == "real":
        assert len(backend.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["real", "mock"])
async def test_node_revocation_matches_type_field_not_embedded_text(kind):
    verifier = (
        TrustVerifier(PolicyBackend(), TrustVerifierConfig(mode="enforcing"))
        if kind == "real"
        else MockTrustVerifier()
    )
    await verifier.verify_node_access("node", "Chosen", "agent")
    await verifier.verify_node_access("node", "prefix\x00Chosen\x00suffix", "agent")
    await verifier.verify_node_access("embedded\x00Chosen", "Other", "agent")
    assert verifier.invalidate_node("Chosen") == 1
    assert set(verifier._cache) == {
        ("node", "node", "prefix\x00Chosen\x00suffix", "agent"),
        ("node", "embedded\x00Chosen", "Other", "agent"),
    }
    assert verifier.invalidate_node("Other") == 1
    assert verifier.invalidate_node("prefix\x00Chosen\x00suffix") == 1
    assert not verifier._cache


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", PAIRS)
@pytest.mark.parametrize("audit", [False, True])
async def test_mock_permissive_cache_uses_same_audit_path(caplog, surface, audit):
    verifier = MockTrustVerifier(
        default_allow=False,
        config=TrustVerifierConfig(mode="permissive", audit_denials=audit),
    )
    operation = getattr(verifier, "verify_" + surface + "_access")
    args = PAIRS[surface][0]
    first = await operation(*args)
    caplog.clear()
    cached = await operation(*args)
    assert first.allowed and cached.allowed
    assert first.reason == cached.reason
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == "kailash.runtime.trust.verifier"
    ]
    assert any("PERMISSIVE mode: allowing denied operation" in m for m in messages)
    assert any("Trust verification DENIED" in m for m in messages) is audit
