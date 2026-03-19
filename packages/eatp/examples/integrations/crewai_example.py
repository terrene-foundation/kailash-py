"""EATP + CrewAI Integration -- trust-constrained crew agents.

Demonstrates how to integrate EATP trust verification into a CrewAI-style
multi-agent crew. This example uses real EATP API calls and shows the
integration pattern with comments explaining where CrewAI primitives go.

Pattern:
    1. ESTABLISH trust for each crew role (researcher, writer, reviewer)
    2. Map EATP capabilities to CrewAI task permissions
    3. VERIFY trust before each task execution
    4. DELEGATE capabilities when agents hand off work
    5. AUDIT every completed task

Integration points (marked with # CREWAI:):
    - Agent creation with EATP-bound roles
    - Task execution gating
    - Crew process hooks

Run:
    python examples/integrations/crewai_example.py
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
# Crew Role Definitions -- maps crew roles to EATP capabilities
# ---------------------------------------------------------------------------

CREW_ROLES = {
    "researcher": {
        "agent_id": "crew-researcher",
        "capabilities": [
            CapabilityRequest(capability="search_web", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="read_documents", capability_type=CapabilityType.ACCESS),
            CapabilityRequest(capability="analyze_data", capability_type=CapabilityType.ACTION),
        ],
        "constraints": ["audit_required", "no_pii_export"],
    },
    "writer": {
        "agent_id": "crew-writer",
        "capabilities": [
            CapabilityRequest(capability="generate_content", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="edit_document", capability_type=CapabilityType.ACTION),
        ],
        "constraints": ["audit_required"],
    },
    "reviewer": {
        "agent_id": "crew-reviewer",
        "capabilities": [
            CapabilityRequest(capability="review_content", capability_type=CapabilityType.ACTION),
            CapabilityRequest(capability="approve_publication", capability_type=CapabilityType.ACTION),
        ],
        "constraints": ["audit_required", "read_only"],
    },
}


# ---------------------------------------------------------------------------
# Task definitions -- in CrewAI these would be Task objects
# ---------------------------------------------------------------------------


@dataclass
class CrewTask:
    """Represents a task in the crew pipeline.

    CREWAI: In a real CrewAI integration this would be:

        task = Task(
            description="Research quarterly trends",
            agent=researcher_agent,
            expected_output="Research summary with citations",
        )
    """

    name: str
    description: str
    required_action: str
    assigned_role: str
    output: Optional[str] = None


# ---------------------------------------------------------------------------
# EATP-Gated Task Runner
# ---------------------------------------------------------------------------


async def execute_task_with_trust(
    task: CrewTask,
    ops: TrustOperations,
    enforcer: StrictEnforcer,
) -> bool:
    """Execute a crew task with EATP trust verification.

    CREWAI: Wrap this as a CrewAI step_callback or task callback:

        @crew.task_callback
        def before_task(task, agent):
            result = ops.verify(agent_id=agent.eatp_id, action=task.action)
            enforcer.enforce(agent_id=agent.eatp_id, action=task.action, result=result)
    """
    role_config = CREW_ROLES[task.assigned_role]
    agent_id = role_config["agent_id"]

    print(f"\n  --- Task: {task.name} (role={task.assigned_role}) ---")

    # Step 1: VERIFY trust before execution
    result = await ops.verify(
        agent_id=agent_id,
        action=task.required_action,
        level=VerificationLevel.STANDARD,
    )

    verdict = enforcer.classify(result)
    print(f"  VERIFY: agent={agent_id} action={task.required_action} -> {verdict.value}")

    if not result.valid:
        print(f"  BLOCKED: {result.reason}")
        return False

    # Step 2: Execute the task (simulated -- in CrewAI this is the agent's work)
    task.output = f"[{task.assigned_role}] Completed: {task.description}"
    print(f"  EXECUTE: {task.output}")

    # Step 3: AUDIT the completed task
    anchor = await ops.audit(
        agent_id=agent_id,
        action=task.required_action,
        resource=f"task:{task.name}",
        result=ActionResult.SUCCESS,
        context_data={
            "task_name": task.name,
            "role": task.assigned_role,
            "description": task.description,
        },
    )
    print(f"  AUDIT: anchor={anchor.id[:12]}...")

    return True


# ---------------------------------------------------------------------------
# Crew Pipeline with Delegation
# ---------------------------------------------------------------------------


async def run_crew_pipeline(ops: TrustOperations, enforcer: StrictEnforcer):
    """Run a full crew pipeline with inter-agent delegation.

    CREWAI: In a real CrewAI integration:

        crew = Crew(
            agents=[researcher, writer, reviewer],
            tasks=[research_task, write_task, review_task],
            process=Process.sequential,
        )
        result = crew.kickoff()
    """
    tasks = [
        CrewTask(
            name="research",
            description="Research Q4 market trends in AI infrastructure",
            required_action="analyze_data",
            assigned_role="researcher",
        ),
        CrewTask(
            name="write_report",
            description="Write market analysis report from research findings",
            required_action="generate_content",
            assigned_role="writer",
        ),
        CrewTask(
            name="review_report",
            description="Review and approve the market analysis report",
            required_action="review_content",
            assigned_role="reviewer",
        ),
    ]

    print("--- Sequential Crew Pipeline ---")
    completed = []
    for task in tasks:
        success = await execute_task_with_trust(task, ops, enforcer)
        if success:
            completed.append(task)
        else:
            print(f"\n  Pipeline halted at task '{task.name}' -- trust denied")
            break

    return completed


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
            id="org-content-team",
            name="Content Production Team",
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

    # -- ESTABLISH trust for each crew role ----------------------------------
    print("=== Setup: ESTABLISH trust for crew roles ===")
    for role_name, role_config in CREW_ROLES.items():
        await ops.establish(
            agent_id=role_config["agent_id"],
            authority_id="org-content-team",
            capabilities=role_config["capabilities"],
            constraints=role_config["constraints"],
        )
        caps = await ops.get_agent_capabilities(role_config["agent_id"])
        constraints = await ops.get_agent_constraints(role_config["agent_id"])
        print(f"  {role_name}: capabilities={caps}, constraints={constraints}")

    # -- Scenario 1: Full pipeline -- all roles authorized -------------------
    print("\n=== Scenario 1: Full Authorized Pipeline ===")
    completed = await run_crew_pipeline(ops, enforcer)
    print(f"\n  Completed {len(completed)}/{3} tasks")

    # -- Scenario 2: Role attempts unauthorized action -----------------------
    print("\n=== Scenario 2: Writer Tries to Approve (Unauthorized) ===")
    unauthorized_task = CrewTask(
        name="writer_approves",
        description="Writer tries to approve their own content",
        required_action="approve_publication",
        assigned_role="writer",
    )
    success = await execute_task_with_trust(unauthorized_task, ops, enforcer)
    print(f"  Result: {'succeeded (unexpected)' if success else 'correctly blocked'}")

    # -- Scenario 3: Delegation within the crew ------------------------------
    print("\n=== Scenario 3: Researcher Delegates to Intern ===")
    delegation = await ops.delegate(
        delegator_id="crew-researcher",
        delegatee_id="crew-intern",
        task_id="task-data-collection",
        capabilities=["read_documents"],
        additional_constraints=["read_only"],
    )
    print(f"  Delegation ID: {delegation.id[:12]}...")

    intern_caps = await ops.get_agent_capabilities("crew-intern")
    intern_constraints = await ops.get_agent_constraints("crew-intern")
    print(f"  Intern capabilities: {intern_caps}")
    print(f"  Intern constraints: {intern_constraints}")

    # Intern can read documents
    intern_read = CrewTask(
        name="intern_reads",
        description="Intern reads background documents",
        required_action="read_documents",
        assigned_role="researcher",  # role config used for display only
    )
    # Override agent_id directly for the intern
    result = await ops.verify(agent_id="crew-intern", action="read_documents")
    print(f"\n  Intern read_documents: verified={result.valid}")

    # Intern cannot search the web (not delegated)
    result = await ops.verify(agent_id="crew-intern", action="search_web")
    print(f"  Intern search_web: verified={result.valid} ({result.reason})")

    # Intern cannot analyze data (not delegated)
    result = await ops.verify(agent_id="crew-intern", action="analyze_data")
    print(f"  Intern analyze_data: verified={result.valid} ({result.reason})")

    # -- Summary -------------------------------------------------------------
    print("\n=== Summary ===")
    print("EATP integration with CrewAI ensures:")
    print("  1. Each crew role has explicit, bounded capabilities")
    print("  2. Tasks are verified before execution")
    print("  3. Delegation narrows capabilities (never widens)")
    print("  4. Every action is recorded in the audit trail")
    print("\nCrewAI integration pattern completed.")


if __name__ == "__main__":
    asyncio.run(main())
