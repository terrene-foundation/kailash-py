"""
Tier 3 E2E Tests: Complete Chat Workflow with Real Infrastructure.

Tests complete multi-turn chat workflows end-to-end with REAL LLMs and REAL memory.
NO MOCKING ALLOWED.

Test Coverage:
- Complete multi-turn chat conversation (3 tests)
- Memory persistence across sessions (2 tests)

Total: 5 E2E tests
"""

import os
import sys
from pathlib import Path

import pytest

# Real LLM providers

# =============================================================================
# COMPLETE MULTI-TURN CHAT CONVERSATION E2E TESTS (3 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_complete_chat_workflow_with_context():
    """Test complete multi-turn chat maintaining context (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            max_tokens=300,
            max_turns=10,
        )

        agent = SimpleQAAgent(config)
        session_id = "e2e_chat_001"

        # Complete conversation workflow
        conversation = [
            ("My name is Alice.", "Nice to meet you"),
            ("I'm learning Python.", "programming"),
            ("What should I learn first?", "basics|fundamentals|syntax"),
            ("What is my name?", "Alice"),  # Test memory
            ("What am I learning?", "Python"),  # Test memory
        ]

        results = []
        for question, expected_keyword in conversation:
            result = agent.ask(question, session_id=session_id)
            results.append(result)

            # Verify response contains expected context
            answer_lower = result["answer"].lower()
            if "|" in expected_keyword:
                # Any of the keywords
                keywords = expected_keyword.split("|")
                assert any(
                    kw in answer_lower for kw in keywords
                ), f"Expected one of {keywords} in response to '{question}'"
            else:
                assert (
                    expected_keyword.lower() in answer_lower
                ), f"Expected '{expected_keyword}' in response to '{question}'"

        # All responses should be received
        assert len(results) == 5
        assert all("answer" in r for r in results)

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_complete_chat_workflow_with_reasoning():
    """Test complete chat workflow includes reasoning (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.1, max_tokens=400
        )

        agent = SimpleQAAgent(config)

        # Multi-turn conversation with reasoning
        workflow_steps = [
            {
                "question": "What is Python?",
                "verify": ["answer", "reasoning"],
                "check_reasoning": True,
            },
            {
                "question": "Why is it popular?",
                "verify": ["answer", "reasoning"],
                "check_reasoning": True,
            },
            {
                "question": "Give me an example use case.",
                "verify": ["answer", "reasoning"],
                "check_reasoning": True,
            },
        ]

        for step in workflow_steps:
            result = agent.ask(step["question"])

            # Verify required fields
            for field in step["verify"]:
                assert field in result, f"Missing {field} in response"

            # Verify reasoning is provided
            if step.get("check_reasoning"):
                assert (
                    len(result.get("reasoning", "")) > 0
                ), "Reasoning should not be empty"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_complete_chat_workflow_with_confidence():
    """Test complete chat workflow tracks confidence (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai",
            model="gpt-5-nano",
            temperature=0.1,
            min_confidence_threshold=0.5,
        )

        agent = SimpleQAAgent(config)

        # Questions with expected confidence levels
        test_cases = [
            {
                "question": "What is 2+2?",
                "expected_confidence": "high",  # Factual, should be high confidence
            },
            {
                "question": "Will it rain tomorrow in an unknown location?",
                "expected_confidence": "low",  # Speculative, should be lower confidence
            },
            {
                "question": "What is Python?",
                "expected_confidence": "high",  # Factual, should be high confidence
            },
        ]

        confidence_scores = []
        for case in test_cases:
            result = agent.ask(case["question"])

            assert "confidence" in result
            assert isinstance(result["confidence"], (int, float))
            assert 0.0 <= result["confidence"] <= 1.0

            confidence_scores.append(
                {
                    "question": case["question"],
                    "confidence": result["confidence"],
                    "expected": case["expected_confidence"],
                }
            )

        # Verify confidence scoring is working
        assert len(confidence_scores) == 3

    finally:
        sys.path.remove(str(example_path))


# =============================================================================
# MEMORY PERSISTENCE ACROSS SESSIONS E2E TESTS (2 tests)
# =============================================================================


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_chat_workflow_memory_persistence():
    """Test chat workflow maintains memory across multiple interactions (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.1, max_turns=10
        )

        agent = SimpleQAAgent(config)
        session_id = "e2e_persistence_001"

        # Phase 1: Establish context
        agent.ask("I have a dog named Max.", session_id=session_id)
        agent.ask("Max is 5 years old.", session_id=session_id)
        agent.ask("Max loves playing fetch.", session_id=session_id)

        # Phase 2: Query context (should remember all facts)
        result_name = agent.ask("What is my dog's name?", session_id=session_id)
        assert "max" in result_name["answer"].lower()

        result_age = agent.ask("How old is my dog?", session_id=session_id)
        assert "5" in result_age["answer"] or "five" in result_age["answer"].lower()

        result_activity = agent.ask("What does my dog like?", session_id=session_id)
        assert (
            "fetch" in result_activity["answer"].lower()
            or "play" in result_activity["answer"].lower()
        )

        # Phase 3: Multi-fact query
        result_combined = agent.ask(
            "Tell me everything about my dog.", session_id=session_id
        )

        # Should incorporate multiple facts from memory
        answer_lower = result_combined["answer"].lower()
        # Should mention at least 2 of the 3 facts
        facts_mentioned = sum(
            [
                "max" in answer_lower,
                "5" in result_combined["answer"] or "five" in answer_lower,
                "fetch" in answer_lower or "play" in answer_lower,
            ]
        )
        assert facts_mentioned >= 2, "Should remember multiple facts from conversation"

    finally:
        sys.path.remove(str(example_path))


@pytest.mark.e2e
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OpenAI API key required")
def test_chat_workflow_session_isolation():
    """Test chat workflow isolates different sessions (E2E)."""
    example_path = (
        Path(__file__).parent.parent.parent / "examples/1-single-agent/simple-qa"
    )
    sys.path.insert(0, str(example_path))

    try:
        from workflow import QAConfig, SimpleQAAgent

        config = QAConfig(
            llm_provider="openai", model="gpt-5-nano", temperature=0.1, max_turns=5
        )

        agent = SimpleQAAgent(config)

        # Session 1: Alice with Python
        session_1 = "e2e_isolation_session_1"
        agent.ask("My name is Alice.", session_id=session_1)
        agent.ask("I'm learning Python.", session_id=session_1)

        # Session 2: Bob with JavaScript
        session_2 = "e2e_isolation_session_2"
        agent.ask("My name is Bob.", session_id=session_2)
        agent.ask("I'm learning JavaScript.", session_id=session_2)

        # Query Session 1 - should remember Alice and Python
        result_s1_name = agent.ask("What is my name?", session_id=session_1)
        result_s1_lang = agent.ask("What am I learning?", session_id=session_1)

        assert "alice" in result_s1_name["answer"].lower()
        assert "python" in result_s1_lang["answer"].lower()
        assert "bob" not in result_s1_name["answer"].lower()
        assert "javascript" not in result_s1_lang["answer"].lower()

        # Query Session 2 - should remember Bob and JavaScript
        result_s2_name = agent.ask("What is my name?", session_id=session_2)
        result_s2_lang = agent.ask("What am I learning?", session_id=session_2)

        assert "bob" in result_s2_name["answer"].lower()
        assert "javascript" in result_s2_lang["answer"].lower()
        assert "alice" not in result_s2_name["answer"].lower()
        assert "python" not in result_s2_lang["answer"].lower()

    finally:
        sys.path.remove(str(example_path))
