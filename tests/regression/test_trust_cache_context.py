"""Every serialized trust-context value participates in decision reuse."""

import asyncio
from types import SimpleNamespace

import pytest

from kailash.runtime.trust.context import RuntimeTrustContext
from kailash.runtime.trust.verifier import (
    MockTrustVerifier,
    TrustVerifier,
    TrustVerifierConfig,
)

pytestmark = pytest.mark.regression
ARGS = {
    "workflow": ("wf", "agent"),
    "node": ("node", "Type", "agent"),
    "resource": ("resource", "read", "agent"),
}


class ContextBackend:
    def __init__(self):
        self.calls = []

    async def verify(self, **kwargs):
        self.calls.append(kwargs)
        allowed = kwargs["context"]["constraints"]["access"]
        return SimpleNamespace(
            valid=allowed,
            reason="allowed" if allowed else "context denied",
            effective_constraints=[],
            capability_used=None,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ARGS)
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_tightened_context_never_reuses_a_weaker_allow(surface, mode):
    backend = ContextBackend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode=mode))
    original = RuntimeTrustContext(constraints={"access": True})
    tighter = original.with_constraints({"access": False})
    operation = getattr(verifier, f"verify_{surface}_access")
    assert (await operation(*ARGS[surface], original)).allowed
    result = await operation(*ARGS[surface], tighter)
    again = await operation(*ARGS[surface], tighter)
    assert result.allowed is again.allowed is (mode == "permissive")
    assert (
        result.reason
        == again.reason
        == ("PERMISSIVE: " if mode == "permissive" else "") + "context denied"
    )
    assert len(backend.calls) == 2
    assert backend.calls[0]["context"]["constraints"] == {"access": True}
    assert backend.calls[1]["context"]["constraints"] == {"access": False}
    assert verifier.invalidate_agent("agent") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ARGS)
@pytest.mark.parametrize("kind", ["real", "mock"])
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_context_trace_identity_is_never_borrowed(surface, kind, mode):
    backend = ContextBackend()
    config = TrustVerifierConfig(mode=mode)
    verifier = (
        TrustVerifier(backend, config)
        if kind == "real"
        else MockTrustVerifier(default_allow=False, config=config)
    )
    first = RuntimeTrustContext(trace_id="first", constraints={"access": False})
    second = RuntimeTrustContext.from_dict(first.to_dict())
    second.trace_id = "second"
    operation = getattr(verifier, f"verify_{surface}_access")
    for context in (first, second, first, second):
        result = await operation(*ARGS[surface], context)
        assert result.trace_id == context.trace_id
        assert result.allowed is (mode == "permissive")
    assert len(verifier._cache) == 2
    if kind == "real":
        assert len(backend.calls) == 2
    if surface == "node":
        assert verifier.invalidate_node("Type") == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "human_origin",
        "delegation_chain",
        "delegation_depth",
        "workflow_id",
        "node_path",
        "metadata",
        "verification_mode",
        "created_at",
    ],
)
async def test_other_context_fields_are_not_dropped_from_identity(field):
    from datetime import timedelta

    from kailash.runtime.trust.context import TrustVerificationMode

    first = RuntimeTrustContext(constraints={"access": True})
    second = RuntimeTrustContext.from_dict(first.to_dict())
    replacement = {
        "human_origin": {"origin": "different"},
        "delegation_chain": ["other"],
        "delegation_depth": 1,
        "workflow_id": "other",
        "node_path": ["other"],
        "metadata": {"tenant": "different"},
        "verification_mode": TrustVerificationMode.ENFORCING,
        "created_at": first.created_at + timedelta(seconds=1),
    }[field]
    setattr(second, field, replacement)
    expected = first.to_dict()

    class Policy:
        def __init__(self):
            self.calls = []

        async def verify(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                valid=kwargs["context"] == expected,
                reason="context policy",
                effective_constraints=[],
                capability_used=None,
            )

    backend = Policy()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    assert (await verifier.verify_workflow_access("wf", "agent", first)).allowed
    assert not (await verifier.verify_workflow_access("wf", "agent", second)).allowed
    assert len(backend.calls) == 2
    assert backend.calls[1]["context"] == second.to_dict()


@pytest.mark.asyncio
@pytest.mark.parametrize("shape", ["opaque", "cycle", "deep"])
async def test_unrepresentable_context_is_forwarded_but_never_cached(shape):
    class Opaque:
        def __str__(self):
            raise AssertionError("context identity must never stringify objects")

    value = Opaque() if shape == "opaque" else []
    if shape == "cycle":
        value.append(value)
    elif shape == "deep":
        for _ in range(40):
            value = [value]
    context = RuntimeTrustContext(
        constraints={"access": True}, metadata={"value": value}
    )
    backend = ContextBackend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    assert (await verifier.verify_workflow_access("wf", "agent", context)).allowed
    context.constraints["access"] = False
    assert not (await verifier.verify_workflow_access("wf", "agent", context)).allowed
    assert len(backend.calls) == 2 and not verifier._cache
    assert backend.calls[0]["context"]["metadata"]["value"] is value


@pytest.mark.asyncio
async def test_nested_context_is_snapshotted_before_backend_await():
    entered, release = asyncio.Event(), asyncio.Event()
    context = RuntimeTrustContext(
        constraints={"access": True}, metadata={"policy": {"allow": True}}
    )

    class Backend(ContextBackend):
        async def verify(self, **kwargs):
            self.calls.append(kwargs)
            entered.set()
            await release.wait()
            return SimpleNamespace(
                valid=kwargs["context"]["metadata"]["policy"]["allow"],
                reason="snapshot policy",
                effective_constraints=[],
                capability_used=None,
            )

    backend = Backend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    task = asyncio.create_task(verifier.verify_workflow_access("wf", "agent", context))
    await entered.wait()
    context.metadata["policy"]["allow"] = False
    release.set()
    assert (await task).allowed
    assert not (await verifier.verify_workflow_access("wf", "agent", context)).allowed
    assert len(backend.calls) == 2
    assert backend.calls[0]["context"]["metadata"]["policy"] == {"allow": True}


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ARGS)
async def test_context_serialization_failure_keeps_failure_diagnostics_and_decision(
    caplog, surface
):
    secret = "opaque-context-error-canary-735191"

    class BrokenContext(RuntimeTrustContext):
        def to_dict(self):
            raise RuntimeError(secret)

    backend = ContextBackend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    result = await getattr(verifier, f"verify_{surface}_access")(
        *ARGS[surface], BrokenContext()
    )
    assert not result.allowed and secret in result.reason
    assert not backend.calls and not verifier._cache
    records = [
        r.getMessage()
        for r in caplog.records
        if r.name == "kailash.runtime.trust.verifier"
    ]
    assert records and all(secret not in text for text in records)


@pytest.mark.parametrize(
    "first,second",
    [
        (True, 1),
        (1, 1.0),
        (0.0, -0.0),
        (["value"], ("value",)),
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
    ],
)
def test_context_tokens_preserve_builtin_types_and_order(first, second):
    from kailash.runtime.trust.verifier import _prepare_cache_context

    context = RuntimeTrustContext(metadata={"value": first})
    first_data, first_key, error = _prepare_cache_context(context)
    assert error is None and first_key is not None
    context.metadata["value"] = second
    second_data, second_key, error = _prepare_cache_context(context)
    assert error is None and second_key is not None
    assert first_key != second_key
    assert type(first_data["metadata"]["value"]) is type(first)
    assert type(second_data["metadata"]["value"]) is type(second)


@pytest.mark.asyncio
async def test_context_serialization_occurs_once_per_request_including_cache_hit():
    class CountedContext(RuntimeTrustContext):
        count = 0

        def to_dict(self):
            self.count += 1
            return super().to_dict()

    context = CountedContext(constraints={"access": True})
    backend = ContextBackend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode="enforcing"))
    for expected_count in (1, 2):
        assert (await verifier.verify_workflow_access("wf", "agent", context)).allowed
        assert context.count == expected_count
    assert len(backend.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "surface,invalidation",
    [
        ("workflow", "agent"),
        ("node", "agent"),
        ("resource", "agent"),
        ("node", "node"),
        ("workflow", "clear"),
        ("node", "clear"),
        ("resource", "clear"),
    ],
)
@pytest.mark.parametrize("with_context", [False, True])
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_invalidation_prevents_late_publication_of_inflight_allow(
    surface, invalidation, with_context, mode
):
    class Backend:
        def __init__(self):
            self.entered = asyncio.Event()
            self.release = asyncio.Event()
            self.allowed = True
            self.calls = 0

        async def verify(self, **kwargs):
            self.calls += 1
            decision = self.allowed
            if self.calls == 1:
                self.entered.set()
                await self.release.wait()
            return SimpleNamespace(
                valid=decision,
                reason="captured allow" if decision else "revoked",
                effective_constraints=[],
                capability_used=None,
            )

    backend = Backend()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode=mode))
    operation = getattr(verifier, f"verify_{surface}_access")
    context = RuntimeTrustContext() if with_context else None
    pending = asyncio.create_task(operation(*ARGS[surface], context))
    try:
        await backend.entered.wait()
        backend.allowed = False
        if invalidation == "agent":
            assert verifier.invalidate_agent("agent") == 0
        elif invalidation == "node":
            assert verifier.invalidate_node("Type") == 0
        else:
            verifier.clear_cache()
    finally:
        backend.release.set()
    assert (await pending).allowed  # Already-started backend decision may finish.
    assert not verifier._cache  # Its older decision may not publish after revocation.
    for _ in range(2):
        result = await operation(*ARGS[surface], context)
        assert result.allowed is (mode == "permissive")
        assert (
            result.reason
            == ("PERMISSIVE: " if mode == "permissive" else "") + "revoked"
        )
    assert backend.calls == 2  # One fresh denial then genuine cache reuse.


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ARGS)
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_nonstring_trust_metadata_reaches_shared_credential_mask(
    caplog, surface, mode
):
    secret = "bytes-trust-credential-canary-902147"
    payload = f"https://user:{secret}@example.invalid/?token={secret}".encode()
    calls = []

    class Backend:
        async def verify(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                valid=False,
                reason=payload,
                effective_constraints=[],
                capability_used=None,
            )

    verifier = TrustVerifier(Backend(), TrustVerifierConfig(mode=mode))
    args = (*ARGS[surface][:-1], payload)
    result = await getattr(verifier, f"verify_{surface}_access")(*args)
    assert result.allowed is (mode == "permissive")
    assert result.reason == (
        f"PERMISSIVE: {payload}" if mode == "permissive" else payload
    )
    assert calls[0]["agent_id"] == payload
    records = [
        r.getMessage()
        for r in caplog.records
        if r.name == "kailash.runtime.trust.verifier"
    ]
    assert records and all(
        secret not in text and text.isprintable() for text in records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ARGS)
@pytest.mark.parametrize("mode", ["enforcing", "permissive"])
async def test_metaclass_equality_cannot_promote_opaque_values_into_cache(
    surface, mode
):
    equality_calls = []

    class PretendBuiltin(type):
        def __eq__(cls, other):
            equality_calls.append(other)
            return other is str or type.__eq__(cls, other)

        __hash__ = type.__hash__

    class OpaquePolicyValue(metaclass=PretendBuiltin):
        def __init__(self, allowed):
            self.allowed = allowed

        def __eq__(self, other):
            return isinstance(other, OpaquePolicyValue)

        def __hash__(self):
            return 1

    class Policy:
        def __init__(self):
            self.calls = []

        async def verify(self, **kwargs):
            self.calls.append(kwargs)
            allowed = kwargs["context"]["constraints"]["opaque"].allowed
            return SimpleNamespace(
                valid=allowed,
                reason="allowed" if allowed else "context denied",
                effective_constraints=[],
                capability_used=None,
            )

    backend = Policy()
    verifier = TrustVerifier(backend, TrustVerifierConfig(mode=mode))
    original = OpaquePolicyValue(True)
    tightened = OpaquePolicyValue(False)
    context = RuntimeTrustContext(constraints={"opaque": original})
    operation = getattr(verifier, f"verify_{surface}_access")
    assert (await operation(*ARGS[surface], context)).allowed
    context.constraints["opaque"] = tightened
    result = await operation(*ARGS[surface], context)
    repeated = await operation(*ARGS[surface], context)
    assert result.allowed is repeated.allowed is (mode == "permissive")
    assert (
        result.reason
        == repeated.reason
        == ("PERMISSIVE: " if mode == "permissive" else "") + "context denied"
    )
    assert len(backend.calls) == 3
    assert backend.calls[-1]["context"]["constraints"]["opaque"] is tightened
    assert not verifier._cache
    assert equality_calls == []
