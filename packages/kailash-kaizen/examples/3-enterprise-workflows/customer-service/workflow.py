"""
Customer Service Enterprise Workflow

This example demonstrates automated customer support using multi-agent collaboration.

Agents:
1. TicketTriageAgent - Triages support tickets by priority, category, urgency
2. KnowledgeSearchAgent - Searches knowledge base for solutions
3. ResponseGeneratorAgent - Generates customer-facing responses
4. TicketRouterAgent - Routes tickets to appropriate teams/agents

Use Cases:
- Automated ticket triage
- Knowledge base search
- Response generation
- Ticket routing and escalation
- Customer sentiment analysis

Architecture Pattern: Sequential Pipeline with Shared Memory
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaizen.core.base_agent import BaseAgent
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# ===== Configuration =====


@dataclass
class CustomerServiceConfig:
    """Configuration for customer service workflow."""

    llm_provider: str = "mock"
    model: str = "gpt-3.5-turbo"
    auto_response: bool = True
    knowledge_base_enabled: bool = True
    max_articles: int = 5
    response_tone: str = "professional"  # "professional", "friendly", "formal"
    routing_enabled: bool = True
    escalation_threshold: str = "high"  # "low", "medium", "high", "critical"


# ===== Signatures =====


class TicketTriageSignature(Signature):
    """Signature for ticket triage."""

    ticket: str = InputField(description="Support ticket data as JSON")

    priority: str = OutputField(
        description="Ticket priority (low, medium, high, critical)"
    )
    category: str = OutputField(description="Ticket category")
    urgency: str = OutputField(description="Urgency level")


class KnowledgeSearchSignature(Signature):
    """Signature for knowledge base search."""

    query: str = InputField(description="Search query")

    articles: str = OutputField(description="Relevant articles as JSON")
    solutions: str = OutputField(description="Suggested solutions as JSON")


class ResponseGenerationSignature(Signature):
    """Signature for response generation."""

    ticket: str = InputField(description="Support ticket as JSON")
    knowledge: str = InputField(description="Knowledge base results as JSON")

    response: str = OutputField(description="Customer response text")
    tone: str = OutputField(description="Response tone")


class TicketRoutingSignature(Signature):
    """Signature for ticket routing."""

    triage_result: str = InputField(description="Triage result as JSON")

    routing_decision: str = OutputField(description="Routing decision")
    assigned_team: str = OutputField(description="Assigned team/agent")


# ===== Agents =====


class TicketTriageAgent(BaseAgent):
    """Agent for triaging support tickets."""

    def __init__(
        self,
        config: CustomerServiceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "triage",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=TicketTriageSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.service_config = config

    def triage(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        """Triage support ticket."""
        # Run agent
        result = self.run(ticket=json.dumps(ticket))

        # Extract outputs
        priority = result.get("priority", "medium")
        category = result.get("category", "general")
        urgency = result.get("urgency", "normal")

        triage_result = {"priority": priority, "category": category, "urgency": urgency}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=triage_result,  # Auto-serialized
            tags=["triage", "pipeline"],
            importance=0.9,
            segment="pipeline",
        )

        return triage_result


class KnowledgeSearchAgent(BaseAgent):
    """Agent for searching knowledge base."""

    def __init__(
        self,
        config: CustomerServiceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "search",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=KnowledgeSearchSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.service_config = config

    def search_knowledge(self, query: str) -> Dict[str, Any]:
        """Search knowledge base."""
        # Run agent
        result = self.run(query=query)

        # Extract outputs
        articles_raw = result.get("articles", "[]")
        if isinstance(articles_raw, str):
            try:
                articles = json.loads(articles_raw) if articles_raw else []
            except:
                articles = [articles_raw]
        else:
            articles = (
                articles_raw
                if isinstance(articles_raw, list)
                else [articles_raw] if articles_raw else []
            )

        solutions_raw = result.get("solutions", "[]")
        if isinstance(solutions_raw, str):
            try:
                solutions = json.loads(solutions_raw) if solutions_raw else []
            except:
                solutions = [solutions_raw]
        else:
            solutions = (
                solutions_raw
                if isinstance(solutions_raw, list)
                else [solutions_raw] if solutions_raw else []
            )

        search_result = {
            "articles": articles[: self.service_config.max_articles],
            "solutions": solutions,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=search_result,  # Auto-serialized
            tags=["knowledge", "pipeline"],
            importance=0.8,
            segment="pipeline",
        )

        return search_result


class ResponseGeneratorAgent(BaseAgent):
    """Agent for generating customer responses."""

    def __init__(
        self,
        config: CustomerServiceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "response",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=ResponseGenerationSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.service_config = config

    def generate_response(
        self, ticket: Dict[str, Any], knowledge: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate customer response."""
        # Run agent
        result = self.run(ticket=json.dumps(ticket), knowledge=json.dumps(knowledge))

        # Extract outputs
        response = result.get(
            "response", "Thank you for contacting us. We will review your request."
        )
        tone = result.get("tone", self.service_config.response_tone)

        response_result = {"response": response, "tone": tone}

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=response_result,  # Auto-serialized
            tags=["response", "pipeline"],
            importance=1.0,
            segment="pipeline",
        )

        return response_result


class TicketRouterAgent(BaseAgent):
    """Agent for routing tickets."""

    def __init__(
        self,
        config: CustomerServiceConfig,
        shared_memory: Optional[SharedMemoryPool] = None,
        agent_id: str = "router",
    ):
        # UX Improvement: Pass config directly - auto-converted to BaseAgentConfig!
        super().__init__(
            config=config,  # Auto-extracted!
            signature=TicketRoutingSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

        self.service_config = config

    def route(self, triage_result: Dict[str, Any]) -> Dict[str, Any]:
        """Route ticket to appropriate team."""
        # Run agent
        result = self.run(triage_result=json.dumps(triage_result))

        # Extract outputs
        routing_decision = result.get("routing_decision", "general_support")
        assigned_team = result.get("assigned_team", "support_team")

        routing_result = {
            "routing_decision": routing_decision,
            "assigned_team": assigned_team,
        }

        # Write to shared memory if available
        # UX Improvement: Concise shared memory write

        self.write_to_memory(
            content=routing_result,  # Auto-serialized
            tags=["routing", "pipeline"],
            importance=0.85,
            segment="pipeline",
        )

        return routing_result


# ===== Workflow Functions =====


def customer_service_workflow(
    ticket: Dict[str, Any], config: Optional[CustomerServiceConfig] = None
) -> Dict[str, Any]:
    """
    Execute customer service workflow.

    Args:
        ticket: Support ticket with 'ticket_id', 'subject', 'description', etc.
        config: Configuration for customer service

    Returns:
        Complete ticket processing with triage, knowledge, response, and routing
    """
    if config is None:
        config = CustomerServiceConfig()

    # Create shared memory pool
    shared_pool = SharedMemoryPool()

    # Create agents
    triage_agent = TicketTriageAgent(config, shared_pool, "triage")
    search_agent = KnowledgeSearchAgent(config, shared_pool, "search")
    response_agent = ResponseGeneratorAgent(config, shared_pool, "response")
    router_agent = TicketRouterAgent(config, shared_pool, "router")

    # Execute pipeline
    # Stage 1: Triage ticket
    triage = triage_agent.triage(ticket)

    # Stage 2: Search knowledge base
    query = ticket.get("subject", "") + " " + ticket.get("description", "")
    knowledge = search_agent.search_knowledge(query)

    # Stage 3: Generate response
    response = response_agent.generate_response(ticket, knowledge)

    # Stage 4: Route ticket
    routing = router_agent.route(triage)

    return {
        "ticket_id": ticket.get("ticket_id", "unknown"),
        "triage": triage,
        "knowledge": knowledge,
        "response": response,
        "routing": routing,
    }


def batch_ticket_processing(
    tickets: List[Dict[str, Any]], config: Optional[CustomerServiceConfig] = None
) -> List[Dict[str, Any]]:
    """
    Execute batch ticket processing.

    Args:
        tickets: List of support tickets
        config: Configuration for customer service

    Returns:
        List of complete ticket processing results
    """
    if config is None:
        config = CustomerServiceConfig()

    results = []

    # Process each ticket
    for ticket in tickets:
        result = customer_service_workflow(ticket, config)
        results.append(result)

    return results


# ===== Main Entry Point =====

if __name__ == "__main__":
    # Example usage
    config = CustomerServiceConfig(llm_provider="mock")

    # Single ticket processing
    ticket = {
        "ticket_id": "T12345",
        "subject": "Cannot login to my account",
        "description": "I'm getting an error message when trying to log in. It says 'Invalid credentials' but I'm sure my password is correct.",
        "customer_email": "customer@example.com",
        "priority": "high",
    }

    print("=== Single Ticket Processing ===")
    result = customer_service_workflow(ticket, config)
    print(f"Ticket: {result['ticket_id']}")
    print(f"Priority: {result['triage']['priority']}")
    print(f"Category: {result['triage']['category']}")
    print(f"Articles: {len(result['knowledge']['articles'])}")
    print(f"Response: {result['response']['response'][:100]}...")
    print(f"Assigned to: {result['routing']['assigned_team']}")

    # Batch ticket processing
    tickets = [
        {"ticket_id": "T1", "subject": "Login issue", "description": "Cannot login"},
        {
            "ticket_id": "T2",
            "subject": "Payment failed",
            "description": "Card declined",
        },
        {
            "ticket_id": "T3",
            "subject": "Feature request",
            "description": "Need export feature",
        },
    ]

    print("\n=== Batch Ticket Processing ===")
    results = batch_ticket_processing(tickets, config)
    print(f"Processed {len(results)} tickets")
    for i, result in enumerate(results, 1):
        print(
            f"{i}. {result['ticket_id']}: {result['triage']['priority']} priority, {result['routing']['assigned_team']}"
        )
