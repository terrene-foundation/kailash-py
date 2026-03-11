"""EATP + LangGraph Integration -- trust-verified graph execution.

Demonstrates how to integrate EATP trust verification into a LangGraph-style
stateful graph. This example uses real EATP API calls and shows the integration
pattern with comments explaining where LangGraph primitives would go.

Pattern:
    1. ESTABLISH trust for each agent node in the graph
    2. Before every tool/action node, run EATP VERIFY
    3. Use StrictEnforcer to block unauthorized transitions
    4. Record AUDIT anchors for every completed graph step

Integration points (marked with # LANGGRAPH:):
    - StateGraph node registration
    - Conditional edge routing based on trust verdicts
    - Graph state annotation with trust metadata

Run:
    python examples/integrations/langgraph_example.py
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from eatp import CapabilityRequest, TrustKeyManager, TrustOperations
from eatp.authority import AuthorityPermission, OrganizationalAuthority
from eatp.chain import ActionResult, AuthorityType, CapabilityType, VerificationLevel
from eatp.crypto import generate_keypair
from eatp.enforce.strict import EATPBlockedError, StrictEnforcer, Verdict
from eatp.store.memory import InMemoryTrustStore


class SimpleAuthorityRegistry:
    """Minimal in-memory authority registry for examples."""

    def __init__(self):
        self._authorities = {}

    async def initialize(self):
        pass

    def register(self, authority: OrganizationalAuthority):
        self._authorities[authority.id] = authority

    async def get_authority(self, authority_id: str, include_inactive: bool = False):
        authority = self._authorities.get(authority_id)
        if authority is None:
            raise KeyError(f"Authority not found: {authority_id}")
        return authority


# ---------------------------------------------------------------------------
# Graph State -- in LangGraph this would be a TypedDict with Annotated fields
# ---------------------------------------------------------------------------


@dataclass
class GraphState:
    """State object flowing through the graph.

    LANGGRAPH: In a real LangGraph integration this would be:

        class GraphState(TypedDict):
            query: str
            trust_verified: Annotated[bool, "EATP verification status"]
            results: list[str]
            audit_trail: list[str]
    """

    query: str = ""
    trust_verified: bool = False
    results: List[str] = field(default_factory=list)
    audit_trail: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph Nodes -- each function represents a node in the LangGraph graph
# ---------------------------------------------------------------------------


async def eatp_verify_node(
    state: GraphState,
    ops: TrustOperations,
    enforcer: StrictEnforcer,
    agent_id: str,
    action: str,
) -> GraphState:
    """EATP verification node -- gates downstream execution.

    LANGGRAPH: Register this as a graph node:

        graph.add_node("verify_trust", eatp_verify_node)
        graph.add_edge("__start__", "verify_trust")
    """
    print(f"  [verify_trust] Verifying agent={agent_id} action={action}")
    result = await ops.verify(
        agent_id=agent_id,
        action=action,
        level=VerificationLevel.STANDARD,
    )

    verdict = enforcer.classify(result)
    state.trust_verified = result.valid
    state.audit_trail.append(
        f"VERIFY agent={agent_id} action={action} verdict={verdict.value}"
    )

    if verdict == Verdict.BLOCKED:
        print(f"  [verify_trust] BLOCKED: {result.reason}")
    else:
        print(f"  [verify_trust] {verdict.value} -- proceeding")
    return state


async def analyze_node(
    state: GraphState, ops: TrustOperations, agent_id: str
) -> GraphState:
    """Analysis node -- only runs if trust was verified.

    LANGGRAPH: Register and connect conditionally:

        graph.add_node("analyze", analyze_node)
        graph.add_conditional_edges(
            "verify_trust",
            lambda s: "analyze" if s["trust_verified"] else "__end__",
        )
    """
    print(f"  [analyze] Processing query: {state.query}")

    # Simulate analysis work
    analysis_result = (
        f"Analysis of '{state.query}': 42 records found, 3 anomalies detected"
    )
    state.results.append(analysis_result)

    # Record audit trail
    anchor = await ops.audit(
        agent_id=agent_id,
        action="analyze_data",
        resource=f"query:{state.query}",
        result=ActionResult.SUCCESS,
        context_data={"records": 42, "anomalies": 3},
    )
    state.audit_trail.append(f"AUDIT anchor={anchor.id[:12]}... action=analyze_data")
    print(f"  [analyze] Complete -- audit anchor {anchor.id[:12]}...")
    return state


async def report_node(
    state: GraphState, ops: TrustOperations, agent_id: str
) -> GraphState:
    """Report generation node.

    LANGGRAPH: graph.add_node("report", report_node)
               graph.add_edge("analyze", "report")
    """
    print(f"  [report] Generating report from {len(state.results)} result(s)")

    report = f"Report: {'; '.join(state.results)}"
    state.results.append(report)

    anchor = await ops.audit(
        agent_id=agent_id,
        action="generate_report",
        resource="report:quarterly",
        result=ActionResult.SUCCESS,
        context_data={"sections": len(state.results)},
    )
    state.audit_trail.append(f"AUDIT anchor={anchor.id[:12]}... action=generate_report")
    print(f"  [report] Complete -- audit anchor {anchor.id[:12]}...")
    return state


# ---------------------------------------------------------------------------
# Graph Execution -- simulates LangGraph's compile-and-invoke pattern
# ---------------------------------------------------------------------------


async def run_graph(
    ops: TrustOperations,
    enforcer: StrictEnforcer,
    agent_id: str,
    action: str,
    query: str,
) -> GraphState:
    """Execute the trust-gated graph.

    LANGGRAPH: In real LangGraph you would do:

        graph = StateGraph(GraphState)
        graph.add_node("verify_trust", eatp_verify_node)
        graph.add_node("analyze", analyze_node)
        graph.add_node("report", report_node)
        graph.add_edge("__start__", "verify_trust")
        graph.add_conditional_edges(
            "verify_trust",
            lambda s: "analyze" if s["trust_verified"] else "__end__",
        )
        graph.add_edge("analyze", "report")
        graph.add_edge("report", "__end__")
        app = graph.compile()
        result = await app.ainvoke({"query": query})
    """
    state = GraphState(query=query)

    # Step 1: EATP verification gate
    state = await eatp_verify_node(state, ops, enforcer, agent_id, action)

    # Step 2: Conditional routing -- only proceed if verified
    if not state.trust_verified:
        print("  [router] Trust verification failed -- ending graph")
        return state

    # Step 3: Analysis
    state = await analyze_node(state, ops, agent_id)

    # Step 4: Report
    state = await report_node(state, ops, agent_id)

    return state


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    # -- Setup EATP infrastructure -------------------------------------------
    store = InMemoryTrustStore()
    await store.initialize()

    key_mgr = TrustKeyManager()
    priv_key, pub_key = generate_keypair()
    key_mgr.register_key("key-org", priv_key)

    registry = SimpleAuthorityRegistry()
    registry.register(
        OrganizationalAuthority(
            id="org-research",
            name="Research Division",
            authority_type=AuthorityType.ORGANIZATION,
            public_key=pub_key,
            signing_key_id="key-org",
            permissions=[
                AuthorityPermission.CREATE_AGENTS,
                AuthorityPermission.DELEGATE_TRUST,
            ],
        )
    )

    ops = TrustOperations(
        authority_registry=registry,
        key_manager=key_mgr,
        trust_store=store,
    )

    enforcer = StrictEnforcer()

    # -- Establish trust for the graph agent ---------------------------------
    print("=== Setup: ESTABLISH trust for graph-agent ===")
    await ops.establish(
        agent_id="graph-agent",
        authority_id="org-research",
        capabilities=[
            CapabilityRequest(
                capability="analyze_data",
                capability_type=CapabilityType.ACTION,
            ),
            CapabilityRequest(
                capability="generate_report",
                capability_type=CapabilityType.ACTION,
            ),
        ],
        constraints=["audit_required"],
    )
    caps = await ops.get_agent_capabilities("graph-agent")
    print(f"  Agent capabilities: {caps}")

    # -- Scenario 1: Authorized graph execution ------------------------------
    print("\n=== Scenario 1: Authorized Action (analyze_data) ===")
    state = await run_graph(
        ops=ops,
        enforcer=enforcer,
        agent_id="graph-agent",
        action="analyze_data",
        query="quarterly revenue trends",
    )
    print(f"\n  Final results: {len(state.results)} items")
    print(f"  Audit trail: {len(state.audit_trail)} entries")
    for entry in state.audit_trail:
        print(f"    - {entry}")

    # -- Scenario 2: Unauthorized action -- graph halts at verify node -------
    print("\n=== Scenario 2: Unauthorized Action (delete_records) ===")
    state = await run_graph(
        ops=ops,
        enforcer=enforcer,
        agent_id="graph-agent",
        action="delete_records",
        query="purge old data",
    )
    print(f"\n  Final results: {len(state.results)} items (should be 0)")
    print(f"  Audit trail: {len(state.audit_trail)} entries")
    for entry in state.audit_trail:
        print(f"    - {entry}")

    # -- Scenario 3: Delegated agent with tighter constraints ----------------
    print("\n=== Scenario 3: Delegated Agent in Graph ===")
    await ops.delegate(
        delegator_id="graph-agent",
        delegatee_id="junior-graph-agent",
        task_id="task-q4-analysis",
        capabilities=["analyze_data"],
        additional_constraints=["no_pii_export"],
    )
    junior_caps = await ops.get_agent_capabilities("junior-graph-agent")
    print(f"  Junior agent capabilities: {junior_caps}")

    state = await run_graph(
        ops=ops,
        enforcer=enforcer,
        agent_id="junior-graph-agent",
        action="analyze_data",
        query="employee satisfaction survey",
    )
    print(f"\n  Final results: {len(state.results)} items")
    for entry in state.audit_trail:
        print(f"    - {entry}")

    # Junior cannot generate reports (not delegated)
    print("\n=== Scenario 4: Junior Agent -- Unauthorized Report ===")
    state = await run_graph(
        ops=ops,
        enforcer=enforcer,
        agent_id="junior-graph-agent",
        action="generate_report",
        query="annual summary",
    )
    print(f"\n  Blocked: results={len(state.results)} (should be 0)")

    print("\nLangGraph integration pattern completed.")
    print(
        "Replace the run_graph() simulation with LangGraph's StateGraph for production."
    )


if __name__ == "__main__":
    asyncio.run(main())
