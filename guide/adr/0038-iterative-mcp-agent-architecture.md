# ADR-0038: Iterative MCP Agent Architecture

## Status
Proposed

## Context

Current LLMAgentNode implementation provides single-turn interaction with pre-configured MCP context. However, real-world AI applications require agents that can:

1. **Progressive Discovery**: Discover MCP tools/resources/prompts without pre-configuration
2. **Iterative Execution**: Plan, execute, reflect, and adapt across multiple cycles
3. **Semantic Understanding**: Dynamically understand tool capabilities through descriptions
4. **Convergence Intelligence**: Know when to stop iterating and synthesize results

### Current Limitations

The existing LLMAgentNode architecture has these constraints:

```python
# Current: Pre-configured context (agent can't discover)
mcp_context=["ai-registry://stats/overview", "ai-registry://use-cases/healthcare"]

# Current: Single-turn execution (no iteration)
result = agent.run(messages=[...])  # One call, one response
```

### Problem Statement

Users envision agents that can:
- Start with zero MCP knowledge and progressively discover available tools/resources
- Iterate through discovery → planning → execution → reflection cycles
- Converge when satisfied or reach iteration limits
- Understand tool capabilities through semantic descriptions rather than hard-coded configs

## Decision

Implement **IterativeLLMAgentNode** with a 6-phase iterative architecture:

### Core Architecture

```python
class IterativeLLMAgentNode(LLMAgentNode):
    """Iterative LLM Agent with progressive MCP discovery and execution."""

    def get_parameters(self) -> Dict[str, NodeParameter]:
        return {
            # Iteration Control
            "max_iterations": NodeParameter(
                name="max_iterations", type=int, default=5,
                description="Maximum number of discovery-execution cycles"
            ),
            "convergence_criteria": NodeParameter(
                name="convergence_criteria", type=dict, default={},
                description="Criteria for determining when to stop iterating"
            ),

            # Discovery Configuration
            "discovery_mode": NodeParameter(
                name="discovery_mode", type=str, default="progressive",
                description="Discovery strategy: progressive, exhaustive, semantic"
            ),
            "discovery_budget": NodeParameter(
                name="discovery_budget", type=dict, default={"max_servers": 5, "max_tools": 20},
                description="Limits for discovery process"
            ),

            # Iterative Configuration
            "reflection_enabled": NodeParameter(
                name="reflection_enabled", type=bool, default=True,
                description="Enable reflection phase between iterations"
            ),
            "adaptation_strategy": NodeParameter(
                name="adaptation_strategy", type=str, default="dynamic",
                description="How to adapt strategy: static, dynamic, ml_guided"
            ),

            # Base LLMAgent parameters inherited...
        }
```

### 6-Phase Iterative Process

#### Phase 1: Discovery
- **Purpose**: Progressively discover MCP servers, tools, and resources
- **Input**: Initial query, available MCP servers
- **Process**:
  - Connect to MCP registry endpoints
  - List available tools with semantic descriptions
  - Categorize tools by capability and domain
  - Build dynamic understanding of available capabilities
- **Output**: Discovery map with tool descriptions and capabilities

#### Phase 2: Planning
- **Purpose**: Create execution strategy based on discoveries
- **Input**: Discovery map, user query, previous iteration context
- **Process**:
  - Analyze user intent and requirements
  - Map requirements to discovered capabilities
  - Create step-by-step execution plan
  - Estimate resource requirements and success probability
- **Output**: Structured execution plan with tool selection

#### Phase 3: Execution
- **Purpose**: Execute planned actions using discovered tools
- **Input**: Execution plan, tool configurations
- **Process**:
  - Execute tools in planned sequence
  - Handle tool errors and retries
  - Collect intermediate results
  - Monitor execution progress and resource usage
- **Output**: Execution results with success/failure status

#### Phase 4: Reflection
- **Purpose**: Analyze results and determine next steps
- **Input**: Execution results, original query, iteration history
- **Process**:
  - Evaluate result quality and completeness
  - Identify gaps or areas for improvement
  - Determine if goal is achieved or more iteration needed
  - Plan adaptations for next iteration if needed
- **Output**: Reflection analysis with continuation decision

#### Phase 5: Convergence
- **Purpose**: Decide whether to continue iterating or finalize
- **Input**: Reflection analysis, convergence criteria, iteration count
- **Process**:
  - Check convergence criteria (goal achieved, max iterations, diminishing returns)
  - Make continue/stop decision
  - If continuing, adapt strategy for next iteration
  - If stopping, prepare for synthesis
- **Output**: Continue/stop decision with reasoning

#### Phase 6: Synthesis
- **Purpose**: Combine all iteration results into final response
- **Input**: All iteration results, reflection analyses, user query
- **Process**:
  - Aggregate results from all iterations
  - Synthesize comprehensive response
  - Include confidence scores and evidence
  - Provide transparency about process and sources
- **Output**: Final synthesized response with full traceability

### Dynamic Tool Understanding

```python
class MCPToolSemanticAnalyzer:
    """Analyzes MCP tool descriptions to understand capabilities."""

    def analyze_tool_capability(self, tool_description: str) -> Dict[str, Any]:
        """Extract semantic understanding from tool description."""
        return {
            "primary_function": "...",  # What the tool does
            "input_requirements": [...],  # What it needs
            "output_format": "...",      # What it produces
            "domain": "...",             # Application area
            "complexity": "...",         # Simple/medium/complex
            "dependencies": [...],       # Other tools it might need
            "confidence": 0.95           # Confidence in analysis
        }
```

### Convergence Criteria

```python
DEFAULT_CONVERGENCE_CRITERIA = {
    "goal_satisfaction": {
        "threshold": 0.85,           # Confidence that goal is met
        "metric": "semantic_similarity"
    },
    "diminishing_returns": {
        "enabled": True,
        "min_improvement": 0.05,     # Minimum improvement per iteration
        "lookback_window": 2         # Compare last N iterations
    },
    "resource_limits": {
        "max_tool_calls": 50,
        "max_execution_time": 300,   # seconds
        "max_cost": 0.50            # USD
    },
    "quality_gates": {
        "min_confidence": 0.7,
        "require_evidence": True,
        "validate_consistency": True
    }
}
```

## Implementation Strategy

### Phase 1: Base Architecture (Week 1)
- Create IterativeLLMAgentNode class extending LLMAgentNode
- Implement 6-phase workflow orchestration
- Add basic discovery and planning capabilities
- Create convergence detection framework

### Phase 2: Discovery Engine (Week 1-2)
- Implement progressive MCP discovery
- Add semantic tool analysis
- Create tool capability mapping
- Add discovery budget management

### Phase 3: Iteration Management (Week 2)
- Implement reflection and adaptation logic
- Add iteration state management
- Create strategy adaptation mechanisms
- Add performance monitoring

### Phase 4: Convergence Intelligence (Week 2-3)
- Implement sophisticated convergence criteria
- Add goal satisfaction measurement
- Create diminishing returns detection
- Add quality gate validation

### Phase 5: Integration and Examples (Week 3)
- Create comprehensive usage examples
- Add performance benchmarks
- Create debugging and monitoring tools
- Write comprehensive documentation

## Consequences

### Positive
- **True Autonomy**: Agents can discover and use new capabilities without pre-configuration
- **Adaptive Intelligence**: Agents improve their approach based on results
- **Resource Efficiency**: Convergence criteria prevent unnecessary iterations
- **Transparency**: Full traceability of discovery and decision process
- **Scalability**: Works with any number of MCP servers and tools

### Negative
- **Complexity**: Significantly more complex than single-turn agents
- **Performance**: Multiple iterations may increase latency
- **Cost**: More LLM calls for reflection and planning
- **Debugging**: Harder to debug multi-iteration behavior

### Mitigation Strategies
- Provide simple usage patterns for common cases
- Add performance monitoring and optimization
- Implement cost controls and budgets
- Create comprehensive debugging and logging tools

## Alternatives Considered

### 1. Enhanced Single-Turn Agent
- **Approach**: Improve current LLMAgentNode with better discovery
- **Rejected**: Doesn't address iterative needs

### 2. Workflow-Based Agent
- **Approach**: Use workflow orchestration for iterations
- **Rejected**: Too heavyweight for agent use cases

### 3. Chain-of-Thought Extension
- **Approach**: Extend current agent with CoT reasoning
- **Rejected**: Still single-turn, limited adaptation

## References

- [MCP Protocol Specification](https://github.com/modelcontextprotocol/specification)
- [LLM Agent Patterns](https://github.com/microsoft/autogen)
- [Iterative AI Systems](https://arxiv.org/abs/2303.17071)
- [Agent-Computer Interaction](https://github.com/OpenAdaptAI/OpenAdapt)

## Notes

This ADR establishes the foundation for truly autonomous AI agents that can progressively discover, learn, and adapt their capabilities through iterative interaction with MCP ecosystems.

The implementation will maintain backward compatibility with existing LLMAgentNode usage while providing opt-in iterative capabilities for advanced use cases.
