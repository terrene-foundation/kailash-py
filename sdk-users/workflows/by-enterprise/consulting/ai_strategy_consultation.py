#!/usr/bin/env python3
"""
AI Strategy Consultation Workflow - Iterative MCP Agent Architecture

This example demonstrates the new MCP architecture with an iterative agent that can:
- Discover MCP tools and resources progressively over multiple iterations
- Plan and execute multi-step analyses
- Call tools iteratively based on findings from previous iterations
- Reflect on results and decide what to investigate next
- Use prompts and resources from MCP servers
- Converge when sufficient information is gathered

Key Features:
- AI Registry MCP Server with real AI use cases from ISO/IEC standards
- IterativeLLMAgentNode with 6-phase iterative process:
  1. DISCOVERY: Find available MCP tools and resources
  2. PLANNING: Decide what analysis to do this iteration
  3. EXECUTION: Call tools with specific parameters
  4. REFLECTION: Analyze learnings and identify gaps
  5. CONVERGENCE: Decide if more iterations are needed
  6. SYNTHESIS: Generate final comprehensive response
- Real tool calls with healthcare AI use case data
- Progressive strategy building over multiple iterations

To run this example:
1. Make sure Ollama is running with llama3.2 model
2. Run this workflow:
   python workflow_ai_strategy_consultation.py

The agent will iteratively discover and use these MCP tools:
- search_use_cases: Search AI use cases by keywords
- filter_by_domain: Get domain-specific use cases
- get_use_case_details: Get detailed use case information
- list_domains: See all available domains
And access resources like registry://stats for statistics.
"""

import os

from kailash import Workflow
from kailash.nodes.ai.iterative_llm_agent import IterativeLLMAgentNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.data import JSONWriterNode
from kailash.runtime.local import LocalRuntime

from examples.utils.data_paths import get_output_data_path


def create_ai_strategy_workflow() -> Workflow:
    """
    Create workflow with LLM agent that uses MCP capabilities.

    The agent connects to the AI Registry MCP server to:
    - Discover available tools and resources
    - Search and analyze AI use cases
    - Provide strategic recommendations
    """

    workflow = Workflow("ai-strategy", name="ai_strategy_consultation")

    # Iterative LLM Agent with embedded MCP capabilities
    workflow.add_node("strategy_consultant", IterativeLLMAgentNode())

    # Report generator - create a simple function-based node
    def generate_report(consultant_output=None, mcp_context=None):
        """Generate strategic report from consultant output."""
        consultant_output = consultant_output or {}
        mcp_context = mcp_context or {}

        # Extract response from iterative agent
        if isinstance(consultant_output, dict):
            # Check if this is an iterative agent response
            if "final_response" in consultant_output:
                response_text = consultant_output.get("final_response", "")
                iterations = consultant_output.get("iterations", [])
                convergence_reason = consultant_output.get("convergence_reason", "")
                total_iterations = consultant_output.get("total_iterations", 0)
            else:
                response_text = consultant_output.get("content", str(consultant_output))
                iterations = []
                convergence_reason = "single_shot"
                total_iterations = 1
        else:
            response_text = str(consultant_output)
            iterations = []
            convergence_reason = "single_shot"
            total_iterations = 1

        # Build comprehensive report
        report = {
            "consultation_response": response_text,
            "iterative_analysis": {
                "total_iterations": total_iterations,
                "convergence_reason": convergence_reason,
                "iterations_summary": [
                    {
                        "iteration": i.get("iteration", 0),
                        "phase": i.get("phase", ""),
                        "success": i.get("success", False),
                        "duration": i.get("duration", 0),
                    }
                    for i in iterations
                ],
            },
            "mcp_integration": {
                "tools_used": mcp_context.get("tools_available", 0),
                "resources_accessed": mcp_context.get("mcp_resources_used", 0),
                "discovery_details": mcp_context,
            },
            "timestamp": "2024-06-08 01:00:00",
        }

        return {"result": report, "report": report}

    workflow.add_node(
        "report_generator",
        PythonCodeNode.from_function(
            func=generate_report,
            name="report_generator",
            description="Generate strategic report from consultant output",
        ),
    )

    # Save results
    workflow.add_node(
        "save_report",
        JSONWriterNode(
            file_path=str(get_output_data_path("consulting/temp_report.json"))
        ),
    )

    # Connect workflow
    workflow.connect(
        "strategy_consultant",
        "report_generator",
        mapping={"final_response": "consultant_output", "discoveries": "mcp_context"},
    )
    workflow.connect("report_generator", "save_report", mapping={"report": "data"})

    return workflow


def run_with_mock_data():
    """Run the workflow with mock data when MCP server is not available."""
    print("\n" + "=" * 70)
    print("AI STRATEGY CONSULTATION - MOCK MODE")
    print("=" * 70)
    print("\nNote: Running with mock data. For full functionality:")
    print(
        "1. Start AI Registry server: python -m kailash.mcp_server.servers.ai_registry"
    )
    print("2. Run this example again")

    workflow = create_ai_strategy_workflow()
    runtime = LocalRuntime()

    # Run with mock provider
    parameters = {
        "strategy_consultant": {
            "provider": "mock",
            "model": "mock-model",
            "messages": [
                {
                    "role": "user",
                    "content": "I'm a healthcare startup looking to implement AI for patient diagnosis. What are the key opportunities and challenges?",
                }
            ],
            "system_prompt": """You are an AI strategy consultant.
            Provide strategic recommendations for AI implementation.""",
            # MCP configuration (would connect to real server if available)
            "mcp_servers": [],
            "auto_discover_tools": False,
        },
        # report_generator is now a function-based node - no parameters needed
        "save_report": {
            "file_path": str(get_output_data_path("consulting/ai_strategy_report.json"))
        },
    }

    print("\nExecuting workflow...")
    results, execution_id = runtime.execute(workflow, parameters)

    if results.get("save_report", {}).get("success"):
        print("\n✅ Strategy report generated successfully!")
        print("Report saved to: outputs/ai_strategy_report.json")

        # Display summary
        report_gen = results.get("report_generator", {})
        if "report" in report_gen:
            report = report_gen["report"]
            print("\n📊 Executive Summary:")
            print(f"   {report.get('executive_summary', 'N/A')}")
            print("\n🎯 Key Opportunities:")
            for opp in report.get("key_opportunities", []):
                print(f"   - {opp}")
    else:
        print(
            "\n❌ Workflow failed:",
            results.get("save_report", {}).get("error", "Unknown error"),
        )


def run_with_mcp_server():
    """Run the workflow with actual MCP server connection."""
    print("\n" + "=" * 70)
    print("AI STRATEGY CONSULTATION - MCP MODE")
    print("=" * 70)

    # Enable real MCP usage
    os.environ["KAILASH_USE_REAL_MCP"] = "true"

    workflow = create_ai_strategy_workflow()
    runtime = LocalRuntime()

    # Real parameters with MCP server configured for stdio transport
    parameters = {
        "strategy_consultant": {
            # LLM Configuration
            "provider": "ollama",
            "model": "llama3.2",
            "temperature": 0.7,
            "messages": [
                {
                    "role": "user",
                    "content": """I'm a healthcare startup looking to implement AI for patient diagnosis.
                Please iteratively analyze the AI registry to find relevant use cases, assess implementation complexity,
                and provide strategic recommendations. Use multiple iterations to build a comprehensive analysis.""",
                }
            ],
            "system_prompt": """You are an expert AI strategy consultant with iterative analysis capabilities.
            You have access to an MCP service containing real AI use cases from ISO/IEC standards.

ITERATIVE PROCESS:
Each iteration, you should:
1. DISCOVER: Find new tools and resources from the AI Registry
2. PLAN: Decide what specific analysis to do this iteration
3. EXECUTE: Call tools with specific parameters based on your plan
4. REFLECT: Analyze what you learned and what gaps remain
5. CONVERGE: Decide if you have enough information or need another iteration

AVAILABLE MCP CAPABILITIES:
Tools you can discover and use:
- search_use_cases(query, limit): Search AI use cases by keywords
- filter_by_domain(domain): Get use cases for specific domain like "Healthcare"
- get_use_case_details(use_case_id): Get detailed info about specific use cases
- list_domains(): See all available domains in the registry

Resources you can access:
- registry://stats: Get overall statistics about the AI registry
- registry://domains/{domain}: Get all use cases for a specific domain

STRATEGIC FOCUS:
For this healthcare startup, provide insights on:
- Relevant healthcare AI use cases and their implementation details
- Technical complexity and resource requirements
- Regulatory considerations and compliance requirements
- Success patterns and common challenges
- Step-by-step implementation recommendations
- ROI considerations and business case elements

Use multiple iterations to build a comprehensive strategic analysis.""",
            # MCP Configuration
            "mcp_servers": [
                {
                    "name": "ai-registry",
                    "transport": "stdio",
                    "command": "python",
                    "args": ["scripts/start-ai-registry-server.py"],
                }
            ],
            "auto_discover_tools": True,
            "mcp_context": ["registry://stats"],
            # Iterative Agent Configuration
            "max_iterations": 4,
            "discovery_mode": "progressive",
            "reflection_enabled": True,
            "adaptation_strategy": "dynamic",
            "convergence_criteria": {
                "goal_satisfaction": {"threshold": 0.85},
                "diminishing_returns": {"enabled": True, "min_improvement": 0.1},
            },
            "discovery_budget": {"max_servers": 3, "max_tools": 10, "max_resources": 5},
            "enable_detailed_logging": True,
        },
        # report_generator is now a function-based node - no parameters needed
        "save_report": {
            "file_path": str(
                get_output_data_path("consulting/ai_strategy_consultation_mcp.json")
            )
        },
    }

    print("\nExecuting workflow with MCP integration...")
    print("⚙️  MCP Configuration:")
    print(f"   Real MCP enabled: {os.environ.get('KAILASH_USE_REAL_MCP', 'false')}")
    print(f"   Server config: {parameters['strategy_consultant']['mcp_servers']}")
    print(
        f"   Auto-discover tools: {parameters['strategy_consultant']['auto_discover_tools']}"
    )
    print()

    try:
        results, execution_id = runtime.execute(workflow, parameters)

        if results.get("strategy_consultant", {}).get("success"):
            print("\n✅ Consultation completed successfully!")

            # Show iterative agent response
            agent_result = results["strategy_consultant"]
            final_response = agent_result.get("final_response", "No response")
            total_iterations = agent_result.get("total_iterations", 0)
            convergence_reason = agent_result.get("convergence_reason", "unknown")

            print("\n🔄 Iterative Analysis Complete:")
            print(f"   Total iterations: {total_iterations}")
            print(f"   Convergence reason: {convergence_reason}")

            print("\n📋 Final Strategic Response:")
            print("-" * 60)
            print(
                final_response[:800] + "..."
                if len(final_response) > 800
                else final_response
            )

            # Show MCP discoveries
            discoveries = agent_result.get("discoveries", {})
            tools = discoveries.get("tools", {})
            resources = discoveries.get("resources", {})

            print("\n🔧 MCP Discoveries:")
            print(f"   Tools discovered: {len(tools)}")
            print(f"   Resources accessed: {len(resources)}")

            if tools:
                print(f"   Tool names: {list(tools.keys())}")

            # Show iteration details
            iterations = agent_result.get("iterations", [])
            if iterations:
                print("\n📊 Iteration Summary:")
                for i, iteration in enumerate(iterations):
                    success = "✅" if iteration.get("success") else "❌"
                    duration = iteration.get("duration", 0)
                    phase = iteration.get("phase", "unknown")
                    print(
                        f"   Iteration {i+1}: {success} Phase: {phase} ({duration:.2f}s)"
                    )

            if results.get("save_report", {}).get("success"):
                print(
                    "\n📄 Full report saved to: outputs/ai_strategy_consultation_mcp.json"
                )
        else:
            print(
                "\n❌ Consultation failed:",
                results.get("strategy_consultant", {}).get("error", "Unknown error"),
            )

    except Exception as e:
        print(f"\n❌ Error executing workflow: {e}")
        print("\nMake sure the MCP server is running:")
        print("python -m kailash.mcp_server.servers.ai_registry --port 8080")


def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("AI STRATEGY CONSULTATION WORKFLOW")
    print("New MCP Architecture Demonstration")
    print("=" * 70)

    print("\n🚀 Running with real MCP server and Ollama...")
    print("This demonstrates the new MCP architecture with:")
    print("- AI Registry MCP server providing real AI use cases")
    print("- Ollama LLM with embedded MCP client capabilities")
    print("- Real tool calls and resource access")

    run_with_mcp_server()

    print("\n" + "=" * 70)
    print("Example completed!")
    print("\nKey Takeaways:")
    print("1. MCP servers run as independent services via stdio transport")
    print("2. LLM agents have built-in MCP client capabilities")
    print("3. No separate MCPClient nodes needed")
    print("4. Clean separation between workflow and MCP services")
    print("5. Real tools and resources accessed via MCP protocol")


if __name__ == "__main__":
    # Ensure output directory exists
    os.makedirs("outputs", exist_ok=True)
    main()
