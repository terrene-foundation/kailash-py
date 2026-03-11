"""
ReAct Agent with Kaizen MCP Tool Integration

Implements the Reasoning and Acting pattern with external tool integration
through the Model Context Protocol (MCP) using Kaizen's signature-based
programming for complex problem-solving workflows.
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple

# Kaizen Framework imports for signature-based ReAct agent (Option 3: DSPy-inspired)
import kaizen
from kaizen.signatures import InputField, OutputField, Signature

# Configure detailed logging for ReAct tracing
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of actions the ReAct agent can take."""

    TOOL_USE = "tool_use"
    FINISH = "finish"
    CLARIFY = "clarify"


@dataclass
class MCPToolConfig:
    """Configuration for MCP tool servers."""

    name: str
    endpoint: str
    capabilities: List[str]
    timeout: int = 30
    max_retries: int = 3


class ReActSignature(Signature):
    """Signature for ReAct reasoning and acting pattern (Option 3: DSPy-inspired)."""

    # Input fields - Option 3: DSPy-inspired syntax
    task: str = InputField(desc="The task to solve")
    context: str = InputField(desc="Previous context and observations", default="")
    available_tools: list = InputField(desc="List of available MCP tools", default=[])
    previous_actions: list = InputField(desc="Previous actions taken", default=[])

    # Output fields - structured ReAct response
    thought: str = OutputField(desc="Current reasoning step")
    action: str = OutputField(desc="Action to take (tool_use, finish, clarify)")
    action_input: dict = OutputField(desc="Input parameters for the action")
    confidence: float = OutputField(desc="Confidence in the action (0.0-1.0)")
    need_tool: bool = OutputField(desc="Whether external tool is needed")


@dataclass
class ReActConfig:
    """Configuration for ReAct agent behavior."""

    max_cycles: int = 10
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    confidence_threshold: float = 0.7
    mcp_discovery_enabled: bool = True
    enable_parallel_tools: bool = False
    timeout: int = 30
    max_retries: int = 3


class KaizenReActAgent:
    """
    ReAct Agent using Kaizen framework with MCP tool integration.

    Implements the Reasoning and Acting pattern with signature-based programming,
    enterprise features, and automatic MCP tool discovery and integration.
    """

    def __init__(self, config: ReActConfig):
        self.config = config
        self.kaizen_framework = None
        self.agent = None
        self.available_tools = []
        self.action_history = []
        self._initialize_framework()

    def _initialize_framework(self):
        """Initialize Kaizen framework with MCP integration."""
        logger.info("Initializing Kaizen ReAct agent with MCP integration")
        start_time = time.time()

        try:
            # Configure Kaizen with MCP and enterprise features
            framework_config = kaizen.KaizenConfig(
                signature_programming_enabled=True,
                mcp_enabled=True,
                optimization_enabled=True,
                monitoring_enabled=True,
                audit_trail_enabled=True,
                debug=False,
            )

            self.kaizen_framework = kaizen.Kaizen(config=framework_config)

            # Create ReAct signature (Option 3)
            react_signature = ReActSignature()

            # Configure agent with ReAct capabilities
            agent_config = {
                "provider": self.config.llm_provider,
                "model": self.config.model,
                "temperature": self.config.temperature,
                "timeout": self.config.timeout,
                "enable_monitoring": True,
                "mcp_integration": True,
                "reasoning_pattern": "react",
            }

            # Create agent with signature
            self.agent = self.kaizen_framework.create_agent(
                agent_id="react_agent", config=agent_config, signature=react_signature
            )

            # Initialize MCP tools if discovery is enabled
            if self.config.mcp_discovery_enabled:
                self._discover_mcp_tools()

            init_time = (time.time() - start_time) * 1000
            logger.info(f"Kaizen ReAct agent initialized in {init_time:.1f}ms")

        except Exception as e:
            logger.error(f"Failed to initialize Kaizen ReAct agent: {e}")
            raise

    def _discover_mcp_tools(self):
        """Discover available MCP tools using Kaizen's MCP integration."""
        logger.info("Discovering MCP tools...")
        try:
            # Use Kaizen's MCP discovery
            discovered_tools = self.kaizen_framework.discover_mcp_tools(
                capabilities=["search", "calculate", "web_browse", "file_operations"],
                include_local=True,
                timeout=10,
            )

            self.available_tools = []
            for tool in discovered_tools:
                tool_info = {
                    "name": tool.get("tool_name", tool.get("name", "unknown")),
                    "description": tool.get("description", ""),
                    "capabilities": tool.get("capabilities", []),
                    "source": tool.get("source", "external"),
                    "endpoint": tool.get("server_url", tool.get("endpoint", "")),
                }
                self.available_tools.append(tool_info)

            logger.info(f"Discovered {len(self.available_tools)} MCP tools")
            for tool in self.available_tools:
                logger.info(f"  - {tool['name']}: {tool['description']}")

        except Exception as e:
            logger.warning(f"MCP tool discovery failed: {e}")
            # Fallback to mock tools for demo
            self._setup_mock_tools()

    def _setup_mock_tools(self):
        """Setup mock tools for demonstration when MCP discovery fails."""
        logger.info("Setting up mock tools for demonstration")
        self.available_tools = [
            {
                "name": "calculator",
                "description": "Perform mathematical calculations",
                "capabilities": ["arithmetic", "algebra"],
                "source": "mock",
                "endpoint": "mock://calculator",
            },
            {
                "name": "web_search",
                "description": "Search the web for information",
                "capabilities": ["search", "information_retrieval"],
                "source": "mock",
                "endpoint": "mock://web_search",
            },
            {
                "name": "file_reader",
                "description": "Read and analyze files",
                "capabilities": ["file_operations", "text_analysis"],
                "source": "mock",
                "endpoint": "mock://file_reader",
            },
        ]

    def solve(self, task: str, context: str = "") -> Dict[str, Any]:
        """
        Solve a task using ReAct pattern with MCP tools.

        Args:
            task: The task to solve
            context: Additional context for the task

        Returns:
            Dict containing solution, reasoning trace, and metadata
        """
        logger.info(f"Starting ReAct solving for task: {task[:100]}...")
        start_time = time.time()

        self.action_history = []
        observations = []
        current_context = context

        for cycle in range(self.config.max_cycles):
            logger.info(f"ReAct cycle {cycle + 1}/{self.config.max_cycles}")

            try:
                # Prepare signature input
                signature_input = {
                    "task": task,
                    "context": current_context,
                    "available_tools": [tool["name"] for tool in self.available_tools],
                    "previous_actions": (
                        self.action_history[-3:] if self.action_history else []
                    ),
                }

                # Execute reasoning step using signature
                if self.agent.has_signature:
                    result = self.agent.execute(**signature_input)
                else:
                    # Fallback execution
                    prompt = self._build_react_prompt(signature_input)
                    result = self.agent.execute(prompt)

                # Parse result
                if isinstance(result, dict) and "action" in result:
                    thought = result.get("thought", "")
                    action = result.get("action", "finish")
                    action_input = result.get("action_input", {})
                    confidence = result.get("confidence", 0.8)
                    need_tool = result.get("need_tool", False)
                else:
                    # Parse from text response
                    thought, action, action_input, confidence, need_tool = (
                        self._parse_react_response(str(result))
                    )

                logger.info(f"Thought: {thought}")
                logger.info(f"Action: {action}")
                logger.info(f"Confidence: {confidence}")

                # Record action
                action_record = {
                    "cycle": cycle + 1,
                    "thought": thought,
                    "action": action,
                    "action_input": action_input,
                    "confidence": confidence,
                    "timestamp": time.time(),
                }

                # Handle different action types
                if action == "finish":
                    action_record["observation"] = "Task completed"
                    self.action_history.append(action_record)
                    break

                elif action == "tool_use" and need_tool:
                    # Execute tool
                    observation = self._execute_tool(action_input)
                    action_record["observation"] = observation
                    observations.append(observation)

                    # Update context with observation
                    current_context += f"\n\nObservation {cycle + 1}: {observation}"

                elif action == "clarify":
                    action_record["observation"] = "Need clarification from user"
                    self.action_history.append(action_record)
                    break

                else:
                    # Continue reasoning without tool
                    action_record["observation"] = "Continuing analysis..."

                self.action_history.append(action_record)

                # Check confidence threshold
                if confidence < self.config.confidence_threshold:
                    logger.warning(
                        f"Low confidence ({confidence:.2f}) in cycle {cycle + 1}"
                    )

            except Exception as e:
                logger.error(f"Error in ReAct cycle {cycle + 1}: {e}")
                self.action_history.append(
                    {"cycle": cycle + 1, "error": str(e), "timestamp": time.time()}
                )
                break

        # Build final response
        execution_time = (time.time() - start_time) * 1000
        final_action = self.action_history[-1] if self.action_history else {}

        response = {
            "solution": final_action.get("observation", "Task completed"),
            "reasoning_trace": self.action_history,
            "total_cycles": len(self.action_history),
            "tools_used": len(
                [a for a in self.action_history if a.get("action") == "tool_use"]
            ),
            "metadata": {
                "execution_time_ms": round(execution_time, 1),
                "framework": "kaizen",
                "pattern": "react",
                "mcp_tools_available": len(self.available_tools),
                "max_cycles": self.config.max_cycles,
                "signature_used": self.agent.has_signature,
            },
        }

        logger.info(
            f"ReAct task completed in {execution_time:.1f}ms with {len(self.action_history)} cycles"
        )
        return response

    def _build_react_prompt(self, signature_input: Dict[str, Any]) -> str:
        """Build ReAct prompt for fallback execution."""
        tools_list = ", ".join(signature_input["available_tools"])
        previous_actions_text = ""

        if signature_input["previous_actions"]:
            previous_actions_text = "\n\nPrevious actions:\n" + "\n".join(
                [
                    f"- {action.get('action', 'unknown')}: {action.get('thought', '')}"
                    for action in signature_input["previous_actions"]
                ]
            )

        prompt = f"""You are a ReAct agent that solves tasks by reasoning and acting.

Task: {signature_input['task']}
Context: {signature_input['context']}
Available tools: {tools_list}
{previous_actions_text}

Use the ReAct pattern: Think step by step, then decide on an action.

Respond in this format:
Thought: [your reasoning]
Action: [tool_use/finish/clarify]
Action Input: [parameters for the action]
Confidence: [0.0-1.0]
Need Tool: [true/false]"""

        return prompt

    def _parse_react_response(
        self, response: str
    ) -> Tuple[str, str, Dict, float, bool]:
        """Parse ReAct response from text."""
        thought = ""
        action = "finish"
        action_input = {}
        confidence = 0.8
        need_tool = False

        lines = response.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("Thought:"):
                thought = line[8:].strip()
            elif line.startswith("Action:"):
                action = line[7:].strip().lower()
            elif line.startswith("Action Input:"):
                try:
                    action_input = json.loads(line[13:].strip())
                except:
                    action_input = {"input": line[13:].strip()}
            elif line.startswith("Confidence:"):
                try:
                    confidence = float(line[11:].strip())
                except:
                    confidence = 0.8
            elif line.startswith("Need Tool:"):
                need_tool = line[10:].strip().lower() in ["true", "yes", "1"]

        return thought, action, action_input, confidence, need_tool

    def _execute_tool(self, action_input: Dict[str, Any]) -> str:
        """Execute a tool and return observation."""
        tool_name = action_input.get("tool", action_input.get("name", ""))

        # Find the tool
        tool = next((t for t in self.available_tools if t["name"] == tool_name), None)
        if not tool:
            return f"Error: Tool '{tool_name}' not found"

        logger.info(f"Executing tool: {tool_name}")

        try:
            if tool["source"] == "mock":
                # Mock tool execution for demonstration
                return self._execute_mock_tool(tool_name, action_input)
            else:
                # Real MCP tool execution via Kaizen
                return self._execute_mcp_tool(tool, action_input)

        except Exception as e:
            return f"Error executing tool {tool_name}: {e}"

    def _execute_mock_tool(self, tool_name: str, action_input: Dict[str, Any]) -> str:
        """Execute mock tools for demonstration."""
        if tool_name == "calculator":
            expression = action_input.get("expression", action_input.get("input", ""))
            try:
                # Simple math evaluation (unsafe in production!)
                result = eval(expression.replace("^", "**"))
                return f"Calculation result: {expression} = {result}"
            except:
                return f"Error: Invalid mathematical expression: {expression}"

        elif tool_name == "web_search":
            query = action_input.get("query", action_input.get("input", ""))
            return f"Web search results for '{query}': [Mock results - would contain real search results]"

        elif tool_name == "file_reader":
            filename = action_input.get("filename", action_input.get("input", ""))
            return f"File content of '{filename}': [Mock content - would contain actual file content]"

        return f"Mock tool {tool_name} executed with input: {action_input}"

    def _execute_mcp_tool(
        self, tool: Dict[str, Any], action_input: Dict[str, Any]
    ) -> str:
        """Execute real MCP tool via Kaizen framework."""
        # This would use Kaizen's MCP client capabilities
        logger.info(f"Executing MCP tool {tool['name']} via Kaizen")

        # For now, return a placeholder
        return f"MCP tool {tool['name']} executed successfully (placeholder implementation)"


def main():
    """Example usage and testing of Kaizen ReAct agent."""
    print("=== Kaizen ReAct Agent with MCP Integration Testing ===\n")

    # Configure ReAct agent
    config = ReActConfig(
        max_cycles=5,
        llm_provider="mock",  # Use mock provider for demo
        model="gpt-4",
        temperature=0.1,
        confidence_threshold=0.7,
        mcp_discovery_enabled=True,
    )

    print("Initializing Kaizen ReAct agent...")
    agent = KaizenReActAgent(config)

    # Show discovered tools
    print(f"Available MCP tools: {len(agent.available_tools)}")
    for tool in agent.available_tools:
        print(f"  - {tool['name']}: {tool['description']}")
    print()

    # Test cases
    test_tasks = [
        {
            "task": "Calculate the area of a circle with radius 5",
            "context": "Use mathematical formulas for precision",
            "expected_tools": ["calculator"],
        },
        {
            "task": "Find information about machine learning trends in 2024",
            "context": "Look for recent developments and industry insights",
            "expected_tools": ["web_search"],
        },
        {
            "task": "What is 2 + 2?",
            "context": "Simple arithmetic question",
            "expected_tools": [],  # Might not need tools for simple questions
        },
    ]

    for i, test in enumerate(test_tasks, 1):
        print(f"=== Test {i}: {test['task']} ===")
        print(f"Context: {test['context']}")
        print(f"Expected tools: {test['expected_tools']}")
        print()

        # Solve the task
        result = agent.solve(test["task"], test["context"])

        print("SOLUTION:")
        print(result["solution"])
        print()

        print("REASONING TRACE:")
        for action in result["reasoning_trace"]:
            cycle = action.get("cycle", 0)
            thought = action.get("thought", "")
            action_type = action.get("action", "")
            observation = action.get("observation", "")
            confidence = action.get("confidence", 0)

            print(f"  Cycle {cycle}:")
            print(f"    Thought: {thought}")
            print(f"    Action: {action_type}")
            print(f"    Confidence: {confidence:.2f}")
            print(f"    Observation: {observation}")
            print()

        print("METADATA:")
        metadata = result["metadata"]
        print(f"  Execution time: {metadata['execution_time_ms']}ms")
        print(f"  Total cycles: {result['total_cycles']}")
        print(f"  Tools used: {result['tools_used']}")
        print(f"  Framework: {metadata['framework']}")
        print(f"  Pattern: {metadata['pattern']}")
        print(f"  Signature used: {metadata['signature_used']}")
        print(f"  MCP tools available: {metadata['mcp_tools_available']}")

        print("-" * 80)
        print()

    # Enterprise audit trail
    if hasattr(agent.kaizen_framework, "get_audit_trail"):
        audit_trail = agent.kaizen_framework.get_audit_trail(limit=5)
        if audit_trail:
            print("=== Enterprise Audit Trail (last 5 entries) ===")
            for entry in audit_trail[-5:]:
                action = entry.get("action", "unknown")
                timestamp = entry.get("timestamp", "unknown")
                print(f"Action: {action} at {timestamp}")
            print()

    # Performance summary
    print("=== Performance Summary ===")
    print("ReAct agent configuration:")
    print(f"  Model: {config.model}")
    print(f"  Max cycles: {config.max_cycles}")
    print(f"  Confidence threshold: {config.confidence_threshold}")
    print(f"  MCP discovery: {config.mcp_discovery_enabled}")
    print("Framework features:")
    print(f"  Signature programming: {agent.agent.has_signature}")
    print("  MCP integration: Available")
    print("  Enterprise audit: Enabled")


def performance_benchmark():
    """Run performance benchmarks for ReAct agent."""
    print("=== Kaizen ReAct Agent Performance Benchmark ===\n")

    config = ReActConfig(
        max_cycles=3,
        llm_provider="mock",  # Use mock provider for speed
        model="gpt-3.5-turbo",
        temperature=0.0,
        mcp_discovery_enabled=False,  # Skip discovery for speed
    )

    # Benchmark initialization times
    init_times = []
    solve_times = []

    for i in range(3):
        print(f"Benchmark run {i+1}/3...")

        # Time initialization
        start_time = time.time()
        agent = KaizenReActAgent(config)
        init_time = (time.time() - start_time) * 1000
        init_times.append(init_time)

        # Time simple task solving
        start_time = time.time()
        result = agent.solve("What is 10 + 15?", "Simple arithmetic")
        solve_time = (time.time() - start_time) * 1000
        solve_times.append(solve_time)

        # Cleanup
        agent.kaizen_framework.cleanup()

    avg_init_time = sum(init_times) / len(init_times)
    avg_solve_time = sum(solve_times) / len(solve_times)

    print("\nPerformance Results:")
    print(f"Average initialization time: {avg_init_time:.1f}ms")
    print(f"Average simple task solve time: {avg_solve_time:.1f}ms")

    # Performance targets
    init_target = 500  # ms for ReAct is more complex than simple agents
    solve_target = 2000  # ms for reasoning cycles

    print(
        f"Initialization target (<{init_target}ms): {'PASS' if avg_init_time < init_target else 'FAIL'}"
    )
    print(
        f"Solve time target (<{solve_target}ms): {'PASS' if avg_solve_time < solve_target else 'FAIL'}"
    )

    return avg_init_time < init_target and avg_solve_time < solve_target


if __name__ == "__main__":
    main()
    print("\n" + "=" * 80 + "\n")
    performance_benchmark()
