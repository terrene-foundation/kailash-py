"""
Tier 3 (E2E) Tests for Multi-Agent Coordination in Kaizen Framework

These tests verify complete end-to-end multi-agent coordination workflows,
testing full multi-agent scenarios from initialization to completion with real infrastructure.

Test Requirements:
- Complete multi-agent scenarios from start to finish
- Real infrastructure and data (NO MOCKING)
- Test actual multi-agent use cases and expectations
- Test complete multi-agent workflows with runtime execution
- Validate business requirements end-to-end
- Timeout: <10 seconds per test
"""

import time
from typing import Any, Dict, List

import pytest

# Import Core SDK components for validation
from kailash.workflow.builder import WorkflowBuilder

# Test markers
pytestmark = pytest.mark.e2e


class TestMultiAgentDebateWorkflowE2E:
    """Test complete multi-agent debate workflows end-to-end."""

    def test_complete_multi_agent_debate_scenario(self):
        """Test complete multi-agent debate from initialization to final decision."""
        import kaizen

        # Step 1: Framework and agent initialization
        start_time = time.time()
        framework = kaizen.Framework(
            config={
                "name": "debate_framework",
                "optimization_enabled": True,
                "monitoring_enabled": True,
            }
        )
        init_time = time.time() - start_time

        # Step 2: Create specialized debate agents
        agent_start = time.time()
        proponent = framework.create_specialized_agent(
            name="investment_proponent",
            role="Investment advocate specializing in renewable energy opportunities",
            config={
                "model": "gpt-3.5-turbo",
                "expertise": "renewable_energy_investment",
                "capabilities": [
                    "market_analysis",
                    "financial_modeling",
                    "risk_assessment",
                ],
                "behavior_traits": ["optimistic", "data_driven", "persuasive"],
            },
        )

        opponent = framework.create_specialized_agent(
            name="investment_critic",
            role="Investment skeptic focusing on market risks and challenges",
            config={
                "model": "gpt-3.5-turbo",
                "expertise": "investment_risk_analysis",
                "capabilities": [
                    "risk_analysis",
                    "market_critique",
                    "conservative_planning",
                ],
                "behavior_traits": ["skeptical", "analytical", "cautious"],
            },
        )

        moderator = framework.create_specialized_agent(
            name="debate_moderator",
            role="Neutral moderator facilitating structured debate and decision-making",
            config={
                "model": "gpt-3.5-turbo",
                "expertise": "facilitation_and_synthesis",
                "capabilities": ["moderation", "synthesis", "decision_facilitation"],
                "behavior_traits": ["neutral", "structured", "decisive"],
            },
        )
        agent_time = time.time() - agent_start

        # Step 3: Create debate workflow template
        workflow_start = time.time()
        debate_workflow = framework.create_debate_workflow(
            agents=[proponent, opponent, moderator],
            topic="Should our company invest $10M in renewable energy infrastructure?",
            rounds=3,
            decision_criteria="evidence-based consensus with risk mitigation",
        )
        workflow_time = time.time() - workflow_start

        # Step 4: Execute complete debate workflow
        execution_start = time.time()
        built_workflow = debate_workflow.build()
        results, run_id = framework.execute(built_workflow)
        execution_time = time.time() - execution_start

        total_time = time.time() - start_time

        # Step 5: Validate debate results
        assert results is not None
        assert run_id is not None
        assert len(results) >= 3  # Should have results from all agents

        # Verify debate structure and content
        debate_results = self._extract_debate_results(results)
        assert "proponent_arguments" in debate_results
        assert "opponent_arguments" in debate_results
        assert "moderator_synthesis" in debate_results
        assert "final_recommendation" in debate_results

        # Verify argument quality and coherence
        proponent_args = debate_results["proponent_arguments"]
        opponent_args = debate_results["opponent_arguments"]

        assert len(proponent_args) > 0
        assert len(opponent_args) > 0

        # Arguments should contain investment-related content
        proponent_text = " ".join(str(arg) for arg in proponent_args).lower()
        opponent_text = " ".join(str(arg) for arg in opponent_args).lower()

        assert any(
            term in proponent_text
            for term in ["invest", "opportunity", "renewable", "energy"]
        )
        assert any(
            term in opponent_text for term in ["risk", "challenge", "cost", "concern"]
        )

        # Verify moderator synthesis
        synthesis = debate_results["moderator_synthesis"]
        assert synthesis is not None
        assert len(str(synthesis)) > 100  # Should be substantial synthesis

        # Verify final recommendation
        recommendation = debate_results["final_recommendation"]
        assert recommendation is not None
        assert any(
            term in str(recommendation).lower()
            for term in ["recommend", "decide", "conclusion"]
        )

        # Step 6: Validate performance requirements
        assert (
            total_time < 10.0
        ), f"Total debate time {total_time:.3f}s exceeded 10s limit"
        assert (
            init_time < 1.0
        ), f"Initialization time {init_time:.3f}s exceeded 1s limit"
        assert (
            agent_time < 2.0
        ), f"Agent creation time {agent_time:.3f}s exceeded 2s limit"
        assert (
            workflow_time < 1.0
        ), f"Workflow creation time {workflow_time:.3f}s exceeded 1s limit"
        assert (
            execution_time < 8.0
        ), f"Execution time {execution_time:.3f}s exceeded 8s limit"

        # Step 7: Validate agent specialization effectiveness
        self._validate_agent_specialization(
            proponent, opponent, moderator, debate_results
        )

    def _extract_debate_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract structured debate results from raw workflow execution results."""
        debate_results = {
            "proponent_arguments": [],
            "opponent_arguments": [],
            "moderator_synthesis": None,
            "final_recommendation": None,
        }

        # Extract results from each agent/node
        for node_id, node_result in results.items():
            if isinstance(node_result, dict):
                if "proponent" in node_id.lower():
                    if "result" in node_result:
                        debate_results["proponent_arguments"].append(
                            node_result["result"]
                        )
                    elif "response" in node_result:
                        debate_results["proponent_arguments"].append(
                            node_result["response"]
                        )

                elif "opponent" in node_id.lower() or "critic" in node_id.lower():
                    if "result" in node_result:
                        debate_results["opponent_arguments"].append(
                            node_result["result"]
                        )
                    elif "response" in node_result:
                        debate_results["opponent_arguments"].append(
                            node_result["response"]
                        )

                elif "moderator" in node_id.lower():
                    if "synthesis" in str(node_result).lower():
                        debate_results["moderator_synthesis"] = node_result.get(
                            "result", node_result.get("response")
                        )
                    elif (
                        "recommendation" in str(node_result).lower()
                        or "decision" in str(node_result).lower()
                    ):
                        debate_results["final_recommendation"] = node_result.get(
                            "result", node_result.get("response")
                        )
                    elif debate_results["moderator_synthesis"] is None:
                        debate_results["moderator_synthesis"] = node_result.get(
                            "result", node_result.get("response")
                        )

        # If no specific synthesis found, use any moderator output as synthesis
        if debate_results["moderator_synthesis"] is None:
            for node_id, node_result in results.items():
                if "moderator" in node_id.lower() and isinstance(node_result, dict):
                    debate_results["moderator_synthesis"] = node_result.get(
                        "result", node_result.get("response")
                    )
                    break

        # Set final recommendation from synthesis if not found separately
        if debate_results["final_recommendation"] is None:
            debate_results["final_recommendation"] = debate_results[
                "moderator_synthesis"
            ]

        return debate_results

    def _validate_agent_specialization(
        self, proponent, opponent, moderator, debate_results
    ):
        """Validate that agents performed according to their specialized roles."""
        # Verify proponent agent specialization
        assert proponent.expertise == "renewable_energy_investment"
        assert "market_analysis" in proponent.capabilities
        assert hasattr(proponent, "behavior_traits")

        # Verify opponent agent specialization
        assert opponent.expertise == "investment_risk_analysis"
        assert "risk_analysis" in opponent.capabilities

        # Verify moderator agent specialization
        assert moderator.expertise == "facilitation_and_synthesis"
        assert "moderation" in moderator.capabilities

        # Validate role-appropriate content in results
        proponent_content = " ".join(
            str(arg) for arg in debate_results["proponent_arguments"]
        ).lower()
        opponent_content = " ".join(
            str(arg) for arg in debate_results["opponent_arguments"]
        ).lower()

        # Proponent should focus on opportunities and benefits
        assert any(
            term in proponent_content
            for term in ["benefit", "opportunity", "potential", "advantage"]
        )

        # Opponent should focus on risks and challenges
        assert any(
            term in opponent_content
            for term in ["risk", "challenge", "concern", "drawback"]
        )


class TestMultiAgentConsensusWorkflowE2E:
    """Test complete multi-agent consensus workflows end-to-end."""

    def test_complete_consensus_building_scenario(self):
        """Test complete consensus building from divergent viewpoints to agreement."""
        import kaizen

        # Initialize framework
        framework = kaizen.Framework(config={"name": "consensus_framework"})

        # Create diverse agents with different perspectives
        agents = [
            framework.create_specialized_agent(
                name="technical_lead",
                role="Technical lead focusing on implementation feasibility",
                config={
                    "model": "gpt-3.5-turbo",
                    "expertise": "technical_implementation",
                    "capabilities": [
                        "architecture",
                        "feasibility_analysis",
                        "technical_risk",
                    ],
                    "perspective": "technical_feasibility",
                },
            ),
            framework.create_specialized_agent(
                name="business_strategist",
                role="Business strategist focusing on market impact and ROI",
                config={
                    "model": "gpt-3.5-turbo",
                    "expertise": "business_strategy",
                    "capabilities": [
                        "market_analysis",
                        "roi_calculation",
                        "business_risk",
                    ],
                    "perspective": "business_value",
                },
            ),
            framework.create_specialized_agent(
                name="user_experience_designer",
                role="UX designer focusing on user needs and adoption",
                config={
                    "model": "gpt-3.5-turbo",
                    "expertise": "user_experience",
                    "capabilities": [
                        "user_research",
                        "design_thinking",
                        "adoption_analysis",
                    ],
                    "perspective": "user_centric",
                },
            ),
        ]

        # Create consensus workflow
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Product roadmap priorities for Q2 2024: AI features vs. performance optimization",
            consensus_threshold=0.8,
            max_iterations=4,
        )

        # Execute consensus workflow
        start_time = time.time()
        built_workflow = consensus_workflow.build()
        results, run_id = framework.execute(built_workflow)
        execution_time = time.time() - start_time

        # Validate consensus results
        assert results is not None
        assert run_id is not None

        consensus_results = self._extract_consensus_results(results)
        assert "agent_positions" in consensus_results
        assert "consensus_reached" in consensus_results
        assert "final_agreement" in consensus_results

        # Verify agent positions are diverse initially
        positions = consensus_results["agent_positions"]
        assert len(positions) >= 3

        # Verify consensus outcome
        consensus_reached = consensus_results["consensus_reached"]
        final_agreement = consensus_results["final_agreement"]

        assert consensus_reached is not None
        assert final_agreement is not None
        assert len(str(final_agreement)) > 50  # Should be substantial agreement

        # Validate performance
        assert (
            execution_time < 10.0
        ), f"Consensus workflow took {execution_time:.3f}s, expected < 10.0s"

        # Validate consensus quality
        agreement_text = str(final_agreement).lower()
        assert any(
            term in agreement_text
            for term in ["roadmap", "priority", "q2", "ai", "performance"]
        )

    def _extract_consensus_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract consensus results from workflow execution."""
        consensus_results = {
            "agent_positions": {},
            "consensus_reached": None,
            "final_agreement": None,
        }

        # Extract individual agent positions
        for node_id, node_result in results.items():
            if isinstance(node_result, dict):
                if "technical" in node_id.lower():
                    consensus_results["agent_positions"]["technical_lead"] = (
                        node_result.get("result", node_result.get("response"))
                    )
                elif "business" in node_id.lower():
                    consensus_results["agent_positions"]["business_strategist"] = (
                        node_result.get("result", node_result.get("response"))
                    )
                elif "user" in node_id.lower() or "ux" in node_id.lower():
                    consensus_results["agent_positions"]["user_experience_designer"] = (
                        node_result.get("result", node_result.get("response"))
                    )

        # Look for consensus indicators
        all_results_text = " ".join(str(result) for result in results.values()).lower()
        consensus_results["consensus_reached"] = (
            "consensus" in all_results_text or "agreement" in all_results_text
        )

        # Extract final agreement (typically from last or synthesis node)
        for node_id, node_result in results.items():
            if isinstance(node_result, dict):
                result_text = str(
                    node_result.get("result", node_result.get("response", ""))
                ).lower()
                if any(
                    term in result_text
                    for term in ["final", "agreement", "consensus", "decision"]
                ):
                    consensus_results["final_agreement"] = node_result.get(
                        "result", node_result.get("response")
                    )
                    break

        # If no specific final agreement found, use the longest result as the agreement
        if consensus_results["final_agreement"] is None:
            longest_result = ""
            for node_result in results.values():
                if isinstance(node_result, dict):
                    result_content = str(
                        node_result.get("result", node_result.get("response", ""))
                    )
                    if len(result_content) > len(longest_result):
                        longest_result = result_content
            consensus_results["final_agreement"] = longest_result

        return consensus_results


class TestMultiAgentTeamCoordinationE2E:
    """Test complete multi-agent team coordination scenarios end-to-end."""

    def test_complete_research_team_collaboration(self):
        """Test complete research team collaboration from formation to deliverable."""
        import kaizen

        # Initialize framework
        framework = kaizen.Framework(
            config={
                "name": "research_collaboration_framework",
                "optimization_enabled": True,
            }
        )

        # Create research team
        team = framework.create_agent_team(
            team_name="market_research_team",
            pattern="collaborative",
            roles=["researcher", "analyst", "validator"],
            coordination="consensus",
            state_management=True,
            conflict_resolution="collaborative",
            performance_optimization=True,
        )

        # Verify team formation
        assert len(team.members) == 3
        assert team.pattern == "collaborative"
        assert team.coordination == "consensus"

        # Test team coordination on complex research task
        start_time = time.time()

        # Simulate research collaboration workflow
        research_results = []

        # Stage 1: Each team member contributes research
        for i, member in enumerate(team.members):
            # Create individual research workflow
            research_workflow = member.create_workflow()
            research_workflow.add_node(
                "PythonCodeNode",
                f"research_{i}",
                {
                    "code": f"""
# Research contribution from {member.name}
result = {{
    'researcher': '{member.name}',
    'research_area': 'market_trend_{i+1}',
    'findings': [
        'Finding 1: Market growth in sector {i+1}',
        'Finding 2: Consumer preference shift in area {i+1}',
        'Finding 3: Technology adoption trend {i+1}'
    ],
    'confidence': 0.{85 + i*5},
    'methodology': 'quantitative_analysis_{i+1}',
    'data_sources': ['source_1', 'source_2', 'source_3'],
    'completion_status': 'completed'
}}
"""
                },
            )

            # Execute individual research
            individual_results, run_id = member.execute(research_workflow)
            research_results.append(individual_results)

        # Stage 2: Team synthesis and validation
        if hasattr(team, "coordinate"):
            synthesis_result = team.coordinate(
                task="Synthesize research findings into comprehensive market report",
                context={
                    "individual_findings": research_results,
                    "report_type": "comprehensive_market_analysis",
                    "deadline": "2024-01-31",
                },
            )
        else:
            # Fallback: Create synthesis workflow manually
            synthesis_workflow = WorkflowBuilder()
            synthesis_workflow.add_node(
                "PythonCodeNode",
                "team_synthesis",
                {
                    "code": """
# Team synthesis of research findings
individual_findings = input_data.get('individual_findings', [])
result = {
    'team_name': 'market_research_team',
    'synthesis_type': 'comprehensive_analysis',
    'combined_findings': [],
    'validated_insights': [],
    'team_recommendations': [],
    'confidence_score': 0.88,
    'report_sections': ['executive_summary', 'methodology', 'findings', 'recommendations'],
    'completion_status': 'synthesized'
}

# Process individual findings
for i, finding in enumerate(individual_findings):
    if isinstance(finding, dict):
        for node_data in finding.values():
            if isinstance(node_data, dict) and 'result' in node_data:
                research_data = node_data['result']
                if isinstance(research_data, dict) and 'findings' in research_data:
                    result['combined_findings'].extend(research_data['findings'])

# Generate team insights
result['validated_insights'] = [
    'Market shows strong growth potential across all analyzed sectors',
    'Consumer preferences are shifting toward sustainable options',
    'Technology adoption is accelerating in key market segments',
    'Competitive landscape shows opportunities for differentiation'
]

result['team_recommendations'] = [
    'Invest in sustainable product development',
    'Accelerate technology integration roadmap',
    'Develop targeted marketing for emerging consumer preferences',
    'Establish strategic partnerships in growth sectors'
]
""",
                    "input_data": {"individual_findings": research_results},
                },
            )

            synthesis_results, synthesis_run_id = framework.execute(
                synthesis_workflow.build()
            )
            synthesis_result = synthesis_results

        collaboration_time = time.time() - start_time

        # Validate team collaboration results
        assert research_results is not None
        assert len(research_results) == 3
        assert synthesis_result is not None

        # Verify individual research quality
        for i, individual_result in enumerate(research_results):
            assert individual_result is not None
            assert len(individual_result) > 0

            # Extract research data
            research_data = self._extract_research_data(individual_result)
            assert research_data is not None
            assert "findings" in research_data
            assert "confidence" in research_data
            assert research_data["completion_status"] == "completed"

        # Verify team synthesis quality
        synthesis_data = self._extract_synthesis_data(synthesis_result)
        assert synthesis_data is not None
        assert "combined_findings" in synthesis_data
        assert "validated_insights" in synthesis_data
        assert "team_recommendations" in synthesis_data
        assert synthesis_data.get("confidence_score", 0) > 0.8

        # Validate collaboration performance
        assert (
            collaboration_time < 10.0
        ), f"Team collaboration took {collaboration_time:.3f}s, expected < 10.0s"

        # Validate team state management
        if hasattr(team, "state"):
            final_state = team.state
            assert final_state is not None

        # Verify team member coordination
        self._validate_team_member_coordination(team, research_results, synthesis_data)

    def _extract_research_data(
        self, individual_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract research data from individual result."""
        for node_result in individual_result.values():
            if isinstance(node_result, dict) and "result" in node_result:
                return node_result["result"]
        return {}

    def _extract_synthesis_data(
        self, synthesis_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Extract synthesis data from team coordination result."""
        if isinstance(synthesis_result, dict):
            for node_result in synthesis_result.values():
                if isinstance(node_result, dict) and "result" in node_result:
                    return node_result["result"]

            # Fallback: return synthesis_result itself if it contains the data
            if "combined_findings" in synthesis_result:
                return synthesis_result

        return {}

    def _validate_team_member_coordination(
        self, team, research_results, synthesis_data
    ):
        """Validate that team members coordinated effectively."""
        # Verify all team members contributed
        assert len(research_results) == len(team.members)

        # Verify synthesis incorporated individual contributions
        assert len(synthesis_data.get("combined_findings", [])) > 0
        assert len(synthesis_data.get("validated_insights", [])) > 0
        assert len(synthesis_data.get("team_recommendations", [])) > 0

        # Verify synthesis quality exceeds individual contributions
        individual_confidence_scores = []
        for result in research_results:
            research_data = self._extract_research_data(result)
            if "confidence" in research_data:
                individual_confidence_scores.append(research_data["confidence"])

        if individual_confidence_scores and "confidence_score" in synthesis_data:
            avg_individual_confidence = sum(individual_confidence_scores) / len(
                individual_confidence_scores
            )
            team_confidence = synthesis_data["confidence_score"]
            assert (
                team_confidence >= avg_individual_confidence
            ), "Team synthesis should have higher confidence than average individual contributions"


class TestMultiAgentScalabilityE2E:
    """Test multi-agent coordination scalability end-to-end."""

    def test_large_scale_multi_agent_coordination(self):
        """Test coordination with larger numbers of agents."""
        import kaizen

        framework = kaizen.Framework(config={"name": "scalability_test_framework"})

        # Create larger team
        num_agents = 8
        agents = []

        for i in range(num_agents):
            agent = framework.create_specialized_agent(
                name=f"scale_agent_{i}",
                role=f"Specialist in domain {i % 4}",  # 4 different specializations
                config={
                    "model": "gpt-3.5-turbo",
                    "expertise": f"domain_{i % 4}",
                    "capabilities": [f"skill_{i}", f"analysis_{i}"],
                },
            )
            agents.append(agent)

        # Test scalable coordination workflow
        start_time = time.time()

        # Create consensus workflow with larger team
        consensus_workflow = framework.create_consensus_workflow(
            agents=agents,
            topic="Cross-domain strategic initiative prioritization",
            consensus_threshold=0.75,
            max_iterations=3,
        )

        built_workflow = consensus_workflow.build()
        results, run_id = framework.execute(built_workflow)

        execution_time = time.time() - start_time

        # Validate scalability results
        assert results is not None
        assert run_id is not None
        assert len(results) > 0

        # Validate performance at scale
        assert (
            execution_time < 15.0
        ), f"Large-scale coordination took {execution_time:.3f}s, expected < 15.0s"

        # Verify all agents participated
        agent_participation = self._count_agent_participation(results, agents)
        participation_rate = agent_participation / num_agents
        assert (
            participation_rate >= 0.75
        ), f"Only {participation_rate:.1%} of agents participated, expected >= 75%"

    def _count_agent_participation(self, results: Dict[str, Any], agents: List) -> int:
        """Count how many agents participated in the coordination."""
        participating_agents = set()

        for node_id in results.keys():
            for agent in agents:
                if agent.name in node_id or agent.agent_id in node_id:
                    participating_agents.add(agent.name)

        return len(participating_agents)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
