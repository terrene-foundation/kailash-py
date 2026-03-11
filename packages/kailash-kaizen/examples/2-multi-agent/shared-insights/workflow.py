"""
Multi-Agent Shared Memory Collaboration Example.

This example demonstrates multi-agent collaboration using SharedMemoryPool
from Phase 2 (Week 3). Three specialized agents collaborate on a research task:

1. ResearcherAgent - Conducts research, writes findings to shared memory
2. AnalystAgent - Reads research findings, performs analysis, writes insights
3. SynthesizerAgent - Reads all insights, creates synthesis report

Key Features:
- SharedMemoryPool for agent-to-agent communication
- Attention filtering (tags, importance, segment)
- Exclude own insights (agents read only others' work)
- Statistics tracking (insight count, agent count, distributions)

Architecture:
    ResearcherAgent
         |
         v (writes findings)
    SharedMemoryPool
         |
         v (reads findings, exclude_own=True)
    AnalystAgent
         |
         v (writes analysis)
    SharedMemoryPool
         |
         v (reads all insights, exclude_own=False)
    SynthesizerAgent
         |
         v
    Final Synthesis Report

Author: Kaizen Framework Team
Created: 2025-10-02 (Phase 4, Task 4I.3)
Reference: src/kaizen/memory/shared_memory.py (Phase 2 implementation)
"""

import json
from typing import Any, Dict

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.signatures import InputField, OutputField, Signature

# Signature definitions for each agent


class ResearchSignature(Signature):
    """Signature for research agent."""

    topic: str = InputField(desc="Research topic")

    findings: str = OutputField(desc="Research findings")
    key_points: str = OutputField(desc="Key points (JSON list)", default="[]")
    confidence: float = OutputField(desc="Confidence level 0.0-1.0", default=0.8)


class AnalysisSignature(Signature):
    """Signature for analysis agent."""

    findings: str = InputField(desc="Research findings (JSON list)")
    topic: str = InputField(desc="Analysis topic")

    analysis: str = OutputField(desc="Analysis results")
    insights: str = OutputField(desc="Insights derived (JSON list)", default="[]")
    recommendations: str = OutputField(desc="Recommendations (JSON list)", default="[]")


class SynthesisSignature(Signature):
    """Signature for synthesis agent."""

    insights: str = InputField(desc="All insights (JSON list)")
    topic: str = InputField(desc="Synthesis topic")

    synthesis: str = OutputField(desc="Full synthesis")
    summary: str = OutputField(desc="Executive summary")
    conclusions: str = OutputField(desc="Conclusions (JSON list)", default="[]")


# Agent implementations


class ResearcherAgent(BaseAgent):
    """
    ResearcherAgent: Conducts research and writes findings to shared memory.

    Responsibilities:
    - Research a given topic
    - Extract key findings and points
    - Write findings to shared memory with tags

    Shared Memory Behavior:
    - Writes insights with tags: ["research", topic]
    - Importance: 0.8 (high relevance)
    - Segment: "findings"
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize ResearcherAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=ResearchSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

    def research(self, topic: str) -> Dict[str, Any]:
        """
        Research a topic and write findings to shared memory.

        Args:
            topic: Topic to research

        Returns:
            Dictionary with research results:
            - findings: Research findings text
            - key_points: List of key points
            - confidence: Confidence level (0.0-1.0)
        """
        # Execute research via base agent
        result = self.run(topic=topic, session_id=f"research_{topic}")

        # Parse key_points if it's a JSON string
        key_points = result.get("key_points", "[]")
        if isinstance(key_points, str):
            try:
                key_points = json.loads(key_points)
            except json.JSONDecodeError:
                key_points = []

        # Write insight to shared memory
        if self.shared_memory:
            insight = {
                "agent_id": self.agent_id,
                "content": result.get("findings", ""),
                "tags": ["research", topic],
                "importance": 0.8,
                "segment": "findings",
                "metadata": {
                    "topic": topic,
                    "key_points": key_points,
                    "confidence": result.get("confidence", 0.8),
                },
            }
            self.shared_memory.write_insight(insight)

        # Update result with parsed key_points
        result["key_points"] = key_points
        return result


class AnalystAgent(BaseAgent):
    """
    AnalystAgent: Analyzes research findings from shared memory.

    Responsibilities:
    - Read research findings from shared memory
    - Perform deep analysis
    - Write analysis insights to shared memory

    Shared Memory Behavior:
    - Reads insights with tags: ["research", topic]
    - Excludes own insights (exclude_own=True)
    - Writes insights with tags: ["analysis", topic]
    - Importance: 0.9 (very high relevance)
    - Segment: "analysis"
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize AnalystAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=AnalysisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

    def analyze(self, topic: str) -> Dict[str, Any]:
        """
        Read research findings and perform analysis.

        Args:
            topic: Topic to analyze

        Returns:
            Dictionary with analysis results:
            - analysis: Analysis text
            - insights: List of insights derived
            - recommendations: List of recommendations
        """
        # Read research findings from shared memory
        findings = []
        if self.shared_memory:
            findings = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=["research", topic],
                exclude_own=True,  # Don't read own insights
                limit=5,
            )

        # Execute analysis (pass findings as JSON string)
        result = self.run(
            findings=json.dumps(findings), topic=topic, session_id=f"analysis_{topic}"
        )

        # Parse insights and recommendations if they're JSON strings
        insights = result.get("insights", "[]")
        if isinstance(insights, str):
            try:
                insights = json.loads(insights)
            except json.JSONDecodeError:
                insights = []

        recommendations = result.get("recommendations", "[]")
        if isinstance(recommendations, str):
            try:
                recommendations = json.loads(recommendations)
            except json.JSONDecodeError:
                recommendations = []

        # Write analysis insights to shared memory
        if self.shared_memory:
            insight = {
                "agent_id": self.agent_id,
                "content": result.get("analysis", ""),
                "tags": ["analysis", topic],
                "importance": 0.9,
                "segment": "analysis",
                "metadata": {
                    "topic": topic,
                    "sources": len(findings),
                    "insights": insights,
                    "recommendations": recommendations,
                },
            }
            self.shared_memory.write_insight(insight)

        # Update result with parsed values
        result["insights"] = insights
        result["recommendations"] = recommendations
        return result


class SynthesizerAgent(BaseAgent):
    """
    SynthesizerAgent: Synthesizes all insights into final report.

    Responsibilities:
    - Read ALL insights from shared memory (research + analysis)
    - Create comprehensive synthesis
    - Generate final report with conclusions

    Shared Memory Behavior:
    - Reads ALL insights with topic tag
    - Includes own insights (exclude_own=False)
    - Does NOT write to shared memory (final step)
    """

    def __init__(
        self, config: BaseAgentConfig, shared_memory: SharedMemoryPool, agent_id: str
    ):
        """
        Initialize SynthesizerAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
        """
        super().__init__(
            config=config,
            signature=SynthesisSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
        )

    def synthesize(self, topic: str) -> Dict[str, Any]:
        """
        Read all insights and create synthesis.

        Args:
            topic: Topic to synthesize

        Returns:
            Dictionary with synthesis results:
            - synthesis: Full synthesis text
            - summary: Executive summary
            - conclusions: List of conclusions
        """
        # Read ALL insights related to topic
        all_insights = []
        if self.shared_memory:
            all_insights = self.shared_memory.read_relevant(
                agent_id=self.agent_id,
                tags=[topic],
                exclude_own=False,  # Include ALL agents' insights
                limit=20,
            )

        # Execute synthesis (pass insights as JSON string)
        result = self.run(
            insights=json.dumps(all_insights),
            topic=topic,
            session_id=f"synthesis_{topic}",
        )

        # Parse conclusions if it's a JSON string
        conclusions = result.get("conclusions", "[]")
        if isinstance(conclusions, str):
            try:
                conclusions = json.loads(conclusions)
            except json.JSONDecodeError:
                conclusions = []

        # Update result with parsed conclusions
        result["conclusions"] = conclusions

        # Note: Synthesizer does NOT write to shared memory (final step)

        return result


# Collaboration workflow


def research_collaboration_workflow(topic: str) -> Dict[str, Any]:
    """
    Run multi-agent research collaboration workflow.

    This workflow demonstrates SharedMemoryPool collaboration:
    1. ResearcherAgent conducts research → writes findings to pool
    2. AnalystAgent reads findings → performs analysis → writes insights to pool
    3. SynthesizerAgent reads all insights → creates synthesis report

    Args:
        topic: Research topic

    Returns:
        Dictionary containing:
        - research: Research results
        - analysis: Analysis results
        - synthesis: Synthesis results
        - stats: Shared memory statistics
    """
    # Setup shared memory pool
    shared_pool = SharedMemoryPool()
    config = BaseAgentConfig(llm_provider="mock", model="gpt-3.5-turbo")

    # Create agents
    researcher = ResearcherAgent(config, shared_pool, agent_id="researcher_1")
    analyst = AnalystAgent(config, shared_pool, agent_id="analyst_1")
    synthesizer = SynthesizerAgent(config, shared_pool, agent_id="synthesizer_1")

    print(f"\n{'='*60}")
    print(f"Multi-Agent Research Collaboration: {topic}")
    print(f"{'='*60}\n")

    # Step 1: Research phase
    print(f"Step 1: Researching '{topic}'...")
    research_result = researcher.research(topic)
    print(f"  - Findings: {research_result.get('findings', 'N/A')[:100]}...")
    print(f"  - Key points: {len(research_result.get('key_points', []))}")

    # Step 2: Analysis phase
    print("\nStep 2: Analyzing findings...")
    analysis_result = analyst.analyze(topic)
    print(f"  - Analysis: {analysis_result.get('analysis', 'N/A')[:100]}...")
    print(f"  - Insights: {len(analysis_result.get('insights', []))}")
    print(f"  - Recommendations: {len(analysis_result.get('recommendations', []))}")

    # Step 3: Synthesis phase
    print("\nStep 3: Synthesizing insights...")
    synthesis_result = synthesizer.synthesize(topic)
    print(f"  - Synthesis: {synthesis_result.get('synthesis', 'N/A')[:100]}...")
    print(f"  - Summary: {synthesis_result.get('summary', 'N/A')[:100]}...")
    print(f"  - Conclusions: {len(synthesis_result.get('conclusions', []))}")

    # Show shared memory stats
    stats = shared_pool.get_stats()
    print(f"\n{'='*60}")
    print("Shared Memory Statistics:")
    print(f"{'='*60}")
    print(f"  - Total insights: {stats['insight_count']}")
    print(f"  - Agents involved: {stats['agent_count']}")
    print(f"  - Tag distribution: {stats['tag_distribution']}")
    print(f"  - Segment distribution: {stats['segment_distribution']}")
    print(f"{'='*60}\n")

    return {
        "research": research_result,
        "analysis": analysis_result,
        "synthesis": synthesis_result,
        "stats": stats,
    }


# Main execution
if __name__ == "__main__":
    # Run example workflow
    topic = "Artificial Intelligence in Healthcare"
    result = research_collaboration_workflow(topic)

    print("\nWorkflow Complete!")
    print(f"Research findings: {result['research']}")
    print(f"Analysis insights: {result['analysis']}")
    print(f"Final synthesis: {result['synthesis']}")
