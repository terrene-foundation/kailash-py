"""The Delegate -- autonomous core engine for governed AI assistants.

The Delegate is the reusable autonomous engine that powers all AI assistant
products (kz CLI, aegis, arbor, impact-verse). It executes within constraint
envelopes defined by human judgment quality.

Named after organizational economics: a delegate receives delegated authority
and executes within defined boundaries, bearing no wealth effects.

Architecture (see terrene/terrene docs/03-technology/architecture/05-delegate-architecture.md):
    Layer 1: PRIMITIVES (kailash-kaizen, kailash-pact) -- deterministic, no LLM
    Layer 2: ENGINES (kaizen-agents: Delegate + Orchestration) -- LLM judgment
    Layer 3: ENTRYPOINTS (kaizen-cli-py, aegis, arbor) -- human interface

Usage::

    from kaizen_agents.delegate import Delegate

    delegate = Delegate(
        model="claude-sonnet-4-20250514",
        budget_usd=10.0,
    )
    async for event in delegate.run("analyze this codebase"):
        match event:
            case TextDelta(text=t): render(t)
            case ToolCallStart(name=n): show_status(n)
            case TurnComplete(text=t): finish(t)

Sub-modules:
    - ``delegate.py``: :class:`Delegate` facade (progressive-disclosure API)
    - ``events.py``: Typed event dataclasses (:class:`DelegateEvent` hierarchy)
    - ``loop.py``: :class:`AgentLoop` core engine
    - ``adapters/``: Multi-provider streaming adapters
    - ``tools/``: Tool hydration and search
    - ``config/``: Three-level config loader
"""

from kaizen_agents.delegate.delegate import (
    ConstructorIOError,
    Delegate,
    ToolRegistryCollisionError,
)
from kaizen_agents.delegate.events import (
    BudgetExhausted,
    DelegateEvent,
    ErrorEvent,
    TextDelta,
    ToolCallEnd,
    ToolCallStart,
    TurnComplete,
)

__all__ = [
    "Delegate",
    "ConstructorIOError",
    "ToolRegistryCollisionError",
    "DelegateEvent",
    "TextDelta",
    "ToolCallStart",
    "ToolCallEnd",
    "TurnComplete",
    "BudgetExhausted",
    "ErrorEvent",
]
