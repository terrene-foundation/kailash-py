"""
DebatePattern - Multi-Agent Coordination Pattern

Production-ready adversarial reasoning pattern with structured debate.
Provides zero-config factory function with progressive configuration support.

Pattern Components:
- ProponentAgent: Argues FOR a position
- OpponentAgent: Argues AGAINST a position
- JudgeAgent: Evaluates arguments and makes decision
- DebatePattern: Pattern container with convenience methods

Usage:
    # Zero-config
    from kaizen.orchestration.patterns import create_debate_pattern

    pattern = create_debate_pattern()
    result = pattern.debate("Should AI be regulated?", rounds=2)
    judgment = pattern.get_judgment(result["debate_id"])

    # Progressive configuration
    pattern = create_debate_pattern(
        model="gpt-4",
        temperature=0.7,
        rounds=3
    )

Architecture:
    User Topic → ProponentAgent (argues FOR)
              → OpponentAgent (argues AGAINST)
              → SharedMemoryPool (stores arguments)
              → ProponentAgent (rebuts opponent)
              → OpponentAgent (rebuts proponent)
              → (Repeat for N rounds)
              → JudgeAgent (evaluates & decides)
              → Final Judgment

Author: Kaizen Framework Team
Created: 2025-10-04 (Phase 3, Multi-Agent Patterns)
Reference: SupervisorWorkerPattern, ConsensusPattern
"""

import json
import os
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from kaizen.tools.registry import ToolRegistry

from kaizen.core.base_agent import BaseAgent, BaseAgentConfig
from kaizen.memory.shared_memory import SharedMemoryPool
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.signatures import InputField, OutputField, Signature

# ============================================================================
# Signature Definitions
# ============================================================================


class ArgumentConstructionSignature(Signature):
    """Signature for argument construction."""

    topic: str = InputField(desc="Topic to argue about")
    position: str = InputField(desc="Position: for or against")
    context: str = InputField(desc="Additional context", default="")

    argument: str = OutputField(desc="Constructed argument")
    key_points: str = OutputField(desc="Main points (JSON list)", default="[]")
    evidence: str = OutputField(desc="Supporting evidence", default="")


class RebuttalSignature(Signature):
    """Signature for rebuttal construction."""

    opponent_argument: str = InputField(desc="Opponent's argument")
    original_position: str = InputField(desc="Position: for or against")
    topic: str = InputField(desc="Debate topic")

    rebuttal: str = OutputField(desc="Counter-argument")
    counterpoints: str = OutputField(
        desc="Specific counterpoints (JSON list)", default="[]"
    )
    strength: float = OutputField(desc="Rebuttal strength 0.0-1.0", default=0.5)


class JudgmentSignature(Signature):
    """Signature for judgment."""

    topic: str = InputField(desc="Debate topic")
    proponent_argument: str = InputField(desc="FOR argument")
    opponent_argument: str = InputField(desc="AGAINST argument")
    proponent_rebuttal: str = InputField(desc="FOR rebuttal", default="")
    opponent_rebuttal: str = InputField(desc="AGAINST rebuttal", default="")

    decision: str = OutputField(desc="Decision: for/against/tie", default="tie")
    winner: str = OutputField(desc="Winning side", default="tie")
    reasoning: str = OutputField(desc="Judgment reasoning", default="")
    confidence: float = OutputField(desc="Decision confidence 0.0-1.0", default=0.5)


# ============================================================================
# Agent Implementations
# ============================================================================


class ProponentAgent(BaseAgent):
    """
    ProponentAgent: Argues FOR a position.

    Responsibilities:
    - Construct arguments FOR the topic
    - Provide key points and evidence
    - Rebut opponent's arguments
    - Maintain FOR position throughout debate
    - Write arguments to shared memory

    Shared Memory Behavior:
    - Writes arguments with tags: ["argument", "for", debate_id]
    - Segment: "arguments"
    - Importance: 0.8
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize ProponentAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=ArgumentConstructionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.tool_registry = tool_registry

    def construct_argument(self, topic: str, context: str = "") -> Dict[str, Any]:
        """
        Build argument FOR position.

        Args:
            topic: Topic to argue about
            context: Additional context

        Returns:
            Argument dict with argument, key_points, evidence
        """
        # Generate debate ID (will be overridden by pattern)
        debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Execute argument construction via base agent
        result = self.run(
            topic=topic,
            position="for",
            context=context,
            session_id=f"construct_{self.agent_id}_{debate_id}",
        )

        # Build argument dict
        argument_data = {
            "argument": result.get("argument", ""),
            "key_points": result.get("key_points", "[]"),
            "evidence": result.get("evidence", ""),
            "position": "for",
            "topic": topic,
            "debate_id": debate_id,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(argument_data),
                    "tags": ["argument", "for", debate_id],
                    "importance": 0.8,
                    "segment": "arguments",
                    "metadata": {
                        "debate_id": debate_id,
                        "position": "for",
                        "topic": topic,
                    },
                }
            )

        return argument_data

    def rebut(self, opponent_argument: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """
        Counter opponent's argument.

        Args:
            opponent_argument: Opponent's argument dict
            topic: Debate topic

        Returns:
            Rebuttal dict with rebuttal, counterpoints, strength
        """
        # Get debate_id from opponent argument
        debate_id = opponent_argument.get("debate_id", f"debate_{uuid.uuid4().hex[:8]}")

        # Extract opponent argument text
        opponent_text = opponent_argument.get("argument", "")
        if isinstance(opponent_text, dict):
            opponent_text = json.dumps(opponent_text)

        # Switch signature temporarily
        original_signature = self.signature
        self.signature = RebuttalSignature()

        # Execute rebuttal via base agent
        result = self.run(
            opponent_argument=opponent_text,
            original_position="for",
            topic=topic,
            session_id=f"rebut_{self.agent_id}_{debate_id}",
        )

        # Switch back
        self.signature = original_signature

        # Validate strength
        strength = result.get("strength", 0.5)
        try:
            strength = float(strength)
            if strength < 0.0:
                strength = 0.0
            elif strength > 1.0:
                strength = 1.0
        except (ValueError, TypeError):
            strength = 0.5

        # Build rebuttal dict
        rebuttal_data = {
            "rebuttal": result.get("rebuttal", ""),
            "counterpoints": result.get("counterpoints", "[]"),
            "strength": strength,
            "position": "for",
            "topic": topic,
            "debate_id": debate_id,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(rebuttal_data),
                    "tags": ["argument", "for", debate_id, "rebuttal"],
                    "importance": 0.8,
                    "segment": "arguments",
                    "metadata": {
                        "debate_id": debate_id,
                        "position": "for",
                        "type": "rebuttal",
                        "topic": topic,
                    },
                }
            )

        return rebuttal_data


class OpponentAgent(BaseAgent):
    """
    OpponentAgent: Argues AGAINST a position.

    Responsibilities:
    - Construct arguments AGAINST the topic
    - Provide key points and evidence
    - Rebut proponent's arguments
    - Maintain AGAINST position throughout debate
    - Write arguments to shared memory

    Shared Memory Behavior:
    - Writes arguments with tags: ["argument", "against", debate_id]
    - Segment: "arguments"
    - Importance: 0.8
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize OpponentAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=ArgumentConstructionSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.tool_registry = tool_registry

    def construct_argument(self, topic: str, context: str = "") -> Dict[str, Any]:
        """
        Build argument AGAINST position.

        Args:
            topic: Topic to argue about
            context: Additional context

        Returns:
            Argument dict with argument, key_points, evidence
        """
        # Generate debate ID (will be overridden by pattern)
        debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Execute argument construction via base agent
        result = self.run(
            topic=topic,
            position="against",
            context=context,
            session_id=f"construct_{self.agent_id}_{debate_id}",
        )

        # Build argument dict
        argument_data = {
            "argument": result.get("argument", ""),
            "key_points": result.get("key_points", "[]"),
            "evidence": result.get("evidence", ""),
            "position": "against",
            "topic": topic,
            "debate_id": debate_id,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(argument_data),
                    "tags": ["argument", "against", debate_id],
                    "importance": 0.8,
                    "segment": "arguments",
                    "metadata": {
                        "debate_id": debate_id,
                        "position": "against",
                        "topic": topic,
                    },
                }
            )

        return argument_data

    def rebut(self, proponent_argument: Dict[str, Any], topic: str) -> Dict[str, Any]:
        """
        Counter proponent's argument.

        Args:
            proponent_argument: Proponent's argument dict
            topic: Debate topic

        Returns:
            Rebuttal dict with rebuttal, counterpoints, strength
        """
        # Get debate_id from proponent argument
        debate_id = proponent_argument.get(
            "debate_id", f"debate_{uuid.uuid4().hex[:8]}"
        )

        # Extract proponent argument text
        proponent_text = proponent_argument.get("argument", "")
        if isinstance(proponent_text, dict):
            proponent_text = json.dumps(proponent_text)

        # Switch signature temporarily
        original_signature = self.signature
        self.signature = RebuttalSignature()

        # Execute rebuttal via base agent
        result = self.run(
            opponent_argument=proponent_text,
            original_position="against",
            topic=topic,
            session_id=f"rebut_{self.agent_id}_{debate_id}",
        )

        # Switch back
        self.signature = original_signature

        # Validate strength
        strength = result.get("strength", 0.5)
        try:
            strength = float(strength)
            if strength < 0.0:
                strength = 0.0
            elif strength > 1.0:
                strength = 1.0
        except (ValueError, TypeError):
            strength = 0.5

        # Build rebuttal dict
        rebuttal_data = {
            "rebuttal": result.get("rebuttal", ""),
            "counterpoints": result.get("counterpoints", "[]"),
            "strength": strength,
            "position": "against",
            "topic": topic,
            "debate_id": debate_id,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(rebuttal_data),
                    "tags": ["argument", "against", debate_id, "rebuttal"],
                    "importance": 0.8,
                    "segment": "arguments",
                    "metadata": {
                        "debate_id": debate_id,
                        "position": "against",
                        "type": "rebuttal",
                        "topic": topic,
                    },
                }
            )

        return rebuttal_data


class JudgeAgent(BaseAgent):
    """
    JudgeAgent: Evaluates arguments and makes decision.

    Responsibilities:
    - Read all arguments from shared memory
    - Evaluate both sides (FOR and AGAINST)
    - Determine winner (for/against/tie)
    - Provide reasoning and confidence
    - Write judgment to shared memory

    Shared Memory Behavior:
    - Reads arguments with tags: ["argument", debate_id]
    - Writes judgment with tags: ["judgment", debate_id]
    - Segment: "judgments"
    - Importance: 0.9
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        shared_memory: SharedMemoryPool,
        agent_id: str,
        mcp_servers: Optional[List[Dict]] = None,
        tool_registry: Optional["ToolRegistry"] = None,
    ):
        """
        Initialize JudgeAgent.

        Args:
            config: Agent configuration
            shared_memory: Shared memory pool for collaboration
            agent_id: Unique identifier for this agent
            mcp_servers: Optional MCP server configurations for tool discovery
            tool_registry: Optional tool registry for tool documentation injection
        """
        super().__init__(
            config=config,
            signature=JudgmentSignature(),
            shared_memory=shared_memory,
            agent_id=agent_id,
            mcp_servers=mcp_servers,
        )
        self.tool_registry = tool_registry

    def get_arguments(self, debate_id: str) -> Dict[str, Any]:
        """
        Read all arguments for debate.

        Args:
            debate_id: Debate identifier

        Returns:
            Dict with all arguments and rebuttals
        """
        if not self.shared_memory:
            return {}

        # Read all arguments for this debate
        insights = self.shared_memory.read_relevant(
            agent_id=self.agent_id,
            tags=["argument", debate_id],
            exclude_own=True,
            limit=100,
        )

        # Parse and organize arguments
        proponent_argument = ""
        opponent_argument = ""
        proponent_rebuttal = ""
        opponent_rebuttal = ""

        for insight in insights:
            content = insight.get("content", "{}")
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    continue
            else:
                data = content

            position = data.get("position", "")
            is_rebuttal = "rebuttal" in insight.get("tags", [])

            if position == "for" and not is_rebuttal:
                proponent_argument = data.get("argument", "")
            elif position == "against" and not is_rebuttal:
                opponent_argument = data.get("argument", "")
            elif position == "for" and is_rebuttal:
                proponent_rebuttal = data.get("rebuttal", "")
            elif position == "against" and is_rebuttal:
                opponent_rebuttal = data.get("rebuttal", "")

        return {
            "proponent_argument": proponent_argument,
            "opponent_argument": opponent_argument,
            "proponent_rebuttal": proponent_rebuttal,
            "opponent_rebuttal": opponent_rebuttal,
            "for_argument": proponent_argument,
            "against_argument": opponent_argument,
            "for_rebuttal": proponent_rebuttal,
            "against_rebuttal": opponent_rebuttal,
        }

    def judge_debate(self, debate_id: str) -> Dict[str, Any]:
        """
        Evaluate arguments and make decision.

        Args:
            debate_id: Debate identifier

        Returns:
            Judgment dict with decision, winner, reasoning, confidence
        """
        # Get all arguments
        arguments = self.get_arguments(debate_id)

        # Extract arguments for judgment
        proponent_arg = arguments.get("proponent_argument", "")
        opponent_arg = arguments.get("opponent_argument", "")
        proponent_reb = arguments.get("proponent_rebuttal", "")
        opponent_reb = arguments.get("opponent_rebuttal", "")

        # Get topic from shared memory
        topic = "Unknown"
        if self.shared_memory:
            all_insights = self.shared_memory.read_relevant(
                agent_id=self.agent_id, tags=[debate_id], exclude_own=True, limit=10
            )
            for insight in all_insights:
                metadata = insight.get("metadata", {})
                if "topic" in metadata:
                    topic = metadata["topic"]
                    break

        # Execute judgment via base agent
        result = self.run(
            topic=topic,
            proponent_argument=proponent_arg,
            opponent_argument=opponent_arg,
            proponent_rebuttal=proponent_reb,
            opponent_rebuttal=opponent_reb,
            session_id=f"judge_{debate_id}",
        )

        # Validate decision
        decision = result.get("decision", "tie")
        valid_decisions = ["for", "against", "tie"]
        if decision not in valid_decisions:
            decision = "tie"

        # Determine winner based on decision
        winner = result.get("winner", "")
        if not winner:
            if decision == "for":
                winner = "Proponent (FOR)"
            elif decision == "against":
                winner = "Opponent (AGAINST)"
            else:
                winner = "Tie"

        # Validate confidence
        confidence = result.get("confidence", 0.5)
        try:
            confidence = float(confidence)
            if confidence < 0.0:
                confidence = 0.0
            elif confidence > 1.0:
                confidence = 1.0
        except (ValueError, TypeError):
            confidence = 0.5

        # Build judgment dict
        judgment_data = {
            "decision": decision,
            "winner": winner,
            "reasoning": result.get("reasoning", ""),
            "confidence": confidence,
            "debate_id": debate_id,
            "topic": topic,
        }

        # Write to shared memory
        if self.shared_memory:
            self.shared_memory.write_insight(
                {
                    "agent_id": self.agent_id,
                    "content": json.dumps(judgment_data),
                    "tags": ["judgment", debate_id],
                    "importance": 0.9,
                    "segment": "judgments",
                    "metadata": {
                        "debate_id": debate_id,
                        "decision": decision,
                        "winner": winner,
                        "topic": topic,
                    },
                }
            )

        return judgment_data


# ============================================================================
# Pattern Container
# ============================================================================


@dataclass
class DebatePattern(BaseMultiAgentPattern):
    """
    DebatePattern: Container for adversarial reasoning through structured debate.

    Provides convenience methods for common operations:
    - debate(): Run complete debate with N rounds
    - get_judgment(): Retrieve final judgment

    Attributes:
        proponent: ProponentAgent instance (FOR position)
        opponent: OpponentAgent instance (AGAINST position)
        judge: JudgeAgent instance (evaluates and decides)
        shared_memory: SharedMemoryPool for coordination
    """

    proponent: ProponentAgent
    opponent: OpponentAgent
    judge: JudgeAgent

    def debate(self, topic: str, context: str = "", rounds: int = 1) -> Dict[str, Any]:
        """
        Run debate with N rounds.

        Args:
            topic: Topic to debate
            context: Additional context
            rounds: Number of debate rounds (default: 1)

        Returns:
            Dict with debate_id and judgment
        """
        # Handle edge case: 0 or negative rounds
        if rounds <= 0:
            return {"debate_id": f"debate_{uuid.uuid4().hex[:8]}", "rounds": 0}

        # Generate debate ID
        debate_id = f"debate_{uuid.uuid4().hex[:8]}"

        # Round 1: Initial arguments
        proponent_arg = self.proponent.construct_argument(topic, context)
        opponent_arg = self.opponent.construct_argument(topic, context)

        # Override debate_id to ensure consistency
        proponent_arg["debate_id"] = debate_id
        opponent_arg["debate_id"] = debate_id

        # Additional rounds: Rebuttals
        for round_num in range(1, rounds):
            proponent_reb = self.proponent.rebut(opponent_arg, topic)
            opponent_reb = self.opponent.rebut(proponent_arg, topic)

            # Override debate_id
            proponent_reb["debate_id"] = debate_id
            opponent_reb["debate_id"] = debate_id

            # Update arguments for next round
            proponent_arg = proponent_reb
            opponent_arg = opponent_reb

        # Judge evaluates all arguments
        judgment = self.judge.judge_debate(debate_id)

        return {
            "debate_id": debate_id,
            "topic": topic,
            "rounds": rounds,
            "judgment": judgment,
        }

    def get_judgment(self, debate_id: str) -> Dict[str, Any]:
        """
        Get final judgment for debate.

        Args:
            debate_id: Debate identifier

        Returns:
            Judgment dict or None if not found
        """
        if not self.shared_memory:
            return None

        # Read judgment from shared memory
        judgments = self.shared_memory.read_relevant(
            agent_id="_pattern_",
            tags=["judgment", debate_id],
            exclude_own=False,
            limit=10,
        )

        if not judgments:
            return None

        # Return most recent judgment
        judgment = judgments[0]
        content = judgment.get("content", "{}")
        if isinstance(content, str):
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        return content

    def get_agents(self) -> List[BaseAgent]:
        """
        Get all agents in this pattern.

        Returns:
            List of agent instances (filters out None agents)
        """
        agents = []
        if self.proponent:
            agents.append(self.proponent)
        if self.opponent:
            agents.append(self.opponent)
        if self.judge:
            agents.append(self.judge)
        return agents

    def get_agent_ids(self) -> List[str]:
        """
        Get all agent IDs in this pattern.

        Returns:
            List of agent ID strings
        """
        return [agent.agent_id for agent in self.get_agents() if agent is not None]

    async def execute_async(
        self, topic: str, context: str = "", rounds: int = 1
    ) -> Dict[str, Any]:
        """
        Execute debate pattern asynchronously using AsyncLocalRuntime.

        This method provides async execution for Docker/FastAPI environments.
        For synchronous execution in CLI/scripts, use the debate() and
        get_judgment() methods directly.

        Args:
            topic: Topic to debate
            context: Additional context
            rounds: Number of debate rounds (default: 1)

        Returns:
            Dict with debate_id, topic, rounds, and judgment

        Example:
            >>> pattern = create_debate_pattern()
            >>> result = await pattern.execute_async("Should AI be regulated?", rounds=2)
            >>> print(result['judgment']['winner'])
        """
        # Run debate (which already handles multiple rounds)
        return self.debate(topic, context=context, rounds=rounds)


# ============================================================================
# Factory Function
# ============================================================================


def create_debate_pattern(
    llm_provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    shared_memory: Optional[SharedMemoryPool] = None,
    proponent_config: Optional[Dict[str, Any]] = None,
    opponent_config: Optional[Dict[str, Any]] = None,
    judge_config: Optional[Dict[str, Any]] = None,
) -> DebatePattern:
    """
    Create debate pattern with zero-config defaults.

    Zero-Config Usage:
        >>> pattern = create_debate_pattern()
        >>> result = pattern.debate("Should AI be regulated?", rounds=2)
        >>> judgment = pattern.get_judgment(result["debate_id"])

    Progressive Configuration:
        >>> pattern = create_debate_pattern(
        ...     model="gpt-4",
        ...     temperature=0.7
        ... )

    Separate Agent Configs:
        >>> pattern = create_debate_pattern(
        ...     proponent_config={'model': 'gpt-4'},
        ...     opponent_config={'model': 'gpt-3.5-turbo'},
        ...     judge_config={'model': 'gpt-4'}
        ... )

    Args:
        llm_provider: LLM provider (default: from env or "openai")
        model: Model name (default: from env or "gpt-3.5-turbo")
        temperature: Temperature (default: 0.7)
        max_tokens: Max tokens (default: 1000)
        shared_memory: Existing SharedMemoryPool (default: creates new)
        proponent_config: Override proponent config
        opponent_config: Override opponent config
        judge_config: Override judge config

    Returns:
        DebatePattern: Pattern ready to use
    """
    # Create shared memory if not provided
    if shared_memory is None:
        shared_memory = SharedMemoryPool()

    # Build base config from parameters (or use defaults)
    base_config_dict = {
        "llm_provider": llm_provider or os.getenv("KAIZEN_LLM_PROVIDER", "openai"),
        "model": model or os.getenv("KAIZEN_MODEL", "gpt-3.5-turbo"),
        "temperature": (
            temperature
            if temperature is not None
            else float(os.getenv("KAIZEN_TEMPERATURE", "0.7"))
        ),
        "max_tokens": (
            max_tokens
            if max_tokens is not None
            else int(os.getenv("KAIZEN_MAX_TOKENS", "1000"))
        ),
    }

    # Build proponent config
    proponent_cfg_dict = {**base_config_dict}
    if proponent_config:
        proponent_cfg_dict.update(proponent_config)
    proponent_cfg = BaseAgentConfig(**proponent_cfg_dict)

    # Build opponent config
    opponent_cfg_dict = {**base_config_dict}
    if opponent_config:
        opponent_cfg_dict.update(opponent_config)
    opponent_cfg = BaseAgentConfig(**opponent_cfg_dict)

    # Build judge config
    judge_cfg_dict = {**base_config_dict}
    if judge_config:
        judge_cfg_dict.update(judge_config)
    judge_cfg = BaseAgentConfig(**judge_cfg_dict)

    # Create proponent
    proponent = ProponentAgent(
        config=proponent_cfg, shared_memory=shared_memory, agent_id="proponent_1"
    )

    # Create opponent
    opponent = OpponentAgent(
        config=opponent_cfg, shared_memory=shared_memory, agent_id="opponent_1"
    )

    # Create judge
    judge = JudgeAgent(
        config=judge_cfg, shared_memory=shared_memory, agent_id="judge_1"
    )

    return DebatePattern(
        proponent=proponent, opponent=opponent, judge=judge, shared_memory=shared_memory
    )
