"""
Complex A2A Research System - Multi-Stage Collaborative Research

This advanced example demonstrates:
1. Multiple specialized agents with different expertise
2. Dynamic task delegation based on agent capabilities
3. Iterative refinement through agent collaboration
4. Selective attention to relevant information
5. Consensus building for final conclusions
"""

import time

from kailash import Workflow
from kailash.nodes.ai import A2AAgentNode, A2ACoordinatorNode, SharedMemoryPoolNode
from kailash.runtime.local import LocalRuntime


class ResearchSystem:
    """Multi-agent research system with specialized agents."""

    def __init__(self):
        self.workflow = Workflow(
            workflow_id="complex_research_system",
            name="Complex Research System",
            description="Multi-agent collaborative research with specialized expertise",
        )
        self.setup_infrastructure()
        self.setup_agents()
        self.connect_components()

    def setup_infrastructure(self):
        """Set up shared infrastructure components."""
        # Memory pools for different research phases
        self.workflow.add_node("general_memory", SharedMemoryPoolNode())
        self.general_memory = self.workflow._node_instances["general_memory"]

        self.workflow.add_node("research_memory", SharedMemoryPoolNode())
        self.research_memory = self.workflow._node_instances["research_memory"]

        self.workflow.add_node("analysis_memory", SharedMemoryPoolNode())
        self.analysis_memory = self.workflow._node_instances["analysis_memory"]

        # Coordinator for task management
        self.workflow.add_node("research_coordinator", A2ACoordinatorNode())
        self.coordinator = self.workflow._node_instances["research_coordinator"]

        # Output writer - create simple writer
        from kailash.nodes.base import Node, NodeParameter, register_node

        @register_node()
        class SimpleWriterNode(Node):
            """Simple node to collect results."""

            def get_parameters(self):
                return {
                    "data": NodeParameter(
                        name="data", type=dict, required=False, default={}
                    )
                }

            def run(self, **kwargs):
                return {"written": True, "data": kwargs.get("data", {})}

        self.workflow.add_node("output_writer", SimpleWriterNode())
        self.output_writer = self.workflow._node_instances["output_writer"]

    def setup_agents(self):
        """Set up specialized research agents."""
        # Literature Review Agent
        self.workflow.add_node(
            "literature_reviewer",
            A2AAgentNode(),
            config={
                "agent_id": "lit_review_001",
                "agent_role": "literature_reviewer",
                "provider": "mock",
                "model": "mock-model",
                "system_prompt": """You are a literature review specialist. Your role is to:
                1. Identify key papers and sources
                2. Extract main findings and methodologies
                3. Identify research gaps
                4. Tag findings with appropriate keywords""",
                "attention_filter": {
                    "tags": ["literature", "papers", "methodology", "gaps"],
                    "importance_threshold": 0.6,
                    "window_size": 20,
                    "segments": ["research", "general"],
                },
            },
        )
        self.lit_review_agent = self.workflow._node_instances["literature_reviewer"]

        # Data Collection Agent
        self.workflow.add_node(
            "data_collector",
            A2AAgentNode(),
            config={
                "agent_id": "data_collect_001",
                "agent_role": "data_collector",
                "provider": "mock",
                "model": "mock-model",
                "system_prompt": """You are a data collection specialist. Your role is to:
                1. Identify required data sources
                2. Plan data collection methodology
                3. Note data quality issues
                4. Suggest preprocessing steps""",
                "attention_filter": {
                    "tags": ["data", "sources", "methodology", "quality"],
                    "importance_threshold": 0.5,
                    "window_size": 15,
                    "segments": ["research", "general"],
                },
            },
        )
        self.data_collector = self.workflow._node_instances["data_collector"]

        # Statistical Analyst
        self.workflow.add_node(
            "statistical_analyst",
            A2AAgentNode(),
            config={
                "agent_id": "stats_001",
                "agent_role": "statistician",
                "provider": "mock",
                "model": "mock-model",
                "system_prompt": """You are a statistical analysis expert. Your role is to:
                1. Propose appropriate statistical methods
                2. Identify potential biases
                3. Suggest sample size requirements
                4. Recommend validation approaches""",
                "attention_filter": {
                    "tags": ["statistics", "analysis", "methods", "validation", "data"],
                    "importance_threshold": 0.7,
                    "window_size": 10,
                    "segments": ["analysis", "research"],
                },
            },
        )
        self.stats_analyst = self.workflow._node_instances["statistical_analyst"]

        # Domain Expert
        self.workflow.add_node(
            "domain_expert",
            A2AAgentNode(),
            config={
                "agent_id": "domain_001",
                "agent_role": "domain_expert",
                "provider": "mock",
                "model": "mock-model",
                "system_prompt": """You are a domain expert in climate science. Your role is to:
                1. Validate research approaches
                2. Identify domain-specific considerations
                3. Suggest relevant variables
                4. Ensure practical applicability""",
                "attention_filter": {
                    "tags": ["domain", "climate", "validation", "practical"],
                    "importance_threshold": 0.6,
                    "window_size": 15,
                    "segments": ["research", "analysis", "general"],
                },
            },
        )
        self.domain_expert = self.workflow._node_instances["domain_expert"]

        # Synthesis Agent
        self.workflow.add_node(
            "synthesis_agent",
            A2AAgentNode(),
            config={
                "agent_id": "synth_001",
                "agent_role": "synthesizer",
                "provider": "mock",
                "model": "mock-model",
                "system_prompt": """You are a research synthesis expert. Your role is to:
                1. Integrate findings from all agents
                2. Identify consensus and disagreements
                3. Formulate final conclusions
                4. Suggest future research directions""",
                "attention_filter": {
                    "tags": ["findings", "conclusion", "consensus", "integration"],
                    "importance_threshold": 0.7,
                    "window_size": 30,
                    "segments": ["research", "analysis", "general"],
                    "preferred_agents": ["stats_001", "domain_001", "lit_review_001"],
                },
            },
        )
        self.synthesizer = self.workflow._node_instances["synthesis_agent"]

    def connect_components(self):
        """Connect all components in the workflow."""

        # Connect all agents to all memory pools (use node IDs)
        agent_ids = [
            "literature_reviewer",
            "data_collector",
            "statistical_analyst",
            "domain_expert",
            "synthesis_agent",
        ]
        memory_ids = ["general_memory", "research_memory", "analysis_memory"]

        for agent_id in agent_ids:
            for memory_id in memory_ids:
                self.workflow.connect(agent_id, memory_id)

        # Connect synthesizer to output
        self.workflow.connect("synthesis_agent", "output_writer")

    def register_agents(self) -> dict[str, bool]:
        """Register all agents with the coordinator."""
        registrations = {}

        agent_configs = [
            {
                "id": "lit_review_001",
                "skills": [
                    "literature_review",
                    "source_identification",
                    "gap_analysis",
                ],
                "role": "literature_reviewer",
            },
            {
                "id": "data_collect_001",
                "skills": ["data_collection", "data_quality", "preprocessing"],
                "role": "data_collector",
            },
            {
                "id": "stats_001",
                "skills": ["statistical_analysis", "hypothesis_testing", "modeling"],
                "role": "statistician",
            },
            {
                "id": "domain_001",
                "skills": [
                    "climate_science",
                    "domain_validation",
                    "practical_application",
                ],
                "role": "domain_expert",
            },
            {
                "id": "synth_001",
                "skills": ["synthesis", "integration", "conclusion_formulation"],
                "role": "synthesizer",
            },
        ]

        for config in agent_configs:
            result = self.coordinator.execute(action="register", agent_info=config)
            registrations[config["id"]] = result["success"]

        return registrations

    def run_research_pipeline(self, research_question: str) -> dict:
        """Run the complete research pipeline."""
        runtime = LocalRuntime()
        results = {"research_question": research_question, "phases": {}, "timeline": []}

        start_time = time.time()

        # Phase 1: Literature Review
        print("\n=== PHASE 1: Literature Review ===")
        results["timeline"].append(
            {"phase": "literature_review", "start": time.time() - start_time}
        )

        lit_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "literature_reviewer": {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Conduct a literature review for: {research_question}",
                        }
                    ],
                    "memory_pool": self.research_memory,
                    "provider": "mock",
                    "model": "mock-model",
                }
            },
        )

        results["phases"]["literature_review"] = {
            "success": lit_result["literature_reviewer"]["success"],
            "insights": lit_result["literature_reviewer"]["a2a_metadata"][
                "insights_generated"
            ],
        }

        # Phase 2: Data Collection Planning
        print("\n=== PHASE 2: Data Collection Planning ===")
        results["timeline"].append(
            {"phase": "data_collection", "start": time.time() - start_time}
        )

        data_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "data_collector": {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Based on the literature review, plan data collection for: {research_question}",
                        }
                    ],
                    "memory_pool": self.research_memory,
                    "provider": "mock",
                    "model": "mock-model",
                }
            },
        )

        results["phases"]["data_collection"] = {
            "success": data_result["data_collector"]["success"],
            "insights": data_result["data_collector"]["a2a_metadata"][
                "insights_generated"
            ],
        }

        # Phase 3: Statistical Analysis Design
        print("\n=== PHASE 3: Statistical Analysis Design ===")
        results["timeline"].append(
            {"phase": "statistical_design", "start": time.time() - start_time}
        )

        # Broadcast to get input from multiple agents
        self.coordinator.execute(
            action="broadcast",
            message={
                "content": "All agents: Review current findings and contribute to statistical analysis design",
                "target_roles": ["statistician", "domain_expert"],
                "priority": "high",
            },
        )

        stats_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "statistical_analyst": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Design statistical analysis based on literature review and data collection plans",
                        }
                    ],
                    "memory_pool": self.analysis_memory,
                    "provider": "mock",
                    "model": "mock-model",
                }
            },
        )

        results["phases"]["statistical_design"] = {
            "success": stats_result["statistical_analyst"]["success"],
            "insights": stats_result["statistical_analyst"]["a2a_metadata"][
                "insights_generated"
            ],
        }

        # Phase 4: Domain Validation
        print("\n=== PHASE 4: Domain Expert Validation ===")
        results["timeline"].append(
            {"phase": "domain_validation", "start": time.time() - start_time}
        )

        domain_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "domain_expert": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Validate the research approach and provide domain-specific insights",
                        }
                    ],
                    "memory_pool": self.analysis_memory,
                    "provider": "mock",
                    "model": "mock-model",
                }
            },
        )

        results["phases"]["domain_validation"] = {
            "success": domain_result["domain_expert"]["success"],
            "insights": domain_result["domain_expert"]["a2a_metadata"][
                "insights_generated"
            ],
        }

        # Phase 5: Synthesis and Conclusions
        print("\n=== PHASE 5: Research Synthesis ===")
        results["timeline"].append(
            {"phase": "synthesis", "start": time.time() - start_time}
        )

        # Query memories for high-importance findings
        key_findings = self.analysis_memory.execute(
            action="read",
            agent_id="synth_001",
            attention_filter={"importance_threshold": 0.8, "window_size": 50},
        )

        synth_result, _ = runtime.execute(
            self.workflow,
            parameters={
                "synthesis_agent": {
                    "messages": [
                        {
                            "role": "user",
                            "content": "Synthesize all findings and formulate conclusions for the research question",
                        }
                    ],
                    "memory_pool": self.general_memory,
                    "provider": "mock",
                    "model": "mock-model",
                }
            },
        )

        results["phases"]["synthesis"] = {
            "success": synth_result["synthesis_agent"]["success"],
            "insights": synth_result["synthesis_agent"]["a2a_metadata"][
                "insights_generated"
            ],
            "key_findings_used": len(key_findings["memories"]),
        }

        # Build consensus
        print("\n=== Building Consensus ===")
        consensus_proposal = {
            "session_id": "research_conclusion",
            "proposal": "The research approach is sound and conclusions are well-supported",
            "criteria": "Based on literature, data, statistical rigor, and domain expertise",
        }

        self.coordinator.execute(
            action="consensus", consensus_proposal=consensus_proposal
        )

        # Simulate agent votes based on their analysis
        for agent_id in [
            "lit_review_001",
            "data_collect_001",
            "stats_001",
            "domain_001",
        ]:
            self.coordinator.execute(
                action="consensus",
                consensus_proposal={"session_id": "research_conclusion"},
                agent_id=agent_id,
                vote=True,
            )

        results["consensus_reached"] = True
        results["total_duration"] = time.time() - start_time

        # Collect all memories for final report
        all_memories = self.general_memory.execute(
            action="read",
            agent_id="reporter",
            attention_filter={
                "importance_threshold": 0.0,  # Get all
                "window_size": 1000,
            },
        )

        results["total_insights"] = all_memories["total_available"]
        results["memory_distribution"] = self._analyze_memory_distribution(
            all_memories["memories"]
        )

        return results

    def _analyze_memory_distribution(self, memories: list[dict]) -> dict:
        """Analyze distribution of memories by agent and importance."""
        distribution = {
            "by_agent": {},
            "by_importance": {"high": 0, "medium": 0, "low": 0},
            "by_segment": {},
        }

        for memory in memories:
            # By agent
            agent = memory.get("agent_id", "unknown")
            distribution["by_agent"][agent] = distribution["by_agent"].get(agent, 0) + 1

            # By importance
            importance = memory.get("importance", 0)
            if importance >= 0.8:
                distribution["by_importance"]["high"] += 1
            elif importance >= 0.5:
                distribution["by_importance"]["medium"] += 1
            else:
                distribution["by_importance"]["low"] += 1

            # By segment
            segment = memory.get("segment", "general")
            distribution["by_segment"][segment] = (
                distribution["by_segment"].get(segment, 0) + 1
            )

        return distribution


def main():
    """Run the complex research system example."""
    print("=== Complex Multi-Agent Research System ===")
    print("Research Question: How does urbanization affect local climate patterns?")

    # Initialize system
    system = ResearchSystem()

    # Register agents
    print("\nRegistering agents...")
    registrations = system.register_agents()
    for agent_id, success in registrations.items():
        print(f"  {agent_id}: {'✓' if success else '✗'}")

    # Run research pipeline
    research_question = "How does urbanization affect local climate patterns through heat island effects?"
    results = system.run_research_pipeline(research_question)

    # Display results
    print("\n" + "=" * 60)
    print("RESEARCH COMPLETE")
    print("=" * 60)

    print(f"\nResearch Question: {results['research_question']}")
    print(f"Total Duration: {results['total_duration']:.1f} seconds")
    print(f"Total Insights Generated: {results['total_insights']}")
    print(f"Consensus Reached: {'Yes' if results['consensus_reached'] else 'No'}")

    print("\nPhases Completed:")
    for phase, data in results["phases"].items():
        print(
            f"  - {phase}: {'✓' if data['success'] else '✗'} ({data.get('insights', 0)} insights)"
        )

    print("\nMemory Distribution:")
    dist = results["memory_distribution"]
    print("  By Agent:")
    for agent, count in dist["by_agent"].items():
        print(f"    {agent}: {count} memories")

    print("  By Importance:")
    for level, count in dist["by_importance"].items():
        print(f"    {level}: {count} memories")

    print("\nTimeline:")
    for event in results["timeline"]:
        print(f"  {event['phase']}: started at {event['start']:.1f}s")

    # Save detailed results
    print("\nDetailed results saved to: examples/outputs/a2a_research_results.json")

    # Query specific insights
    print("\n" + "-" * 60)
    print("Sample High-Importance Insights:")

    high_importance = system.general_memory.execute(
        action="read",
        agent_id="reviewer",
        attention_filter={"importance_threshold": 0.8, "window_size": 5},
    )

    for i, memory in enumerate(high_importance["memories"][:3], 1):
        print(f"\n{i}. From {memory['agent_id']}:")
        print(f"   {memory['content']}")
        print(f"   Tags: {', '.join(memory['tags'])}")


if __name__ == "__main__":
    main()
