"""The Delegate — autonomous core engine for governed AI assistants.

The Delegate is the reusable autonomous engine that powers all AI assistant
products (kz CLI, aegis, arbor, impact-verse). It executes within constraint
envelopes defined by human judgment quality.

Named after organizational economics: a delegate receives delegated authority
and executes within defined boundaries, bearing no wealth effects.

Architecture (see terrene/terrene docs/03-technology/architecture/05-delegate-architecture.md):
    Layer 1: PRIMITIVES (kailash-kaizen, kailash-pact) — deterministic, no LLM
    Layer 2: ENGINES (kaizen-agents: Delegate + Orchestration) — LLM judgment
    Layer 3: ENTRYPOINTS (kaizen-cli-py, aegis, arbor) — human interface

Usage:
    from kaizen_agents.delegate import Delegate

    delegate = Delegate(
        model="claude-sonnet-4-6",
        budget_usd=10.0,
        tools=["read_file", "grep", "bash"],
    )
    async for event in delegate.run("analyze this codebase"):
        match event:
            case TextDelta(text): render(text)
            case ToolCallStart(...): show_status(...)
            case Done(summary): finish(summary)

Current State:
    This module contains code moved from the kaizen-cli-py repo (src/kz/).
    It needs to be wired to real SDK types (kaizen.l3, pact.governance)
    and refactored to extract the LLMAdapter protocol from the OpenAI
    hard-coupling in loop.py.

    Key refactoring needed:
    - loop.py: extract LLMAdapter protocol, split TAOD core from interactive
    - tools/base.py: unify the two ToolRegistry implementations
    - adapters/openai_stream.py: make provider-specific, not the only option
"""
