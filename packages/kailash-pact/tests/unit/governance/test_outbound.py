# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for the universal outbound-effect governance interceptor (#1517 leg-b).

Covers the domain-neutral core in kailash.trust.pact.outbound:
- OutboundEffect validation (NaN/Inf/negative/empty-op/unknown-kind fail-closed)
- OutboundVerdict serialization
- OutboundEffectInterceptor allow -> invoke; refuse -> raise + invoke NOT called
- Fail-closed when the governor raises
- Bounded audit trail (deque maxlen)
- wrap_transport / wrap_transport_async transparent seam
- Process-global install registry
- EngineEffectGovernor reusing a REAL GovernanceEngine (university org)
"""

from __future__ import annotations

import asyncio

import pytest

from kailash.trust.pact.engine import GovernanceEngine
from kailash.trust.pact.outbound import (
    DEFAULT_MAX_AUDIT_ENTRIES,
    EffectGovernor,
    EffectKind,
    EngineEffectGovernor,
    OutboundEffect,
    OutboundEffectInterceptor,
    OutboundEffectRefused,
    OutboundVerdict,
    active_interceptor,
    clear_interceptor,
    install_interceptor,
    wrap_transport,
    wrap_transport_async,
)
from pact.examples.university.org import create_university_org

# An HR-Director role with no envelope set -> auto_approved for any action.
ALLOWED_CALLER = "D1-R1-D2-R1-T1-R1"
# A grammar-valid-but-nonexistent address -> fail-closed BLOCKED at the engine.
REFUSED_CALLER = "INVALID-ADDRESS-DOES-NOT-EXIST"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> GovernanceEngine:
    compiled, _ = create_university_org()
    return GovernanceEngine(compiled)


@pytest.fixture
def interceptor(engine: GovernanceEngine) -> OutboundEffectInterceptor:
    return OutboundEffectInterceptor(EngineEffectGovernor(engine))


# ---------------------------------------------------------------------------
# OutboundEffect validation
# ---------------------------------------------------------------------------


class TestOutboundEffect:
    def test_valid_effect_freezes_metadata(self) -> None:
        eff = OutboundEffect(
            kind=EffectKind.HTTP,
            operation="http.POST",
            target="api.example.com",
            cost_estimate=2.5,
            caller="D1-R1",
            metadata={"k": "v"},
        )
        assert eff.kind is EffectKind.HTTP
        assert eff.governance_context()["cost"] == 2.5
        assert eff.governance_context()["effect_kind"] == "http"
        # metadata is a read-only view
        with pytest.raises(TypeError):
            eff.metadata["x"] = 1  # type: ignore[index]

    def test_nan_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            OutboundEffect(
                kind=EffectKind.LLM, operation="llm.chat", cost_estimate=float("nan")
            )

    def test_inf_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            OutboundEffect(
                kind=EffectKind.LLM, operation="llm.chat", cost_estimate=float("inf")
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            OutboundEffect(kind=EffectKind.TOOL, operation="tool.x", cost_estimate=-1.0)

    def test_empty_operation_rejected(self) -> None:
        with pytest.raises(ValueError, match="operation"):
            OutboundEffect(kind=EffectKind.TOOL, operation="   ")

    def test_bool_cost_rejected(self) -> None:
        # bool is a subclass of int; a boolean cost is a type-confusion bug.
        with pytest.raises(ValueError, match="real number"):
            OutboundEffect(
                kind=EffectKind.HTTP, operation="http.GET", cost_estimate=True  # type: ignore[arg-type]
            )

    def test_from_dict_roundtrip(self) -> None:
        eff = OutboundEffect(
            kind=EffectKind.TOOL,
            operation="tool.search",
            target="search",
            cost_estimate=3.0,
        )
        assert OutboundEffect.from_dict(eff.to_dict()) == eff

    def test_from_dict_unknown_kind_fails_closed(self) -> None:
        with pytest.raises(ValueError, match="Unknown EffectKind"):
            OutboundEffect.from_dict({"kind": "telepathy", "operation": "x"})


# ---------------------------------------------------------------------------
# OutboundVerdict
# ---------------------------------------------------------------------------


def test_verdict_to_dict() -> None:
    eff = OutboundEffect(kind=EffectKind.HTTP, operation="http.GET")
    v = OutboundVerdict(allowed=True, level="auto_approved", reason="ok", effect=eff)
    d = v.to_dict()
    assert d["allowed"] is True
    assert d["effect"]["operation"] == "http.GET"
    assert "timestamp" in d


# ---------------------------------------------------------------------------
# Interceptor allow / refuse (real engine)
# ---------------------------------------------------------------------------


class TestInterceptorSync:
    def test_allowed_effect_invokes_transport(
        self, interceptor: OutboundEffectInterceptor
    ) -> None:
        eff = OutboundEffect(
            kind=EffectKind.HTTP, operation="read", caller=ALLOWED_CALLER
        )
        ran = {"called": False}

        def invoke() -> str:
            ran["called"] = True
            return "response-body"

        result = interceptor.intercept(eff, invoke)
        assert result == "response-body"
        assert ran["called"] is True
        assert interceptor.audit_log()[-1].allowed is True

    def test_refused_effect_does_not_invoke_transport(
        self, interceptor: OutboundEffectInterceptor
    ) -> None:
        eff = OutboundEffect(
            kind=EffectKind.HTTP, operation="read", caller=REFUSED_CALLER
        )
        ran = {"called": False}

        def invoke() -> str:
            ran["called"] = True
            return "should-never-return"

        with pytest.raises(OutboundEffectRefused) as excinfo:
            interceptor.intercept(eff, invoke)
        # Fail-closed: transport NEVER ran.
        assert ran["called"] is False
        assert excinfo.value.verdict.allowed is False
        assert interceptor.audit_log()[-1].allowed is False


class TestInterceptorAsync:
    def test_allowed_async_effect_invokes(
        self, interceptor: OutboundEffectInterceptor
    ) -> None:
        eff = OutboundEffect(
            kind=EffectKind.LLM, operation="read", caller=ALLOWED_CALLER
        )
        ran = {"called": False}

        async def invoke() -> str:
            ran["called"] = True
            return "async-body"

        result = asyncio.run(interceptor.aintercept(eff, invoke))
        assert result == "async-body"
        assert ran["called"] is True

    def test_refused_async_effect_does_not_invoke(
        self, interceptor: OutboundEffectInterceptor
    ) -> None:
        eff = OutboundEffect(
            kind=EffectKind.LLM, operation="read", caller=REFUSED_CALLER
        )
        ran = {"called": False}

        async def invoke() -> str:
            ran["called"] = True
            return "nope"

        with pytest.raises(OutboundEffectRefused):
            asyncio.run(interceptor.aintercept(eff, invoke))
        assert ran["called"] is False


# ---------------------------------------------------------------------------
# Fail-closed when the governor raises
# ---------------------------------------------------------------------------


class _RaisingGovernor(EffectGovernor):
    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        raise RuntimeError("governor contract violation")


def test_governor_raise_fails_closed() -> None:
    interceptor = OutboundEffectInterceptor(_RaisingGovernor())
    eff = OutboundEffect(kind=EffectKind.HTTP, operation="read", caller=ALLOWED_CALLER)
    ran = {"called": False}

    def invoke() -> str:
        ran["called"] = True
        return "x"

    with pytest.raises(OutboundEffectRefused):
        interceptor.intercept(eff, invoke)
    assert ran["called"] is False  # never ran despite governor bug


# ---------------------------------------------------------------------------
# Bounded audit trail
# ---------------------------------------------------------------------------


class _AllowGovernor(EffectGovernor):
    def evaluate(self, effect: OutboundEffect) -> OutboundVerdict:
        return OutboundVerdict(
            allowed=True, level="auto_approved", reason="ok", effect=effect
        )


def test_audit_trail_is_bounded() -> None:
    interceptor = OutboundEffectInterceptor(_AllowGovernor(), max_audit_entries=5)
    for i in range(20):
        interceptor.intercept(
            OutboundEffect(kind=EffectKind.TOOL, operation=f"tool.op{i}"),
            lambda: None,
        )
    log = interceptor.audit_log()
    assert len(log) == 5  # deque(maxlen=5) capped
    # oldest evicted; newest retained
    assert log[-1].effect.operation == "tool.op19"


def test_default_max_audit_positive() -> None:
    assert DEFAULT_MAX_AUDIT_ENTRIES > 0


def test_invalid_governor_type_rejected() -> None:
    with pytest.raises(TypeError):
        OutboundEffectInterceptor(object())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# wrap_transport / wrap_transport_async transparent seam
# ---------------------------------------------------------------------------


def test_wrap_transport_sync_is_transparent() -> None:
    interceptor = OutboundEffectInterceptor(_AllowGovernor())

    def raw_send(method: str, url: str) -> str:
        return f"{method} {url}"

    def builder(args, kwargs):
        return OutboundEffect(
            kind=EffectKind.HTTP, operation=f"http.{args[0]}", target=args[1]
        )

    governed = wrap_transport(interceptor, builder, raw_send)
    # Same signature, same result -- caller code unchanged.
    assert governed("GET", "example.com") == "GET example.com"
    assert interceptor.audit_log()[-1].effect.target == "example.com"


def test_wrap_transport_async_is_transparent() -> None:
    interceptor = OutboundEffectInterceptor(_AllowGovernor())

    async def raw_send(payload: str) -> str:
        return payload.upper()

    def builder(args, kwargs):
        return OutboundEffect(kind=EffectKind.LLM, operation="llm.chat")

    governed = wrap_transport_async(interceptor, builder, raw_send)
    assert asyncio.run(governed("hi")) == "HI"


# ---------------------------------------------------------------------------
# Install registry
# ---------------------------------------------------------------------------


def test_install_and_active_interceptor() -> None:
    clear_interceptor()
    assert active_interceptor() is None
    interceptor = OutboundEffectInterceptor(_AllowGovernor())
    install_interceptor(interceptor)
    try:
        assert active_interceptor() is interceptor
    finally:
        clear_interceptor()
    assert active_interceptor() is None
