"""
Multi-Agent Debate for Decision Making

Implements sophisticated agent coordination for structured debates,
enabling evidence-based decision making through diverse perspectives
and adversarial reasoning.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

import dspy

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# Configure comprehensive logging for multi-agent coordination
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class DebatePhase(Enum):
    """Phases of multi-agent debate process."""

    INITIALIZATION = "initialization"
    POSITION_STATEMENTS = "position_statements"
    EVIDENCE_PRESENTATION = "evidence_presentation"
    CONSENSUS_BUILDING = "consensus_building"
    SYNTHESIS = "synthesis"


class AgentRole(Enum):
    """Roles for agents in debate system."""

    MODERATOR = "moderator"
    ADVOCATE = "advocate"
    CRITIC = "critic"
    SYNTHESIZER = "synthesizer"


@dataclass
class DebateConfig:
    """Configuration for multi-agent debate system."""

    rounds: int = 3
    time_per_round: int = 120  # seconds
    consensus_threshold: float = 0.8
    evidence_weight: float = 0.6
    stakeholder_alignment_weight: float = 0.4
    max_agents: int = 6
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.2


@dataclass
class DebateOption:
    """Represents an option being debated."""

    name: str
    description: str
    pros: List[str]
    cons: List[str]
    stakeholder_impact: Dict[str, str]


class ModeratorSignature(dspy.Signature):
    """Moderator agent for orchestrating debates."""

    topic: str = dspy.InputField(desc="Decision topic being debated")
    options: str = dspy.InputField(desc="JSON list of options being considered")
    current_phase: str = dspy.InputField(desc="Current debate phase")
    agent_inputs: str = dspy.InputField(desc="Recent agent contributions")

    moderation_action: str = dspy.OutputField(desc="Next moderation action to take")
    phase_summary: str = dspy.OutputField(desc="Summary of current phase progress")
    next_speaker: str = dspy.OutputField(desc="Which agent should speak next")
    time_guidance: str = dspy.OutputField(desc="Time management guidance")


class AdvocateSignature(dspy.Signature):
    """Advocate agent for arguing specific positions."""

    position: str = dspy.InputField(desc="Position being advocated")
    topic: str = dspy.InputField(desc="Topic being debated")
    opposing_arguments: str = dspy.InputField(desc="Arguments from other advocates")
    evidence_context: str = dspy.InputField(desc="Available evidence and data")
    debate_phase: str = dspy.InputField(desc="Current phase of debate")

    argument: str = dspy.OutputField(desc="Main argument for this position")
    evidence: str = dspy.OutputField(desc="Supporting evidence and examples")
    counter_rebuttals: str = dspy.OutputField(desc="Responses to opposing arguments")
    confidence: float = dspy.OutputField(desc="Confidence in position strength")


class CriticSignature(dspy.Signature):
    """Critic agent for challenging arguments and identifying weaknesses."""

    all_arguments: str = dspy.InputField(desc="All arguments presented so far")
    topic_context: str = dspy.InputField(desc="Context and constraints of decision")
    stakeholder_concerns: str = dspy.InputField(desc="Stakeholder requirements")

    critical_analysis: str = dspy.OutputField(desc="Critical analysis of arguments")
    identified_risks: str = dspy.OutputField(desc="Risks and weaknesses identified")
    missing_considerations: str = dspy.OutputField(
        desc="Important factors not addressed"
    )
    challenge_questions: str = dspy.OutputField(desc="Questions to strengthen debate")


class SynthesizerSignature(dspy.Signature):
    """Synthesizer agent for integrating perspectives into recommendations."""

    topic: str = dspy.InputField(desc="Decision topic")
    all_arguments: str = dspy.InputField(desc="Complete set of arguments presented")
    evidence_summary: str = dspy.InputField(desc="Summary of evidence presented")
    stakeholder_requirements: str = dspy.InputField(
        desc="Stakeholder needs and constraints"
    )

    synthesis: str = dspy.OutputField(desc="Integrated analysis of all perspectives")
    recommendation: str = dspy.OutputField(
        desc="Final recommendation with justification"
    )
    implementation_plan: str = dspy.OutputField(
        desc="High-level implementation approach"
    )
    success_criteria: str = dspy.OutputField(desc="Criteria for measuring success")
    confidence: float = dspy.OutputField(desc="Confidence in recommendation")


class MultiAgentDebateSystem:
    """
    Sophisticated multi-agent debate system for complex decision making.

    Coordinates multiple agents with different roles to explore options,
    present evidence, challenge assumptions, and reach evidence-based
    consensus on complex decisions.
    """

    def __init__(self, config: DebateConfig):
        self.config = config
        self.workflow = None
        self.runtime = None
        self.debate_state = {
            "phase": DebatePhase.INITIALIZATION,
            "round": 0,
            "arguments": [],
            "evidence": [],
            "consensus_score": 0.0,
        }
        self._initialize_workflow()

    def _initialize_workflow(self):
        """Initialize multi-agent debate workflow."""
        logger.info("Initializing multi-agent debate system")
        start_time = time.time()

        try:
            # Create workflow builder
            self.workflow = WorkflowBuilder()

            # Agent configurations
            agent_configs = {
                "moderator": {
                    "signature": ModeratorSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": 0.1,  # More deterministic for moderation
                        "max_tokens": 500,
                    },
                },
                "advocate_a": {
                    "signature": AdvocateSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": self.config.temperature,
                        "max_tokens": 600,
                    },
                },
                "advocate_b": {
                    "signature": AdvocateSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": self.config.temperature,
                        "max_tokens": 600,
                    },
                },
                "advocate_c": {
                    "signature": AdvocateSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": self.config.temperature,
                        "max_tokens": 600,
                    },
                },
                "critic": {
                    "signature": CriticSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": 0.3,  # Slightly more creative for criticism
                        "max_tokens": 700,
                    },
                },
                "synthesizer": {
                    "signature": SynthesizerSignature,
                    "llm_config": {
                        "provider": self.config.llm_provider,
                        "model": self.config.model,
                        "temperature": 0.1,  # Deterministic for synthesis
                        "max_tokens": 800,
                    },
                },
            }

            # Add all agents to workflow
            for agent_id, config in agent_configs.items():
                self.workflow.add_node("LLMAgentNode", agent_id, config)

            # Initialize runtime
            self.runtime = LocalRuntime()

            init_time = (time.time() - start_time) * 1000
            logger.info(f"Multi-agent debate system initialized in {init_time:.1f}ms")

        except Exception as e:
            logger.error(f"Failed to initialize debate system: {e}")
            raise

    async def conduct_debate(
        self,
        topic: str,
        options: List[DebateOption],
        stakeholders: List[str],
        constraints: str = "",
    ) -> Dict[str, Any]:
        """
        Conduct a comprehensive multi-agent debate.

        Args:
            topic: The decision topic to debate
            options: List of options being considered
            stakeholders: Stakeholder groups to consider
            constraints: Additional constraints or requirements

        Returns:
            Complete debate results with recommendation
        """
        start_time = time.time()
        logger.info(f"Starting multi-agent debate: {topic}")

        try:
            # Initialize debate
            debate_context = await self._initialize_debate(
                topic, options, stakeholders, constraints
            )

            # Phase 1: Position Statements
            round1_results = await self._conduct_round(
                1, DebatePhase.POSITION_STATEMENTS, debate_context
            )

            # Phase 2: Evidence and Rebuttals
            round2_results = await self._conduct_round(
                2, DebatePhase.EVIDENCE_PRESENTATION, debate_context, round1_results
            )

            # Phase 3: Consensus Building
            round3_results = await self._conduct_round(
                3,
                DebatePhase.CONSENSUS_BUILDING,
                debate_context,
                round1_results + round2_results,
            )

            # Final Synthesis
            final_recommendation = await self._synthesize_decision(
                debate_context, round1_results + round2_results + round3_results
            )

            # Calculate execution metrics
            execution_time = (time.time() - start_time) * 1000

            result = {
                "recommendation": final_recommendation["recommendation"],
                "confidence": final_recommendation["confidence"],
                "implementation_plan": final_recommendation["implementation_plan"],
                "success_criteria": final_recommendation["success_criteria"],
                "debate_summary": {
                    "topic": topic,
                    "options_considered": len(options),
                    "rounds_completed": 3,
                    "total_arguments": len(
                        round1_results + round2_results + round3_results
                    ),
                    "consensus_score": self.debate_state["consensus_score"],
                },
                "complete_transcript": {
                    "round_1": round1_results,
                    "round_2": round2_results,
                    "round_3": round3_results,
                    "synthesis": final_recommendation["synthesis"],
                },
                "metadata": {
                    "execution_time_ms": round(execution_time, 1),
                    "agents_participated": 6,
                    "stakeholders_considered": len(stakeholders),
                    "timestamp": time.time(),
                },
            }

            logger.info(
                f"Debate completed in {execution_time:.1f}ms with confidence {final_recommendation['confidence']:.2f}"
            )
            return result

        except Exception as e:
            logger.error(f"Error during debate: {e}")
            return self._error_response(str(e), topic)

    async def _initialize_debate(
        self,
        topic: str,
        options: List[DebateOption],
        stakeholders: List[str],
        constraints: str,
    ) -> Dict[str, Any]:
        """Initialize debate context and structure."""
        logger.info("Initializing debate structure")

        context = {
            "topic": topic,
            "options": [
                {"name": opt.name, "description": opt.description} for opt in options
            ],
            "stakeholders": stakeholders,
            "constraints": constraints,
            "evidence_base": {},
            "argument_history": [],
        }

        # Assign positions to advocates
        if len(options) >= 3:
            context["advocate_assignments"] = {
                "advocate_a": options[0].name,
                "advocate_b": options[1].name,
                "advocate_c": (
                    options[2].name if len(options) > 2 else "alternative_approach"
                ),
            }
        else:
            # Handle fewer options case
            context["advocate_assignments"] = {
                "advocate_a": options[0].name,
                "advocate_b": options[1].name if len(options) > 1 else "status_quo",
                "advocate_c": "hybrid_approach",
            }

        logger.info(
            f"Debate structure initialized: {len(options)} options, {len(stakeholders)} stakeholders"
        )
        return context

    async def _conduct_round(
        self,
        round_num: int,
        phase: DebatePhase,
        context: Dict[str, Any],
        previous_results: List[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """Conduct a single round of the debate."""
        logger.info(f"Starting Round {round_num}: {phase.value}")

        round_results = []
        previous_arguments = self._format_previous_arguments(previous_results or [])

        # Moderate the round
        moderation = await self._moderate_round(
            round_num, phase, context, previous_arguments
        )
        round_results.append(
            {
                "agent": "moderator",
                "type": "moderation",
                "content": moderation,
                "timestamp": time.time(),
            }
        )

        # Get advocate arguments
        for advocate_id, position in context["advocate_assignments"].items():
            argument = await self._get_advocate_argument(
                advocate_id, position, context, previous_arguments, phase
            )
            round_results.append(
                {
                    "agent": advocate_id,
                    "type": "argument",
                    "position": position,
                    "content": argument,
                    "timestamp": time.time(),
                }
            )

        # Get critic analysis
        critic_analysis = await self._get_critic_analysis(context, round_results)
        round_results.append(
            {
                "agent": "critic",
                "type": "analysis",
                "content": critic_analysis,
                "timestamp": time.time(),
            }
        )

        logger.info(
            f"Round {round_num} completed with {len(round_results)} contributions"
        )
        return round_results

    async def _moderate_round(
        self,
        round_num: int,
        phase: DebatePhase,
        context: Dict[str, Any],
        previous_arguments: str,
    ) -> Dict[str, Any]:
        """Moderate a debate round."""
        workflow_input = {
            "moderator": {
                "topic": context["topic"],
                "options": str(context["options"]),
                "current_phase": phase.value,
                "agent_inputs": previous_arguments,
            }
        }

        results, run_id = self.runtime.execute(self.workflow.build(), workflow_input)
        return results["moderator"]

    async def _get_advocate_argument(
        self,
        advocate_id: str,
        position: str,
        context: Dict[str, Any],
        previous_arguments: str,
        phase: DebatePhase,
    ) -> Dict[str, Any]:
        """Get argument from specific advocate agent."""
        workflow_input = {
            advocate_id: {
                "position": position,
                "topic": context["topic"],
                "opposing_arguments": previous_arguments,
                "evidence_context": str(context.get("evidence_base", {})),
                "debate_phase": phase.value,
            }
        }

        results, run_id = self.runtime.execute(self.workflow.build(), workflow_input)
        return results[advocate_id]

    async def _get_critic_analysis(
        self, context: Dict[str, Any], round_results: List[Dict]
    ) -> Dict[str, Any]:
        """Get critical analysis from critic agent."""
        all_arguments = self._format_round_results(round_results)

        workflow_input = {
            "critic": {
                "all_arguments": all_arguments,
                "topic_context": f"Topic: {context['topic']}, Constraints: {context.get('constraints', '')}",
                "stakeholder_concerns": str(context["stakeholders"]),
            }
        }

        results, run_id = self.runtime.execute(self.workflow.build(), workflow_input)
        return results["critic"]

    async def _synthesize_decision(
        self, context: Dict[str, Any], all_results: List[Dict]
    ) -> Dict[str, Any]:
        """Generate final synthesis and recommendation."""
        logger.info("Synthesizing final recommendation")

        all_arguments = self._format_round_results(all_results)
        evidence_summary = self._extract_evidence_summary(all_results)

        workflow_input = {
            "synthesizer": {
                "topic": context["topic"],
                "all_arguments": all_arguments,
                "evidence_summary": evidence_summary,
                "stakeholder_requirements": str(context["stakeholders"]),
            }
        }

        results, run_id = self.runtime.execute(self.workflow.build(), workflow_input)
        return results["synthesizer"]

    def _format_previous_arguments(self, results: List[Dict]) -> str:
        """Format previous arguments for context."""
        if not results:
            return "No previous arguments."

        formatted = []
        for result in results[-10:]:  # Last 10 to avoid context overflow
            if result["type"] == "argument":
                formatted.append(
                    f"{result['agent']} ({result['position']}): {result['content'].get('argument', '')}"
                )
            elif result["type"] == "analysis":
                formatted.append(
                    f"Critic: {result['content'].get('critical_analysis', '')}"
                )

        return "\n\n".join(formatted)

    def _format_round_results(self, results: List[Dict]) -> str:
        """Format round results for processing."""
        formatted = []
        for result in results:
            if result["type"] == "argument":
                content = result["content"]
                formatted.append(
                    f"Position: {result['position']}\n"
                    f"Argument: {content.get('argument', '')}\n"
                    f"Evidence: {content.get('evidence', '')}\n"
                    f"Confidence: {content.get('confidence', 0.0)}"
                )
            elif result["type"] == "analysis":
                content = result["content"]
                formatted.append(
                    f"Critical Analysis: {content.get('critical_analysis', '')}\n"
                    f"Risks: {content.get('identified_risks', '')}\n"
                    f"Missing: {content.get('missing_considerations', '')}"
                )

        return "\n\n---\n\n".join(formatted)

    def _extract_evidence_summary(self, results: List[Dict]) -> str:
        """Extract and summarize evidence presented."""
        evidence_items = []
        for result in results:
            if result["type"] == "argument" and "evidence" in result["content"]:
                evidence_items.append(result["content"]["evidence"])

        return "\n".join(evidence_items)

    def _error_response(self, error_message: str, topic: str) -> Dict[str, Any]:
        """Generate error response for failed debates."""
        return {
            "recommendation": f"Unable to complete debate on '{topic}' due to error: {error_message}",
            "confidence": 0.0,
            "implementation_plan": "Review error and retry debate process",
            "success_criteria": "Successful completion of debate process",
            "metadata": {"error": error_message, "timestamp": time.time()},
        }


async def main():
    """Example usage of multi-agent debate system."""
    # Configure debate system
    config = DebateConfig(
        rounds=3, consensus_threshold=0.8, model="gpt-4", temperature=0.2
    )

    # Initialize debate system
    debate_system = MultiAgentDebateSystem(config)

    # Define decision options
    options = [
        DebateOption(
            name="Microservices Architecture",
            description="Decompose application into small, independent services",
            pros=["Scalability", "Team autonomy", "Technology diversity"],
            cons=["Complexity", "Network latency", "Data consistency"],
            stakeholder_impact={
                "dev": "higher_complexity",
                "ops": "more_monitoring",
                "business": "faster_features",
            },
        ),
        DebateOption(
            name="Monolithic Architecture",
            description="Single deployable unit with all functionality",
            pros=["Simplicity", "Performance", "Easier debugging"],
            cons=["Scaling limitations", "Team coordination", "Technology lock-in"],
            stakeholder_impact={
                "dev": "easier_development",
                "ops": "simpler_deployment",
                "business": "faster_initial_delivery",
            },
        ),
        DebateOption(
            name="Hybrid Approach",
            description="Start monolith, extract services gradually",
            pros=["Risk mitigation", "Evolutionary approach", "Learning path"],
            cons=["Transition complexity", "Dual paradigms", "Unclear boundaries"],
            stakeholder_impact={
                "dev": "gradual_learning",
                "ops": "phased_complexity",
                "business": "balanced_risk",
            },
        ),
    ]

    stakeholders = [
        "Development Team",
        "Operations Team",
        "Business Team",
        "Security Team",
    ]
    constraints = (
        "6-month delivery timeline, team of 12 developers, cloud-native deployment"
    )

    print("=== Multi-Agent Debate for Architecture Decision ===\n")

    # Conduct debate
    result = await debate_system.conduct_debate(
        topic="Choose optimal architecture for new e-commerce platform",
        options=options,
        stakeholders=stakeholders,
        constraints=constraints,
    )

    print("Topic: Choose optimal architecture for new e-commerce platform")
    print(f"Options Considered: {result['debate_summary']['options_considered']}")
    print(f"Rounds Completed: {result['debate_summary']['rounds_completed']}")
    print(f"Consensus Score: {result['debate_summary']['consensus_score']:.2f}")
    print("-" * 80)
    print(f"RECOMMENDATION: {result['recommendation']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Implementation Plan: {result['implementation_plan']}")
    print(f"Success Criteria: {result['success_criteria']}")
    print(f"Execution Time: {result['metadata']['execution_time_ms']}ms")


if __name__ == "__main__":
    asyncio.run(main())
