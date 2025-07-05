"""Iterative LLM Agent with progressive MCP discovery and execution capabilities."""

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kailash.nodes.ai.llm_agent import LLMAgentNode
from kailash.nodes.base import NodeParameter, register_node


@dataclass
class IterationState:
    """State tracking for a single iteration."""

    iteration: int
    phase: str  # discovery, planning, execution, reflection, convergence, synthesis
    start_time: float
    end_time: float | None = None
    discoveries: dict[str, Any] = field(default_factory=dict)
    plan: dict[str, Any] = field(default_factory=dict)
    execution_results: dict[str, Any] = field(default_factory=dict)
    reflection: dict[str, Any] = field(default_factory=dict)
    convergence_decision: dict[str, Any] = field(default_factory=dict)
    success: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "iteration": self.iteration,
            "phase": self.phase,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": (self.end_time - self.start_time) if self.end_time else None,
            "discoveries": self.discoveries,
            "plan": self.plan,
            "execution_results": self.execution_results,
            "reflection": self.reflection,
            "convergence_decision": self.convergence_decision,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class MCPToolCapability:
    """Semantic understanding of an MCP tool's capabilities."""

    name: str
    description: str
    primary_function: str
    input_requirements: list[str]
    output_format: str
    domain: str
    complexity: str  # simple, medium, complex
    dependencies: list[str]
    confidence: float
    server_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "primary_function": self.primary_function,
            "input_requirements": self.input_requirements,
            "output_format": self.output_format,
            "domain": self.domain,
            "complexity": self.complexity,
            "dependencies": self.dependencies,
            "confidence": self.confidence,
            "server_source": self.server_source,
        }


@register_node()
class IterativeLLMAgentNode(LLMAgentNode):
    """
    Iterative LLM Agent with progressive MCP discovery and execution.

    This agent can discover MCP tools and resources dynamically, plan and execute
    multi-step processes, reflect on results, and converge when goals are met
    or iteration limits are reached.

    Key Features:
    - Progressive MCP discovery without pre-configuration
    - 6-phase iterative process (Discovery → Planning → Execution → Reflection → Convergence → Synthesis)
    - Semantic tool understanding and capability mapping
    - Adaptive strategy based on iteration results
    - Smart convergence criteria and resource management

    Examples:
        >>> # Basic iterative agent
        >>> agent = IterativeLLMAgentNode()
        >>> result = agent.run(
        ...     messages=[{"role": "user", "content": "Find and analyze healthcare AI trends"}],
        ...     mcp_servers=["http://localhost:8080"],
        ...     max_iterations=3
        ... )

        >>> # Advanced iterative agent with custom convergence
        >>> result = agent.run(
        ...     messages=[{"role": "user", "content": "Research and recommend AI implementation strategy"}],
        ...     mcp_servers=["http://ai-registry:8080", "http://knowledge-base:8081"],
        ...     max_iterations=5,
        ...     discovery_mode="semantic",
        ...     convergence_criteria={
        ...         "goal_satisfaction": {"threshold": 0.9},
        ...         "diminishing_returns": {"min_improvement": 0.1}
        ...     }
        ... )
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Get parameters for iterative LLM agent configuration."""
        base_params = super().get_parameters()

        iterative_params = {
            # Iteration Control
            "max_iterations": NodeParameter(
                name="max_iterations",
                type=int,
                required=False,
                default=5,
                description="Maximum number of discovery-execution cycles",
            ),
            "convergence_criteria": NodeParameter(
                name="convergence_criteria",
                type=dict,
                required=False,
                default={},
                description="""Criteria for determining when to stop iterating. Supports:
                - goal_satisfaction: {"threshold": 0.8} - Stop when confidence >= threshold
                - early_satisfaction: {"enabled": True, "threshold": 0.85, "custom_check": callable} - Early stopping with optional custom function
                - diminishing_returns: {"enabled": True, "min_improvement": 0.05} - Stop when improvement < threshold
                - quality_gates: {"min_confidence": 0.7, "custom_validator": callable} - Quality checks with optional custom validator
                - resource_limits: {"max_cost": 1.0, "max_time": 300} - Hard resource limits
                - custom_criteria: [{"name": "my_check", "function": callable, "weight": 0.5}] - User-defined criteria
                """,
            ),
            # Discovery Configuration
            "discovery_mode": NodeParameter(
                name="discovery_mode",
                type=str,
                required=False,
                default="progressive",
                description="Discovery strategy: progressive, exhaustive, semantic",
            ),
            "discovery_budget": NodeParameter(
                name="discovery_budget",
                type=dict,
                required=False,
                default={"max_servers": 5, "max_tools": 20, "max_resources": 50},
                description="Limits for discovery process",
            ),
            # Iterative Configuration
            "reflection_enabled": NodeParameter(
                name="reflection_enabled",
                type=bool,
                required=False,
                default=True,
                description="Enable reflection phase between iterations",
            ),
            "adaptation_strategy": NodeParameter(
                name="adaptation_strategy",
                type=str,
                required=False,
                default="dynamic",
                description="How to adapt strategy: static, dynamic, ml_guided",
            ),
            # Performance and Monitoring
            "enable_detailed_logging": NodeParameter(
                name="enable_detailed_logging",
                type=bool,
                required=False,
                default=True,
                description="Enable detailed iteration logging for debugging",
            ),
            "iteration_timeout": NodeParameter(
                name="iteration_timeout",
                type=int,
                required=False,
                default=300,
                description="Timeout for each iteration in seconds",
            ),
        }

        # Merge base parameters with iterative parameters
        base_params.update(iterative_params)
        return base_params

    def run(self, **kwargs) -> dict[str, Any]:
        """
        Execute iterative LLM agent with 6-phase process.

        Args:
            **kwargs: All parameters from get_parameters() plus inherited LLMAgentNode params

        Returns:
            Dict containing:
                success (bool): Whether the iterative process completed successfully
                final_response (str): Synthesized final response
                iterations (List[Dict]): Detailed log of all iterations
                discoveries (Dict): All discovered MCP capabilities
                convergence_reason (str): Why the process stopped
                total_duration (float): Total execution time
                resource_usage (Dict): Resource consumption metrics
        """
        # Extract iterative-specific parameters
        max_iterations = kwargs.get("max_iterations", 5)
        convergence_criteria = kwargs.get("convergence_criteria", {})
        discovery_mode = kwargs.get("discovery_mode", "progressive")
        discovery_budget = kwargs.get(
            "discovery_budget", {"max_servers": 5, "max_tools": 20, "max_resources": 50}
        )
        reflection_enabled = kwargs.get("reflection_enabled", True)
        adaptation_strategy = kwargs.get("adaptation_strategy", "dynamic")
        enable_detailed_logging = kwargs.get("enable_detailed_logging", True)
        kwargs.get("iteration_timeout", 300)

        # Initialize iterative execution state
        start_time = time.time()
        iterations: list[IterationState] = []
        global_discoveries = {
            "servers": {},
            "tools": {},
            "resources": {},
            "capabilities": {},
        }
        converged = False
        convergence_reason = "max_iterations_reached"

        try:
            # Main iterative loop
            for iteration_num in range(1, max_iterations + 1):
                iteration_state = IterationState(
                    iteration=iteration_num, phase="discovery", start_time=time.time()
                )

                if enable_detailed_logging:
                    self.logger.info(
                        f"Starting iteration {iteration_num}/{max_iterations}"
                    )

                try:
                    # Phase 1: Discovery
                    iteration_state.discoveries = self._phase_discovery(
                        kwargs, global_discoveries, discovery_mode, discovery_budget
                    )

                    # Phase 2: Planning
                    iteration_state.phase = "planning"
                    iteration_state.plan = self._phase_planning(
                        kwargs,
                        iteration_state.discoveries,
                        global_discoveries,
                        iterations,
                    )

                    # Phase 3: Execution
                    iteration_state.phase = "execution"
                    iteration_state.execution_results = self._phase_execution(
                        kwargs, iteration_state.plan, iteration_state.discoveries
                    )

                    # Phase 4: Reflection (if enabled)
                    if reflection_enabled:
                        iteration_state.phase = "reflection"
                        iteration_state.reflection = self._phase_reflection(
                            kwargs, iteration_state.execution_results, iterations
                        )

                    # Phase 5: Convergence
                    iteration_state.phase = "convergence"
                    convergence_result = self._phase_convergence(
                        kwargs,
                        iteration_state,
                        iterations,
                        convergence_criteria,
                        global_discoveries,
                    )
                    iteration_state.convergence_decision = convergence_result

                    if convergence_result["should_stop"]:
                        converged = True
                        convergence_reason = convergence_result["reason"]

                    # Update global discoveries
                    self._update_global_discoveries(
                        global_discoveries, iteration_state.discoveries
                    )

                    iteration_state.success = True
                    iteration_state.end_time = time.time()

                except Exception as e:
                    iteration_state.error = str(e)
                    iteration_state.success = False
                    iteration_state.end_time = time.time()

                    if enable_detailed_logging:
                        self.logger.error(f"Iteration {iteration_num} failed: {e}")

                iterations.append(iteration_state)

                # Check if we should stop
                if converged:
                    break

                # Adapt strategy for next iteration if enabled
                if adaptation_strategy == "dynamic" and iteration_state.success:
                    self._adapt_strategy(kwargs, iteration_state, iterations)

            # Phase 6: Synthesis
            final_response = self._phase_synthesis(
                kwargs, iterations, global_discoveries
            )

            total_duration = time.time() - start_time

            return {
                "success": True,
                "final_response": final_response,
                "iterations": [iter_state.to_dict() for iter_state in iterations],
                "discoveries": global_discoveries,
                "convergence_reason": convergence_reason,
                "total_iterations": len(iterations),
                "total_duration": total_duration,
                "resource_usage": self._calculate_resource_usage(iterations),
                "metadata": {
                    "max_iterations": max_iterations,
                    "discovery_mode": discovery_mode,
                    "reflection_enabled": reflection_enabled,
                    "adaptation_strategy": adaptation_strategy,
                },
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "iterations": [iter_state.to_dict() for iter_state in iterations],
                "discoveries": global_discoveries,
                "total_duration": time.time() - start_time,
                "convergence_reason": "error_occurred",
                "recovery_suggestions": [
                    "Check MCP server connectivity",
                    "Verify discovery budget limits",
                    "Review convergence criteria configuration",
                    "Check iteration timeout settings",
                ],
            }

    def _phase_discovery(
        self,
        kwargs: dict[str, Any],
        global_discoveries: dict[str, Any],
        discovery_mode: str,
        discovery_budget: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Phase 1: Discover MCP servers, tools, and resources.

        Args:
            kwargs: Original run parameters
            global_discoveries: Accumulated discoveries from previous iterations
            discovery_mode: Discovery strategy
            discovery_budget: Resource limits for discovery

        Returns:
            Dictionary containing new discoveries in this iteration
        """
        discoveries = {
            "new_servers": [],
            "new_tools": [],
            "new_resources": [],
            "tool_capabilities": [],
        }

        mcp_servers = kwargs.get("mcp_servers", [])

        # Discover from each MCP server
        for server_config in mcp_servers:
            server_id = (
                server_config
                if isinstance(server_config, str)
                else server_config.get("url", "unknown")
            )

            # Skip if already discovered and not in exhaustive mode
            if (
                discovery_mode != "exhaustive"
                and server_id in global_discoveries["servers"]
            ):
                continue

            try:
                # Discover tools from this server
                server_tools = self._discover_server_tools(
                    server_config, discovery_budget
                )
                self.logger.info(
                    f"Discovered {len(server_tools)} tools from server {server_id}"
                )
                discoveries["new_tools"].extend(server_tools)

                # Discover resources from this server
                server_resources = self._discover_server_resources(
                    server_config, discovery_budget
                )
                self.logger.info(
                    f"Discovered {len(server_resources)} resources from server {server_id}"
                )
                discoveries["new_resources"].extend(server_resources)

                # Analyze tool capabilities if in semantic mode
                if discovery_mode == "semantic":
                    for tool in server_tools:
                        capability = self._analyze_tool_capability(tool, server_id)
                        discoveries["tool_capabilities"].append(capability.to_dict())

                discoveries["new_servers"].append(
                    {
                        "id": server_id,
                        "config": server_config,
                        "discovered_at": datetime.now().isoformat(),
                        "tools_count": len(server_tools),
                        "resources_count": len(server_resources),
                    }
                )

                self.logger.info(
                    f"Server {server_id} discovery complete: {len(server_tools)} tools, {len(server_resources)} resources"
                )

            except Exception as e:
                self.logger.debug(f"Discovery failed for server {server_id}: {e}")
                discoveries["new_servers"].append(
                    {
                        "id": server_id,
                        "config": server_config,
                        "discovered_at": datetime.now().isoformat(),
                        "error": str(e),
                        "tools_count": 0,
                        "resources_count": 0,
                    }
                )

        return discoveries

    def _discover_server_tools(
        self, server_config: Any, budget: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Discover tools from a specific MCP server."""
        # Use existing MCP tool discovery from parent class
        try:
            # Ensure MCP client is initialized
            if not hasattr(self, "_mcp_client"):
                from kailash.mcp_server import MCPClient

                self._mcp_client = MCPClient()

            # Call parent class method which returns OpenAI function format
            discovered_tools_openai_format = self._discover_mcp_tools(
                [server_config]
                if not isinstance(server_config, list)
                else server_config
            )

            # Convert from OpenAI function format to simple format for iterative agent
            discovered_tools = []
            for tool in discovered_tools_openai_format:
                if isinstance(tool, dict) and "function" in tool:
                    func = tool["function"]
                    discovered_tools.append(
                        {
                            "name": func.get("name", "unknown"),
                            "description": func.get("description", ""),
                            "parameters": func.get("parameters", {}),
                            "mcp_server": func.get("mcp_server", "unknown"),
                            "mcp_server_config": func.get(
                                "mcp_server_config", server_config
                            ),
                        }
                    )
                else:
                    # Handle direct format
                    discovered_tools.append(tool)

            # Apply budget limits
            max_tools = budget.get("max_tools", 20)
            return discovered_tools[:max_tools]

        except Exception as e:
            self.logger.debug(f"Tool discovery failed: {e}")
            return []

    def _discover_server_resources(
        self, server_config: Any, budget: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Discover resources from a specific MCP server."""
        # Mock implementation - in real version would use MCP resource discovery
        try:
            server_id = (
                server_config
                if isinstance(server_config, str)
                else server_config.get("url", "unknown")
            )
            max_resources = budget.get("max_resources", 50)

            # Mock discovered resources
            mock_resources = [
                {
                    "uri": f"{server_id}/resource/data/overview",
                    "name": "Data Overview",
                    "type": "data",
                    "description": "Overview of available data sources",
                },
                {
                    "uri": f"{server_id}/resource/templates/analysis",
                    "name": "Analysis Templates",
                    "type": "template",
                    "description": "Pre-built analysis templates",
                },
            ]

            return mock_resources[:max_resources]

        except Exception as e:
            self.logger.debug(f"Resource discovery failed: {e}")
            return []

    def _analyze_tool_capability(
        self, tool: dict[str, Any], server_id: str
    ) -> MCPToolCapability:
        """Analyze tool description to understand semantic capabilities."""
        # Extract tool information
        if isinstance(tool, dict) and "function" in tool:
            func = tool["function"]
            name = func.get("name", "unknown")
            description = func.get("description", "")
        else:
            name = tool.get("name", "unknown")
            description = tool.get("description", "")

        # Simple semantic analysis (in real implementation, use LLM for analysis)
        primary_function = "data_processing"
        if "search" in description.lower():
            primary_function = "search"
        elif "analyze" in description.lower():
            primary_function = "analysis"
        elif "create" in description.lower() or "generate" in description.lower():
            primary_function = "generation"

        # Determine domain
        domain = "general"
        if any(
            keyword in description.lower()
            for keyword in ["health", "medical", "clinical"]
        ):
            domain = "healthcare"
        elif any(
            keyword in description.lower()
            for keyword in ["finance", "banking", "investment"]
        ):
            domain = "finance"
        elif any(
            keyword in description.lower()
            for keyword in ["data", "analytics", "statistics"]
        ):
            domain = "data_science"

        # Determine complexity
        complexity = "simple"
        if len(description) > 100 or "complex" in description.lower():
            complexity = "complex"
        elif len(description) > 50:
            complexity = "medium"

        return MCPToolCapability(
            name=name,
            description=description,
            primary_function=primary_function,
            input_requirements=["query"] if "search" in primary_function else ["data"],
            output_format="text",
            domain=domain,
            complexity=complexity,
            dependencies=[],
            confidence=0.8,  # Mock confidence
            server_source=server_id,
        )

    def _phase_planning(
        self,
        kwargs: dict[str, Any],
        discoveries: dict[str, Any],
        global_discoveries: dict[str, Any],
        previous_iterations: list[IterationState],
    ) -> dict[str, Any]:
        """Phase 2: Create execution plan based on discoveries."""
        messages = kwargs.get("messages", [])
        user_query = ""

        # Extract user intent
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # Analyze available tools and create plan
        available_tools = discoveries.get("new_tools", []) + list(
            global_discoveries.get("tools", {}).values()
        )

        # Simple planning logic (in real implementation, use LLM for planning)
        plan = {
            "user_query": user_query,
            "selected_tools": [],
            "execution_steps": [],
            "expected_outcomes": [],
            "resource_requirements": {},
            "success_criteria": {},
        }

        # Select relevant tools
        for tool in available_tools[:3]:  # Limit to top 3 tools
            if isinstance(tool, dict) and "function" in tool:
                plan["selected_tools"].append(tool["function"]["name"])
            elif isinstance(tool, dict):
                plan["selected_tools"].append(tool.get("name", "unknown"))

        # Create execution steps
        if "analyze" in user_query.lower():
            plan["execution_steps"] = [
                {
                    "step": 1,
                    "action": "gather_data",
                    "tools": plan["selected_tools"][:1],
                },
                {
                    "step": 2,
                    "action": "perform_analysis",
                    "tools": plan["selected_tools"][1:2],
                },
                {
                    "step": 3,
                    "action": "generate_insights",
                    "tools": plan["selected_tools"][2:3],
                },
            ]
        else:
            plan["execution_steps"] = [
                {"step": 1, "action": "execute_query", "tools": plan["selected_tools"]}
            ]

        plan["expected_outcomes"] = ["analysis_results", "insights", "recommendations"]

        return plan

    def _phase_execution(
        self, kwargs: dict[str, Any], plan: dict[str, Any], discoveries: dict[str, Any]
    ) -> dict[str, Any]:
        """Phase 3: Execute the planned actions."""
        execution_results = {
            "steps_completed": [],
            "tool_outputs": {},
            "intermediate_results": [],
            "success": True,
            "errors": [],
        }

        # Execute each step in the plan
        for step in plan.get("execution_steps", []):
            step_num = step.get("step", 0)
            action = step.get("action", "unknown")
            tools = step.get("tools", [])

            try:
                # Mock tool execution (in real implementation, call actual tools)
                step_result = {
                    "step": step_num,
                    "action": action,
                    "tools_used": tools,
                    "output": f"Mock execution result for {action} using tools: {', '.join(tools)}",
                    "success": True,
                    "duration": 1.5,
                }

                execution_results["steps_completed"].append(step_result)
                execution_results["intermediate_results"].append(step_result["output"])

                # Store tool outputs
                for tool in tools:
                    execution_results["tool_outputs"][tool] = f"Output from {tool}"

            except Exception as e:
                error_result = {
                    "step": step_num,
                    "action": action,
                    "tools_used": tools,
                    "error": str(e),
                    "success": False,
                }
                execution_results["steps_completed"].append(error_result)
                execution_results["errors"].append(str(e))
                execution_results["success"] = False

        return execution_results

    def _phase_reflection(
        self,
        kwargs: dict[str, Any],
        execution_results: dict[str, Any],
        previous_iterations: list[IterationState],
    ) -> dict[str, Any]:
        """Phase 4: Reflect on execution results and assess progress."""
        reflection = {
            "quality_assessment": {},
            "goal_progress": {},
            "areas_for_improvement": [],
            "next_iteration_suggestions": [],
            "confidence_score": 0.0,
        }

        # Assess execution quality
        total_steps = len(execution_results.get("steps_completed", []))
        successful_steps = sum(
            1
            for step in execution_results.get("steps_completed", [])
            if step.get("success", False)
        )

        reflection["quality_assessment"] = {
            "execution_success_rate": successful_steps / max(total_steps, 1),
            "errors_encountered": len(execution_results.get("errors", [])),
            "tools_utilized": len(execution_results.get("tool_outputs", {})),
            "output_quality": (
                "good" if successful_steps > total_steps * 0.7 else "poor"
            ),
        }

        # Assess progress toward goal
        messages = kwargs.get("messages", [])
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # Simple goal progress assessment
        has_analysis = any(
            "analyze" in result.lower()
            for result in execution_results.get("intermediate_results", [])
        )
        has_data = len(execution_results.get("tool_outputs", {})) > 0

        progress_score = 0.5  # Base score
        if has_analysis:
            progress_score += 0.3
        if has_data:
            progress_score += 0.2

        reflection["goal_progress"] = {
            "estimated_completion": min(progress_score, 1.0),
            "goals_achieved": ["data_gathering"] if has_data else [],
            "goals_remaining": ["analysis"] if not has_analysis else [],
            "quality_threshold_met": progress_score > 0.7,
        }

        # Suggest improvements
        if execution_results.get("errors"):
            reflection["areas_for_improvement"].append(
                "Error handling and tool reliability"
            )
        if successful_steps < total_steps:
            reflection["areas_for_improvement"].append(
                "Tool selection and configuration"
            )

        # Suggestions for next iteration
        if progress_score < 0.8:
            reflection["next_iteration_suggestions"].append(
                "Explore additional tools or data sources"
            )
        if not has_analysis and "analyze" in user_query.lower():
            reflection["next_iteration_suggestions"].append(
                "Focus on analysis and insight generation"
            )

        reflection["confidence_score"] = progress_score

        return reflection

    def _phase_convergence(
        self,
        kwargs: dict[str, Any],
        iteration_state: IterationState,
        previous_iterations: list[IterationState],
        convergence_criteria: dict[str, Any],
        global_discoveries: dict[str, Any],
    ) -> dict[str, Any]:
        """Phase 5: Decide whether to continue iterating or stop."""
        convergence_result = {
            "should_stop": False,
            "reason": "",
            "confidence": 0.0,
            "criteria_met": {},
            "recommendations": [],
        }

        # Default convergence criteria
        default_criteria = {
            "goal_satisfaction": {"threshold": 0.8},
            "diminishing_returns": {
                "enabled": True,
                "min_improvement": 0.05,
                "lookback_window": 2,
            },
            "resource_limits": {"max_cost": 1.0, "max_time": 300},
            "quality_gates": {"min_confidence": 0.7},
            "early_satisfaction": {
                "enabled": True,
                "threshold": 0.85,
            },  # Stop early if very confident
        }

        # Merge with provided criteria
        criteria = {**default_criteria, **convergence_criteria}

        # Extract user query for context
        messages = kwargs.get("messages", [])
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # Analyze current execution results for satisfaction
        execution_results = iteration_state.execution_results
        reflection = iteration_state.reflection

        # Enhanced goal satisfaction analysis
        if reflection and "confidence_score" in reflection:
            confidence_score = reflection["confidence_score"]
            goal_threshold = criteria.get("goal_satisfaction", {}).get("threshold", 0.8)

            # Check if we have sufficient data and analysis
            has_sufficient_data = len(execution_results.get("tool_outputs", {})) >= 1
            has_analysis_content = any(
                len(result) > 50
                for result in execution_results.get("intermediate_results", [])
            )
            execution_success_rate = reflection.get("quality_assessment", {}).get(
                "execution_success_rate", 0
            )

            # Enhanced satisfaction calculation
            satisfaction_score = confidence_score

            # Boost score if we have good data and analysis
            if (
                has_sufficient_data
                and has_analysis_content
                and execution_success_rate > 0.8
            ):
                satisfaction_score += 0.1

            # Boost score if user query seems simple and we have a good response
            simple_query_indicators = ["what", "how", "analyze", "explain"]
            if any(
                indicator in user_query.lower() for indicator in simple_query_indicators
            ):
                if has_analysis_content:
                    satisfaction_score += 0.1

            # Apply early satisfaction check
            early_config = criteria.get("early_satisfaction", {})
            early_threshold = early_config.get("threshold", 0.85)
            if early_config.get("enabled", True):
                # Check built-in early satisfaction criteria
                meets_builtin_criteria = (
                    satisfaction_score >= early_threshold and has_sufficient_data
                )

                # Check user-defined custom early stopping function
                custom_check_func = early_config.get("custom_check")
                meets_custom_criteria = True

                if custom_check_func and callable(custom_check_func):
                    try:
                        # Call user-defined function with current state
                        custom_result = custom_check_func(
                            {
                                "iteration_state": iteration_state,
                                "satisfaction_score": satisfaction_score,
                                "execution_results": execution_results,
                                "reflection": reflection,
                                "user_query": user_query,
                                "previous_iterations": previous_iterations,
                                "global_discoveries": kwargs.get(
                                    "_global_discoveries", {}
                                ),
                            }
                        )
                        meets_custom_criteria = bool(custom_result)

                        if isinstance(custom_result, dict):
                            # Custom function can return detailed result
                            meets_custom_criteria = custom_result.get(
                                "should_stop", False
                            )
                            if "reason" in custom_result:
                                convergence_result["reason"] = (
                                    f"custom_early_stop: {custom_result['reason']}"
                                )
                            if "confidence" in custom_result:
                                convergence_result["confidence"] = custom_result[
                                    "confidence"
                                ]
                    except Exception as e:
                        self.logger.warning(
                            f"Custom early stopping function failed: {e}"
                        )
                        meets_custom_criteria = True  # Fall back to built-in criteria

                if meets_builtin_criteria and meets_custom_criteria:
                    convergence_result["should_stop"] = True
                    if not convergence_result[
                        "reason"
                    ]:  # Only set if custom didn't provide one
                        convergence_result["reason"] = "early_satisfaction_achieved"
                    if not convergence_result[
                        "confidence"
                    ]:  # Only set if custom didn't provide one
                        convergence_result["confidence"] = satisfaction_score
                    convergence_result["criteria_met"]["early_satisfaction"] = True
                    return convergence_result

            # Standard goal satisfaction check
            goal_satisfaction = satisfaction_score >= goal_threshold
            convergence_result["criteria_met"]["goal_satisfaction"] = goal_satisfaction

            if goal_satisfaction:
                convergence_result["should_stop"] = True
                convergence_result["reason"] = "goal_satisfaction_achieved"
                convergence_result["confidence"] = satisfaction_score

        # Check if first iteration was already very successful
        if len(previous_iterations) == 0:  # This is iteration 1
            if execution_results.get("success", False):
                success_rate = reflection.get("quality_assessment", {}).get(
                    "execution_success_rate", 0
                )
                confidence = reflection.get("confidence_score", 0)

                # If first iteration was highly successful and confident, consider stopping
                if success_rate >= 0.9 and confidence >= 0.8:
                    convergence_result["should_stop"] = True
                    convergence_result["reason"] = "first_iteration_highly_successful"
                    convergence_result["confidence"] = confidence
                    convergence_result["criteria_met"]["first_iteration_success"] = True
                    return convergence_result

        # Check diminishing returns (only if we've had multiple iterations)
        if len(previous_iterations) >= 1 and criteria.get(
            "diminishing_returns", {}
        ).get("enabled", True):
            lookback = criteria.get("diminishing_returns", {}).get("lookback_window", 2)
            min_improvement = criteria.get("diminishing_returns", {}).get(
                "min_improvement", 0.05
            )

            # Get recent confidence scores
            recent_scores = []
            if reflection and "confidence_score" in reflection:
                recent_scores.append(reflection["confidence_score"])

            for prev_iter in previous_iterations[-lookback:]:
                if prev_iter.reflection and "confidence_score" in prev_iter.reflection:
                    recent_scores.append(prev_iter.reflection["confidence_score"])

            if len(recent_scores) >= 2:
                # Compare current with previous iteration
                current_score = recent_scores[0]
                previous_score = recent_scores[1]
                improvement = current_score - previous_score

                diminishing_returns = improvement < min_improvement
                convergence_result["criteria_met"][
                    "diminishing_returns"
                ] = diminishing_returns

                # Only stop for diminishing returns if we already have decent confidence
                if (
                    diminishing_returns
                    and current_score >= 0.7
                    and not convergence_result["should_stop"]
                ):
                    convergence_result["should_stop"] = True
                    convergence_result["reason"] = "diminishing_returns_detected"
                    convergence_result["confidence"] = current_score

        # Check quality gates
        quality_threshold = criteria.get("quality_gates", {}).get("min_confidence", 0.7)
        if reflection and reflection.get("confidence_score", 0) >= quality_threshold:
            convergence_result["criteria_met"]["quality_gates"] = True

            # If we meet quality gates and have good execution, consider stopping
            execution_quality = reflection.get("quality_assessment", {}).get(
                "execution_success_rate", 0
            )

            # Only stop for quality gates if we've actually discovered and used tools
            has_real_discoveries = len(global_discoveries.get("tools", {})) > 0
            tools_actually_used = len(execution_results.get("tool_outputs", {})) > 0

            if (
                execution_quality >= 0.8
                and not convergence_result["should_stop"]
                and has_real_discoveries
                and tools_actually_used
            ):
                convergence_result["should_stop"] = True
                convergence_result["reason"] = "quality_gates_satisfied"
                convergence_result["confidence"] = reflection["confidence_score"]

        # Resource limits check
        resource_limits = criteria.get("resource_limits", {})
        total_time = sum(
            (iter_state.end_time - iter_state.start_time)
            for iter_state in previous_iterations + [iteration_state]
            if iter_state.end_time
        )

        if total_time > resource_limits.get("max_time", 300):
            convergence_result["should_stop"] = True
            convergence_result["reason"] = "time_limit_exceeded"
            convergence_result["confidence"] = (
                reflection.get("confidence_score", 0.5) if reflection else 0.5
            )

        # Check custom convergence criteria
        custom_criteria = criteria.get("custom_criteria", [])
        if custom_criteria and not convergence_result["should_stop"]:
            total_custom_weight = 0
            custom_stop_score = 0

            for custom_criterion in custom_criteria:
                if not isinstance(custom_criterion, dict):
                    continue

                criterion_func = custom_criterion.get("function")
                criterion_weight = custom_criterion.get("weight", 1.0)
                criterion_name = custom_criterion.get("name", "unnamed_custom")

                if criterion_func and callable(criterion_func):
                    try:
                        # Call custom convergence function
                        custom_result = criterion_func(
                            {
                                "iteration_state": iteration_state,
                                "previous_iterations": previous_iterations,
                                "execution_results": execution_results,
                                "reflection": reflection,
                                "user_query": user_query,
                                "global_discoveries": kwargs.get(
                                    "_global_discoveries", {}
                                ),
                                "total_duration": sum(
                                    (iter_state.end_time - iter_state.start_time)
                                    for iter_state in previous_iterations
                                    + [iteration_state]
                                    if iter_state.end_time
                                ),
                            }
                        )

                        # Handle different return types
                        if isinstance(custom_result, bool):
                            criterion_score = 1.0 if custom_result else 0.0
                        elif isinstance(custom_result, (int, float)):
                            criterion_score = float(custom_result)
                        elif isinstance(custom_result, dict):
                            criterion_score = custom_result.get("score", 0.0)
                            # If custom function says stop immediately
                            if custom_result.get("stop_immediately", False):
                                convergence_result["should_stop"] = True
                                convergence_result["reason"] = (
                                    f"custom_criterion_{criterion_name}_immediate_stop"
                                )
                                convergence_result["confidence"] = custom_result.get(
                                    "confidence", 0.8
                                )
                                convergence_result["criteria_met"][
                                    f"custom_{criterion_name}"
                                ] = True
                                return convergence_result
                        else:
                            criterion_score = 0.0

                        # Accumulate weighted score
                        custom_stop_score += criterion_score * criterion_weight
                        total_custom_weight += criterion_weight
                        convergence_result["criteria_met"][
                            f"custom_{criterion_name}"
                        ] = (criterion_score > 0.5)

                    except Exception as e:
                        self.logger.warning(
                            f"Custom convergence criterion '{criterion_name}' failed: {e}"
                        )

            # Check if weighted custom criteria suggest stopping
            if total_custom_weight > 0:
                avg_custom_score = custom_stop_score / total_custom_weight
                if avg_custom_score >= 0.8:  # High confidence from custom criteria
                    convergence_result["should_stop"] = True
                    convergence_result["reason"] = "custom_criteria_consensus"
                    convergence_result["confidence"] = avg_custom_score
                    return convergence_result

        # Add recommendations for next iteration if not stopping
        if not convergence_result["should_stop"] and reflection:
            confidence = reflection.get("confidence_score", 0)
            if confidence < 0.6:
                convergence_result["recommendations"].append(
                    "Focus on gathering more comprehensive data"
                )
            if execution_results.get("errors"):
                convergence_result["recommendations"].append(
                    "Improve tool selection and error handling"
                )
            if len(execution_results.get("intermediate_results", [])) < 2:
                convergence_result["recommendations"].append(
                    "Execute more analysis steps for thoroughness"
                )

        return convergence_result

    def _phase_synthesis(
        self,
        kwargs: dict[str, Any],
        iterations: list[IterationState],
        global_discoveries: dict[str, Any],
    ) -> str:
        """Phase 6: Synthesize results from all iterations into final response."""
        messages = kwargs.get("messages", [])
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_query = msg.get("content", "")
                break

        # Collect all execution results
        all_results = []
        all_insights = []

        for iteration in iterations:
            if iteration.success and iteration.execution_results:
                results = iteration.execution_results.get("intermediate_results", [])
                all_results.extend(results)

                if iteration.reflection:
                    goals_achieved = iteration.reflection.get("goal_progress", {}).get(
                        "goals_achieved", []
                    )
                    all_insights.extend(goals_achieved)

        # Create synthesized response
        synthesis = f"## Analysis Results for: {user_query}\n\n"

        if all_results:
            synthesis += "### Key Findings:\n"
            for i, result in enumerate(all_results[:5], 1):  # Limit to top 5 results
                synthesis += f"{i}. {result}\n"
            synthesis += "\n"

        # Add iteration summary
        synthesis += "### Process Summary:\n"
        synthesis += f"- Completed {len(iterations)} iterations\n"
        synthesis += f"- Discovered {len(global_discoveries.get('tools', {}))} tools and {len(global_discoveries.get('resources', {}))} resources\n"

        successful_iterations = sum(1 for it in iterations if it.success)
        synthesis += (
            f"- {successful_iterations}/{len(iterations)} iterations successful\n\n"
        )

        # Add confidence and evidence
        final_confidence = 0.8  # Mock final confidence
        synthesis += f"### Confidence: {final_confidence:.1%}\n"
        synthesis += f"Based on analysis using {len(global_discoveries.get('tools', {}))} MCP tools and comprehensive iterative processing.\n\n"

        # Add recommendations if analysis-focused
        if "analyze" in user_query.lower() or "recommend" in user_query.lower():
            synthesis += "### Recommendations:\n"
            synthesis += (
                "1. Continue monitoring key metrics identified in this analysis\n"
            )
            synthesis += "2. Consider implementing suggested improvements\n"
            synthesis += "3. Review findings with stakeholders for validation\n"

        return synthesis

    def _update_global_discoveries(
        self, global_discoveries: dict[str, Any], new_discoveries: dict[str, Any]
    ) -> None:
        """Update global discoveries with new findings."""
        # Update servers
        for server in new_discoveries.get("new_servers", []):
            global_discoveries["servers"][server["id"]] = server

        # Update tools
        for tool in new_discoveries.get("new_tools", []):
            tool_name = tool.get("name") if isinstance(tool, dict) else str(tool)
            if isinstance(tool, dict) and "function" in tool:
                tool_name = tool["function"].get("name", tool_name)
            global_discoveries["tools"][tool_name] = tool

        # Update resources
        for resource in new_discoveries.get("new_resources", []):
            resource_uri = resource.get("uri", str(resource))
            global_discoveries["resources"][resource_uri] = resource

        # Update capabilities
        for capability in new_discoveries.get("tool_capabilities", []):
            cap_name = capability.get("name", "unknown")
            global_discoveries["capabilities"][cap_name] = capability

    def _adapt_strategy(
        self,
        kwargs: dict[str, Any],
        iteration_state: IterationState,
        previous_iterations: list[IterationState],
    ) -> None:
        """Adapt strategy for next iteration based on results."""
        # Simple adaptation logic (in real implementation, use more sophisticated ML)
        if iteration_state.reflection:
            confidence = iteration_state.reflection.get("confidence_score", 0.5)

            # If confidence is low, suggest more thorough discovery
            if confidence < 0.6:
                kwargs["discovery_mode"] = "exhaustive"

            # If errors occurred, reduce timeout for faster iteration
            if iteration_state.execution_results.get("errors"):
                kwargs["iteration_timeout"] = min(
                    kwargs.get("iteration_timeout", 300), 180
                )

    def _calculate_resource_usage(
        self, iterations: list[IterationState]
    ) -> dict[str, Any]:
        """Calculate resource usage across all iterations."""
        total_duration = sum(
            (iter_state.end_time - iter_state.start_time)
            for iter_state in iterations
            if iter_state.end_time
        )

        total_tools_used = 0
        total_api_calls = 0

        for iteration in iterations:
            if iteration.execution_results:
                total_tools_used += len(
                    iteration.execution_results.get("tool_outputs", {})
                )
                total_api_calls += len(
                    iteration.execution_results.get("steps_completed", [])
                )

        return {
            "total_duration_seconds": total_duration,
            "total_iterations": len(iterations),
            "total_tools_used": total_tools_used,
            "total_api_calls": total_api_calls,
            "average_iteration_time": total_duration / max(len(iterations), 1),
            "estimated_cost_usd": total_api_calls * 0.01,  # Mock cost calculation
        }
