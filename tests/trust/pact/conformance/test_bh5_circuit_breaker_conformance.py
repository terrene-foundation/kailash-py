# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""BH5 (#1510) conformance -- cross-SDK behavioural vectors for the governance
circuit-breaker AND the sliding-window rate enforcer it stands beside.

Unlike the byte-pinned signing pre-image vectors (BH3), these pin the STATE
MACHINE's observable behaviour: the Rust SDK drives the same vectors through its
sibling breaker / rate enforcer and MUST reproduce the same admit/block +
state transitions for cross-implementation conformance (EATP D6).

``encoding="utf-8"`` on EVERY vector read is LOAD-BEARING (issue #1590
Windows-CI fix). The vector JSON carries NO non-finite float literal
(trust-plane-security MUST-8); a fail-closed case is expressed via an
``inject_nonfinite`` marker the driver decodes to ``float('nan')`` at runtime.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from kailash.trust.pact.circuit_breaker import (
    CircuitBreakerConfig,
    PactCircuitBreaker,
)
from kailash.trust.pact.rate_limit_enforcer import RateLimitEnforcer

UTC = timezone.utc
VECTORS_DIR = Path(__file__).parent / "vectors"

# The two BH5-family vector files this test owns (exact-set orphan guard).
BH5_VECTORS = [
    "circuit_breaker.json",
    "rate_limit_enforcement.json",
]


def _load(name: str) -> dict:
    return json.loads((VECTORS_DIR / name).read_text(encoding="utf-8"))


def _at(t: float) -> datetime:
    return datetime.fromtimestamp(t, tz=UTC)


class TestBh5VectorIntegrity:
    """The BH5 family owns its own exact-set orphan check (mirrors BH3)."""

    def test_all_expected_bh5_vectors_present(self) -> None:
        for name in BH5_VECTORS:
            assert (VECTORS_DIR / name).exists(), f"missing BH5 vector {name}"
        # Orphan direction: every vector tagged conformance_family=="bh5" MUST be
        # declared here -- a new bh5 vector file that this test does not drive is
        # a coverage gap the exact-set assertion surfaces loudly.
        tagged = sorted(
            p.name
            for p in VECTORS_DIR.glob("*.json")
            if json.loads(p.read_text(encoding="utf-8")).get("conformance_family")
            == "bh5"
        )
        assert tagged == sorted(BH5_VECTORS), (
            f"BH5 vector set mismatch.\n"
            f"Declared: {sorted(BH5_VECTORS)}\nTagged bh5: {tagged}"
        )


class TestCircuitBreakerConformance:
    """Drive PactCircuitBreaker through every circuit_breaker.json vector."""

    @pytest.mark.parametrize(
        "vector",
        _load("circuit_breaker.json")["vectors"],
        ids=lambda v: v["name"],
    )
    def test_circuit_breaker_vector(self, vector: dict) -> None:
        br = PactCircuitBreaker()
        if "max_entries" in vector:
            br._MAX_TRACKER_ENTRIES = vector["max_entries"]
        cfg = CircuitBreakerConfig(
            vector["config"]["failure_threshold"],
            vector["config"]["window_seconds"],
            vector["config"]["cooldown_seconds"],
        )
        key = vector["key"]

        for ev in vector["events"]:
            now = _at(ev["t"])

            if ev.get("inject_nonfinite"):
                axis = ev["inject_nonfinite"]
                bad = CircuitBreakerConfig(
                    float("nan") if axis == "threshold" else cfg.failure_threshold,
                    float("nan") if axis == "window" else cfg.window_seconds,
                    float("nan") if axis == "cooldown" else cfg.cooldown_seconds,
                )
                with pytest.raises(ValueError):
                    br.check(key, bad, now)
                continue

            decision = br.check(key, cfg, now)
            assert decision.level == ev["expect_level"], ev
            assert decision.state == ev["expect_state"], ev
            if "expect_probe" in ev:
                assert decision.was_probe == ev["expect_probe"], ev

            do_record = ev.get("do_record", True)
            if decision.record and do_record and "breached" in ev:
                br.record(
                    key,
                    cfg,
                    now,
                    breached=ev["breached"],
                    was_probe=decision.was_probe,
                )


class TestRateLimitEnforcementConformance:
    """Drive RateLimitEnforcer through every rate_limit_enforcement.json vector."""

    @pytest.mark.parametrize(
        "vector",
        _load("rate_limit_enforcement.json")["vectors"],
        ids=lambda v: v["name"],
    )
    def test_rate_limit_vector(self, vector: dict) -> None:
        enf = RateLimitEnforcer()
        if "max_entries" in vector:
            enf._MAX_TRACKER_ENTRIES = vector["max_entries"]

        for ev in vector["events"]:
            specs = [(s["key"], s["limit"], s["window_seconds"]) for s in ev["specs"]]
            breach = enf.check_and_record(specs, _at(ev["t"]))
            expected = ev["expect_breach"]
            if expected is None:
                assert breach is None, ev
            else:
                assert breach is not None, ev
                assert breach.kind == expected["kind"], ev
                assert breach.limit == expected["limit"], ev
