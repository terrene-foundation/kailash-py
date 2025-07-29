# Agent Patterns

Patterns for building intelligent agent systems with coordination, self-organization, and tool integration.

## 1. Basic Self-Organizing Agent Pool

**Purpose**: Create autonomous agent teams that solve problems collaboratively

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.ai import (
    OrchestrationManagerNode,
    IntelligentCacheNode,
    SharedMemoryPoolNode
)

# Create self-organizing agent workflow
workflow = WorkflowBuilder()

# Shared infrastructure for agents
workflow.add_node("SharedMemoryPoolNode", "memory", {
    "capacity": 1000,
    "eviction_policy": "lru"
})

workflow.add_node("IntelligentCacheNode", "cache", {
    "ttl": 3600,
    "max_size": 500,
    "similarity_threshold": 0.85
})

# Orchestration manager coordinates agents
workflow.add_node("OrchestrationManagerNode", "orchestrator", {
    "max_iterations": 5,
    "quality_threshold": 0.8,
    "time_limit_minutes": 10,
    "min_confidence": 0.7,
    "enable_learning": True
})

# Connect shared resources
workflow.add_connection("memory", "pool", "orchestrator", "shared_memory")
workflow.add_connection("cache", "cache", "orchestrator", "shared_cache")

# Execute with dynamic agent configuration
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build(), parameters={
    "orchestrator": {
        "query": "Analyze market trends and recommend investment strategy",
        "agent_pool_config": {
            "size": 10,
            "diversity_factor": 0.7,  # Mix of specialists and generalists
            "collaboration_mode": "competitive_cooperation"
        },
        "tool_access": {
            "market_data": {"type": "api", "rate_limit": 100},
            "financial_analysis": {"type": "compute", "priority": "high"},
            "news_sentiment": {"type": "stream", "real_time": True}
        }
    }
})

print(f"Agent pool generated {len(results['orchestrator']['iterations'])} iterations")
print(f"Final quality score: {results['orchestrator']['quality_score']}")
print(f"Consensus reached: {results['orchestrator']['consensus']}")

```

## 2. MCP-Enhanced Agent Pattern

**Purpose**: Agents with external tool access via Model Context Protocol

```python
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.mixins import MCPMixin

# Create custom MCP-enabled agent
class ResearchAgentNode(MCPMixin, LLMAgentNode):
    """Research agent with MCP tool access"""

    def __init__(self, **config):
        super().__init__(**config)
        self.mcp_capabilities = [
            "web_search",
            "document_analysis",
            "citation_extraction",
            "fact_checking"
        ]

    async def run(self, **kwargs):
        query = kwargs.get('query')

        # Use MCP tools for research
        search_results = await self.call_mcp_tool(
            "web_search",
            {"query": query, "max_results": 10}
        )

        # Analyze documents
        analyses = []
        for result in search_results:
            if result.get('url'):
                analysis = await self.call_mcp_tool(
                    "document_analysis",
                    {"url": result['url'], "extract": ["key_points", "citations"]}
                )
                analyses.append(analysis)

        # Fact check key claims
        facts_to_check = self.extract_claims(analyses)
        fact_checks = await self.call_mcp_tool(
            "fact_checking",
            {"claims": facts_to_check}
        )

        # Generate research summary
        prompt = self.build_research_prompt(query, analyses, fact_checks)
        response = await super().run(prompt=prompt)

        return {
            'research_summary': response,
            'sources': search_results,
            'fact_checks': fact_checks,
            'confidence': self.calculate_confidence(fact_checks)
        }

# Create specialized agent team
workflow = WorkflowBuilder()

# Add specialized agents
workflow.add_node("ResearchAgentNode", "research_lead", {}),
    model="gpt-4",
    mcp_server="research_tools",
    shared_cache=True
)

workflow.add_node("LLMAgentNode", "data_analyst", {}),
    model="gpt-4",
    mcp_server="data_tools",
    mcp_capabilities=["sql_query", "data_visualization", "statistical_analysis"]
)

workflow.add_node("LLMAgentNode", "strategist", {}),
    model="claude-3-opus",
    mcp_server="strategy_tools",
    mcp_capabilities=["swot_analysis", "scenario_planning", "risk_assessment"]
)

# Coordinator to manage agent collaboration
workflow.add_node("PythonCodeNode", "coordinator", {}),
    code="""
# Coordinate agent outputs
research = research_summary.get('research_summary')
data_insights = data_analysis.get('insights')
strategy = strategy_recommendation.get('recommendation')

# Synthesize findings
synthesis = {
    'executive_summary': f"{research['key_finding']} supported by {len(data_insights)} data points",
    'recommended_actions': strategy['actions'],
    'confidence_level': min(
        research_summary.get('confidence', 0),
        data_analysis.get('confidence', 0),
        strategy_recommendation.get('confidence', 0)
    ),
    'supporting_evidence': {
        'research': research['sources'][:3],
        'data': data_insights[:3],
        'strategic_rationale': strategy['rationale']
    }
}

result = synthesis
"""
)

# Connect agents through coordinator
workflow.add_connection("research_lead", "coordinator", "result", "research_summary")
workflow.add_connection("data_analyst", "coordinator", "result", "data_analysis")
workflow.add_connection("strategist", "coordinator", "result", "strategy_recommendation")

```

## 3. Hierarchical Agent Organization

**Purpose**: Multi-level agent hierarchy for complex problem decomposition

```python
from kailash.nodes.ai import AgentSupervisorNode, AgentWorkerNode

workflow = WorkflowBuilder()

# Top-level supervisor
workflow.add_node("AgentSupervisorNode", "ceo_agent", {}),
    role="strategic_oversight",
    decision_authority=["approve", "reject", "delegate"],
    subordinates=["cto_agent", "cfo_agent", "cmo_agent"]
)

# Department heads
workflow.add_node("AgentSupervisorNode", "cto_agent", {}),
    role="technology_leadership",
    expertise=["architecture", "innovation", "technical_feasibility"],
    subordinates=["dev_team_lead", "qa_team_lead", "devops_lead"]
)

workflow.add_node("AgentSupervisorNode", "cfo_agent", {}),
    role="financial_oversight",
    expertise=["budgeting", "roi_analysis", "risk_assessment"],
    subordinates=["budget_analyst", "risk_analyst"]
)

# Worker agents
workflow.add_node("AgentWorkerNode", "dev_team_lead", {}),
    role="development_execution",
    skills=["coding", "architecture", "estimation"],
    report_to="cto_agent"
)

workflow.add_node("AgentWorkerNode", "budget_analyst", {}),
    role="budget_analysis",
    skills=["financial_modeling", "cost_analysis"],
    report_to="cfo_agent"
)

# Task delegation flow
workflow.add_node("PythonCodeNode", "task_delegator", {}),
    code="""
# Parse high-level request
request = parse_request(input_request)

# CEO agent breaks down into strategic initiatives
strategic_breakdown = {
    'initiatives': [
        {
            'id': 'tech_modernization',
            'owner': 'cto_agent',
            'budget_required': True,
            'timeline': '6_months'
        },
        {
            'id': 'cost_optimization',
            'owner': 'cfo_agent',
            'dependencies': ['tech_modernization'],
            'timeline': '3_months'
        }
    ]
}

# Delegate to department heads
delegated_tasks = []
for initiative in strategic_breakdown['initiatives']:
    task = {
        'initiative_id': initiative['id'],
        'assigned_to': initiative['owner'],
        'requirements': extract_requirements(request, initiative),
        'constraints': {
            'timeline': initiative['timeline'],
            'budget': initiative.get('budget_limit'),
            'dependencies': initiative.get('dependencies', [])
        }
    }
    delegated_tasks.append(task)

result = {
    'strategic_plan': strategic_breakdown,
    'delegated_tasks': delegated_tasks,
    'coordination_required': identify_coordination_needs(delegated_tasks)
}
"""
)

# Connect hierarchy
workflow.add_connection("task_delegator", "ceo_agent", "result", "strategic_input")
workflow.add_connection("ceo_agent", "cto_agent", "tech_initiatives", "tasks")
workflow.add_connection("ceo_agent", "cfo_agent", "financial_initiatives", "tasks")
workflow.add_connection("cto_agent", "dev_team_lead", "dev_tasks", "assignments")
workflow.add_connection("cfo_agent", "budget_analyst", "budget_tasks", "assignments")

```

## 4. Swarm Intelligence Pattern

**Purpose**: Large-scale parallel agent coordination for exploration tasks

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()

# Swarm configuration
workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "swarm_controller", {}),
    code="""
import random
import numpy as np

class SwarmController:
    def __init__(self, swarm_size=50, dimensions=10):
        self.swarm_size = swarm_size
        self.dimensions = dimensions
        self.agents = self._initialize_swarm()
        self.global_best = None
        self.global_best_score = float('-inf')

    def _initialize_swarm(self):
        agents = []
        for i in range(self.swarm_size):
            agent = {
                'id': f'agent_{i}',
                'position': np.random.rand(self.dimensions),
                'velocity': np.random.rand(self.dimensions) * 0.1,
                'personal_best': None,
                'personal_best_score': float('-inf'),
                'exploration_factor': random.uniform(0.1, 0.9)
            }
            agents.append(agent)
        return agents

    def update_swarm(self, fitness_function):
        for agent in self.agents:
            # Evaluate current position
            score = fitness_function(agent['position'])

            # Update personal best
            if score > agent['personal_best_score']:
                agent['personal_best'] = agent['position'].copy()
                agent['personal_best_score'] = score

            # Update global best
            if score > self.global_best_score:
                self.global_best = agent['position'].copy()
                self.global_best_score = score

        # Update velocities and positions
        for agent in self.agents:
            # PSO update rules with exploration factor
            inertia = 0.7
            cognitive = 2.0 * agent['exploration_factor']
            social = 2.0 * (1 - agent['exploration_factor'])

            r1, r2 = random.random(), random.random()

            if agent['personal_best'] is not None:
                cognitive_component = cognitive * r1 * (agent['personal_best'] - agent['position'])
            else:
                cognitive_component = 0

            if self.global_best is not None:
                social_component = social * r2 * (self.global_best - agent['position'])
            else:
                social_component = 0

            agent['velocity'] = (inertia * agent['velocity'] +
                                cognitive_component +
                                social_component)

            agent['position'] = agent['position'] + agent['velocity']

            # Boundary handling
            agent['position'] = np.clip(agent['position'], 0, 1)

# Initialize swarm
controller = SwarmController(
    swarm_size=config.get('swarm_size', 30),
    dimensions=config.get('search_dimensions', 10)
)

# Run swarm optimization
iterations = config.get('iterations', 100)
for i in range(iterations):
    controller.update_swarm(evaluate_solution)

    if i % 10 == 0:
        print(f"Iteration {i}: Best score = {controller.global_best_score:.4f}")

result = {
    'best_solution': controller.global_best.tolist(),
    'best_score': controller.global_best_score,
    'convergence_history': controller.convergence_history,
    'exploration_diversity': calculate_diversity(controller.agents)
}

def evaluate_solution(position):
    # Problem-specific fitness function
    return sum(position) - sum(position**2) + np.prod(position)

def calculate_diversity(agents):
    positions = [agent['position'] for agent in agents]
    return np.std(positions)
""",
    imports=["random", "numpy as np"],
    config={"swarm_size": 50, "iterations": 200, "search_dimensions": 15}
)

# Parallel agent executors
for i in range(5):  # 5 parallel swarm executors
workflow = WorkflowBuilder()
workflow.add_node(f"swarm_executor_{i}", "PythonCodeNode",
        code="""
# Execute subset of swarm agents
agent_subset = agents[start_idx:end_idx]
results = []

for agent in agent_subset:
    # Simulate agent exploring solution space
    exploration_result = explore_solution_space(
        agent['position'],
        agent['exploration_factor']
    )
    results.append({
        'agent_id': agent['id'],
        'findings': exploration_result,
        'quality_score': evaluate_findings(exploration_result)
    })

result = results
"""
    )

```

## 5. Consensus Building Pattern

**Purpose**: Democratic decision-making among agent collective

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "consensus_builder", {}),
    code="""
from collections import Counter
import numpy as np

class ConsensusBuilder:
    def __init__(self, voting_threshold=0.7):
        self.voting_threshold = voting_threshold
        self.voting_history = []

    def collect_proposals(self, agents, topic):
        proposals = []
        for agent in agents:
            proposal = {
                'agent_id': agent['id'],
                'solution': agent['proposed_solution'],
                'confidence': agent['confidence'],
                'rationale': agent['rationale']
            }
            proposals.append(proposal)
        return proposals

    def weighted_voting(self, proposals):
        # Weight votes by agent confidence and track record
        votes = {}
        total_weight = 0

        for proposal in proposals:
            solution_key = str(proposal['solution'])
            weight = proposal['confidence'] * self.get_agent_reputation(proposal['agent_id'])

            if solution_key not in votes:
                votes[solution_key] = {
                    'weight': 0,
                    'supporters': [],
                    'solution': proposal['solution']
                }

            votes[solution_key]['weight'] += weight
            votes[solution_key]['supporters'].append(proposal['agent_id'])
            total_weight += weight

        # Normalize weights
        for solution in votes.values():
            solution['support_ratio'] = solution['weight'] / total_weight

        return votes

    def build_consensus(self, proposals):
        votes = self.weighted_voting(proposals)

        # Check for clear majority
        sorted_solutions = sorted(
            votes.items(),
            key=lambda x: x[1]['support_ratio'],
            reverse=True
        )

        if sorted_solutions[0][1]['support_ratio'] >= self.voting_threshold:
            # Clear consensus
            return {
                'consensus_reached': True,
                'solution': sorted_solutions[0][1]['solution'],
                'support_ratio': sorted_solutions[0][1]['support_ratio'],
                'supporters': sorted_solutions[0][1]['supporters']
            }
        else:
            # No clear consensus - need negotiation
            return {
                'consensus_reached': False,
                'top_proposals': [
                    {
                        'solution': sol[1]['solution'],
                        'support': sol[1]['support_ratio'],
                        'supporters': sol[1]['supporters']
                    }
                    for sol in sorted_solutions[:3]
                ],
                'negotiation_required': True
            }

    def negotiate_consensus(self, proposals, max_rounds=3):
        for round in range(max_rounds):
            # Agents adjust proposals based on feedback
            adjusted_proposals = []

            for proposal in proposals:
                # Find common ground with top proposals
                adjusted = self.adjust_proposal(
                    proposal,
                    proposals,
                    round
                )
                adjusted_proposals.append(adjusted)

            # Try consensus again
            result = self.build_consensus(adjusted_proposals)
            if result['consensus_reached']:
                result['negotiation_rounds'] = round + 1
                return result

        # Failed to reach consensus - use fallback
        return {
            'consensus_reached': False,
            'fallback': 'majority_vote',
            'final_solution': self.majority_vote(proposals)
        }

# Build consensus among agents
consensus_builder = ConsensusBuilder(
    voting_threshold=config.get('consensus_threshold', 0.7)
)

# Collect proposals from all agents
proposals = agent_outputs.get('proposals', [])

# Attempt consensus
consensus_result = consensus_builder.build_consensus(proposals)

if not consensus_result['consensus_reached']:
    # Negotiate if needed
    consensus_result = consensus_builder.negotiate_consensus(
        proposals,
        max_rounds=config.get('max_negotiation_rounds', 3)
    )

result = consensus_result
""",
    config={"consensus_threshold": 0.7, "max_negotiation_rounds": 5}
)

```

## 6. Adaptive Agent Learning Pattern

**Purpose**: Agents that learn and improve from experience

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "adaptive_agent", {}),
    code="""
class AdaptiveAgent:
    def __init__(self, agent_id, initial_strategy="balanced"):
        self.agent_id = agent_id
        self.strategy = initial_strategy
        self.performance_history = []
        self.learning_rate = 0.1
        self.exploration_rate = 0.2

        # Strategy parameters
        self.strategy_params = {
            'risk_tolerance': 0.5,
            'innovation_factor': 0.5,
            'collaboration_weight': 0.5
        }

    def execute_task(self, task, environment):
        # Choose action based on current strategy
        if random.random() < self.exploration_rate:
            # Explore new approach
            action = self.explore_new_strategy(task)
        else:
            # Exploit learned strategy
            action = self.apply_strategy(task, self.strategy_params)

        # Execute and get feedback
        result = environment.execute_action(action)
        performance = self.evaluate_performance(result)

        # Learn from outcome
        self.update_strategy(action, performance)

        return {
            'action': action,
            'result': result,
            'performance': performance,
            'strategy_updated': True
        }

    def update_strategy(self, action, performance):
        # Record performance
        self.performance_history.append({
            'action': action,
            'performance': performance,
            'strategy_params': self.strategy_params.copy()
        })

        # Update strategy parameters using gradient-like approach
        if len(self.performance_history) > 1:
            prev_performance = self.performance_history[-2]['performance']
            performance_delta = performance - prev_performance

            # Adjust parameters based on performance change
            for param, value in self.strategy_params.items():
                if param in action['influenced_by']:
                    # Reinforce successful parameters
                    adjustment = self.learning_rate * performance_delta
                    self.strategy_params[param] = np.clip(
                        value + adjustment,
                        0,
                        1
                    )

        # Decay exploration over time
        self.exploration_rate *= 0.995
        self.exploration_rate = max(0.05, self.exploration_rate)

    def share_knowledge(self, other_agents):
        # Share successful strategies with other agents
        if self.get_average_performance() > 0.7:
            knowledge = {
                'agent_id': self.agent_id,
                'successful_params': self.strategy_params,
                'performance': self.get_average_performance(),
                'experience_count': len(self.performance_history)
            }
            return knowledge
        return None

    def learn_from_others(self, shared_knowledge):
        # Incorporate successful strategies from other agents
        for knowledge in shared_knowledge:
            if knowledge['performance'] > self.get_average_performance():
                # Blend strategies
                blend_factor = 0.3
                for param, value in knowledge['successful_params'].items():
                    self.strategy_params[param] = (
                        (1 - blend_factor) * self.strategy_params[param] +
                        blend_factor * value
                    )

# Create adaptive agent
agent = AdaptiveAgent(
    agent_id=config.get('agent_id', 'adaptive_001'),
    initial_strategy=config.get('initial_strategy', 'balanced')
)

# Execute multiple tasks with learning
results = []
for task in tasks:
    result = agent.execute_task(task, environment)
    results.append(result)

    # Periodic knowledge sharing
    if len(results) % 10 == 0:
        knowledge = agent.share_knowledge(other_agents)
        if knowledge:
            broadcast_knowledge(knowledge)

        # Learn from others
        shared_knowledge = collect_shared_knowledge()
        agent.learn_from_others(shared_knowledge)

result = {
    'agent_id': agent.agent_id,
    'final_strategy': agent.strategy_params,
    'performance_trend': agent.performance_history,
    'learning_complete': True
}
""")

```

## Best Practices

1. **Agent Design**:
   - Give agents clear roles and capabilities
   - Implement proper communication protocols
   - Balance autonomy with coordination
   - Include learning mechanisms

2. **Coordination**:
   - Use appropriate coordination patterns (hierarchical, swarm, consensus)
   - Implement conflict resolution mechanisms
   - Monitor agent interactions
   - Prevent deadlocks and infinite loops

3. **Performance**:
   - Cache shared computations
   - Limit agent pool sizes appropriately
   - Use async operations for parallel execution
   - Implement resource quotas

4. **Reliability**:
   - Handle agent failures gracefully
   - Implement timeout mechanisms
   - Log agent decisions for debugging
   - Include fallback strategies

## See Also
- [Control Flow Patterns](02-control-flow-patterns.md) - Agent routing logic
- [Data Processing Patterns](03-data-processing-patterns.md) - Agent data handling
- [Performance Patterns](06-performance-patterns.md) - Optimizing agent systems
