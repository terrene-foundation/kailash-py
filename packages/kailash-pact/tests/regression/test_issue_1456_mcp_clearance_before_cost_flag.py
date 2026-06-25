# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #1456 -- MCP clearance evaluated before cost flag.

The MCP governance enforcer advertises ``clearance_required`` on ``McpToolPolicy``
("Minimum confidentiality level required to invoke this tool") and the package
docstring advertises clearance enforcement. Before this fix the field was
DOCUMENTED-BUT-UNENFORCED: ``McpGovernanceEnforcer._evaluate`` never read it and
``McpActionContext`` carried no caller clearance, so a tool marked
``clearance_required="secret"`` was invokable by any caller -- an authorization
gap (zero-tolerance Rule 3c: a documented field with zero consumers).

The specific failure shape (cross-SDK sibling of kailash-rs#1492): a caller with
absent/insufficient clearance whose ``cost_estimate`` lands in the
``(0.8*max_cost, max_cost]`` soft-flag band received ``flagged`` (allowed)
because the cost-flag short-circuit ran before any clearance check. The fix
evaluates clearance as a fail-closed Layer-2 gate BEFORE the cost ladder, so an
unmet-clearance caller is BLOCKED regardless of cost band.

Acceptance criteria (issue #1456):
  1. Clearance is evaluated before any non-blocking cost-flag short-circuit.
  2. A no/insufficient-clearance caller in the (0.8*max, max] band is BLOCKED,
     not flagged.
  3. The 0.80 flagging threshold value is unchanged.

Fail-closed semantics (PACT governance Rule 4): when a policy sets
``clearance_required`` (even to "public"), the caller MUST present a clearance
that meets it. An absent, unrecognized, or insufficient caller clearance -- and
an unrecognized policy requirement -- all fail closed to BLOCKED. Policies that
do NOT set ``clearance_required`` are wholly unaffected (the common case).

Cross-SDK parity: kailash-rs#1492 (the issue's stated sibling). EATP D6 intends
independent implementations with matching semantics; the Python gate here is
independently correct and pins its own structural invariant (Rule 3a), but the
byte/semantic equivalence to the Rust enforcer is NOT verified in this Python
session (repo-scope) -- confirm via a kailash-rs session per
cross-sdk-inspection.md Rule 5. Clearance levels are ConfidentialityLevel
values ordered PUBLIC < RESTRICTED < CONFIDENTIAL < SECRET < TOP_SECRET.

Behavioral tests: each calls ``check_tool_call`` / middleware ``invoke`` and
asserts the resulting decision -- never grep over source.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from pact.mcp.enforcer import McpGovernanceEnforcer
from pact.mcp.middleware import McpGovernanceMiddleware
from pact.mcp.types import McpActionContext, McpGovernanceConfig, McpToolPolicy

# Fixed base instant so every test is fully deterministic (no wall-clock).
_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _enforcer(
    *,
    clearance_required: str | None = "secret",
    max_cost: float | None = 10.0,
) -> McpGovernanceEnforcer:
    return McpGovernanceEnforcer(
        McpGovernanceConfig(
            tool_policies={
                "search": McpToolPolicy(
                    tool_name="search",
                    max_cost=max_cost,
                    clearance_required=clearance_required,
                )
            },
            audit_enabled=False,
        )
    )


def _decide(
    enf: McpGovernanceEnforcer,
    *,
    cost_estimate: float | None = None,
    caller_clearance: str | None = None,
):
    return enf.check_tool_call(
        McpActionContext(
            tool_name="search",
            agent_id="agent-1",
            timestamp=_T0,
            cost_estimate=cost_estimate,
            caller_clearance=caller_clearance,
        )
    )


# ---------------------------------------------------------------------------
# Criterion 2 -- the core repro: unmet clearance in the soft-flag band BLOCKS
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
def test_unmet_clearance_in_flagged_cost_band_blocks_not_flagged() -> None:
    """The kailash-rs#1492 repro: max_cost=10, clearance_required=secret,
    cost=9.0 (in the (8.0, 10.0] soft-flag band), caller clearance ABSENT.

    Pre-fix: cost-flag short-circuit returned ``flagged`` (allowed) before any
    clearance check -- an authorization-ordering bypass. Post-fix: BLOCKED.
    """
    decision = _decide(_enforcer(), cost_estimate=9.0, caller_clearance=None)
    assert decision.level == "blocked"
    assert decision.allowed is False
    assert "clearance" in decision.reason.lower()


@pytest.mark.regression
@pytest.mark.security
def test_unmet_clearance_blocks_regardless_of_cost_band() -> None:
    """Clearance gates independent of where cost lands: a low cost that would
    otherwise auto-approve is still BLOCKED when clearance is unmet."""
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance=None)
    assert decision.level == "blocked"
    assert "clearance" in decision.reason.lower()


@pytest.mark.regression
@pytest.mark.security
def test_insufficient_clearance_blocks() -> None:
    """A caller below the required level is BLOCKED (confidential < secret)."""
    decision = _decide(_enforcer(), cost_estimate=9.0, caller_clearance="confidential")
    assert decision.level == "blocked"
    assert "below the required" in decision.reason


# ---------------------------------------------------------------------------
# Criterion 1 -- ordering: clearance is evaluated BEFORE the cost ladder
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
def test_clearance_evaluated_before_cost_over_max() -> None:
    """When cost ALSO exceeds max_cost, the BLOCK cites clearance, proving the
    clearance gate runs before the Step-4 cost ladder."""
    decision = _decide(_enforcer(), cost_estimate=15.0, caller_clearance=None)
    assert decision.level == "blocked"
    assert "clearance" in decision.reason.lower()
    assert "exceeds max_cost" not in decision.reason


# ---------------------------------------------------------------------------
# Sufficient clearance does NOT over-block; cost band still governs
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
def test_sufficient_clearance_passes_gate_cost_band_governs() -> None:
    """Caller clearance equal to the requirement passes the clearance gate; the
    decision then reflects the cost band (flagged at 9.0/10.0), not blocked."""
    decision = _decide(_enforcer(), cost_estimate=9.0, caller_clearance="secret")
    assert decision.level == "flagged"
    assert decision.allowed is True


@pytest.mark.regression
@pytest.mark.security
def test_higher_clearance_passes_gate() -> None:
    """A caller above the requirement (top_secret > secret) passes."""
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance="top_secret")
    assert decision.level == "auto_approved"
    assert decision.allowed is True


@pytest.mark.regression
@pytest.mark.security
def test_clearance_match_is_case_insensitive() -> None:
    """Clearance strings are matched case-insensitively (SECRET == secret)."""
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance="SECRET")
    assert decision.level == "auto_approved"


@pytest.mark.regression
@pytest.mark.security
def test_clearance_match_strips_surrounding_whitespace() -> None:
    """Clearance strings are normalized (strip + lower) before parsing, so a
    config value with surrounding whitespace is the same level -- not a
    surprise fail-closed over-block. Normalization is symmetric: the policy
    requirement and the caller clearance both go through strip().lower(), so no
    asymmetric-normalization bypass is introduced."""
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance="  Secret \n")
    assert decision.level == "auto_approved"
    # All-whitespace still fails closed (normalizes to "" -> unrecognized).
    blocked = _decide(_enforcer(), cost_estimate=1.0, caller_clearance="   ")
    assert blocked.level == "blocked"


@pytest.mark.regression
@pytest.mark.security
def test_zero_width_padded_clearance_fails_closed() -> None:
    """A zero-width-space-suffixed clearance ("secret\\u200b") is NOT stripped by
    str.strip() (U+200B is not str.isspace()), so it fails closed to BLOCKED --
    a normalization quirk cannot up-parse a non-canonical token into a level.
    Pins the fail-closed edge against a future normalization change."""
    padded = "secret" + chr(0x200B)  # zero-width space suffix (not str.isspace())
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance=padded)
    assert decision.level == "blocked"
    assert "not a recognized confidentiality level" in decision.reason


# ---------------------------------------------------------------------------
# Fail-closed edge cases (PACT governance Rule 4)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
def test_unrecognized_policy_requirement_fails_closed() -> None:
    """An unrecognized ``clearance_required`` value BLOCKS rather than silently
    permitting (fail-closed on a malformed requirement)."""
    enf = _enforcer(clearance_required="bogus_level")
    decision = _decide(enf, cost_estimate=1.0, caller_clearance="top_secret")
    assert decision.level == "blocked"
    assert "not a recognized confidentiality level" in decision.reason


@pytest.mark.regression
@pytest.mark.security
def test_unrecognized_caller_clearance_fails_closed() -> None:
    """An unrecognized caller clearance BLOCKS rather than passing."""
    decision = _decide(_enforcer(), cost_estimate=1.0, caller_clearance="ultra")
    assert decision.level == "blocked"
    assert "not a recognized confidentiality level" in decision.reason


@pytest.mark.regression
@pytest.mark.security
def test_public_requirement_still_demands_a_declared_clearance() -> None:
    """Fail-closed: a policy that explicitly sets clearance_required="public"
    still demands the caller DECLARE a clearance; an absent caller is BLOCKED.
    (The common case -- clearance_required=None -- is the no-op tested below.)"""
    enf = _enforcer(clearance_required="public")
    blocked = _decide(enf, cost_estimate=1.0, caller_clearance=None)
    assert blocked.level == "blocked"
    allowed = _decide(enf, cost_estimate=1.0, caller_clearance="public")
    assert allowed.level == "auto_approved"


# ---------------------------------------------------------------------------
# Backward compatibility: clearance_required=None is a no-op
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
def test_no_clearance_required_is_a_noop() -> None:
    """A policy without ``clearance_required`` is unaffected: a caller with no
    clearance in the flagged cost band still gets ``flagged`` (not blocked)."""
    enf = _enforcer(clearance_required=None)
    decision = _decide(enf, cost_estimate=9.0, caller_clearance=None)
    assert decision.level == "flagged"
    assert decision.allowed is True


@pytest.mark.regression
def test_flagging_threshold_value_unchanged_at_80_percent() -> None:
    """Criterion 3: the 0.80 flagging threshold value is unchanged. Exactly at
    80% of max is NOT flagged; just above it IS (clearance satisfied)."""
    enf = _enforcer()
    at_80 = _decide(enf, cost_estimate=8.0, caller_clearance="secret")
    assert at_80.level == "auto_approved"
    above_80 = _decide(enf, cost_estimate=8.01, caller_clearance="secret")
    assert above_80.level == "flagged"


# ---------------------------------------------------------------------------
# Structural invariant (cross-sdk-inspection.md Rule 3a) -- pin the API surface
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_mcp_action_context_exposes_caller_clearance_field() -> None:
    """Structural invariant: McpActionContext MUST carry ``caller_clearance``.
    If a future refactor drops it, the enforcer silently loses the caller's
    clearance input and the issue-#1456 bug class becomes reachable again."""
    field_names = {f.name for f in dataclasses.fields(McpActionContext)}
    assert "caller_clearance" in field_names
    # Round-trips through serialization (audit / wire transfer).
    ctx = McpActionContext(tool_name="t", caller_clearance="secret", timestamp=_T0)
    assert McpActionContext.from_dict(ctx.to_dict()).caller_clearance == "secret"


# ---------------------------------------------------------------------------
# Production path: the middleware forwards caller_clearance to the enforcer
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.security
@pytest.mark.asyncio
async def test_middleware_forwards_caller_clearance_and_blocks() -> None:
    """The governance middleware (the production tools/call path) plumbs
    caller_clearance into the context so an unmet-clearance call is BLOCKED and
    the underlying handler is NEVER invoked."""
    handler_calls: list[str] = []

    async def handler(tool_name: str, args: dict) -> str:
        handler_calls.append(tool_name)
        return "result"

    mw = McpGovernanceMiddleware(_enforcer(), handler)
    result = await mw.invoke(
        "search", agent_id="agent-1", cost_estimate=9.0, caller_clearance=None
    )
    assert result.decision.level == "blocked"
    assert result.executed is False
    assert handler_calls == []  # blocked before the handler ran


@pytest.mark.regression
@pytest.mark.security
@pytest.mark.asyncio
async def test_middleware_forwards_sufficient_clearance_and_executes() -> None:
    """With sufficient caller clearance the middleware forwards to the handler."""
    handler_calls: list[str] = []

    async def handler(tool_name: str, args: dict) -> str:
        handler_calls.append(tool_name)
        return "result"

    mw = McpGovernanceMiddleware(_enforcer(), handler)
    result = await mw.invoke(
        "search", agent_id="agent-1", cost_estimate=1.0, caller_clearance="secret"
    )
    assert result.decision.allowed is True
    assert result.executed is True
    assert handler_calls == ["search"]


# ---------------------------------------------------------------------------
# Redteam follow-up (same bug class as #1456): register_tool monotonic
# tightening MUST cover clearance_required. #1456 promoted clearance_required
# from unread metadata to an enforced Layer-2 gate at the EVALUATION surface,
# but _validate_monotonic_tightening (the RE-REGISTRATION guard) was left blind
# to it -- so register_tool could silently drop/lower the clearance bar (a
# privilege escalation, pact-governance.md Rule 2). These tests pin the guard.
# ---------------------------------------------------------------------------


def _reregister(enf: McpGovernanceEnforcer, clearance_required: str | None) -> None:
    """Re-register tool 'search' with a new clearance_required (max_cost held)."""
    enf.register_tool(
        McpToolPolicy(
            tool_name="search", max_cost=10.0, clearance_required=clearance_required
        )
    )


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_cannot_drop_clearance_requirement() -> None:
    """secret -> None is a widening (drops the gate) and MUST raise; the gate
    MUST remain enforced after the rejected attempt (no silent strip)."""
    enf = _enforcer()  # clearance_required="secret"
    assert _decide(enf, cost_estimate=1.0, caller_clearance="public").level == "blocked"
    with pytest.raises(ValueError, match="clearance_required widened"):
        _reregister(enf, None)
    # The gate still blocks a sub-clearance caller -- the strip did not land.
    assert _decide(enf, cost_estimate=1.0, caller_clearance="public").level == "blocked"


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_cannot_lower_clearance_requirement() -> None:
    """secret -> public lowers the bar (a widening) and MUST raise."""
    enf = _enforcer()
    with pytest.raises(ValueError, match="clearance_required widened"):
        _reregister(enf, "public")
    assert _decide(enf, cost_estimate=1.0, caller_clearance="public").level == "blocked"


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_can_raise_clearance_requirement() -> None:
    """secret -> top_secret is a tightening and MUST be accepted; a secret
    caller that previously passed is now blocked."""
    enf = _enforcer()
    _reregister(enf, "top_secret")
    assert _decide(enf, cost_estimate=1.0, caller_clearance="secret").level == "blocked"
    assert (
        _decide(enf, cost_estimate=1.0, caller_clearance="top_secret").allowed is True
    )


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_can_add_clearance_requirement_where_none() -> None:
    """None -> secret adds a gate where there was none (a tightening): accepted,
    and the new gate immediately blocks an unmet caller."""
    enf = _enforcer(clearance_required=None)
    assert _decide(enf, cost_estimate=1.0, caller_clearance=None).allowed is True
    _reregister(enf, "secret")
    assert _decide(enf, cost_estimate=1.0, caller_clearance=None).level == "blocked"


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_equal_clearance_accepted() -> None:
    """secret -> secret is equal (not a widening): accepted."""
    enf = _enforcer()
    _reregister(enf, "secret")  # must not raise
    assert _decide(enf, cost_estimate=1.0, caller_clearance="secret").allowed is True


@pytest.mark.regression
@pytest.mark.security
def test_register_tool_unrecognized_clearance_is_tightest_not_widest() -> None:
    """An unrecognized clearance fail-closes to BLOCKED-for-all (tightest), so
    secret -> garbage is a tightening (accepted) but garbage -> secret is a
    widening (raises). This prevents an unparseable token being treated as
    'no requirement' and silently dropping the gate."""
    enf = _enforcer()  # secret
    _reregister(enf, "garbage")  # secret -> blocks-all: tightening, accepted
    assert _decide(enf, cost_estimate=1.0, caller_clearance="top_secret").level == (
        "blocked"
    )  # even top_secret is now blocked -- fail-closed
    enf2 = _enforcer(clearance_required="garbage")  # blocks-all base
    with pytest.raises(ValueError, match="clearance_required widened"):
        _reregister(enf2, "secret")  # blocks-all -> secret: widening
