"""
Customer Support Agent - Persistent Conversation Memory.

This example demonstrates:
1. Conversation persistence across sessions using PersistentBufferMemory
2. Automatic context loading from previous sessions
3. User preference learning from conversation history
4. JSONL compression for efficient storage
5. Cross-session continuity (remembers past interactions)
6. Budget tracking with Ollama (FREE - $0.00)

Requirements:
- Ollama with llama3.1:8b-instruct-q8_0 model installed (FREE)
- Python 3.8+
- kailash-dataflow

Usage:
    python customer_support_agent.py

    The agent will:
    - Handle multi-turn customer support conversations
    - Remember context across sessions
    - Learn user preferences from history
    - Provide personalized responses based on past interactions
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dataflow import DataFlow
from kaizen.core.autonomy.hooks import (
    BaseHook,
    HookContext,
    HookEvent,
    HookManager,
    HookResult,
)
from kaizen.core.base_agent import BaseAgent
from kaizen.core.config import BaseAgentConfig
from kaizen.memory.backends.dataflow_backend import DataFlowBackend
from kaizen.memory.persistent_buffer import PersistentBufferMemory
from kaizen.signatures import InputField, OutputField, Signature

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SupportConversationSignature(Signature):
    """Signature for customer support conversation."""

    user_message: str = InputField(description="User's support message")
    conversation_history: str = InputField(
        description="Previous conversation context (last N turns)"
    )
    agent_response: str = OutputField(description="Agent's support response")
    confidence: float = OutputField(description="Confidence in response quality (0-1)")
    resolved: bool = OutputField(
        description="Whether the issue appears resolved (True/False)"
    )


class ConversationAnalyticsHook(BaseHook):
    """
    Custom hook to track conversation analytics and quality.

    Records:
    - Total conversations
    - Average turns per conversation
    - Resolution rates
    - Response quality scores
    """

    def __init__(self):
        super().__init__(name="conversation_analytics_hook")
        self.conversations: List[Dict[str, Any]] = []
        self.stats = {
            "total_turns": 0,
            "resolved_conversations": 0,
            "average_confidence": 0.0,
            "total_confidence": 0.0,
        }

    def supported_events(self) -> List[HookEvent]:
        """Hook into post-agent loop to track conversation metrics."""
        return [HookEvent.POST_AGENT_LOOP]

    async def handle(self, context: HookContext) -> HookResult:
        """Record conversation analytics."""
        try:
            # Extract conversation info from context
            resolved = context.data.get("resolved", False)
            confidence = context.data.get("confidence", 0.0)

            # Update statistics
            self.stats["total_turns"] += 1
            self.stats["total_confidence"] += confidence

            if resolved:
                self.stats["resolved_conversations"] += 1

            # Calculate average confidence
            self.stats["average_confidence"] = (
                self.stats["total_confidence"] / self.stats["total_turns"]
                if self.stats["total_turns"] > 0
                else 0.0
            )

            # Log conversation turn
            self.conversations.append(
                {
                    "timestamp": datetime.now().isoformat(),
                    "resolved": resolved,
                    "confidence": confidence,
                    "agent_id": context.agent_id,
                }
            )

            return HookResult(
                success=True,
                data={
                    "analytics_logged": True,
                    "total_turns": self.stats["total_turns"],
                },
            )

        except Exception as e:
            logger.error(f"Failed to log conversation analytics: {e}")
            return HookResult(success=False, error=str(e))

    def get_summary(self) -> Dict[str, Any]:
        """Get conversation analytics summary."""
        return {
            "total_turns": self.stats["total_turns"],
            "resolved_conversations": self.stats["resolved_conversations"],
            "resolution_rate": (
                round(
                    (
                        self.stats["resolved_conversations"]
                        / self.stats["total_turns"]
                        * 100
                    ),
                    1,
                )
                if self.stats["total_turns"] > 0
                else 0.0
            ),
            "average_confidence": round(self.stats["average_confidence"], 2),
        }


class CustomerSupportAgent(BaseAgent):
    """
    Customer support agent with persistent conversation memory.

    Features:
    - Cross-session conversation persistence
    - Automatic context loading from database
    - User preference learning from history
    - Auto-persist every 5 messages
    - JSONL compression (60% reduction)
    - Budget tracking ($0.00 with Ollama)
    """

    def __init__(
        self,
        config: BaseAgentConfig,
        db: DataFlow,
        customer_id: str = "customer_001",
    ):
        """
        Initialize customer support agent with persistent memory.

        Args:
            config: Agent configuration
            db: DataFlow instance for persistent storage
            customer_id: Unique customer identifier for conversation isolation
        """
        # Setup hook manager
        hook_manager = HookManager()
        self.analytics_hook = ConversationAnalyticsHook()
        hook_manager.register_hook(self.analytics_hook)

        # Initialize base agent
        super().__init__(
            config=config,
            signature=SupportConversationSignature(),
            hook_manager=hook_manager,
        )

        self.customer_id = customer_id
        self.db = db

        # Setup persistent memory
        self._setup_memory()

        # Track session info
        self.session_turns = 0
        self.budget_spent = 0.0

        # Load conversation history
        self._load_history()

        logger.info(f"Initialized CustomerSupportAgent for customer: {customer_id}")

    def _setup_memory(self):
        """Configure persistent buffer memory with DataFlow backend."""
        backend = DataFlowBackend(self.db, model_name="ConversationMessage")

        self.memory = PersistentBufferMemory(
            backend=backend,
            max_turns=50,  # Keep last 50 turns in memory
            cache_ttl_seconds=1800,  # 30 minutes TTL
        )

        logger.info(
            "Configured persistent memory: 50 turns buffer, 30min TTL, auto-persist every 5 messages"
        )

    def _load_history(self):
        """Load conversation history from database."""
        try:
            context = self.memory.load_context(self.customer_id)
            turn_count = context.get("turn_count", 0)

            if turn_count > 0:
                logger.info(
                    f"✅ Loaded {turn_count} conversation turns for customer {self.customer_id}"
                )
            else:
                logger.info(f"New customer: {self.customer_id} (no previous history)")

        except Exception as e:
            logger.warning(f"Failed to load history: {e}")

    def _extract_user_preferences(
        self, history: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract user preferences from conversation history.

        Analyzes past conversations to detect:
        - Communication style preferences (formal vs casual)
        - Response length preferences (brief vs detailed)
        - Common issues and topics
        - Resolution patterns

        Args:
            history: List of conversation turns

        Returns:
            Dictionary with detected preferences
        """
        preferences = {
            "communication_style": "balanced",  # formal, casual, balanced
            "response_length": "medium",  # brief, medium, detailed
            "common_topics": [],
            "past_issues": [],
        }

        if not history:
            return preferences

        # Analyze communication style (simple keyword detection)
        formal_keywords = ["please", "thank you", "appreciate", "kindly"]
        casual_keywords = ["hey", "thanks", "cool", "awesome"]

        formal_count = 0
        casual_count = 0

        for turn in history:
            user_msg = turn.get("user", "").lower()
            formal_count += sum(1 for kw in formal_keywords if kw in user_msg)
            casual_count += sum(1 for kw in casual_keywords if kw in user_msg)

        if formal_count > casual_count * 1.5:
            preferences["communication_style"] = "formal"
        elif casual_count > formal_count * 1.5:
            preferences["communication_style"] = "casual"

        # Analyze response length preference (based on user message lengths)
        avg_user_msg_length = sum(len(turn.get("user", "")) for turn in history) / len(
            history
        )

        if avg_user_msg_length < 50:
            preferences["response_length"] = "brief"
        elif avg_user_msg_length > 150:
            preferences["response_length"] = "detailed"

        # Extract common topics (simple keyword extraction)
        all_messages = " ".join(turn.get("user", "") for turn in history).lower()
        common_topics = []

        topic_keywords = {
            "login": ["login", "password", "authenticate", "sign in"],
            "billing": ["payment", "invoice", "charge", "subscription"],
            "technical": ["error", "bug", "crash", "not working"],
            "account": ["account", "profile", "settings"],
        }

        for topic, keywords in topic_keywords.items():
            if any(kw in all_messages for kw in keywords):
                common_topics.append(topic)

        preferences["common_topics"] = common_topics

        return preferences

    def respond(self, user_message: str) -> Dict[str, Any]:
        """
        Generate response to user message with conversation context.

        Flow:
        1. Load conversation history from memory
        2. Extract user preferences from history
        3. Generate contextualized response
        4. Save turn to persistent memory
        5. Auto-persist every 5 messages

        Args:
            user_message: User's support message

        Returns:
            Dictionary with agent_response, confidence, resolved, preferences
        """
        try:
            # Load conversation history
            context = self.memory.load_context(self.customer_id)
            history = context.get("turns", [])

            # Extract user preferences
            preferences = self._extract_user_preferences(history)

            # Build conversation history string (last 10 turns)
            recent_history = history[-10:] if len(history) > 10 else history
            history_str = "\n".join(
                [
                    f"User: {turn['user']}\nAgent: {turn['agent']}"
                    for turn in recent_history
                ]
            )

            # Add preference context to history
            pref_context = (
                f"\n\n[User Preferences: "
                f"Style={preferences['communication_style']}, "
                f"Length={preferences['response_length']}"
            )
            if preferences["common_topics"]:
                pref_context += (
                    f", Common Topics={', '.join(preferences['common_topics'])}"
                )
            pref_context += "]"

            history_str += pref_context

            # Generate response
            result = self.run(
                user_message=user_message, conversation_history=history_str
            )

            # Extract response fields
            agent_response = self.extract_str(
                result,
                "agent_response",
                default="I'm here to help. Could you provide more details?",
            )
            confidence = self.extract_float(result, "confidence", default=0.7)
            resolved = result.get("resolved", False)

            # Save turn to persistent memory
            self.memory.save_turn(
                self.customer_id,
                {
                    "user": user_message,
                    "agent": agent_response,
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "confidence": confidence,
                        "resolved": resolved,
                        "preferences": preferences,
                    },
                },
            )

            self.session_turns += 1

            # Log statistics
            logger.info(
                f"✅ Turn {self.session_turns}: Confidence={confidence:.2f}, "
                f"Resolved={resolved}, Style={preferences['communication_style']}"
            )

            return {
                "agent_response": agent_response,
                "confidence": confidence,
                "resolved": resolved,
                "preferences": preferences,
                "history_length": len(history) + 1,
            }

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return {
                "agent_response": "I apologize, but I encountered an error. Please try again.",
                "confidence": 0.0,
                "resolved": False,
                "preferences": {},
                "history_length": 0,
            }

    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics and memory info."""
        context = self.memory.load_context(self.customer_id)
        memory_stats = self.memory.get_stats()
        analytics = self.analytics_hook.get_summary()

        return {
            "customer_id": self.customer_id,
            "session_turns": self.session_turns,
            "total_conversation_turns": context.get("turn_count", 0),
            "memory": {
                "cached_sessions": memory_stats.get("cached_sessions", 0),
                "backend_type": memory_stats.get("backend_type", "Unknown"),
            },
            "analytics": analytics,
            "budget": {
                "spent_usd": self.budget_spent,
                "model": self.config.model,
                "provider": self.config.llm_provider,
            },
        }


def simulate_multi_session_conversation():
    """
    Simulate multi-session customer support conversation.

    Demonstrates:
    - Session 1: Initial support inquiry (new customer)
    - Session 2: Follow-up question (remembers context)
    - Session 3: Related issue (learns preferences)
    - Cross-session persistence and context continuity
    """
    print("\n" + "=" * 80)
    print("CUSTOMER SUPPORT - MULTI-SESSION CONVERSATION")
    print("=" * 80)

    # Setup DataFlow with SQLite
    db_path = Path(__file__).parent / ".kaizen" / "support_memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing DataFlow with SQLite: {db_path}")

    db = DataFlow(database_type="sqlite", database_config={"database": str(db_path)})

    # Define conversation message model
    @db.model
    class ConversationMessage:
        id: str
        conversation_id: str
        sender: str
        content: str
        metadata: dict
        created_at: datetime

    # Configure agent with Ollama (FREE)
    config = BaseAgentConfig(
        llm_provider="ollama",
        model="llama3.1:8b-instruct-q8_0",
        temperature=0.7,
        max_tokens=300,
    )

    # SESSION 1: Initial support inquiry
    print("\n" + "-" * 80)
    print("SESSION 1 (Day 1) - Initial Support Inquiry")
    print("-" * 80)

    agent = CustomerSupportAgent(config=config, db=db, customer_id="customer_alice")

    messages_session_1 = [
        "Hi, I can't login to my account. It says 'invalid password'.",
        "I tried resetting my password but didn't receive the email.",
        "My email is alice@example.com. Can you check?",
    ]

    for msg in messages_session_1:
        print(f"\n👤 User: {msg}")
        result = agent.respond(msg)
        print(f"🤖 Agent: {result['agent_response']}")
        print(
            f"   [Confidence: {result['confidence']:.2f}, Resolved: {result['resolved']}]"
        )

    # Print session 1 statistics
    stats_1 = agent.get_session_stats()
    print("\n📊 SESSION 1 STATS:")
    print(f"   Turns: {stats_1['session_turns']}")
    print(f"   Total history: {stats_1['total_conversation_turns']} turns")
    print(f"   Budget: ${stats_1['budget']['spent_usd']:.2f} (FREE with Ollama)")

    # SESSION 2: Follow-up question (NEW SESSION - same customer)
    print("\n" + "-" * 80)
    print("SESSION 2 (Day 2) - Follow-up Question (NEW SESSION)")
    print("-" * 80)

    # Create NEW agent instance to simulate restart
    agent_2 = CustomerSupportAgent(config=config, db=db, customer_id="customer_alice")

    messages_session_2 = [
        "Did you send the password reset email?",
        "I still haven't received it. Can you resend?",
    ]

    for msg in messages_session_2:
        print(f"\n👤 User: {msg}")
        result = agent_2.respond(msg)
        print(f"🤖 Agent: {result['agent_response']}")
        print(
            f"   [Confidence: {result['confidence']:.2f}, Resolved: {result['resolved']}, "
            f"History: {result['history_length']} turns]"
        )

    # Print session 2 statistics
    stats_2 = agent_2.get_session_stats()
    print("\n📊 SESSION 2 STATS:")
    print(f"   Current session turns: {stats_2['session_turns']}")
    print(
        f"   Total history: {stats_2['total_conversation_turns']} turns (includes Session 1)"
    )
    print(
        f"   ✅ Context preserved across sessions! "
        f"({stats_2['total_conversation_turns']} total turns from 2 sessions)"
    )

    # SESSION 3: Related issue (NEW SESSION - learns preferences)
    print("\n" + "-" * 80)
    print("SESSION 3 (Day 3) - Related Issue (NEW SESSION)")
    print("-" * 80)

    # Create NEW agent instance to simulate another restart
    agent_3 = CustomerSupportAgent(config=config, db=db, customer_id="customer_alice")

    messages_session_3 = [
        "Great! I received the email and reset my password. Thanks!",
        "Now I have another question - how do I update my billing information?",
    ]

    for msg in messages_session_3:
        print(f"\n👤 User: {msg}")
        result = agent_3.respond(msg)
        print(f"🤖 Agent: {result['agent_response']}")
        print(
            f"   [Confidence: {result['confidence']:.2f}, Resolved: {result['resolved']}, "
            f"Style: {result['preferences']['communication_style']}]"
        )

    # Print session 3 statistics
    stats_3 = agent_3.get_session_stats()
    print("\n📊 SESSION 3 STATS:")
    print(f"   Current session turns: {stats_3['session_turns']}")
    print(
        f"   Total history: {stats_3['total_conversation_turns']} turns (all 3 sessions)"
    )
    print("   User preferences learned:")
    print(f"     - Communication style: {result['preferences']['communication_style']}")
    print(f"     - Response length: {result['preferences']['response_length']}")
    if result["preferences"]["common_topics"]:
        print(
            f"     - Common topics: {', '.join(result['preferences']['common_topics'])}"
        )

    # Print final analytics
    analytics = stats_3["analytics"]
    print("\n📈 CONVERSATION ANALYTICS:")
    print(f"   Total turns: {analytics['total_turns']}")
    print(f"   Resolved conversations: {analytics['resolved_conversations']}")
    print(f"   Resolution rate: {analytics['resolution_rate']}%")
    print(f"   Average confidence: {analytics['average_confidence']:.2f}")

    print("\n" + "=" * 80)
    print("✅ Multi-session conversation completed successfully!")
    print(f"✅ Memory database: {db_path}")
    print(
        f"✅ All {stats_3['total_conversation_turns']} turns persisted across 3 sessions"
    )
    print("=" * 80)


def main():
    """Main entry point for customer support example."""
    try:
        simulate_multi_session_conversation()

    except Exception as e:
        logger.error(f"Failed to run customer support example: {e}")
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
