# Building Custom Autonomous Agents - Tutorial

**Version**: 0.1.0
**Status**: Production Ready
**Difficulty**: Intermediate
**Time**: 30-60 minutes
**Created**: 2025-10-22

---

## Overview

This tutorial teaches you how to build custom autonomous agents by extending `BaseAutonomousAgent`. You'll learn the core patterns, best practices, and implementation techniques used by ClaudeCodeAgent and CodexAgent.

## What You'll Build

By the end of this tutorial, you'll have built:

1. **ResearchAgent** - Autonomous web research agent
2. **DataAnalysisAgent** - Autonomous data analysis agent
3. **CustomToolAgent** - Agent with custom tool integration

## Prerequisites

### Required Knowledge
- Python 3.11+
- Async/await programming
- Kaizen BaseAgent concepts
- Basic autonomous agent patterns

### Required Setup
```bash
# Install Kaizen
pip install kailash-kaizen

# Verify installation
python -c "from kaizen.agents.autonomous import BaseAutonomousAgent; print('✓ Ready')"
```

---

## Table of Contents

1. [Understanding BaseAutonomousAgent](#understanding-baseautonomousagent)
2. [Tutorial 1: ResearchAgent](#tutorial-1-researchagent)
3. [Tutorial 2: DataAnalysisAgent](#tutorial-2-dataanalysisagent)
4. [Tutorial 3: CustomToolAgent](#tutorial-3-customtoolagent)
5. [Advanced Patterns](#advanced-patterns)
6. [Testing Your Agent](#testing-your-agent)
7. [Production Deployment](#production-deployment)

---

## Understanding BaseAutonomousAgent

### Core Components

Every autonomous agent has these components:

1. **Config Class**: Configuration with agent-specific parameters
2. **Signature Class**: Type-safe I/O definition
3. **Agent Class**: Implementation extending BaseAutonomousAgent
4. **Tool Registry**: Tools available to agent
5. **Convergence Detection**: Logic to determine when task is complete

### Minimal Autonomous Agent

```python
from dataclasses import dataclass
from kaizen.agents.autonomous import BaseAutonomousAgent, AutonomousConfig
from kaizen.signatures import Signature, InputField, OutputField

# 1. Config
@dataclass
class MyAgentConfig(AutonomousConfig):
    max_cycles: int = 20
    custom_param: str = "value"

# 2. Signature
class MySignature(Signature):
    task: str = InputField(description="Task to complete")
    result: str = OutputField(description="Task result")
    tool_calls: list = OutputField(description="Tool calls", default=[])

# 3. Agent
class MyAgent(BaseAutonomousAgent):
    def __init__(self, config: MyAgentConfig, signature: Signature, tool_registry):
        super().__init__(config, signature, tool_registry)
        self.custom_param = config.custom_param

# 4. Usage
agent = MyAgent(config, signature, registry)
result = await agent.execute_autonomously("Complete this task")
```

### Key Methods to Override

| Method | Purpose | Override? |
|--------|---------|-----------|
| `__init__` | Initialize agent | Optional |
| `execute_autonomously` | Main entry point | Optional |
| `_check_convergence` | Detect completion | Optional |
| `_create_plan` | Generate task plan | Optional |
| `_autonomous_loop` | Execution loop | Rarely |

---

## Tutorial 1: ResearchAgent

Build an autonomous agent that conducts web research and generates comprehensive summaries.

### Step 1: Define Configuration

```python
# research_agent.py
from dataclasses import dataclass
from kaizen.agents.autonomous import AutonomousConfig

@dataclass
class ResearchAgentConfig(AutonomousConfig):
    """Configuration for ResearchAgent."""

    # Base config
    llm_provider: str = "openai"
    model: str = "gpt-4"
    max_cycles: int = 25
    planning_enabled: bool = True
    checkpoint_frequency: int = 5

    # Research-specific config
    max_search_results: int = 10
    min_sources: int = 3
    output_format: str = "markdown"  # or "json", "text"
    enable_web_search: bool = True
    enable_url_fetch: bool = True
```

### Step 2: Define Signature

```python
from kaizen.signatures import Signature, InputField, OutputField

class ResearchSignature(Signature):
    """Signature for research tasks."""

    # Inputs
    task: str = InputField(
        description="Research task or question to investigate"
    )
    context: str = InputField(
        description="Additional context or constraints",
        default=""
    )
    observation: str = InputField(
        description="Observations from previous cycle",
        default=""
    )

    # Outputs
    findings: str = OutputField(
        description="Research findings and summary"
    )
    sources: list = OutputField(
        description="List of sources consulted",
        default=[]
    )
    confidence: float = OutputField(
        description="Confidence in findings (0.0-1.0)",
        default=0.0
    )
    next_action: str = OutputField(
        description="Next action to take",
        default=""
    )
    tool_calls: list = OutputField(
        description="Tool calls to execute",
        default=[]
    )
```

### Step 3: Implement Agent Class

```python
import logging
from typing import Dict, Any, List
from kaizen.agents.autonomous import BaseAutonomousAgent
# Tools auto-configured via MCP

logger = logging.getLogger(__name__)

class ResearchAgent(BaseAutonomousAgent):
    """
    Autonomous research agent with web search and analysis capabilities.

    Features:
    - Multi-source web research
    - Automatic fact checking
    - Citation management
    - Structured output generation
    """

    def __init__(
        self,
        config: ResearchAgentConfig,
        signature: ResearchSignature,
        tool_registry: ToolRegistry,
        **kwargs
    ):
        """Initialize ResearchAgent."""
        super().__init__(
            config=config,
            signature=signature,
            tools="all"  # Enable tools via MCP
            **kwargs
        )

        # Store research-specific config
        self.research_config = config
        self.sources_consulted: List[str] = []

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """
        Execute research task autonomously.

        Workflow:
        1. Analyze research question
        2. Plan search strategy
        3. Conduct searches
        4. Fetch and analyze sources
        5. Synthesize findings
        6. Generate structured report
        """
        logger.info(f"Starting research: {task}")

        # Reset sources for new research
        self.sources_consulted = []

        # Execute autonomous loop (from parent)
        result = await super().execute_autonomously(task)

        # Add research metadata
        result["sources"] = self.sources_consulted
        result["source_count"] = len(self.sources_consulted)
        result["output_format"] = self.research_config.output_format

        # Format output based on config
        if self.research_config.output_format == "markdown":
            result["formatted_output"] = self._format_as_markdown(result)
        elif self.research_config.output_format == "json":
            result["formatted_output"] = self._format_as_json(result)

        logger.info(f"Research complete: {len(self.sources_consulted)} sources")
        return result

    def _check_convergence(self, response: Dict[str, Any]) -> bool:
        """
        Custom convergence detection for research tasks.

        Converges when:
        1. No more tool calls (objective)
        2. Minimum sources consulted
        3. Confidence threshold met
        """
        # Objective detection (preferred)
        tool_calls = response.get("tool_calls", [])
        if isinstance(tool_calls, list) and not tool_calls:
            # Check minimum sources
            if len(self.sources_consulted) >= self.research_config.min_sources:
                # Check confidence
                confidence = response.get("confidence", 0.0)
                if confidence >= 0.7:
                    logger.info("Converged: Objective + quality checks passed")
                    return True
                else:
                    logger.debug(f"Not converged: Low confidence ({confidence})")
                    return False
            else:
                logger.debug(
                    f"Not converged: Need more sources "
                    f"({len(self.sources_consulted)}/{self.research_config.min_sources})"
                )
                return False

        # Has tool calls - not converged
        return False

    def _format_as_markdown(self, result: Dict[str, Any]) -> str:
        """Format research findings as markdown."""
        output = f"# Research Report\n\n"
        output += f"## Question\n{result.get('task', 'N/A')}\n\n"
        output += f"## Findings\n{result.get('findings', 'N/A')}\n\n"
        output += f"## Sources\n"
        for i, source in enumerate(self.sources_consulted, 1):
            output += f"{i}. {source}\n"
        output += f"\n## Metadata\n"
        output += f"- Cycles: {result.get('cycles_used', 0)}\n"
        output += f"- Confidence: {result.get('confidence', 0.0):.2f}\n"
        return output

    def _format_as_json(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Format research findings as JSON."""
        return {
            "question": result.get("task", ""),
            "findings": result.get("findings", ""),
            "sources": self.sources_consulted,
            "metadata": {
                "cycles_used": result.get("cycles_used", 0),
                "confidence": result.get("confidence", 0.0),
                "source_count": len(self.sources_consulted)
            }
        }
```

### Step 4: Setup Tools

```python
# Tools auto-configured via MCP


def create_research_agent():
    """Create configured ResearchAgent."""
    # Create config
    config = ResearchAgentConfig(
        llm_provider="openai",
        model="gpt-4",
        max_cycles=25,
        max_search_results=10,
        min_sources=5,
        output_format="markdown"
    )

    # Create signature
    signature = ResearchSignature()

    # Setup tools

    # 12 builtin tools enabled via MCP

    # Create agent
    agent = ResearchAgent(
        config=config,
        signature=signature,
        tools="all"  # Enable 12 builtin tools via MCP
    )

    return agent
```

### Step 5: Use the Agent

```python
import asyncio

async def main():
    """Example usage of ResearchAgent."""
    # Create agent
    agent = create_research_agent()

    # Execute research task
    result = await agent.execute_autonomously(
        "Research the current state of autonomous AI agents in 2025. "
        "Focus on: production deployments, convergence detection methods, "
        "and best practices for long-running sessions."
    )

    # Display results
    print(f"✅ Research complete!")
    print(f"  - Cycles: {result['cycles_used']}")
    print(f"  - Sources: {result['source_count']}")
    print(f"  - Confidence: {result.get('confidence', 0):.2f}")
    print(f"\nFormatted Output:\n{result['formatted_output']}")

    return result

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Tutorial 2: DataAnalysisAgent

Build an autonomous agent that performs data analysis with pandas and generates visualizations.

### Step 1: Define Configuration

```python
@dataclass
class DataAnalysisConfig(AutonomousConfig):
    """Configuration for DataAnalysisAgent."""

    # Base config
    llm_provider: str = "openai"
    model: str = "gpt-4"
    max_cycles: int = 30
    planning_enabled: bool = True

    # Data analysis config
    data_path: str = ""
    output_dir: str = "analysis_output"
    enable_visualizations: bool = True
    enable_statistics: bool = True
    max_rows_to_sample: int = 1000
```

### Step 2: Define Signature

```python
class DataAnalysisSignature(Signature):
    """Signature for data analysis tasks."""

    # Inputs
    task: str = InputField(description="Data analysis task")
    data_path: str = InputField(description="Path to data file")
    context: str = InputField(description="Additional context", default="")
    observation: str = InputField(description="Last observation", default="")

    # Outputs
    analysis: str = OutputField(description="Analysis findings")
    statistics: dict = OutputField(description="Statistical summary", default={})
    visualizations: list = OutputField(description="Generated plots", default=[])
    next_action: str = OutputField(description="Next action", default="")
    tool_calls: list = OutputField(description="Tool calls", default=[])
```

### Step 3: Implement Agent Class

```python
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

class DataAnalysisAgent(BaseAutonomousAgent):
    """Autonomous data analysis agent with pandas and visualization."""

    def __init__(
        self,
        config: DataAnalysisConfig,
        signature: DataAnalysisSignature,
        tool_registry: ToolRegistry,
        **kwargs
    ):
        super().__init__(config, signature, tool_registry, **kwargs)
        self.data_config = config
        self.df: pd.DataFrame = None
        self.visualizations: List[str] = []

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute data analysis task."""
        logger.info(f"Starting data analysis: {task}")

        # Load data if path provided
        if self.data_config.data_path:
            self._load_data(self.data_config.data_path)

        # Setup output directory
        output_dir = Path(self.data_config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Execute autonomous loop
        result = await super().execute_autonomously(task)

        # Add analysis metadata
        result["visualizations"] = self.visualizations
        result["data_shape"] = self.df.shape if self.df is not None else None

        return result

    def _load_data(self, data_path: str) -> None:
        """Load data from file."""
        logger.info(f"Loading data from {data_path}")

        if data_path.endswith('.csv'):
            self.df = pd.read_csv(data_path)
        elif data_path.endswith('.json'):
            self.df = pd.read_json(data_path)
        elif data_path.endswith('.parquet'):
            self.df = pd.read_parquet(data_path)
        else:
            raise ValueError(f"Unsupported file format: {data_path}")

        logger.info(f"Data loaded: {self.df.shape}")

    def _generate_statistics(self) -> Dict[str, Any]:
        """Generate statistical summary."""
        if self.df is None:
            return {}

        stats = {
            "shape": self.df.shape,
            "columns": list(self.df.columns),
            "dtypes": {col: str(dtype) for col, dtype in self.df.dtypes.items()},
            "missing": self.df.isnull().sum().to_dict(),
            "numeric_summary": self.df.describe().to_dict(),
        }

        return stats

    def _generate_visualization(
        self, plot_type: str, x: str, y: str = None, title: str = ""
    ) -> str:
        """Generate visualization and save to file."""
        if self.df is None:
            return ""

        plt.figure(figsize=(10, 6))

        if plot_type == "histogram":
            self.df[x].hist(bins=30)
        elif plot_type == "scatter" and y:
            plt.scatter(self.df[x], self.df[y])
        elif plot_type == "line" and y:
            plt.plot(self.df[x], self.df[y])

        plt.title(title or f"{plot_type.title()} Plot")
        plt.xlabel(x)
        if y:
            plt.ylabel(y)

        # Save plot
        output_path = (
            Path(self.data_config.output_dir) / f"plot_{len(self.visualizations)}.png"
        )
        plt.savefig(output_path)
        plt.close()

        self.visualizations.append(str(output_path))
        logger.info(f"Visualization saved: {output_path}")

        return str(output_path)
```

### Step 4: Add Custom Tools

```python
from kaizen.tools import Tool, ToolParameter

def create_data_analysis_tools() -> List[Tool]:
    """Create custom tools for data analysis."""

    def analyze_data(data_path: str) -> Dict[str, Any]:
        """Load and analyze data."""
        df = pd.read_csv(data_path)
        return {
            "shape": df.shape,
            "columns": list(df.columns),
            "summary": df.describe().to_dict()
        }

    def create_plot(plot_type: str, x: str, y: str = None) -> str:
        """Create visualization."""
        # Implementation
        return "plot.png"

    tools = [
        Tool(
            name="analyze_data",
            description="Load and analyze data file",
            parameters=[
                ToolParameter(
                    name="data_path",
                    type="string",
                    required=True,
                    description="Path to data file"
                )
            ],
            executor=analyze_data,
            danger_level="SAFE"
        ),
        Tool(
            name="create_plot",
            description="Create data visualization",
            parameters=[
                ToolParameter(
                    name="plot_type",
                    type="string",
                    required=True,
                    description="Type: histogram, scatter, line"
                ),
                ToolParameter(
                    name="x",
                    type="string",
                    required=True,
                    description="X-axis column"
                ),
                ToolParameter(
                    name="y",
                    type="string",
                    required=False,
                    description="Y-axis column (optional)"
                )
            ],
            executor=create_plot,
            danger_level="SAFE"
        )
    ]

    return tools
```

### Step 5: Use the Agent

```python
async def main():
    """Example usage of DataAnalysisAgent."""
    # Create config
    config = DataAnalysisConfig(
        llm_provider="openai",
        model="gpt-4",
        data_path="sales_data.csv",
        output_dir="analysis",
        enable_visualizations=True
    )

    # Create agent with custom tools

    # 12 builtin tools enabled via MCP
    for tool in create_data_analysis_tools():
        registry.register(tool)

    agent = DataAnalysisAgent(config, DataAnalysisSignature(), registry)

    # Execute analysis
    result = await agent.execute_autonomously(
        "Analyze sales data and identify trends. "
        "Create visualizations showing sales over time and by region. "
        "Calculate key statistics and identify outliers."
    )

    print(f"✅ Analysis complete!")
    print(f"  - Shape: {result['data_shape']}")
    print(f"  - Visualizations: {len(result['visualizations'])}")
    print(f"\nFindings:\n{result.get('analysis', 'N/A')}")

asyncio.run(main())
```

---

## Tutorial 3: CustomToolAgent

Build an agent with fully custom tool integration.

### Step 1: Define Custom Tools

```python
from kaizen.tools import Tool, ToolParameter
from typing import Any, Dict

def send_email(to: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email (mock implementation)."""
    logger.info(f"Sending email to {to}: {subject}")
    # Real implementation would use SMTP
    return {"status": "sent", "to": to}

def query_database(query: str) -> Dict[str, Any]:
    """Query database (mock implementation)."""
    logger.info(f"Executing query: {query}")
    # Real implementation would use database connection
    return {"rows": [], "count": 0}

def call_api(endpoint: str, method: str = "GET", data: Dict = None) -> Dict[str, Any]:
    """Call external API."""
    logger.info(f"{method} {endpoint}")
    # Real implementation would use requests
    return {"status": 200, "data": {}}

# Create tool definitions
custom_tools = [
    Tool(
        name="send_email",
        description="Send email message",
        parameters=[
            ToolParameter(
                name="to",
                type="string",
                required=True,
                description="Recipient email address"
            ),
            ToolParameter(
                name="subject",
                type="string",
                required=True,
                description="Email subject"
            ),
            ToolParameter(
                name="body",
                type="string",
                required=True,
                description="Email body content"
            )
        ],
        executor=send_email,
        danger_level="MODERATE"
    ),
    Tool(
        name="query_database",
        description="Execute SQL query on database",
        parameters=[
            ToolParameter(
                name="query",
                type="string",
                required=True,
                description="SQL query to execute"
            )
        ],
        executor=query_database,
        danger_level="DANGEROUS"  # Requires approval
    ),
    Tool(
        name="call_api",
        description="Call external API endpoint",
        parameters=[
            ToolParameter(
                name="endpoint",
                type="string",
                required=True,
                description="API endpoint URL"
            ),
            ToolParameter(
                name="method",
                type="string",
                required=False,
                description="HTTP method (GET, POST, etc.)"
            ),
            ToolParameter(
                name="data",
                type="object",
                required=False,
                description="Request body data"
            )
        ],
        executor=call_api,
        danger_level="MODERATE"
    )
]
```

### Step 2: Create Agent with Custom Tools

```python
class CustomToolAgent(BaseAutonomousAgent):
    """Agent with custom tool integration."""

    def __init__(self, config, signature, tool_registry, **kwargs):
        super().__init__(config, signature, tool_registry, **kwargs)

        # Track tool usage
        self.tool_usage: Dict[str, int] = {}

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute with tool usage tracking."""
        result = await super().execute_autonomously(task)

        # Add tool usage stats
        result["tool_usage"] = self.tool_usage

        return result

    def _track_tool_call(self, tool_name: str) -> None:
        """Track tool call for statistics."""
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1
```

### Step 3: Use the Agent

```python
async def main():
    """Example usage with custom tools."""
    # Setup registry with custom tools

    # 12 builtin tools enabled via MCP
    for tool in custom_tools:
        registry.register(tool)

    # Create agent
    config = AutonomousConfig(max_cycles=20)
    agent = CustomToolAgent(
        config,
        Signature(),  # Define appropriate signature
        registry
    )

    # Execute task using custom tools
    result = await agent.execute_autonomously(
        "Query database for user statistics, "
        "analyze results, and email summary to admin@example.com"
    )

    print(f"✅ Task complete!")
    print(f"  - Tool usage: {result['tool_usage']}")

asyncio.run(main())
```

---

## Advanced Patterns

### Pattern 1: Custom Planning

Override planning for domain-specific task decomposition:

```python
class SmartPlanningAgent(BaseAutonomousAgent):
    """Agent with custom planning logic."""

    async def _generate_plan_from_llm(self, task: str) -> List[Dict[str, Any]]:
        """Custom planning with domain knowledge."""
        # Parse task type
        task_type = self._detect_task_type(task)

        if task_type == "research":
            return self._create_research_plan(task)
        elif task_type == "analysis":
            return self._create_analysis_plan(task)
        elif task_type == "implementation":
            return self._create_implementation_plan(task)
        else:
            return await super()._generate_plan_from_llm(task)

    def _create_research_plan(self, task: str) -> List[Dict]:
        """Create research-specific plan."""
        return [
            {"task": "Identify research questions", "priority": "high"},
            {"task": "Search for sources", "priority": "high"},
            {"task": "Analyze sources", "priority": "high"},
            {"task": "Synthesize findings", "priority": "medium"},
            {"task": "Generate report", "priority": "medium"}
        ]
```

### Pattern 2: Multi-Stage Execution

Implement multi-stage workflows:

```python
class MultiStageAgent(BaseAutonomousAgent):
    """Agent with multi-stage execution."""

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute in stages with validation."""
        stages = [
            ("analysis", self._stage_analysis),
            ("implementation", self._stage_implementation),
            ("validation", self._stage_validation)
        ]

        results = {}
        for stage_name, stage_func in stages:
            logger.info(f"Starting stage: {stage_name}")
            stage_result = await stage_func(task, results)

            if stage_result.get("error"):
                logger.error(f"Stage {stage_name} failed")
                break

            results[stage_name] = stage_result

        return results

    async def _stage_analysis(self, task: str, prev_results: Dict) -> Dict:
        """Analysis stage."""
        return await super().execute_autonomously(f"Analyze: {task}")

    async def _stage_implementation(self, task: str, prev_results: Dict) -> Dict:
        """Implementation stage."""
        analysis = prev_results.get("analysis", {})
        return await super().execute_autonomously(
            f"Implement based on analysis: {analysis.get('findings')}"
        )

    async def _stage_validation(self, task: str, prev_results: Dict) -> Dict:
        """Validation stage."""
        return await super().execute_autonomously("Validate implementation")
```

### Pattern 3: Dynamic Tool Loading

Load tools dynamically based on task:

```python
class DynamicToolAgent(BaseAutonomousAgent):
    """Agent with dynamic tool loading."""

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute with dynamic tool loading."""
        # Analyze task to determine required tools
        required_tools = self._analyze_required_tools(task)

        # Load tools dynamically
        for tool_name in required_tools:
            if not self.tool_registry.has(tool_name):
                tool = self._load_tool(tool_name)
                self.tool_registry.register(tool)
                logger.info(f"Loaded tool: {tool_name}")

        # Execute with loaded tools
        return await super().execute_autonomously(task)

    def _analyze_required_tools(self, task: str) -> List[str]:
        """Analyze task to determine required tools."""
        required = []

        if "email" in task.lower():
            required.append("send_email")
        if "database" in task.lower() or "query" in task.lower():
            required.append("query_database")
        if "api" in task.lower():
            required.append("call_api")

        return required

    def _load_tool(self, tool_name: str) -> Tool:
        """Load tool by name."""
        # Load from registry, plugin system, or create dynamically
        pass
```

---

## Testing Your Agent

### Unit Tests

```python
import pytest
from unittest.mock import Mock, patch

@pytest.mark.asyncio
async def test_research_agent_basic_execution():
    """Test ResearchAgent basic execution."""
    # Setup
    config = ResearchAgentConfig(
        llm_provider="mock",
        model="mock-model",
        max_cycles=5
    )
    signature = ResearchSignature()


    agent = ResearchAgent(config, signature, registry)

    # Execute
    result = await agent.execute_autonomously("Test research question")

    # Assert
    assert result is not None
    assert "cycles_used" in result
    assert result["cycles_used"] <= 5

@pytest.mark.asyncio
async def test_research_agent_convergence():
    """Test convergence detection."""
    config = ResearchAgentConfig(min_sources=3)
    agent = ResearchAgent(config, ResearchSignature(), ToolRegistry())

    # Test converged (no tool calls, enough sources)
    agent.sources_consulted = ["src1", "src2", "src3"]
    response = {"tool_calls": [], "confidence": 0.8}
    assert agent._check_convergence(response) is True

    # Test not converged (not enough sources)
    agent.sources_consulted = ["src1"]
    assert agent._check_convergence(response) is False

@pytest.mark.asyncio
async def test_research_agent_output_format():
    """Test output formatting."""
    config = ResearchAgentConfig(output_format="markdown")
    agent = ResearchAgent(config, ResearchSignature(), ToolRegistry())

    result = {"task": "Test", "findings": "Results", "cycles_used": 5}
    formatted = agent._format_as_markdown(result)

    assert "# Research Report" in formatted
    assert "Test" in formatted
    assert "Results" in formatted
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_research_agent_with_real_llm():
    """Integration test with real LLM."""
    config = ResearchAgentConfig(
        llm_provider="openai",
        model="gpt-3.5-turbo",
        max_cycles=10
    )


    # 12 builtin tools enabled via MCP

    agent = ResearchAgent(config, ResearchSignature(), registry)

    result = await agent.execute_autonomously(
        "What are the key features of Python 3.11?"
    )

    # Verify execution
    assert result["cycles_used"] > 0
    assert len(result.get("sources", [])) >= config.min_sources
    assert result.get("findings") is not None
```

---

## Production Deployment

### Error Handling

```python
class RobustAgent(BaseAutonomousAgent):
    """Agent with comprehensive error handling."""

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute with error handling."""
        try:
            return await super().execute_autonomously(task)
        except ToolExecutionError as e:
            logger.error(f"Tool execution failed: {e}")
            return {"error": "tool_failure", "details": str(e)}
        except ConvergenceTimeoutError as e:
            logger.error(f"Failed to converge: {e}")
            return {"error": "convergence_timeout", "details": str(e)}
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return {"error": "unknown", "details": str(e)}
```

### Monitoring

```python
class MonitoredAgent(BaseAutonomousAgent):
    """Agent with monitoring integration."""

    async def execute_autonomously(self, task: str) -> Dict[str, Any]:
        """Execute with monitoring."""
        import time
        start_time = time.time()

        try:
            result = await super().execute_autonomously(task)

            # Record metrics
            duration = time.time() - start_time
            self._record_metric("execution_duration", duration)
            self._record_metric("cycles_used", result.get("cycles_used", 0))

            return result
        except Exception as e:
            self._record_metric("execution_error", 1)
            raise

    def _record_metric(self, name: str, value: float) -> None:
        """Record metric to monitoring system."""
        # Integration with Prometheus, DataDog, etc.
        pass
```

### Rate Limiting

```python
class RateLimitedAgent(BaseAutonomousAgent):
    """Agent with rate limiting."""

    def __init__(self, *args, requests_per_minute: int = 60, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests_per_minute = requests_per_minute
        self.request_times: List[float] = []

    async def _execute_with_rate_limit(self, func, *args, **kwargs):
        """Execute with rate limiting."""
        import time

        # Clean old requests
        current_time = time.time()
        self.request_times = [
            t for t in self.request_times if current_time - t < 60
        ]

        # Check rate limit
        if len(self.request_times) >= self.requests_per_minute:
            wait_time = 60 - (current_time - self.request_times[0])
            logger.warning(f"Rate limit reached, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        # Execute and record
        result = await func(*args, **kwargs)
        self.request_times.append(time.time())

        return result
```

---

## Summary

You've learned how to build custom autonomous agents:

1. ✅ **ResearchAgent** - Web research with custom convergence
2. ✅ **DataAnalysisAgent** - Data analysis with visualizations
3. ✅ **CustomToolAgent** - Custom tool integration
4. ✅ **Advanced Patterns** - Planning, multi-stage, dynamic tools
5. ✅ **Testing** - Unit and integration tests
6. ✅ **Production** - Error handling, monitoring, rate limiting

## Next Steps

- Combine patterns for specialized agents
- Add domain-specific tools
- Integrate with production systems
- Scale with distributed execution

## References

- **[autonomous-patterns.md](../guides/autonomous-patterns.md)** - Core patterns
- **[claude-code-agent.md](../guides/claude-code-agent.md)** - ClaudeCodeAgent example
- **[codex-agent.md](../guides/codex-agent.md)** - CodexAgent example
- **`examples/autonomy/`** - Working examples

---

**Last Updated**: 2025-10-22
**Version**: 0.1.0
**Status**: Production Ready
