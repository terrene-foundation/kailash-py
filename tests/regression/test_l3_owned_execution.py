"""Owned L3 execution uses real factory, registry and wrapper lifecycle APIs."""

import asyncio
from functools import partial

import pytest

from kaizen.l3.factory import (
    AgentFactory,
    AgentInstanceRegistry,
    AgentLifecycleState,
    AgentSpec,
    TerminationReason,
)
from kaizen.l3.integration import L3Runtime
from kaizen_agents._agent_lifecycle import AgentLifecycleManager
from kaizen_agents.types import AgentSpec as LocalSpec

REASON = TerminationReason.EXPLICIT_TERMINATION


def spec(name="worker", **kwargs):
    return AgentSpec(spec_id=name, name=name, description=name, **kwargs)


def factory():
    return AgentFactory(AgentInstanceRegistry())


@pytest.mark.asyncio
async def test_spawn_remains_metadata_and_legacy_terminate_returns_none():
    owner = factory()
    instance = await owner.spawn(spec())
    assert instance.state.name == "pending"
    assert await owner.get_execution(instance.instance_id) is None
    report = await owner.terminate_owned(instance.instance_id, REASON)
    assert report.entries[0].status == "metadata_only"
    assert report.entries[0].local_stopped is None
    assert await owner.terminate(instance.instance_id, REASON) is None


@pytest.mark.asyncio
async def test_dispatch_binds_exact_callable_and_propagates_result():
    owner = factory()
    instance = await owner.spawn(spec())
    calls = []

    async def execute_node(bound_spec, inputs):
        calls.append((bound_spec, inputs))
        return {"result": inputs["value"]}

    blueprint = spec()
    executable = partial(execute_node, blueprint, {"value": 42})
    handle = await owner.dispatch(instance.instance_id, executable)
    assert handle.executable is executable
    assert handle.instance_id == instance.instance_id
    assert await owner.get_execution(instance.instance_id) is handle
    assert await handle.result() == {"result": 42}
    assert calls == [(blueprint, {"value": 42})]
    assert instance.state.name == "completed"
    observed = handle.snapshot()
    assert observed.status == "returned" and observed.local_stopped is True
    assert observed.remote_effects == "unknown"
    assert observed.execution_id == handle.execution_id
    with pytest.raises(ValueError):
        await owner.dispatch(instance.instance_id, executable)


@pytest.mark.asyncio
async def test_cancel_before_executable_starts_is_distinct():
    owner = factory()
    instance = await owner.spawn(spec())
    called = []

    async def executable():
        called.append(True)

    handle = await owner.dispatch(instance.instance_id, executable)
    report = await owner.terminate_owned(instance.instance_id, REASON)
    assert called == []
    assert report.entries[0].status == "never_started"
    assert report.entries[0].remote_effects == "not_started"
    assert handle.snapshot().local_stopped is True
    assert instance.state.name == "terminated"


@pytest.mark.asyncio
async def test_failure_visible_in_result_and_lifecycle_without_logging_payload():
    owner = factory()
    instance = await owner.spawn(spec())

    async def fail():
        raise LookupError("classified test payload")

    handle = await owner.dispatch(instance.instance_id, fail)
    with pytest.raises(LookupError, match="classified test payload"):
        await handle.result()
    assert instance.state.name == "failed"
    assert "classified" not in instance.state.error
    assert handle.snapshot().status == "failed"


@pytest.mark.asyncio
async def test_cascade_stops_owned_children_before_claiming_termination():
    owner = factory()
    parent = await owner.spawn(spec("parent"))
    await owner.update_state(parent.instance_id, AgentLifecycleState.running())
    child = await owner.spawn(spec("child"), parent_id=parent.instance_id)
    started = asyncio.Event()
    closed = []

    async def work():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.append("child")

    handle = await owner.dispatch(child.instance_id, work)
    await started.wait()
    report = await owner.terminate_owned(parent.instance_id, REASON)
    assert closed == ["child"]
    assert report.entries[0].instance_id == child.instance_id
    assert report.entries[0].status == "cancelled"
    assert parent.state.name == child.state.name == "terminated"
    assert handle.snapshot().remote_effects == "unknown"


@pytest.mark.asyncio
async def test_noncooperative_task_remains_live_and_spawn_blocked_until_stopped():
    owner = factory()
    instance = await owner.spawn(spec())
    entered = asyncio.Event()
    release = asyncio.Event()

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
            return "locally returned after cancellation request"

    handle = await owner.dispatch(instance.instance_id, work)
    await entered.wait()
    try:
        report = await owner.terminate_owned(instance.instance_id, REASON, timeout=0.01)
        assert report.entries[0].status == "still_running"
        assert report.entries[0].local_stopped is False
        assert not instance.is_terminal
        with pytest.raises(ValueError, match="terminat"):
            await owner.spawn(spec("late"), parent_id=instance.instance_id)
    finally:
        release.set()
        await handle.result()
    assert instance.state.name == "terminated"
    assert handle.snapshot().status == "returned"


@pytest.mark.asyncio
async def test_cancelled_termination_caller_does_not_claim_stop_or_release_spawn_gate():
    owner = factory()
    instance = await owner.spawn(spec())
    entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            await release.wait()

    handle = await owner.dispatch(instance.instance_id, work)
    await entered.wait()
    stop = asyncio.create_task(owner.terminate_owned(instance.instance_id, REASON))
    await cancelling.wait()
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    try:
        assert not instance.is_terminal
        with pytest.raises(ValueError, match="terminat"):
            await owner.spawn(spec("late"), parent_id=instance.instance_id)
    finally:
        release.set()
        await handle.result()
    assert instance.state.name == "terminated"


@pytest.mark.asyncio
async def test_result_waiter_cancellation_does_not_cancel_owned_work():
    owner = factory()
    instance = await owner.spawn(spec())
    release = asyncio.Event()

    async def work():
        await release.wait()
        return 3

    handle = await owner.dispatch(instance.instance_id, work)
    waiter = asyncio.create_task(handle.result())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert handle.snapshot().local_stopped is False
    release.set()
    assert await handle.result() == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["runtime", "manager"])
async def test_public_wrappers_share_factory_owned_execution(surface):
    registry = AgentInstanceRegistry()
    owner = factory()
    if surface == "runtime":
        wrapper = L3Runtime()
        instance = await wrapper.spawn_agent(spec())
        owner = wrapper.factory
    else:
        owner = AgentFactory(registry)
        wrapper = AgentLifecycleManager(owner, registry)
        instance = await wrapper.spawn_agent(
            LocalSpec(spec_id="worker", name="worker", description="worker")
        )

    async def work():
        return "done"

    handle = await wrapper.dispatch_agent(instance.instance_id, work)
    assert await owner.get_execution(instance.instance_id) is handle
    assert await handle.result() == "done"
    report = await wrapper.terminate_owned_agent(instance.instance_id)
    assert report.entries[0].status == "returned"


@pytest.mark.asyncio
async def test_synchronous_and_duplicate_execution_are_rejected_before_call():
    owner = factory()
    instance = await owner.spawn(spec())
    called = []
    with pytest.raises(TypeError):
        await owner.dispatch(instance.instance_id, lambda: called.append(True))
    assert called == [] and instance.state.name == "pending"

    async def work():
        await asyncio.Event().wait()

    handle = await owner.dispatch(instance.instance_id, work)
    with pytest.raises(ValueError):
        await owner.dispatch(instance.instance_id, work)
    await owner.terminate_owned(instance.instance_id, REASON)
    assert handle.snapshot().local_stopped is True


@pytest.mark.asyncio
async def test_public_state_updates_cannot_forge_owned_completion():
    owner = factory()
    instance = await owner.spawn(spec())
    entered = asyncio.Event()

    async def work():
        entered.set()
        await asyncio.Event().wait()

    handle = await owner.dispatch(instance.instance_id, work)
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="Owned execution"):
            await owner.update_state(
                instance.instance_id, AgentLifecycleState.completed()
            )
        assert handle.snapshot().status == "running"
    finally:
        await owner.terminate(instance.instance_id, REASON)


@pytest.mark.asyncio
async def test_terminal_parent_still_cascades_to_live_owned_child():
    owner = factory()
    parent = await owner.spawn(spec("parent"))
    await owner.update_state(parent.instance_id, AgentLifecycleState.running())
    child = await owner.spawn(spec("child"), parent_id=parent.instance_id)

    async def work():
        await asyncio.Event().wait()

    handle = await owner.dispatch(child.instance_id, work)
    await owner.update_state(parent.instance_id, AgentLifecycleState.completed())
    report = await owner.terminate_owned(parent.instance_id, REASON)
    assert report.entries[0].local_stopped is True
    assert handle.snapshot().status == "never_started"
    assert parent.state.name == "completed"
    assert child.state.name == "terminated"


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout", [-1, float("nan"), float("inf"), True, "bad"])
async def test_invalid_timeout_does_not_request_termination(timeout):
    owner = factory()
    instance = await owner.spawn(spec())
    with pytest.raises(ValueError, match="timeout"):
        await owner.terminate_owned(instance.instance_id, REASON, timeout=timeout)
    assert instance.state.name == "pending"


@pytest.mark.asyncio
async def test_l3_runtime_executes_existing_async_plan_executor():
    from kaizen.l3.plan import Plan, PlanNode, PlanNodeState, PlanState

    runtime = L3Runtime()
    instance = await runtime.spawn_agent(spec())
    calls = []

    async def node_callback(node_id, agent_spec_id):
        calls.append((node_id, agent_spec_id))
        return {"result": 42}

    plan = Plan(
        plan_id="owned-plan",
        name="owned-plan",
        envelope={},
        gradient={},
        edges=[],
        nodes={
            "node": PlanNode(
                node_id="node",
                agent_spec_id="worker",
                input_mapping={},
                state=PlanNodeState.PENDING,
                instance_id=instance.instance_id,
                optional=False,
                retry_count=0,
                output=None,
                error=None,
            )
        },
        state=PlanState.VALIDATED,
    )
    executor = runtime.create_plan_executor(node_callback, agent_id="root")
    executable = partial(executor.execute, plan)
    handle = await runtime.dispatch_agent(instance.instance_id, executable)
    events = await handle.result()
    assert handle.executable is executable
    assert events and calls == [("node", "worker")]
    assert plan.state == PlanState.COMPLETED
    assert instance.state.name == "completed"


@pytest.mark.asyncio
async def test_overlapping_stop_requests_do_not_recancel_cleanup():
    owner = factory()
    instance = await owner.spawn(spec())
    entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    cancellations = []

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellations.append(True)
            cancelling.set()
            await release.wait()

    handle = await owner.dispatch(instance.instance_id, work)
    await entered.wait()
    stop = asyncio.create_task(owner.terminate_owned(instance.instance_id, REASON))
    await cancelling.wait()
    try:
        report = await owner.terminate_owned(instance.instance_id, REASON, timeout=0)
        assert report.entries[0].local_stopped is False
        assert cancellations == [True]
    finally:
        release.set()
        await stop
        await handle.result()
    assert instance.state.name == "terminated"


@pytest.mark.asyncio
async def test_return_before_done_callback_is_not_relabelled_terminated():
    owner = factory()
    instance = await owner.spawn(spec())

    async def work():
        return 42

    handle = await owner.dispatch(instance.instance_id, work)
    await asyncio.sleep(0)
    assert handle.snapshot().status == "returned"
    report = await owner.terminate_owned(instance.instance_id, REASON)
    assert report.entries[0].status == "returned"
    assert instance.state.name == "completed"
    assert await handle.result() == 42


async def wired_pair():
    runtime = L3Runtime()
    parent = await runtime.spawn_agent(spec("parent", envelope={"financial_limit": 10}))
    await runtime.factory.update_state(
        parent.instance_id, AgentLifecycleState.running()
    )
    child = await runtime.spawn_agent(
        spec("child", envelope={"financial_limit": 5}), parent_id=parent.instance_id
    )
    channels = (
        runtime.router._channels[(parent.instance_id, child.instance_id)],
        runtime.router._channels[(child.instance_id, parent.instance_id)],
    )
    assert all(not channel.is_closed() for channel in channels)
    assert runtime.enforcer.is_registered(child.instance_id)
    return runtime, parent, child, channels


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["return", "fail", "cancel", "cascade"])
async def test_owned_terminal_paths_release_actual_runtime_integrations(outcome):
    runtime, parent, child, channels = await wired_pair()
    entered = asyncio.Event()

    async def work():
        entered.set()
        if outcome == "fail":
            raise LookupError("expected owned failure")
        if outcome in {"cancel", "cascade"}:
            await asyncio.Event().wait()
        return 42

    handle = await runtime.dispatch_agent(child.instance_id, work)
    await entered.wait()
    if outcome in {"cancel", "cascade"}:
        target = parent if outcome == "cascade" else child
        report = await runtime.terminate_owned_agent(target.instance_id)
        assert report.entries[0].local_stopped is True
    elif outcome == "fail":
        with pytest.raises(LookupError, match="expected owned failure"):
            await handle.result()
    else:
        assert await handle.result() == 42
    assert all(channel.is_closed() for channel in channels)
    assert not runtime.enforcer.is_registered(child.instance_id)
    await runtime.terminate_owned_agent(parent.instance_id)
    assert not runtime.enforcer.is_registered(parent.instance_id)


@pytest.mark.asyncio
async def test_public_registry_cannot_forge_owned_terminal_state():
    runtime, parent, child, channels = await wired_pair()
    entered, release = asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        await release.wait()
        return 42

    handle = await runtime.dispatch_agent(child.instance_id, work)
    await entered.wait()
    try:
        with pytest.raises(ValueError, match="Owned execution"):
            await runtime.registry.update_state(
                child.instance_id, AgentLifecycleState.completed()
            )
        assert child.state.name == "running"
        assert handle.snapshot().local_stopped is False
        assert runtime.enforcer.is_registered(child.instance_id)
        assert all(not channel.is_closed() for channel in channels)
    finally:
        release.set()
        assert await handle.result() == 42
        await runtime.terminate_owned_agent(parent.instance_id)
    assert all(channel.is_closed() for channel in channels)
    assert not runtime.enforcer.is_registered(child.instance_id)


@pytest.mark.asyncio
async def test_mutated_instance_metadata_cannot_orphan_owned_cleanup():
    from kaizen.l3.factory import RegistryError

    runtime, parent, child, channels = await wired_pair()
    entered, release = asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        await release.wait()

    handle = await runtime.dispatch_agent(child.instance_id, work)
    await entered.wait()
    try:
        # AgentInstance remains mutable; cleanup must not trust this metadata.
        child.state = AgentLifecycleState.completed()
        with pytest.raises(RegistryError, match="live owned execution"):
            await runtime.registry.deregister(child.instance_id)
    finally:
        release.set()
        await handle.result()
        await runtime.terminate_owned_agent(parent.instance_id)
    assert all(channel.is_closed() for channel in channels)
    assert not runtime.enforcer.is_registered(child.instance_id)


@pytest.mark.asyncio
async def test_metadata_only_registry_updates_remain_supported_and_clean_integrations():
    runtime, parent, child, channels = await wired_pair()
    await runtime.registry.update_state(
        child.instance_id, AgentLifecycleState.running()
    )
    await runtime.registry.update_state(
        child.instance_id, AgentLifecycleState.completed()
    )
    assert child.state.name == "completed"
    assert all(channel.is_closed() for channel in channels)
    assert not runtime.enforcer.is_registered(child.instance_id)
    await runtime.terminate_owned_agent(parent.instance_id)


@pytest.mark.asyncio
async def test_shared_registry_keeps_execution_and_stop_ownership_across_factories():
    runtime, parent, child, channels = await wired_pair()
    another = AgentFactory(runtime.registry)
    entered, release = asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()

    handle = await runtime.dispatch_agent(child.instance_id, work)
    await entered.wait()
    try:
        assert await another.get_execution(child.instance_id) is handle
        with pytest.raises(ValueError):
            await another.dispatch(child.instance_id, work)
        report = await another.terminate_owned(parent.instance_id, REASON, timeout=0.01)
        assert report.entries[0].local_stopped is False
        with pytest.raises(ValueError, match="terminat"):
            await runtime.factory.spawn(spec("late"), parent_id=parent.instance_id)
    finally:
        release.set()
        await handle.result()
    assert parent.state.name == child.state.name == "terminated"
    assert all(channel.is_closed() for channel in channels)
    assert not runtime.enforcer.is_registered(child.instance_id)
    assert not runtime.enforcer.is_registered(parent.instance_id)


@pytest.mark.asyncio
async def test_registry_cannot_detach_live_owned_descendants():
    from kaizen.l3.factory import RegistryError

    owner = factory()
    parent = await owner.spawn(spec("parent"))
    await owner.update_state(parent.instance_id, AgentLifecycleState.running())
    child = await owner.spawn(spec("child"), parent_id=parent.instance_id)

    async def work():
        await asyncio.Event().wait()

    await owner.dispatch(child.instance_id, work)
    await owner.update_state(parent.instance_id, AgentLifecycleState.completed())
    try:
        with pytest.raises(RegistryError, match="ancestor of live owned"):
            await owner._registry.deregister(parent.instance_id)
    finally:
        report = await owner.terminate_owned(parent.instance_id, REASON)
    assert report.entries[0].local_stopped is True


@pytest.mark.asyncio
async def test_deregister_after_return_before_done_callback_cleans_integrations():
    runtime, parent, child, channels = await wired_pair()
    entered, release, returning = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def work():
        entered.set()
        await release.wait()
        # Wake the observer before task completion queues its done callback.
        returning.set()
        return 42

    handle = await runtime.dispatch_agent(child.instance_id, work)
    await entered.wait()
    child.transition_to(AgentLifecycleState.completed())
    release.set()
    await returning.wait()
    assert handle.snapshot().local_stopped is True
    assert handle._finalized is False
    assert runtime.enforcer.is_registered(child.instance_id)
    assert all(not channel.is_closed() for channel in channels)
    await runtime.registry.deregister(child.instance_id)
    assert not runtime.enforcer.is_registered(child.instance_id)
    assert all(channel.is_closed() for channel in channels)
    assert await handle.result() == 42
    await runtime.terminate_owned_agent(parent.instance_id)
