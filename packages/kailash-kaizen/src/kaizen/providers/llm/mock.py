# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Mock provider for testing and development.

Generates deterministic responses for both LLM and embedding operations
without making actual API calls. Always available, zero latency.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
from typing import Any, List

from kaizen.providers.base import UnifiedAIProvider
from kaizen.providers.types import Message

logger = logging.getLogger(__name__)


class MockProvider(UnifiedAIProvider):
    """Mock provider for testing and development.

    Always available. Generates consistent responses based on input.
    Supports both chat and embedding operations.
    """

    MODELS = [
        "mock-model",
        "mock-embedding",
        "mock-embedding-small",
        "mock-embedding-large",
    ]

    def is_available(self) -> bool:
        return True

    def chat(self, messages: List[Message], **kwargs: Any) -> dict[str, Any]:
        last_user_message = ""
        has_images = False
        full_conversation: list[str] = []

        for msg in messages:
            if msg.get("role") in ["user", "system", "assistant"]:
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            has_images = True
                    full_conversation.append(
                        f"{msg.get('role', 'user')}: {' '.join(text_parts)}"
                    )
                else:
                    full_conversation.append(f"{msg.get('role', 'user')}: {content}")

        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = []
                    for item in content:
                        if item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                        elif item.get("type") == "image":
                            has_images = True
                    last_user_message = " ".join(text_parts)
                else:
                    last_user_message = content
                break

        conversation_text = " ".join(full_conversation).lower()
        message_lower = last_user_message.lower()

        response_content = self._generate_contextual_response(
            message_lower, conversation_text, has_images, last_user_message
        )

        return {
            "id": f"mock_{hash(last_user_message)}",
            "content": response_content,
            "role": "assistant",
            "model": kwargs.get("model", "mock-model"),
            "created": 1701234567,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": len(response_content) // 4,
                "total_tokens": 0,
            },
            "metadata": {},
        }

    def _generate_contextual_response(
        self,
        message_lower: str,
        conversation_text: str,
        has_images: bool,
        original_message: str,
    ) -> str:
        if has_images:
            return (
                "I can see the image(s) you've provided. The image contains several "
                "distinct elements that I can analyze for you. "
                "[Mock vision response with detailed observation]"
            )

        if any(
            pattern in message_lower
            for pattern in [
                "calculate",
                "math",
                "time",
                "hour",
                "minute",
                "second",
                "duration",
            ]
        ) or any(
            op in message_lower
            for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
        ):
            if (
                "train" in conversation_text
                and "travels" in conversation_text
                and any(num in conversation_text for num in ["300", "450", "4"])
            ):
                return (
                    "Step 1: Calculate the train's speed\n"
                    "First, I need to find the train's speed using the given information.\n"
                    "Given: Distance = 300 km, Time = 4 hours\n"
                    "Speed = Distance / Time = 300 km / 4 hours = 75 km/hour\n\n"
                    "Step 2: Apply the speed to find time for new distance\n"
                    "Now I can use this speed to find how long it takes to travel 450 km.\n"
                    "Given: Speed = 75 km/hour, Distance = 450 km\n"
                    "Time = Distance / Speed = 450 km / 75 km/hour = 6 hours\n\n"
                    "Final Answer: 6 hours"
                )
            if (
                "9" in message_lower
                and "3" in message_lower
                and ("-" in message_lower or "minus" in message_lower)
            ) or (
                "time" in message_lower
                and any(num in message_lower for num in ["9", "3", "6"])
            ):
                return (
                    "Let me calculate this step by step:\n\n"
                    "1. Starting with 9\n2. Subtracting 3: 9 - 3 = 6\n"
                    "3. The result is 6\n\n"
                    "So the answer is 6 hours. This represents a time duration of 6 hours."
                )
            if any(
                op in message_lower
                for op in ["+", "-", "*", "/", "plus", "minus", "times", "divide"]
            ):
                return (
                    "I'll solve this mathematical problem step by step:\n\n"
                    "1. First, I'll identify the operation\n"
                    "2. Then apply the calculation\n"
                    "3. Finally, provide the result with explanation\n\n"
                    "The calculation shows a clear mathematical relationship."
                )
            if any(
                tw in message_lower
                for tw in ["time", "hour", "minute", "second", "duration"]
            ):
                return (
                    "I'll help you with this time calculation. Let me work through this systematically:\n\n"
                    "1. Identifying the time units involved\n"
                    "2. Performing the calculation\n"
                    "3. Providing the result in appropriate time format\n\n"
                    "Time calculations require careful attention to units and precision."
                )
            return (
                "I'll help you with this calculation. Let me work through this "
                "systematically to provide an accurate result with proper explanation "
                "of the mathematical process."
            )

        if any(
            p in message_lower
            for p in [
                "step by step",
                "think through",
                "reasoning",
                "explain",
                "how do",
                "why does",
            ]
        ):
            return (
                "Let me think through this step by step:\n\n"
                "1. **Understanding the problem**: I need to break down the key components\n"
                "2. **Analyzing the context**: Looking at the relevant factors and constraints\n"
                "3. **Reasoning process**: Working through the logical connections\n"
                "4. **Arriving at conclusion**: Based on the systematic analysis\n\n"
                "This step-by-step approach ensures thorough reasoning and accurate results."
            )

        if any(
            p in message_lower
            for p in ["plan", "action", "strategy", "approach", "implement", "execute"]
        ):
            return (
                "**Thought**: I need to analyze this request and determine the best approach.\n\n"
                "**Action**: Let me break this down into actionable steps:\n"
                "1. Assess the current situation\n"
                "2. Identify required resources and constraints\n"
                "3. Develop a systematic plan\n"
                "4. Execute with monitoring\n\n"
                "**Observation**: This approach allows for systematic problem-solving with clear action items.\n\n"
                "**Final Action**: Proceeding with the structured implementation plan."
            )

        if any(
            p in message_lower
            for p in ["analyze", "data", "pattern", "trend", "statistics"]
        ):
            return (
                "Based on my analysis of the provided data, I can identify several key patterns:\n\n"
                "- **Trend Analysis**: The data shows distinct patterns over time\n"
                "- **Statistical Insights**: Key metrics indicate significant relationships\n"
                "- **Pattern Recognition**: I've identified recurring themes and anomalies\n"
                "- **Recommendations**: Based on this analysis, I suggest specific next steps"
            )

        if any(
            p in message_lower
            for p in ["create", "generate", "write", "compose", "design", "build"]
        ):
            return (
                "I'll help you create that. Let me approach this systematically:\n\n"
                "**Planning Phase**:\n- Understanding your requirements\n- Identifying key components needed\n\n"
                "**Creation Process**:\n- Developing the core structure\n- Adding details and refinements\n\n"
                "**Quality Assurance**:\n- Reviewing for completeness\n- Ensuring it meets your needs"
            )

        if "?" in message_lower or any(
            p in message_lower
            for p in ["what is", "how does", "why is", "when does", "where is"]
        ):
            return (
                f"Regarding your question about '{original_message[:100]}...', here's a comprehensive answer:\n\n"
                "The key points to understand are:\n"
                "- **Primary concept**: This relates to fundamental principles\n"
                "- **Practical application**: How this applies in real-world scenarios\n"
                "- **Important considerations**: Factors to keep in mind\n"
                "- **Next steps**: Recommendations for further exploration"
            )

        if any(
            p in message_lower
            for p in ["problem", "issue", "error", "fix", "solve", "troubleshoot"]
        ):
            return (
                "I'll help you solve this problem systematically:\n\n"
                "**Problem Analysis**:\n- Identifying the core issue\n- Understanding contributing factors\n\n"
                "**Solution Development**:\n- Exploring potential approaches\n- Evaluating pros and cons\n\n"
                "**Implementation Plan**:\n- Step-by-step resolution process\n- Monitoring and validation steps"
            )

        if any(
            p in message_lower
            for p in ["tool", "function", "call", "api", "service", "endpoint"]
        ):
            return (
                "I'll help you with this tool/function call. Let me identify the appropriate tools "
                "and execute them systematically:\n\n"
                "**Tool Selection**: Identifying the best tools for this task\n"
                "**Parameter Preparation**: Setting up the required parameters\n"
                "**Execution**: Calling the tools with proper error handling\n"
                "**Result Processing**: Interpreting and formatting the results\n\n"
                "This ensures reliable tool execution with comprehensive error handling."
            )

        if any(
            p in message_lower
            for p in ["code", "algorithm", "script", "program", "debug"]
        ):
            return (
                "I'll help you with this technical implementation:\n\n"
                "```\n# Technical solution approach\n"
                "# 1. Understanding requirements\n"
                "# 2. Designing the solution\n"
                "# 3. Implementation details\n"
                "# 4. Testing and validation\n```\n\n"
                "This approach ensures robust, maintainable code with proper error handling."
            )

        if any(
            p in message_lower
            for p in ["explain", "teach", "learn", "understand", "clarify"]
        ):
            return (
                "Let me explain this concept clearly:\n\n"
                "**Foundation**: Starting with the basic principles\n"
                "**Key Concepts**: The essential ideas you need to understand\n"
                "**Examples**: Practical illustrations to make it concrete\n"
                "**Application**: How to use this knowledge effectively\n\n"
                "This explanation provides a solid foundation for understanding."
            )

        if any(
            p in message_lower
            for p in [
                "argument",
                "debate",
                "position",
                "for or against",
                "key_points",
                "evidence",
                "argue about",
                "topic to argue",
            ]
        ) or (
            "topic" in message_lower
            and ("for" in message_lower or "against" in message_lower)
        ):
            return json.dumps(
                {
                    "argument": "This is a well-reasoned argument supporting the given position with logical analysis and evidence-based conclusions.",
                    "key_points": [
                        "Point 1: Analysis of key factors",
                        "Point 2: Supporting evidence and reasoning",
                        "Point 3: Practical implications",
                    ],
                    "evidence": "Research and analysis support this position based on established principles and documented outcomes.",
                }
            )

        if any(
            p in message_lower
            for p in ["judgment", "decision", "winner", "judge", "verdict"]
        ):
            return json.dumps(
                {
                    "decision": "for",
                    "winner": "proponent",
                    "reasoning": "After careful analysis of both arguments, the proponent presented stronger evidence and more compelling logic.",
                    "confidence": 0.85,
                }
            )

        if any(
            p in message_lower
            for p in ["rebuttal", "counterpoint", "counter argument", "rebut"]
        ):
            return json.dumps(
                {
                    "rebuttal": "This rebuttal addresses the key weaknesses in the opposing argument with focused counterpoints.",
                    "counterpoints": [
                        "Counter 1: Logical flaw in premise",
                        "Counter 2: Missing evidence for claims",
                        "Counter 3: Alternative interpretation",
                    ],
                    "strength": 0.75,
                }
            )

        if any(
            p in message_lower
            for p in ["step1", "step2", "step3", "final_answer", "confidence"]
        ):
            return json.dumps(
                {
                    "step1": "First, I identify and understand the problem components.",
                    "step2": "Next, I analyze the relevant factors and constraints.",
                    "step3": "Then, I develop a systematic approach to solve the problem.",
                    "step4": "I apply the method and verify intermediate results.",
                    "step5": "Finally, I synthesize the findings into a coherent answer.",
                    "final_answer": "Based on the step-by-step analysis, the answer is derived systematically.",
                    "confidence": 0.85,
                }
            )

        if len(original_message) > 100:
            return (
                f"I understand you're asking about '{original_message[:100]}...'. "
                "This is a complex topic that requires careful consideration of multiple factors. "
                "Let me provide a thorough response that addresses your key concerns and offers actionable insights."
            )
        return (
            f"I understand your request about '{original_message}'. "
            "Based on the context and requirements, I can provide a comprehensive response "
            "that addresses your specific needs with practical solutions and clear explanations."
        )

    def embed(self, texts: list[str], **kwargs: Any) -> list[list[float]]:
        model = kwargs.get("model", "mock-embedding")
        dimensions = kwargs.get("dimensions", 1536)
        normalize = kwargs.get("normalize", True)

        embeddings = []
        for text in texts:
            seed = int(hashlib.md5(f"{model}:{text}".encode()).hexdigest()[:8], 16)
            random.seed(seed)
            embedding = [random.gauss(0, 1) for _ in range(dimensions)]

            if normalize:
                magnitude = sum(x * x for x in embedding) ** 0.5
                if magnitude > 0:
                    embedding = [x / magnitude for x in embedding]

            embeddings.append(embedding)

        return embeddings

    def get_model_info(self, model: str) -> dict[str, Any]:
        models = {
            "mock-embedding-small": {"dimensions": 384, "max_tokens": 512},
            "mock-embedding": {"dimensions": 1536, "max_tokens": 8192},
            "mock-embedding-large": {"dimensions": 3072, "max_tokens": 8192},
        }
        return models.get(
            model,
            {
                "dimensions": 1536,
                "max_tokens": 8192,
                "description": f"Mock embedding model: {model}",
                "capabilities": {"all_features": True},
            },
        )
