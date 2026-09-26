"""Issue #2109 defect 1 -- the shared hook timeout silently drops audit records.

``HookManager.trigger`` defaults ``timeout=0.5`` (the "SECURITY FIX #10" guard
against a hook hanging the agent loop). ``AuditTrailHook`` sits behind that same
budget, so an append that exceeds it is abandoned: the entry never reaches
storage and the only trace is a ``logger.error`` string.

The other three builtin hooks are best-effort observability -- a dropped metrics
sample is a gap in a graph. An audit trail is a compliance artifact whose entire
value is that it is complete, so a dropped record is a different KIND of failure
and needs a different treatment.

These tests induce a genuinely slow append (a real ``anyio.sleep`` inside a real
``AuditStorage`` implementation -- the storage is the ENVIRONMENT here, not the
subject; the subject is the manager's timeout handling and the hook's reaction
to a drop). Nothing about the subject is mocked.
"""

import logging
import sys
from pathlib import Path

import anyio
import pytest

from kaizen.core.autonomy.hooks.builtin.audit_trail_hook import AuditTrailHook
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.autonomy.hooks.types import HookEvent, HookResult
from kaizen.core.autonomy.observability.audit import AuditEntry, AuditTrailManager

# Provenance guard -- pinned RELATIVE to this file, never to an absolute
# worktree path, so it travels with the checkout. `kaizen` resolving to an
# INSTALLED copy has produced false greens in this repo; this converts that
# into a loud refusal at collection time.
_PKG_ROOT = Path(__file__).resolve().parents[5]  # .../packages/kailash-kaizen


def test_kaizen_resolves_to_this_checkout():
    """Refuse to report on an installed copy of the package under test."""
    import kaizen

    resolved = Path(kaizen.__file__).resolve()
    expected_src = (_PKG_ROOT / "src").resolve()
    assert resolved.is_relative_to(expected_src), (
        f"kaizen resolved to {resolved}, not this checkout under {expected_src}. "
        f"sys.path[0]={sys.path[0]!r}"
    )


class SlowAuditStorage:
    """A real ``AuditStorage`` whose append genuinely takes time.

    Models the conditions issue #2109 names -- a slow volume, a contended NFS
    mount, a noisy neighbour. The sleep is a REAL await, not a patched clock,
    so it exercises the same cancellation path a real stalled write would.
    """

    def __init__(self, delay_s: float):
        self.delay_s = delay_s
        self.entries: list[AuditEntry] = []

    async def append(self, entry: AuditEntry) -> None:
        await anyio.sleep(self.delay_s)
        self.entries.append(entry)

    async def query(self, **kwargs):
        return list(self.entries)


def _wire(delay_s: float, **hook_kwargs):
    """Build manager + audit hook over a deliberately slow storage."""
    storage = SlowAuditStorage(delay_s)
    hook = AuditTrailHook(
        audit_manager=AuditTrailManager(storage=storage), **hook_kwargs
    )
    manager = HookManager()
    manager.register(HookEvent.PRE_TOOL_USE, hook)
    return manager, hook, storage


@pytest.mark.asyncio
async def test_audit_append_slower_than_shared_budget_still_lands():
    """An append exceeding the 0.5s SHARED budget must NOT be dropped.

    Pre-fix this is the silent-drop defect: storage.entries is empty and the
    record is gone with only a log line.
    """
    manager, _hook, storage = _wire(delay_s=1.0)

    results = await manager.trigger(
        HookEvent.PRE_TOOL_USE, agent_id="agent-1", data={"tool": "bash"}
    )

    assert len(storage.entries) == 1, (
        "audit record was DROPPED: an append slower than the shared 0.5s hook "
        "budget never reached storage"
    )
    assert (
        results[0].success is True
    ), f"audit hook reported failure: {results[0].error}"


@pytest.mark.asyncio
async def test_audit_hook_declares_its_own_budget_larger_than_the_shared_one():
    """The audit path must carry a budget distinct from best-effort hooks."""
    assert hasattr(AuditTrailHook, "timeout_seconds"), (
        "AuditTrailHook does not declare its own timeout budget; it is still "
        "sharing the 0.5s best-effort budget"
    )
    assert AuditTrailHook.timeout_seconds > 0.5


@pytest.mark.asyncio
async def test_a_dropped_audit_record_emits_a_structured_alertable_signal(caplog):
    """Exceeding even the AUDIT budget must be loud, greppable and structured.

    The budget is lowered for this test so the drop is induced quickly; the
    behaviour under test is what happens AT the drop, not where the bound sits.
    """
    manager, _hook, storage = _wire(delay_s=1.0, timeout_seconds=0.2)

    with caplog.at_level(logging.ERROR):
        results = await manager.trigger(
            HookEvent.PRE_TOOL_USE, agent_id="agent-1", data={"tool": "bash"}
        )

    assert storage.entries == [], "test did not induce a drop; it proves nothing"

    dropped = [r for r in caplog.records if "audit_record_dropped" in r.getMessage()]
    assert dropped, (
        "a dropped audit record produced no greppable 'audit_record_dropped' "
        f"signal. Records seen: {[r.getMessage() for r in caplog.records]}"
    )

    record = dropped[0]
    msg = record.getMessage()
    # The event NAME and the REASON must both be present -- an alert that
    # cannot say WHICH event vanished and WHY is not actionable.
    assert HookEvent.PRE_TOOL_USE.value in msg, f"event name absent from: {msg}"
    assert "timeout" in msg.lower(), f"reason absent from: {msg}"
    # Structured, not merely a formatted string: alerting reads fields.
    assert getattr(record, "audit_event", None) == HookEvent.PRE_TOOL_USE.value
    assert getattr(record, "audit_drop_reason", None) == "timeout"
    assert getattr(record, "audit_agent_id", None) == "agent-1"

    # The manager stays domain-agnostic: the HookResult carries the GENERIC
    # timeout facts, and the audit-specific loudness lives in the hook's
    # on_error above. Asserting an "audit_*" key here would be asserting that
    # the manager special-cases one hook, which is the design we rejected.
    assert results[0].success is False
    assert results[0].data["timeout"] is True
    assert results[0].data["handler"] == "audit_trail_hook"
    assert results[0].data["event"] == HookEvent.PRE_TOOL_USE.value
    assert results[0].data["timeout_s"] == 0.2


@pytest.mark.asyncio
async def test_dropped_audit_records_are_counted_for_alerting():
    """A drop must be programmatically detectable, not only greppable in logs."""
    manager, _hook, _storage = _wire(delay_s=1.0, timeout_seconds=0.2)

    await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="agent-1", data={})

    stats = manager.get_stats()["audit_trail_hook"]
    assert stats["timeout_count"] == 1, f"timeout not counted in stats: {stats}"


# --------------------------------------------------------------------------
# Preservation guards for SECURITY FIX #10. These pin behaviour that must NOT
# change, so they are green BEFORE and AFTER -- they are regression fences, not
# red-then-green instruments, and are labelled as such rather than being
# presented as evidence the fix works.
# --------------------------------------------------------------------------


class SlowNonAuditHook(BaseHook):
    """A best-effort hook that hangs -- exactly what SECURITY FIX #10 guards."""

    events = [HookEvent.PRE_TOOL_USE]

    def __init__(self):
        super().__init__(name="slow_non_audit_hook")
        self.completed = False

    async def handle(self, context):
        await anyio.sleep(5.0)
        self.completed = True
        return HookResult(success=True)


@pytest.mark.asyncio
async def test_non_audit_hooks_keep_the_half_second_guard():
    """A non-audit hook must still be cut off at the shared 0.5s budget."""
    hook = SlowNonAuditHook()
    manager = HookManager()
    manager.register(HookEvent.PRE_TOOL_USE, hook)

    start = anyio.current_time()
    results = await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="a", data={})
    elapsed = anyio.current_time() - start

    assert results[0].success is False
    assert "timeout" in results[0].error.lower()
    assert hook.completed is False
    assert elapsed < 2.0, f"the 0.5s guard did not cut the hook off (took {elapsed}s)"


@pytest.mark.asyncio
async def test_an_unbounded_timeout_override_cannot_disable_the_guard():
    """A hook cannot opt OUT of the guard -- only onto a different finite bound."""
    hook = SlowNonAuditHook()
    for bad in (float("inf"), 0, -1, None, "forever"):
        hook.timeout_seconds = bad
        manager = HookManager()
        manager.register(HookEvent.PRE_TOOL_USE, hook)

        start = anyio.current_time()
        results = await manager.trigger(HookEvent.PRE_TOOL_USE, agent_id="a", data={})
        elapsed = anyio.current_time() - start

        assert results[0].success is False, f"override {bad!r} disabled the guard"
        assert elapsed < 2.0, f"override {bad!r} let the hook run {elapsed}s"
