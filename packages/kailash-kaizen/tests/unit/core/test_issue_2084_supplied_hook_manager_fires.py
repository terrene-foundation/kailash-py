"""
#2084, second layer -- a supplied hook_manager must actually fire.

``BaseAgent.__init__`` accepts a ``hook_manager`` and stores it, but
``trigger_hook`` / ``register_hook`` / ``get_hook_stats`` gated on
``config.hooks_enabled``, which is a SEPARATE opt-in defaulting ``False``.

``Agent`` (the unified API) builds a hook manager through
``SmartDefaultsManager.create_observability`` and passes it to ``BaseAgent``,
and ``_convert_to_base_agent_config`` does not set ``hooks_enabled``. So even a
fully populated manager stayed dormant: every hook registered, none invoked.
Fixing only the registration half of #2084 would have left the audit trail
recording nothing on exactly the path users take -- registration is not
recording, and a manager that is never triggered is a stub at the API surface
(``zero-tolerance.md`` Rule 3c: a documented kwarg with zero effect on the body).

The gates now test ``self._hook_manager is None``, which ``__init__`` has
already resolved from BOTH inputs.

Real HookManager and real hooks throughout: a MagicMock manager records a
``trigger`` call whether or not any handler ran, so it cannot tell these two
states apart.
"""

import pytest

from kaizen.core.autonomy.hooks import HookContext, HookEvent, HookResult
from kaizen.core.autonomy.hooks.manager import HookManager
from kaizen.core.autonomy.hooks.protocol import BaseHook
from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.signatures import InputField, OutputField, Signature

# No LLM call is made in this module; the provider is never reached.
PROVIDER = "ollama"
MODEL = "llama3.1:8b-instruct-q8_0"


class SimpleSignature(Signature):
    """Minimal signature -- BaseAgent requires one, nothing here executes it."""

    task: str = InputField(description="Task to perform")
    result: str = OutputField(description="Result of task")


class RecordingHook(BaseHook):
    """A real hook that records every context it is handed."""

    events = list(HookEvent)

    def __init__(self):
        super().__init__(name="recording_hook")
        self.seen: list[HookContext] = []

    async def handle(self, context: HookContext) -> HookResult:
        self.seen.append(context)
        return HookResult(success=True)


def _agent(hook_manager=None, hooks_enabled=False):
    return BaseAgent(
        config=BaseAgentConfig(
            llm_provider=PROVIDER, model=MODEL, hooks_enabled=hooks_enabled
        ),
        signature=SimpleSignature(),
        hook_manager=hook_manager,
    )


@pytest.mark.asyncio
async def test_supplied_hook_manager_fires_without_hooks_enabled():
    """
    Passing a hook_manager is itself the opt-in; the hook must run.

    This is the path SmartDefaultsManager takes. Before the fix the hook was
    registered on the manager, the manager was stored on the agent, and
    trigger_hook returned [] without ever reaching it.
    """
    hook = RecordingHook()
    manager = HookManager()
    manager.register_hook(hook)

    agent = _agent(hook_manager=manager, hooks_enabled=False)
    results = await agent.trigger_hook(
        HookEvent.PRE_AGENT_LOOP, data={"inputs": {"prompt": "hello"}}
    )

    assert hook.seen, (
        "a hook_manager was supplied to BaseAgent and its hook was never "
        "invoked -- the kwarg had no effect"
    )
    assert results
    assert hook.seen[0].event_type is HookEvent.PRE_AGENT_LOOP


@pytest.mark.asyncio
async def test_hooks_enabled_still_works_without_a_supplied_manager():
    """NEGATIVE CONTROL. The original opt-in is unchanged."""
    agent = _agent(hook_manager=None, hooks_enabled=True)
    hook = RecordingHook()
    agent.register_hook(HookEvent.PRE_AGENT_LOOP, hook)

    await agent.trigger_hook(HookEvent.PRE_AGENT_LOOP, data={})

    assert hook.seen


@pytest.mark.asyncio
async def test_no_manager_and_not_enabled_stays_inert():
    """
    NEGATIVE CONTROL. Neither input given means hooks stay off.

    A "fix" that enables hooks unconditionally fails here.
    """
    agent = _agent(hook_manager=None, hooks_enabled=False)

    assert agent.hook_manager is None
    assert await agent.trigger_hook(HookEvent.PRE_AGENT_LOOP, data={}) == []
    assert agent.get_hook_stats() == {}
    with pytest.raises(RuntimeError, match="Hooks are not enabled"):
        agent.register_hook(HookEvent.PRE_AGENT_LOOP, RecordingHook())


@pytest.mark.asyncio
async def test_register_hook_accepts_a_supplied_manager_despite_hooks_enabled_false():
    """
    The BREAKING half of this change, pinned rather than merely described.

    The old gate raised whenever `hooks_enabled` was False, even with a
    manager supplied -- so a caller who relied on `hooks_enabled=False` as an
    off-switch for `register_hook` loses that RuntimeError. It is recorded as
    a break in the CHANGELOG and it is asserted here, because a behaviour
    described only in prose is one the next refactor silently reverts.

    Restoring the flag as an override is not an option: `False` is its
    DEFAULT, so a dataclass cannot tell "explicitly disabled" from "never
    mentioned", and honouring it would reject the manager `SmartDefaults`
    supplies on every default `Agent` construction -- reinstating the exact
    no-effect-kwarg defect this suite exists to prevent.
    """
    manager = HookManager()
    agent = _agent(hook_manager=manager, hooks_enabled=False)
    hook = RecordingHook()

    agent.register_hook(HookEvent.PRE_AGENT_LOOP, hook)
    await agent.trigger_hook(HookEvent.PRE_AGENT_LOOP, data={})

    assert hook.seen, (
        "register_hook accepted the handler against a supplied manager but the "
        "handler never fired -- registration that does not record is the "
        "defect this change fixes, not a fix for it"
    )


@pytest.mark.asyncio
async def test_stats_reflect_a_supplied_manager():
    """get_hook_stats must report the supplied manager, not an empty dict."""
    manager = HookManager()
    manager.register_hook(RecordingHook())

    agent = _agent(hook_manager=manager, hooks_enabled=False)
    await agent.trigger_hook(HookEvent.PRE_AGENT_LOOP, data={})

    assert "recording_hook" in agent.get_hook_stats()


@pytest.mark.asyncio
async def test_unified_agent_default_path_fires_its_observability_hooks(
    tmp_path, monkeypatch
):
    """
    End to end on the path users actually take: Agent() → audit file written.

    Ties both layers of #2084 together. Everything real -- SmartDefaultsManager
    builds the manager, BaseAgent receives it, the audit hook writes JSONL.

    Nothing is passed but the model: the point is the UNTOUCHED default path,
    writing to the shipped default `audit_log_path` relative to the CWD.
    """
    import json

    from kaizen.agent import Agent

    monkeypatch.chdir(tmp_path)

    agent = Agent(model=MODEL, llm_provider=PROVIDER, show_startup_banner=False)

    assert agent.hook_manager is not None
    assert agent.base_agent is not None, "BaseAgent failed to initialise"

    await agent.base_agent.trigger_hook(
        HookEvent.PRE_AGENT_LOOP, data={"inputs": {"prompt": "hello"}}
    )

    audit_file = tmp_path / ".kaizen" / "audit.jsonl"
    assert audit_file.exists(), f"no audit file at the default path: {audit_file}"
    lines = audit_file.read_text().splitlines()
    assert lines, (
        "Agent() was constructed with enable_audit=True (the default), an event "
        "fired, and the audit trail recorded nothing"
    )
    assert json.loads(lines[0])["action"] == "pre_agent_loop"
