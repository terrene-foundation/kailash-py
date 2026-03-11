"""
Multi-Agent Debate for Decision Making - Using Kaizen Framework

Demonstrates sophisticated multi-agent coordination using Kaizen's DebateWorkflow,
replacing direct Core SDK usage with Kaizen's high-level abstractions.

**Kaizen Advantages Demonstrated**:
- Layer 1 (Simple): Single-line debate workflow creation
- Multi-agent coordination without manual workflow construction
- Auto-detection of LLM providers (gpt-5-nano or Ollama)
- Enterprise features built-in (audit trails, monitoring)
- Structured debate results automatically extracted

Performance Targets:
- Framework initialization: <100ms
- Agent team creation: <500ms
- Debate execution: <10s for 3 rounds
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

# Kaizen Framework imports
import kaizen
from kaizen.config import ConfigurationError, get_default_model_config
from kaizen.workflows import DebateWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class DebateConfig:
    """Configuration for multi-agent debate system."""

    rounds: int = 3
    temperature: float = 0.2  # Low temperature for structured debate
    max_tokens: int = 600
    timeout: int = 120
    consensus_threshold: float = 0.8
    provider_config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateOption:
    """Represents an option being debated."""

    name: str
    description: str
    pros: List[str]
    cons: List[str]
    stakeholder_impact: Dict[str, str]


class KaizenDebateSystem:
    """
    Multi-Agent Debate System using Kaizen Framework.

    Demonstrates Kaizen's multi-agent coordination advantages:
    - No manual workflow construction (Kaizen handles it)
    - No direct dspy usage (Kaizen signatures)
    - Provider auto-detection
    - Enterprise features built-in
    """

    def __init__(self, config: DebateConfig):
        self.config = config
        self.kaizen_framework = None
        self.agents = {}
        self._initialize_framework()

    def _initialize_framework(self):
        """Initialize Kaizen framework with provider auto-detection."""
        logger.info("Initializing Kaizen debate system")
        start_time = time.time()

        try:
            # Auto-detect provider
            if not self.config.provider_config:
                try:
                    logger.info("Auto-detecting LLM provider...")
                    self.config.provider_config = get_default_model_config()
                    logger.info(
                        f"Using provider: {self.config.provider_config['provider']} "
                        f"with model: {self.config.provider_config['model']}"
                    )
                except ConfigurationError as e:
                    logger.error(f"Provider auto-detection failed: {e}")
                    raise RuntimeError(
                        f"Failed to configure LLM provider: {e}\n\n"
                        "Please ensure either:\n"
                        "  1. OPENAI_API_KEY is set for OpenAI (gpt-5-nano), or\n"
                        "  2. Ollama is installed and running for local models"
                    )

            # Initialize Kaizen framework with multi-agent support
            framework_config = kaizen.KaizenConfig(
                signature_programming_enabled=True,
                multi_agent_enabled=True,  # Enable multi-agent coordination
                monitoring_enabled=True,
                audit_trail_enabled=True,
            )

            self.kaizen_framework = kaizen.Kaizen(config=framework_config)

            init_time = (time.time() - start_time) * 1000
            logger.info(f"Kaizen framework initialized in {init_time:.1f}ms")

        except Exception as e:
            logger.error(f"Failed to initialize Kaizen framework: {e}")
            raise

    def create_debate_team(
        self, topic: str, options: List[DebateOption], stakeholders: List[str]
    ) -> DebateWorkflow:
        """
        Create multi-agent debate team using Kaizen.

        This demonstrates Layer 1 (Simple) Kaizen usage:
        - Single method call to create entire debate team
        - No manual workflow construction
        - Automatic agent coordination setup

        Args:
            topic: The decision topic
            options: List of options being considered
            stakeholders: Stakeholder groups to consider

        Returns:
            DebateWorkflow ready for execution
        """
        logger.info(f"Creating debate team for: {topic}")
        team_start = time.time()

        # Create agent configurations for different roles
        agent_configs = []

        # Moderator agent
        moderator_config = self.config.provider_config.copy()
        moderator_config.update(
            {
                "temperature": 0.1,  # Very structured for moderation
                "max_tokens": 500,
                "stance": "neutral",
            }
        )
        moderator = self.kaizen_framework.create_agent(
            "moderator", config=moderator_config
        )
        moderator.role = "Moderator"
        agent_configs.append(moderator)

        # Create advocate agents for each option
        for i, option in enumerate(options[:3]):  # Limit to 3 advocates
            advocate_config = self.config.provider_config.copy()
            advocate_config.update(
                {
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
                    "stance": (
                        "supporting" if i == 0 else "opposing" if i == 1 else "neutral"
                    ),
                }
            )
            advocate = self.kaizen_framework.create_agent(
                f"advocate_{chr(97 + i)}",  # advocate_a, advocate_b, advocate_c
                config=advocate_config,
            )
            advocate.role = f"Advocate for {option.name}"
            agent_configs.append(advocate)

        # Critic agent
        critic_config = self.config.provider_config.copy()
        critic_config.update(
            {"temperature": 0.3, "max_tokens": 700, "stance": "critical_analysis"}
        )
        critic = self.kaizen_framework.create_agent("critic", config=critic_config)
        critic.role = "Critic"
        agent_configs.append(critic)

        # Synthesizer agent
        synthesizer_config = self.config.provider_config.copy()
        synthesizer_config.update(
            {"temperature": 0.1, "max_tokens": 800, "stance": "neutral"}
        )
        synthesizer = self.kaizen_framework.create_agent(
            "synthesizer", config=synthesizer_config
        )
        synthesizer.role = "Synthesizer"
        agent_configs.append(synthesizer)

        # Create DebateWorkflow using Kaizen's built-in workflow
        debate_workflow = DebateWorkflow(
            agents=agent_configs,
            topic=topic,
            rounds=self.config.rounds,
            decision_criteria="evidence-based consensus with stakeholder alignment",
            kaizen_instance=self.kaizen_framework,
        )

        team_time = (time.time() - team_start) * 1000
        logger.info(
            f"Debate team created in {team_time:.1f}ms ({len(agent_configs)} agents)"
        )

        return debate_workflow

    def conduct_debate(
        self,
        topic: str,
        options: List[DebateOption],
        stakeholders: List[str],
        constraints: str = "",
    ) -> Dict[str, Any]:
        """
        Conduct a multi-agent debate using Kaizen's DebateWorkflow.

        This demonstrates Kaizen's value proposition:
        - No manual workflow construction
        - No direct Core SDK usage
        - Automatic coordination and result extraction

        Args:
            topic: The decision topic
            options: List of options to debate
            stakeholders: Stakeholder groups
            constraints: Additional constraints

        Returns:
            Structured debate results
        """
        start_time = time.time()
        logger.info(f"Starting debate: {topic}")

        try:
            # Create debate team (Layer 1: Simple)
            debate_workflow = self.create_debate_team(topic, options, stakeholders)

            # Execute debate (Kaizen handles all coordination)
            logger.info("Executing multi-agent debate...")
            results = debate_workflow.execute()

            execution_time = (time.time() - start_time) * 1000

            # Structure final response
            return {
                "topic": topic,
                "recommendation": results.get("final_decision", "No consensus reached"),
                "confidence": results.get("consensus_level", 0.0),
                "debate_rounds": results.get("debate_rounds", []),
                "options_considered": len(options),
                "stakeholders_considered": len(stakeholders),
                "constraints": constraints,
                "metadata": {
                    "execution_time_ms": round(execution_time, 1),
                    "rounds_completed": results.get("rounds_completed", 0),
                    "agents_participated": results.get("participants", 0),
                    "coordination_status": results.get(
                        "coordination_status", "unknown"
                    ),
                    "framework": "kaizen",
                    "provider": self.config.provider_config.get("provider", "unknown"),
                    "model": self.config.provider_config.get("model", "unknown"),
                },
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"Debate failed: {e}", exc_info=True)
            return {
                "topic": topic,
                "recommendation": f"Debate failed: {str(e)}",
                "confidence": 0.0,
                "debate_rounds": [],
                "error": str(e),
                "metadata": {
                    "execution_time_ms": round(execution_time, 1),
                    "framework": "kaizen",
                    "status": "failed",
                },
            }


def main():
    """
    Demonstrate Kaizen's multi-agent debate capabilities.

    Shows how Kaizen simplifies multi-agent coordination compared to
    direct Core SDK or dspy usage.
    """
    print("=== Kaizen Multi-Agent Debate System ===\n")
    print("This example demonstrates Kaizen's multi-agent coordination")
    print("advantages over direct Core SDK or dspy usage:\n")
    print("  ✓ Layer 1 (Simple): Single-line debate team creation")
    print("  ✓ No manual workflow construction required")
    print("  ✓ Provider auto-detection (gpt-5-nano or Ollama)")
    print("  ✓ Enterprise features built-in (audit, monitoring)")
    print("  ✓ Structured results automatically extracted\n")

    # Initialize debate system with auto-detected provider
    try:
        config = DebateConfig(rounds=3, temperature=0.2, consensus_threshold=0.8)

        print("Initializing Kaizen debate system...")
        debate_system = KaizenDebateSystem(config)

        provider = debate_system.config.provider_config.get("provider", "unknown")
        model = debate_system.config.provider_config.get("model", "unknown")
        print(f"✓ Provider: {provider}")
        print(f"✓ Model: {model}")
        print("✓ Multi-agent coordination: enabled")
        print()

    except RuntimeError as e:
        print(f"✗ Failed to initialize: {e}")
        print("\nPlease configure an LLM provider to run this example.")
        return

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

    print("Debate Topic: Choose optimal architecture for new e-commerce platform")
    print(f"Options: {len(options)}")
    print(f"Stakeholders: {len(stakeholders)}")
    print(f"Constraints: {constraints}")
    print("-" * 70)
    print()

    # Conduct debate using Kaizen
    result = debate_system.conduct_debate(
        topic="Choose optimal architecture for new e-commerce platform",
        options=options,
        stakeholders=stakeholders,
        constraints=constraints,
    )

    # Display results
    print("DEBATE RESULTS")
    print("=" * 70)
    print(f"Topic: {result['topic']}")
    print(f"Recommendation: {result['recommendation']}")
    print(f"Confidence: {result['confidence']:.2%}")
    print(f"Options Considered: {result['options_considered']}")
    print(f"Stakeholders Considered: {result['stakeholders_considered']}")
    print()
    print(f"Debate Rounds: {len(result.get('debate_rounds', []))}")
    for round_data in result.get("debate_rounds", []):
        print(
            f"  Round {round_data.get('round', '?')}: {round_data.get('moderator_synthesis', 'Completed')[:50]}..."
        )
    print()
    print("METADATA")
    print("-" * 70)
    metadata = result.get("metadata", {})
    print(f"Framework: {metadata.get('framework', 'unknown')}")
    print(f"Provider: {metadata.get('provider', 'unknown')}")
    print(f"Model: {metadata.get('model', 'unknown')}")
    print(f"Execution Time: {metadata.get('execution_time_ms', 0):.1f}ms")
    print(f"Rounds Completed: {metadata.get('rounds_completed', 0)}")
    print(f"Agents Participated: {metadata.get('agents_participated', 0)}")
    print(f"Coordination Status: {metadata.get('coordination_status', 'unknown')}")


if __name__ == "__main__":
    main()
