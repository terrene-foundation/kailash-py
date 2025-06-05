# ADR-0030: Self-Organizing Agent Pool Architecture

## Status

Accepted

Date: 2025-06-04

Updated: 2025-06-04 - Added real-world validation results

## Context

Building on the A2A communication infrastructure (ADR-0023), we need a system where agents can autonomously organize themselves to solve complex problems without centralized orchestration. Current client projects require dynamic agent collaboration where:

1. The optimal team composition is not known beforehand
2. Problem requirements emerge during execution
3. Agents need to self-select based on capabilities
4. Solutions require iterative refinement through collaboration
5. No single agent has complete knowledge or capabilities

Key drivers:
- **Dynamic Problem Solving**: Problems vary in complexity and required expertise
- **Scalability**: Hundreds of specialized agents need efficient organization
- **Adaptability**: Team composition should adjust as understanding evolves
- **Efficiency**: Minimize coordination overhead while maximizing collaboration
- **Quality**: Self-evaluation ensures solution quality without external validation

## Implementation Status

**Status**: ✅ Fully Implemented and Validated
**Validation**: Real-world testing with Ollama models (llama3.2, mistral, phi)
**Examples**: 11 comprehensive A2A examples demonstrating all capabilities
**Code Location**: `src/kailash/nodes/ai/self_organizing.py`

## Decision

Implement a Self-Organizing Agent Pool (SOAP) system with the following architecture:

### Core Components

1. **Agent Pool Manager**: Maintains registry of available agents with capabilities
2. **Problem Analyzer**: Decomposes problems into capability requirements
3. **Team Formation Engine**: Matches agents to problem requirements
4. **Collaboration Orchestrator**: Manages dynamic agent interactions
5. **Solution Evaluator**: Assesses solution quality and triggers iterations
6. **Consensus Builder**: Facilitates agreement on final solutions

### Self-Organization Mechanisms

1. **Capability-Based Clustering**: Agents group by complementary skills
2. **Reputation System**: Track agent performance for better team formation
3. **Dynamic Role Assignment**: Agents assume roles based on context
4. **Emergent Leadership**: Agents with domain expertise lead relevant phases
5. **Adaptive Team Size**: Teams grow/shrink based on problem complexity

### Communication Protocols

1. **Problem Broadcast**: Announce problems to agent pool
2. **Capability Advertisement**: Agents declare their skills/availability
3. **Team Formation Protocol**: Negotiate team membership
4. **Work Distribution**: Divide tasks based on capabilities
5. **Progress Synchronization**: Share intermediate results
6. **Solution Integration**: Combine partial solutions

## Architecture Design

### 1. Agent Pool Manager

```python
class AgentPoolManager:
    """Manages the pool of available agents."""

    def __init__(self):
        self.agent_registry = {}  # agent_id -> capabilities
        self.availability_tracker = {}  # agent_id -> status
        self.performance_metrics = {}  # agent_id -> metrics
        self.capability_index = defaultdict(set)  # capability -> agent_ids

    def register_agent(self, agent_id: str, capabilities: List[str],
                      metadata: Dict[str, Any]):
        """Register an agent with its capabilities."""

    def find_agents_by_capability(self, required_capabilities: List[str],
                                 min_performance: float = 0.7) -> List[str]:
        """Find agents matching required capabilities."""

    def update_agent_performance(self, agent_id: str, task_result: Dict):
        """Update agent performance metrics."""
```

### 2. Problem Analyzer

```python
class ProblemAnalyzer:
    """Analyzes problems to determine required capabilities."""

    def analyze_problem(self, problem_description: str) -> Dict[str, Any]:
        """Extract required capabilities, complexity, and constraints."""
        return {
            "required_capabilities": ["data_analysis", "visualization"],
            "complexity_score": 0.8,
            "estimated_agents": 3,
            "time_constraint": 300,  # seconds
            "quality_threshold": 0.9,
            "decomposition": [
                {"subtask": "data_preparation", "capabilities": ["data_cleaning"]},
                {"subtask": "analysis", "capabilities": ["statistics", "ml"]},
                {"subtask": "reporting", "capabilities": ["visualization"]}
            ]
        }
```

### 3. Team Formation Engine

```python
class TeamFormationEngine:
    """Forms optimal teams based on problem requirements."""

    def form_team(self, problem_analysis: Dict, available_agents: List[Dict]) -> Dict:
        """Form a team using various strategies."""

    def evaluate_team_fitness(self, team: List[str], requirements: Dict) -> float:
        """Evaluate how well a team matches requirements."""

    def optimize_team_composition(self, initial_team: List[str],
                                feedback: Dict) -> List[str]:
        """Optimize team based on performance feedback."""
```

### 4. Self-Organization Algorithms

#### 4.1 Swarm-Based Organization
```python
def swarm_organize(agents: List[Agent], problem: Dict) -> List[Team]:
    """Agents self-organize like a swarm."""
    # 1. Broadcast problem to all agents
    # 2. Agents calculate their fitness for the problem
    # 3. Agents with high fitness attract others
    # 4. Clusters form around high-fitness agents
    # 5. Clusters become teams
```

#### 4.2 Market-Based Organization
```python
def market_organize(agents: List[Agent], problem: Dict) -> Team:
    """Agents bid for participation in teams."""
    # 1. Problem owner announces task with reward
    # 2. Agents submit bids based on capability match
    # 3. Auction determines team membership
    # 4. Contracts established for deliverables
```

#### 4.3 Hierarchical Organization
```python
def hierarchical_organize(agents: List[Agent], problem: Dict) -> Team:
    """Agents organize in dynamic hierarchy."""
    # 1. Identify agents with leadership capabilities
    # 2. Leaders recruit team members
    # 3. Sub-teams form for specialized tasks
    # 4. Hierarchy adapts based on performance
```

### 5. Collaboration Patterns

#### 5.1 Parallel Exploration
Multiple agents explore different solution approaches simultaneously:
```python
class ParallelExplorationPattern:
    """Multiple agents explore solutions in parallel."""

    def execute(self, agents: List[Agent], problem: Dict) -> List[Solution]:
        # Each agent explores independently
        # Periodic synchronization to share insights
        # Best solutions promoted for refinement
```

#### 5.2 Sequential Refinement
Agents iteratively improve solutions:
```python
class SequentialRefinementPattern:
    """Agents sequentially refine solutions."""

    def execute(self, agents: List[Agent], initial_solution: Solution) -> Solution:
        # Each agent improves the solution
        # Specialized agents handle specific aspects
        # Quality gates between refinements
```

#### 5.3 Consensus Building
Agents collaborate to reach agreement:
```python
class ConsensusBuildingPattern:
    """Agents build consensus on solutions."""

    def execute(self, agents: List[Agent], proposals: List[Solution]) -> Solution:
        # Agents evaluate all proposals
        # Voting or negotiation determines winner
        # Minority opinions documented
```

## Implementation Example

### Self-Organizing Research System

```python
from kailash import Workflow
from kailash.nodes.ai import (
    AgentPoolManagerNode,
    ProblemAnalyzerNode,
    TeamFormationNode,
    SelfOrganizingAgentNode
)

class SelfOrganizingResearchSystem:
    """Research system with self-organizing agents."""

    def __init__(self, agent_pool_size: int = 20):
        self.workflow = Workflow(
            workflow_id="self_organizing_research",
            name="Self-Organizing Research System"
        )

        # Core infrastructure
        self.workflow.add_node(
            "agent_pool_manager",
            AgentPoolManagerNode(),
            config={
                "pool_size": agent_pool_size,
                "capability_distribution": {
                    "research": 0.3,
                    "analysis": 0.3,
                    "synthesis": 0.2,
                    "validation": 0.2
                }
            }
        )

        self.workflow.add_node(
            "problem_analyzer",
            ProblemAnalyzerNode(),
            config={
                "analysis_depth": "comprehensive",
                "decomposition_strategy": "hierarchical"
            }
        )

        self.workflow.add_node(
            "team_formation_engine",
            TeamFormationNode(),
            config={
                "formation_strategy": "capability_matching",
                "optimization_rounds": 3,
                "team_size_limits": {"min": 2, "max": 10}
            }
        )

        # Create agent pool
        self._create_agent_pool(agent_pool_size)

    def _create_agent_pool(self, size: int):
        """Create pool of self-organizing agents."""
        capabilities_pool = [
            ["data_collection", "web_research"],
            ["statistical_analysis", "hypothesis_testing"],
            ["machine_learning", "pattern_recognition"],
            ["domain_expertise", "validation"],
            ["writing", "synthesis"],
            ["visualization", "reporting"]
        ]

        for i in range(size):
            agent_id = f"research_agent_{i:03d}"
            capabilities = capabilities_pool[i % len(capabilities_pool)]

            self.workflow.add_node(
                agent_id,
                SelfOrganizingAgentNode(),
                config={
                    "agent_id": agent_id,
                    "capabilities": capabilities,
                    "collaboration_preference": "cooperative",
                    "availability": "on_demand",
                    "performance_history": {
                        "success_rate": 0.85 + (i % 3) * 0.05,
                        "avg_contribution_score": 0.8
                    }
                }
            )

    def solve_problem(self, problem_description: str) -> Dict:
        """Solve a problem using self-organizing agents."""
        runtime = LocalRuntime()

        # Step 1: Analyze the problem
        analysis_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "problem_analyzer": {
                    "problem_description": problem_description,
                    "context": {"domain": "research", "urgency": "normal"}
                }
            }
        )

        problem_analysis = analysis_result["problem_analyzer"]["analysis"]

        # Step 2: Form initial team
        formation_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "team_formation_engine": {
                    "problem_analysis": problem_analysis,
                    "available_agents": self._get_available_agents()
                }
            }
        )

        team = formation_result["team_formation_engine"]["team"]

        # Step 3: Execute collaborative solution
        solution = self._execute_team_collaboration(
            team, problem_analysis, runtime
        )

        # Step 4: Evaluate and iterate if needed
        evaluation = self._evaluate_solution(solution, problem_analysis)

        iteration_count = 0
        while evaluation["quality_score"] < problem_analysis["quality_threshold"] and iteration_count < 3:
            # Reform team or adjust strategy
            team = self._adapt_team(team, evaluation["feedback"])
            solution = self._execute_team_collaboration(
                team, problem_analysis, runtime
            )
            evaluation = self._evaluate_solution(solution, problem_analysis)
            iteration_count += 1

        return {
            "problem": problem_description,
            "solution": solution,
            "team": team,
            "iterations": iteration_count,
            "quality_score": evaluation["quality_score"]
        }
```

### Advanced Self-Organization Patterns

#### 1. Emergent Specialization
```python
class EmergentSpecializationNode(Node):
    """Agents develop specializations based on success patterns."""

    def run(self, **kwargs):
        agent_history = kwargs["agent_history"]
        task_outcomes = kwargs["task_outcomes"]

        # Analyze which tasks the agent excels at
        specialization_scores = self._analyze_performance_patterns(
            agent_history, task_outcomes
        )

        # Update agent capabilities based on emergent specialization
        new_capabilities = self._derive_specialization(specialization_scores)

        return {
            "emerged_specializations": new_capabilities,
            "confidence_scores": specialization_scores
        }
```

#### 2. Dynamic Coalition Formation
```python
class DynamicCoalitionNode(Node):
    """Forms temporary coalitions for specific objectives."""

    def run(self, **kwargs):
        objective = kwargs["objective"]
        agent_pool = kwargs["agent_pool"]
        time_limit = kwargs.get("time_limit", 300)

        # Agents form coalitions based on shared interests
        coalitions = self._form_coalitions(objective, agent_pool)

        # Coalitions compete/collaborate
        results = self._execute_coalition_dynamics(coalitions, time_limit)

        return {
            "winning_coalition": results["winner"],
            "coalition_solutions": results["solutions"]
        }
```

#### 3. Adaptive Team Topology
```python
class AdaptiveTopologyNode(Node):
    """Team structure adapts based on problem characteristics."""

    def run(self, **kwargs):
        problem_type = kwargs["problem_type"]
        team_members = kwargs["team_members"]

        if problem_type == "exploratory":
            topology = self._create_mesh_topology(team_members)
        elif problem_type == "hierarchical":
            topology = self._create_tree_topology(team_members)
        elif problem_type == "specialized":
            topology = self._create_star_topology(team_members)
        else:
            topology = self._create_hybrid_topology(team_members)

        return {
            "topology": topology,
            "communication_channels": self._derive_channels(topology)
        }
```

## Evaluation Criteria

### Solution Quality Metrics
1. **Completeness**: All aspects of the problem addressed
2. **Correctness**: Solution accuracy and validity
3. **Innovation**: Novel approaches or insights
4. **Efficiency**: Resource usage and time to solution
5. **Robustness**: Solution handles edge cases

### Team Performance Metrics
1. **Formation Time**: Speed of team assembly
2. **Collaboration Efficiency**: Communication overhead
3. **Adaptation Rate**: How quickly team improves
4. **Specialization Emergence**: Development of expertise
5. **Consensus Quality**: Agreement level and speed

## Consequences

### Positive
- **Scalability**: Handles large agent pools efficiently
- **Adaptability**: Teams adjust to problem evolution
- **Robustness**: No single point of failure
- **Innovation**: Diverse perspectives lead to novel solutions
- **Efficiency**: Optimal resource allocation

### Negative
- **Complexity**: Debugging distributed behaviors is challenging
- **Unpredictability**: Emergent behaviors may surprise
- **Overhead**: Coordination has computational cost
- **Quality Variance**: Solution quality may vary
- **Learning Curve**: Requires understanding of self-organization

### Neutral
- **Monitoring Requirements**: Need sophisticated observability
- **Configuration Complexity**: Many parameters to tune
- **Documentation Needs**: Emergent behaviors need documentation

## Real-World Validation

The self-organizing agent pool architecture has been validated with real LLM providers:

### Testing Results (2025-06-04)

1. **Ollama Integration**: All examples tested successfully with local Ollama models
   - Models tested: llama3.2 (2GB), mistral (4.1GB), phi (1.6GB)
   - Auto-detection feature correctly identified 9 available models
   - Response times: 30-50 seconds for typical multi-agent workflows

2. **Key Validations**:
   - ✅ Agents successfully share information through SharedMemoryPoolNode
   - ✅ Selective attention filters relevant memories effectively
   - ✅ Consensus building reaches agreement among agents
   - ✅ Code review system provides actionable insights
   - ✅ Team formation adapts to available agent capabilities

3. **Production Considerations**:
   - Memory pool scales well with ~1000 memories tested
   - Attention mechanisms prevent information overload
   - Caching significantly reduces redundant LLM calls
   - Convergence detection prevents infinite loops

## Related ADRs

- [ADR-0023: A2A Communication Architecture](0023-a2a-communication-architecture.md) - Foundation for agent communication
- [ADR-0024: LLM Agent Architecture](0024-llm-agent-architecture.md) - Individual agent capabilities
- [ADR-0026: Unified AI Provider Architecture](0026-unified-ai-provider-architecture.md) - AI capabilities for agents
- [ADR-0029: MCP Ecosystem Architecture](0029-mcp-ecosystem-architecture.md) - Integration with broader ecosystem

## References

- [Swarm Intelligence Principles](https://www.sciencedirect.com/topics/computer-science/swarm-intelligence)
- [Multi-Agent Systems: Algorithmic, Game-Theoretic, and Logical Foundations](https://www.cambridge.org/core/books/multiagent-systems/4D0FA93B0B88B9F0B1E7E1CE3EEBBE8A)
- [Self-Organization in Multi-Agent Systems](https://www.researchgate.net/publication/220659913_Self-Organisation_in_Multi-Agent_Systems)
- [Market-Based Control of Complex Computational Systems](https://www.cs.cmu.edu/~softagents/papers/market-based-control.pdf)
