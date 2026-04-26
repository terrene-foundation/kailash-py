# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``MLAwareAgent`` — BaseAgent subclass with km-discovered ML tools.

Spec ``specs/kaizen-ml-integration.md §2.4.6`` defines the canonical
ML-aware Kaizen agent: a :class:`~kaizen.core.base_agent.BaseAgent`
subclass whose ML tool-set is built from
:func:`kaizen.ml.discover_ml_tools` rather than from hardcoded
``from kailash_ml.engines.<foo> import <Foo>`` imports. The
discovery path is the structural defense for ``§E11.3 MUST 3`` (the
version-sync invariant) — agents always reflect the runtime
``kailash_ml.__version__``, never the compile-time engine surface.

Architecture
------------

The agent is a thin composition layer:

1. :class:`MLAwareAgent` accepts an optional ``tenant_id`` for PACT
   envelope filtering (spec §2.4.3). ``None`` = single-tenant mode,
   every engine visible.
2. At construction time, :meth:`MLAwareAgent.build_ml_tools` calls
   :func:`kaizen.ml.discover_ml_tools` to enumerate every registered
   :class:`~kailash_ml.engines.registry.EngineInfo`.
3. Each :class:`~kailash_ml.engines.registry.MethodSignature` on each
   engine is converted to a :class:`~kaizen.tools.types.ToolDefinition`
   via :meth:`_signature_to_tool_definition` — the structural
   conversion preserves the engine name + method name + parameters and
   embeds the engine's runtime version into ``description`` so the
   §2.4.4 version-sync invariant is observable from the LLM-visible
   tool surface.
4. The constructed tool list is exposed via :attr:`MLAwareAgent.ml_tools`
   so callers can register the tools with the agent's MCP / tool-calling
   layer or surface them in capability cards.

LLM-First Reasoning Compliance
------------------------------

Per ``rules/agent-reasoning.md`` Permitted Deterministic Logic clauses
1, 5, 6: tool-set construction (mapping ``MethodSignature`` →
``ToolDefinition``), input validation, configuration branching, and
tool-result parsing are STRUCTURAL plumbing. They are NOT routing
decisions, classification, or content analysis — the LLM still owns
every decision about which tool to invoke. This module never inspects
user input nor branches on engine semantics.

Orphan-Detection Compliance
---------------------------

Per ``rules/orphan-detection.md §1`` and ``rules/facade-manager-detection.md``
this class is the production call site for the
:func:`kaizen.ml.discover_ml_tools` discovery surface — without
``MLAwareAgent``, the discovery helpers were advertised but never
invoked from any framework hot path.

Example
-------

.. code-block:: python

    from kaizen.ml import MLAwareAgent
    from kaizen.core import BaseAgentConfig

    agent = MLAwareAgent(
        config=BaseAgentConfig(llm_provider="mock"),
        tenant_id=None,
    )
    print(f"{len(agent.ml_tools)} ML tools available to the LLM")
    for tool in agent.ml_tools:
        print(f"  - {tool.name}: {tool.description[:60]}")

Cross-Reference
---------------

- Authoritative declaration: ``ml-engines-v2-addendum §E11`` (registry).
- Spec: ``specs/kaizen-ml-integration.md §2.4`` (binding clause).
- Helper: :func:`kaizen.ml.discover_ml_tools` (per-engine descriptors).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.ml._tool_discovery import (
    MLEngineDescriptor,
    MLRegistryUnavailableError,
    discover_ml_tools,
)
from kaizen.tools.types import (
    DangerLevel,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
)

__all__ = ["MLAwareAgent"]

logger = logging.getLogger(__name__)


# Sentinel value indicating a parameter has no default — mirrors the
# ``ParamSpec.default = "<NO_DEFAULT>"`` convention from the kailash-ml
# registry (spec ml-engines-v2-addendum §E11.1).
_NO_DEFAULT_SENTINEL = "<NO_DEFAULT>"


# Annotation strings → Python types. The registry stringifies type
# annotations (so ``EngineInfo`` stays hashable per §E11.1); we map
# the common builtins back to types so :class:`ToolParameter` can
# perform isinstance() validation. Unknown annotations fall back to
# ``object`` (accept any value) — ``ToolParameter.validate`` treats
# ``object`` as the universal type so engines exposing custom
# annotations don't fail tool-spec construction.
_ANNOTATION_TO_TYPE: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "bytes": bytes,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    "Any": object,
    "object": object,
    "None": type(None),
}


def _resolve_annotation(annotation: str) -> type:
    """Map a stringified annotation to a Python type.

    Falls back to ``object`` for any annotation the registry exposes
    that we don't recognize (e.g. ``"polars.DataFrame"``,
    ``"Optional[str]"``). ``object`` accepts any value at validation
    time so the LLM can still call the tool — semantic validation
    happens inside the engine, not in the tool-spec layer.
    """
    return _ANNOTATION_TO_TYPE.get(annotation.strip(), object)


class MLAwareAgent(BaseAgent):
    """``BaseAgent`` subclass whose tool-set is derived from the kailash-ml registry.

    Per ``specs/kaizen-ml-integration.md §2.4.6`` this is the canonical
    integration of ``BaseAgent`` with ``km.list_engines()`` /
    ``km.engine_info()`` for version-synchronized agent tool
    construction.

    Parameters
    ----------
    config:
        BaseAgent configuration (BaseAgentConfig or domain config).
        Auto-converted by :class:`BaseAgent.__init__`.
    tenant_id:
        Optional tenant scope. ``None`` = single-tenant mode (every
        engine visible). When set, only engines admissible under the
        tenant's PACT envelope are exposed in :attr:`ml_tools` (spec
        §2.4.3). Tenant-scoped filtering requires a
        ``clearance_filter`` callable; without one, ``tenant_id`` is
        recorded for downstream layers but does not gate engines —
        per spec §2.4.3 the filter implementation lives in PACT, not
        in this module.
    clearance_filter:
        Optional callable ``(EngineInfo, tenant_id) -> bool`` that
        applies PACT-envelope clearance gating. When ``None`` (the
        default), every engine returned by ``km.list_engines()`` is
        exposed. Per ``rules/agent-reasoning.md`` this is a structural
        gate, not agent decision logic.
    **kwargs:
        Forwarded to :class:`BaseAgent.__init__`.

    Attributes
    ----------
    ml_tools:
        Immutable tuple of :class:`ToolDefinition`, one per
        ``MethodSignature`` across all engines visible to this agent.
        The tuple is captured at construction time so the LLM-visible
        tool-set stays consistent across every turn (spec §2.4.6).
    ml_engines:
        Immutable tuple of :class:`MLEngineDescriptor` returned by
        :func:`discover_ml_tools` — kept so callers can introspect the
        underlying engines (e.g. to resolve a tool-name back to the
        canonical EngineInfo before invoking).

    Raises
    ------
    MLRegistryUnavailableError:
        Raised by :func:`discover_ml_tools` when ``km.engine_info`` /
        ``km.list_engines`` are not yet exposed by the installed
        ``kailash_ml``. Spec §2.4.5 blocks the direct-import fallback.
    """

    def __init__(
        self,
        config: Any,
        *,
        tenant_id: Optional[str] = None,
        clearance_filter: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=config, **kwargs)

        self._tenant_id = tenant_id
        self._clearance_filter = clearance_filter

        # Discovery — runs once at construction time so the LLM-visible
        # tool-set stays consistent across every turn (§2.4.6 immutable
        # snapshot guarantee).
        self.ml_engines: tuple[MLEngineDescriptor, ...] = self._discover_engines()
        self.ml_tools: tuple[ToolDefinition, ...] = self.build_ml_tools()

        logger.info(
            "kaizen.ml.aware_agent.ready",
            extra={
                "tenant_id_present": tenant_id is not None,
                "clearance_filter_active": clearance_filter is not None,
                "engine_count": len(self.ml_engines),
                "tool_count": len(self.ml_tools),
                "agent_id": self.agent_id,
            },
        )

    def _discover_engines(self) -> tuple[MLEngineDescriptor, ...]:
        """Return the engine snapshot for this agent.

        Wraps :func:`discover_ml_tools` so subclasses can override
        the discovery layer for testing — production callers MUST
        route through this method (the helper enforces §2.4.5: no
        hardcoded engine imports).
        """
        return discover_ml_tools(
            tenant_id=self._tenant_id,
            clearance_filter=self._clearance_filter,
        )

    def build_ml_tools(self) -> tuple[ToolDefinition, ...]:
        """Convert every discovered engine's signatures into tool definitions.

        Spec §2.4.6: a Kaizen agent's tool-spec list is derived by
        traversing ``EngineInfo.signatures`` — one tool per
        ``MethodSignature``, named ``{engine.name}.{sig.method_name}``.
        The tool's ``description`` embeds the engine's runtime version
        so the §2.4.4 version-sync invariant is observable on the
        LLM-visible surface (the version drift surface, not just the
        ``EngineInfo.version`` field).

        Returns
        -------
        Immutable tuple of :class:`ToolDefinition`. Order matches the
        underlying ``km.list_engines()`` order (insertion-stable per
        §E11.2).
        """
        tools: list[ToolDefinition] = []
        for descriptor in self.ml_engines:
            for sig in descriptor.signatures:
                tools.append(self._signature_to_tool_definition(descriptor, sig))
        return tuple(tools)

    @staticmethod
    def _signature_to_tool_definition(
        descriptor: MLEngineDescriptor,
        signature: Any,
    ) -> ToolDefinition:
        """Map one ``(engine, method)`` pair to a :class:`ToolDefinition`.

        Per spec §2.4.6, the canonical conversion is::

            ToolDefinition(
                name=f"{engine.name}.{sig.method_name}",
                description=f"Version-synchronized with {engine.name} v{engine.version}",
                parameters=[ParamSpec → ToolParameter for every sig.param],
            )

        The ``executor`` field is left as a placeholder lambda that
        raises :class:`MLRegistryUnavailableError` when invoked — the
        LLM-visible tool surface is what matters here. Actual execution
        is the caller's responsibility (resolve tool-name back to
        :class:`MLEngineDescriptor` via :attr:`ml_engines`, then invoke
        the engine's method through the live registry).

        Per ``rules/agent-reasoning.md`` Permitted Deterministic Logic
        Rule 6 (tool-result parsing) this is structural plumbing —
        no decision logic about what the agent should think or do.
        """
        # Convert each ParamSpec into a ToolParameter. The registry
        # uses the sentinel ``"<NO_DEFAULT>"`` to flag positional-required
        # args; map back to ``required=True``.
        tool_params: list[ToolParameter] = []
        for param_spec in signature.params:
            has_default = (
                param_spec.default is not None
                and param_spec.default != _NO_DEFAULT_SENTINEL
            )
            tool_params.append(
                ToolParameter(
                    name=param_spec.name,
                    type=_resolve_annotation(param_spec.annotation),
                    description=(
                        f"Parameter {param_spec.name!r} of "
                        f"{descriptor.name}.{signature.method_name}() "
                        f"(annotation: {param_spec.annotation}, "
                        f"kind: {param_spec.kind})"
                    ),
                    required=not has_default,
                    default=param_spec.default if has_default else None,
                )
            )

        # Description embeds the runtime engine version per spec
        # §2.4.4 — the version-sync invariant is observable on the
        # LLM-visible tool surface, not just the EngineInfo.version
        # field. A future kailash_ml bump that does NOT propagate to
        # tool descriptions flips the wiring test red.
        description = (
            f"Version-synchronized with {descriptor.name} v{descriptor.version}: "
            f"{signature.method_name}() — async={signature.is_async}, "
            f"returns={signature.return_annotation}"
        )

        # Returns shape — the registry stringifies the return
        # annotation; expose it under the conventional ``"result"``
        # key so the LLM has a uniform shape to reason about.
        returns: dict[str, Any] = {"result": signature.return_annotation}

        # Executor placeholder. Real execution requires resolving the
        # tool-name back to the canonical engine via
        # :attr:`MLAwareAgent.ml_engines` and invoking the live method
        # — that's the caller's job, not the tool-spec layer's.
        def _executor(**_kwargs: Any) -> dict[str, Any]:
            raise MLRegistryUnavailableError(
                f"MLAwareAgent tool {descriptor.name}.{signature.method_name!r} "
                "has no executor wired — resolve via MLAwareAgent.ml_engines "
                "and call the engine method directly. The tool-spec layer is "
                "discovery-only per spec §2.4.6."
            )

        return ToolDefinition(
            name=f"{descriptor.name}.{signature.method_name}",
            description=description,
            category=ToolCategory.AI,
            danger_level=DangerLevel.MEDIUM,
            parameters=tool_params,
            returns=returns,
            executor=_executor,
        )
