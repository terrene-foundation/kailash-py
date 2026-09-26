"""Constructor serialization state must not become execution authority/input."""

import logging
from datetime import timedelta

import pytest

from kailash.nodes.auth._actor import MFAActor, StaticActorResolver
from kailash.nodes.auth.mfa import MultiFactorAuthNode
from kailash.nodes.auth.session_management import SessionManagementNode
from kailash.nodes.base import AsyncTypedNode, Node, NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel import ParallelRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.sdk_exceptions import NodeValidationError
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow

pytestmark = pytest.mark.regression


@register_node()
class ConstructorBoundaryNode(Node):
    def __init__(self, policy="locked", name="boundary", value=7, **kwargs):
        self.policy = policy
        super().__init__(name=name, value=value, **kwargs)

    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=int, required=False)}

    def run(self, **kwargs):
        return {"value": kwargs["value"], "policy": self.policy, "keys": sorted(kwargs)}


class InheritedBoundaryNode(ConstructorBoundaryNode):
    def __init__(self, retention=12, **kwargs):
        self.retention = retention
        super().__init__(**kwargs)


class DynamicBoundaryNode(ConstructorBoundaryNode):
    def __init__(self, expose_name=False, **kwargs):
        self.expose_name = expose_name
        super().__init__(**kwargs)

    def get_parameters(self):
        params = super().get_parameters()
        if self.expose_name:
            params["name"] = NodeParameter(name="name", type=str, required=False)
        return params


class AsyncBoundaryNode(AsyncNode):
    def __init__(self, policy="locked", value=7, **kwargs):
        self.policy = policy
        super().__init__(value=value, **kwargs)

    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=int, required=False)}

    async def async_run(self, **kwargs):
        return {"value": kwargs["value"], "keys": sorted(kwargs)}


class AsyncTypedBoundaryNode(AsyncTypedNode):
    def __init__(self, policy="locked", value=7, **kwargs):
        self.policy = policy
        super().__init__(value=value, **kwargs)

    def get_parameters(self):
        return {"value": NodeParameter(name="value", type=int, required=False)}

    async def async_run(self, **kwargs):
        return {"value": kwargs["value"], "keys": sorted(kwargs)}


@pytest.fixture(autouse=True)
def no_unexpected_warnings(caplog):
    caplog.set_level(logging.WARNING)
    yield
    unexpected = [
        r.getMessage()
        for phase in ("setup", "call", "teardown")
        for r in caplog.get_records(phase)
        if r.levelno >= logging.WARNING
    ]
    assert not unexpected, unexpected


def _workflow():
    builder = WorkflowBuilder()
    builder.add_node(
        "ConstructorBoundaryNode", "boundary", {"value": 9, "policy": "fixed"}
    )
    return builder.build()


def test_inherited_constructor_state_retained_and_inputs_remain_separate():
    node = InheritedBoundaryNode(policy="fixed", retention=13, value=9, name="display")
    node._strict_unknown_params = True
    assert node.config == {
        "value": 9,
        "policy": "fixed",
        "name": "display",
        "retention": 13,
    }
    assert node.metadata.name == "display"
    assert node.execute(value=11) == {"value": 11, "policy": "fixed", "keys": ["value"]}
    copy = InheritedBoundaryNode(**node.config)
    assert copy.policy == "fixed" and copy.retention == 13
    assert copy.metadata.name == "display"
    assert copy.execute()["value"] == 9


@pytest.mark.parametrize("expose", [False, True])
def test_dynamic_schema_preserves_declared_name_collision(expose):
    node = DynamicBoundaryNode(expose_name=expose, name="display")
    node._strict_unknown_params = True
    assert node.execute()["keys"] == (["name", "value"] if expose else ["value"])
    assert node.config["name"] == "display"
    assert node.metadata.name == "display"


@pytest.mark.parametrize("key", ["policy", "name", "unknown_option"])
def test_explicit_runtime_inputs_are_never_hidden(key, caplog):
    node = ConstructorBoundaryNode()
    node._strict_unknown_params = True
    with pytest.raises(NodeValidationError, match="Unknown parameter"):
        node.execute(**{key: "override"})
    assert node.policy == "locked"
    assert not caplog.records


def test_unconsumed_constructor_typo_still_warns(caplog):
    node = ConstructorBoundaryNode(unknown_option="typo")
    assert node.execute()["value"] == 7
    assert len(caplog.records) == 1
    assert "Unknown parameter(s)" in caplog.records[0].getMessage()
    assert "unknown_option" in caplog.records[0].getMessage()
    caplog.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("node_type", [AsyncBoundaryNode, AsyncTypedBoundaryNode])
async def test_async_entrypoints_preserve_defaults_and_validate_overrides(
    node_type, caplog
):
    node = node_type(policy="locked", value=9)
    node._strict_unknown_params = True
    assert await node.execute_async() == {"value": 9, "keys": ["value"]}
    assert await node.execute_async(value=11) == {"value": 11, "keys": ["value"]}
    with pytest.raises(NodeValidationError, match="Unknown parameter"):
        await node.execute_async(policy="override")
    assert not caplog.records


@pytest.mark.parametrize("cycles", [False, True])
def test_local_runtime_validation_and_cyclic_execution(cycles):
    with LocalRuntime(enable_cycles=cycles, connection_validation="strict") as runtime:
        results, _ = runtime.execute(_workflow())
    assert results["boundary"]["value"] == 9
    assert results["boundary"]["policy"] == "fixed"
    assert "policy" not in results["boundary"]["keys"]


@pytest.mark.asyncio
async def test_parallel_execution_retains_defaults():
    results, _ = await ParallelRuntime().execute(_workflow())
    assert results["boundary"] == {"value": 9, "policy": "fixed", "keys": ["value"]}


def test_parallel_cyclic_execution_retains_defaults():
    runtime = ParallelCyclicRuntime()
    try:
        results, _ = runtime.execute(_workflow(), parallel_nodes={"boundary"})
        assert results["boundary"]["value"] == 9
        assert "policy" not in results["boundary"]["keys"]
    finally:
        runtime.close()


def test_workflow_execution_and_serialization_preserve_configuration():
    workflow = _workflow()
    rebuilt = Workflow.from_dict(workflow.to_dict())
    node = rebuilt._node_instances["boundary"]
    assert node.config["policy"] == "fixed"
    results = rebuilt.execute()
    assert results["boundary"]["value"] == 9
    assert results["boundary"]["policy"] == "fixed"


def test_session_configuration_is_quiet_and_controls_expiry():
    node = SessionManagementNode(
        name="session_contract",
        idle_timeout=timedelta(seconds=1),
        anomaly_detection=False,
    )
    result = node.execute(
        action="create", user_id="alice", ip_address="127.0.0.1", device_info={}
    )
    session_id = result["session_id"]
    node.sessions[session_id].last_activity -= timedelta(seconds=2)
    assert node.execute(action="validate", session_id=session_id)["valid"] is False
    assert node.idle_timeout == timedelta(seconds=1)
    assert node.config["idle_timeout"] == timedelta(seconds=1)


def test_mfa_constructor_authority_is_retained_and_runtime_cannot_override(caplog):
    resolver = StaticActorResolver({"alice_session": MFAActor(user_id="alice")})
    node = MultiFactorAuthNode(
        name="actor_contract", actor_resolver=resolver, require_actor=True
    )
    own = node.execute(
        action="status", user_id="alice", actor_session_id="alice_session"
    )
    assert own["success"] is True
    denied = node.execute(
        action="status",
        user_id="victim",
        actor_session_id="alice_session",
        require_actor=False,
    )
    assert denied["success"] is False and denied["authorized"] is False
    assert node.require_actor is True and node.actor_resolver is resolver
    unknown = [r for r in caplog.records if "Unknown parameter(s)" in r.getMessage()]
    assert len(unknown) == 1 and "require_actor" in unknown[0].getMessage()
    assert all(
        "Unknown parameter(s)" in r.getMessage()
        or "mfa.authorization_denied" in r.getMessage()
        for r in caplog.records
    )
    caplog.clear()


@pytest.mark.parametrize("alias_kind", ["auto_map_from", "workflow_alias"])
def test_explicit_schema_alias_is_an_execution_default(alias_kind):
    class AliasedNode(Node):
        def __init__(self, source=8, **kwargs):
            super().__init__(**kwargs)

        def get_parameters(self):
            alias = {
                alias_kind: ["source"] if alias_kind == "auto_map_from" else "source"
            }
            return {
                "value": NodeParameter(name="value", type=int, required=True, **alias)
            }

        def run(self, **kwargs):
            return kwargs

    node = AliasedNode(source=12)
    assert node.execute() == {"value": 12}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "node_type", [ConstructorBoundaryNode, AsyncBoundaryNode, AsyncTypedBoundaryNode]
)
async def test_nested_config_remains_an_execution_default(node_type):
    class NestedConfigNode(node_type):
        def __init__(self, config=None, **kwargs):
            super().__init__(**kwargs)

    node = NestedConfigNode(config={"value": 19})
    node._strict_unknown_params = True
    if node_type is ConstructorBoundaryNode:
        assert node.execute()["value"] == 19
        assert node.execute(value=23)["value"] == 23
        with pytest.raises(NodeValidationError, match="Unknown parameter"):
            node.execute(policy="override")
    else:
        assert (await node.execute_async())["value"] == 19
        assert (await node.execute_async(value=23))["value"] == 23
        with pytest.raises(NodeValidationError, match="Unknown parameter"):
            await node.execute_async(policy="override")


def test_actual_cycle_uses_input_defaults_without_constructor_state():
    workflow = _workflow()
    workflow.create_cycle("repeat").connect(
        "boundary", "boundary", {"value": "value"}
    ).max_iterations(2).build()
    assert workflow.has_cycles()
    with LocalRuntime(enable_cycles=True) as runtime:
        results, _ = runtime.execute(workflow)
    assert results["boundary"]["value"] == 9
    assert results["boundary"]["policy"] == "fixed"
    assert "policy" not in results["boundary"]["keys"]


@pytest.mark.parametrize(
    "context",
    [
        None,
        {},
        {
            "location": "test-location",
            "ip_address": "192.0.2.1",
            "browser": "test-browser",
        },
    ],
)
def test_push_context_reaches_actual_dispatch_without_granting_authority(
    context, monkeypatch
):
    resolver = StaticActorResolver({"alice_session": MFAActor(user_id="alice")})
    node = MultiFactorAuthNode(
        actor_resolver=resolver, push_provider={"server_key": "synthetic-test-key"}
    )
    node.user_devices["alice"] = [
        {"device_id": "test-device", "push_token": "synthetic-push-token"}
    ]
    node.user_mfa_data["alice"] = {
        "methods": {"push": {"verified": True}},
        "backup_codes": [],
    }
    sent = []

    class Delivered:
        status_code = 200

    def deliver(endpoint, **kwargs):
        sent.append(kwargs["json"])
        return Delivered()

    monkeypatch.setattr("requests.post", deliver)
    kwargs = {} if context is None else {"auth_context": context}
    result = node.execute(
        action="send_push", user_id="alice", actor_session_id="alice_session", **kwargs
    )
    assert result["success"] is True
    expected = context or {}
    assert sent[0]["notification"]["body"] == "Login attempt from " + expected.get(
        "location", "Unknown location"
    )
    assert sent[0]["data"]["ip_address"] == expected.get("ip_address", "Unknown")
    assert sent[0]["data"]["browser"] == expected.get("browser", "Unknown")
    assert node.push_challenges[result["challenge_id"]]["auth_context"] == expected
    denied = node.execute(
        action="send_push",
        user_id="alice",
        auth_context={
            "actor_session_id": "alice_session",
            "user_id": "alice",
            "admin_override": True,
        },
    )
    assert denied["success"] is False and denied["authorized"] is False
    assert len(sent) == 1


def test_push_context_rejects_invalid_runtime_type():
    node = MultiFactorAuthNode()
    with pytest.raises(NodeValidationError, match="auth_context"):
        node.execute(action="send_push", user_id="alice", auth_context="not-a-dict")
