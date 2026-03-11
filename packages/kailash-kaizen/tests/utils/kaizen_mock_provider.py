"""
Kaizen-Specific Mock Provider for Testing

This mock provider extends the Core SDK's MockProvider to understand Kaizen's
signature-based programming and returns realistic JSON responses that match
the expected output format.

Inherits from Core SDK's MockProvider to maintain compatibility while adding
signature-aware JSON response generation.
"""

import json
import re
from typing import Any, Dict, List

try:
    from kailash.nodes.ai import MockProvider as CoreMockProvider
except ImportError:
    # Fallback if Core SDK not available
    class CoreMockProvider:
        def __init__(self, model: str = "gpt-3.5-turbo", **kwargs):
            self.model = model
            self.kwargs = kwargs


class KaizenMockProvider(CoreMockProvider):
    """
    Mock LLM provider that returns realistic JSON responses for Kaizen signatures.

    Extends Core SDK's MockProvider to add signature-aware response generation.
    This provider analyzes the user message to detect the expected JSON format
    (usually specified in the system prompt) and returns appropriate mock data
    that tests can validate against.
    """

    def __init__(self, model: str = "gpt-3.5-turbo", **kwargs):
        """Initialize mock provider. Parent takes no parameters."""
        super().__init__()  # UnifiedAIProvider.__init__() takes no parameters
        self.model = model
        self.kwargs = kwargs

    def chat(self, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
        """
        Generate mock chat response with realistic JSON based on signature.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Response dict with 'content' containing JSON matching the signature
        """
        # Extract system message (contains signature format)
        system_message = ""
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
                break

        # Extract the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        # Generate JSON response based on both messages
        json_data = self._generate_response(user_message, system_message)

        # Return in Core SDK's expected format
        return {
            "id": f"mock_{hash(str(messages))}",
            "content": json.dumps(json_data),
            "role": "assistant",
            "model": kwargs.get("model", self.model),
            "created": 1701234567,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": len(json.dumps(json_data).split()),
                "total_tokens": 100 + len(json.dumps(json_data).split()),
            },
            "metadata": {},
        }

    def _generate_response(
        self, user_message: str, system_message: str = ""
    ) -> Dict[str, Any]:
        """
        Generate realistic JSON response based on message content.

        Analyzes the message to detect expected output fields and returns
        appropriate mock data.
        """
        user_lower = user_message.lower()

        # PRIORITY 1: Try to extract output format from system message (signature)
        # System message may have signature format like: "Outputs: proposal, reasoning"
        json_format = {}
        if system_message:
            json_format = self._extract_signature_outputs(system_message)

        # PRIORITY 2: If no signature outputs found, try extracting from user message
        # (Only for simple Q&A cases without formal signatures)
        if not json_format:
            json_format = self._extract_json_format(user_message)

            # If JSON was extracted with actual values (not just placeholders),
            # return it as-is for simple test cases
            if json_format and all(v for v in json_format.values()):
                # Check if all values are already filled (not null/empty)
                has_placeholder = any(
                    isinstance(v, str) and v in ["", "string", "value", "..."]
                    for v in json_format.values()
                )
                if not has_placeholder and len(json_format) <= 3:
                    # Small JSON with actual values - return as-is
                    return json_format

        # Generate response based on detected patterns
        response_data = {}

        # PRIORITY PATTERNS: Check these BEFORE generic patterns

        # Handoff pattern - Task Evaluation (HIGH PRIORITY - check first)
        if self._has_fields(json_format, ["can_handle", "complexity_score"]):
            # Determine can_handle based on task complexity hints in message
            complexity_hints = [
                "complex",
                "difficult",
                "advanced",
                "expert",
                "sophisticated",
                "challenging",
            ]
            simple_hints = ["simple", "basic", "easy", "trivial", "straightforward"]

            user_lower = user_message.lower()
            is_complex = any(hint in user_lower for hint in complexity_hints)
            is_simple = any(hint in user_lower for hint in simple_hints)

            # Default behavior: tier 1 can't handle complex, can handle simple
            # Extract tier_level from input if present
            tier_level = 1
            if "tier_level" in user_message or "tier level" in user_message:
                # Try to extract tier number
                import re

                tier_match = re.search(
                    r'tier[_\s]level["\s:]*(\d+)', user_message, re.IGNORECASE
                )
                if tier_match:
                    tier_level = int(tier_match.group(1))

            # Decision logic: tier 1 handles simple, tier 2+ handles complex
            if is_simple and not is_complex:
                response_data["can_handle"] = "yes"
                response_data["complexity_score"] = 0.2
                response_data["requires_tier"] = 1
            elif is_complex and not is_simple:
                if tier_level >= 2:
                    response_data["can_handle"] = "yes"
                    response_data["complexity_score"] = 0.8
                    response_data["requires_tier"] = tier_level
                else:
                    response_data["can_handle"] = "no"
                    response_data["complexity_score"] = 0.8
                    response_data["requires_tier"] = 2
            else:
                # Ambiguous or neutral - default to "can handle" for tier 2+
                if tier_level >= 2:
                    response_data["can_handle"] = "yes"
                    response_data["complexity_score"] = 0.5
                    response_data["requires_tier"] = tier_level
                else:
                    response_data["can_handle"] = "no"
                    response_data["complexity_score"] = 0.5
                    response_data["requires_tier"] = 2

            if "reasoning" in json_format:
                if response_data["can_handle"] == "yes":
                    response_data["reasoning"] = (
                        f"Task is within tier {tier_level} capability based on complexity analysis."
                    )
                else:
                    response_data["reasoning"] = (
                        f"Task exceeds tier {tier_level} capability, requires tier {response_data['requires_tier']}."
                    )

        # Handoff pattern - Task Execution (HIGH PRIORITY - check first)
        elif self._has_fields(
            json_format, ["result", "confidence", "execution_metadata"]
        ):
            response_data["result"] = "Task executed successfully at this tier level."
            response_data["confidence"] = 0.85
            response_data["execution_metadata"] = "{}"
            if "tier_level" in user_message:
                response_data["execution_metadata"] = (
                    '{"tier_level": 1, "execution_time": 0.5}'
                )

        # Simple Q&A
        elif self._has_fields(json_format, ["answer"]):
            response_data["answer"] = (
                "This is a comprehensive answer based on the provided context."
            )
            if "confidence" in json_format:
                response_data["confidence"] = 0.92
            if "reasoning" in json_format:
                response_data["reasoning"] = (
                    "Answer derived from analysis of the question and available context."
                )
            if "sources" in json_format:
                response_data["sources"] = ["source_1", "source_2"]

        # Distributed Retrieval (federated RAG)
        elif self._has_fields(json_format, ["documents", "source_id"]):
            response_data["documents"] = json.dumps(
                [
                    {
                        "id": "doc_1",
                        "title": "Document 1",
                        "content": "Content from source",
                    },
                    {
                        "id": "doc_2",
                        "title": "Document 2",
                        "content": "Additional content",
                    },
                ]
            )
            # Try to extract source_id from user message
            # User message format: ": value1\n\n: value2" (multi-line with each input on separate line)
            source_id = "Mock source id"
            try:
                # Split by lines and look for JSON object
                for line in user_message.split("\n"):
                    line = line.strip()
                    if line.startswith(":"):
                        line = line[1:].strip()  # Remove leading ':'
                    if line.startswith("{") and line.endswith("}"):
                        # Try to parse as JSON
                        source_data = json.loads(line)
                        if isinstance(source_data, dict) and "id" in source_data:
                            source_id = source_data["id"]
                            break
            except:
                pass
            response_data["source_id"] = source_id

        # ReAct (Reasoning + Acting)
        elif self._has_fields(json_format, ["thought", "action", "action_input"]):
            response_data["thought"] = (
                "I need to analyze this task and determine the best action to take."
            )
            response_data["action"] = "finish"
            response_data["action_input"] = {}
            if "confidence" in json_format:
                response_data["confidence"] = 0.85
            if "need_tool" in json_format:
                response_data["need_tool"] = False

        # Chain of Thought (step-by-step pattern step1, step2, ..., step5)
        elif any(f"step{i}" in json_format for i in range(1, 10)):
            # Find max step number
            max_step = 0
            for i in range(1, 10):
                if f"step{i}" in json_format:
                    max_step = i

            # Generate steps
            for i in range(1, max_step + 1):
                step_key = f"step{i}"
                if step_key in json_format:
                    if i == 1:
                        response_data[step_key] = (
                            "Problem understanding: Identify the key elements and requirements."
                        )
                    elif i == 2:
                        response_data[step_key] = (
                            "Data identification: Extract relevant data points and values."
                        )
                    elif i == 3:
                        response_data[step_key] = (
                            "Systematic calculation: Apply appropriate formulas and methods."
                        )
                    elif i == 4:
                        response_data[step_key] = (
                            "Solution verification: Check results for accuracy and consistency."
                        )
                    elif i == 5:
                        response_data[step_key] = (
                            "Final answer formulation: Present the complete solution clearly."
                        )
                    else:
                        response_data[step_key] = (
                            f"Step {i}: Additional reasoning and analysis."
                        )

            if "final_answer" in json_format:
                response_data["final_answer"] = (
                    "Based on step-by-step reasoning, the calculated result is correct."
                )
            if "confidence" in json_format:
                response_data["confidence"] = 0.88

        # Chain of Thought (thoughts array pattern)
        elif self._has_fields(json_format, ["thoughts", "final_answer"]):
            response_data["thoughts"] = [
                "Step 1: Analyze the question to understand requirements",
                "Step 2: Break down the problem into manageable parts",
                "Step 3: Synthesize findings into coherent answer",
            ]
            response_data["final_answer"] = (
                "Based on step-by-step reasoning, the answer is well-supported by analysis."
            )
            if "confidence" in json_format:
                response_data["confidence"] = 0.88

        # Proposal generation (consensus building)
        elif self._has_fields(json_format, ["proposal"]):
            response_data["proposal"] = (
                "Implement automated code review checks with AI assistance"
            )
            if "reasoning" in json_format:
                response_data["reasoning"] = (
                    "This approach combines automation with human oversight for quality."
                )

        # Task delegation (supervisor-worker)
        elif self._has_fields(json_format, ["tasks"]):
            response_data["tasks"] = json.dumps(
                [
                    {
                        "task_id": "task_1",
                        "description": "Process document 1",
                        "assigned_to": "worker_1",
                    },
                    {
                        "task_id": "task_2",
                        "description": "Process document 2",
                        "assigned_to": "worker_2",
                    },
                    {
                        "task_id": "task_3",
                        "description": "Process document 3",
                        "assigned_to": "worker_3",
                    },
                ]
            )
            if "delegation_plan" in json_format:
                response_data["delegation_plan"] = (
                    "Divided work into 3 parallel tasks for efficient processing."
                )
            if "reasoning" in json_format:
                response_data["reasoning"] = (
                    "Workload distributed evenly across available workers."
                )

        # Policy parsing (compliance monitoring)
        elif self._has_fields(json_format, ["parsed_policies"]):
            response_data["parsed_policies"] = json.dumps(
                {
                    "policy_1": {"type": "security", "rules": ["rule_1", "rule_2"]},
                    "policy_2": {"type": "compliance", "rules": ["rule_3"]},
                }
            )
            if "rules" in json_format:
                response_data["rules"] = json.dumps(
                    {
                        "rule_1": {
                            "severity": "high",
                            "description": "Security requirement",
                        },
                        "rule_2": {
                            "severity": "medium",
                            "description": "Access control",
                        },
                        "rule_3": {
                            "severity": "high",
                            "description": "Data protection",
                        },
                    }
                )

        # Proposal Creation
        elif self._has_fields(json_format, ["proposal", "rationale"]):
            response_data["proposal"] = (
                "This is a detailed proposal addressing the topic with comprehensive analysis."
            )
            response_data["rationale"] = (
                "Based on evaluation of requirements and constraints, this proposal provides the best approach."
            )

        # Voting/Review
        elif self._has_fields(json_format, ["vote"]):
            response_data["vote"] = "approve"
            if "reasoning" in json_format:
                response_data["reasoning"] = (
                    "The proposal addresses key concerns effectively and aligns with objectives."
                )
            if "feedback" in json_format:
                response_data["feedback"] = (
                    "The proposal addresses key concerns effectively."
                )
            if "confidence" in json_format:
                response_data["confidence"] = 0.85

        # Consensus Aggregation
        elif self._has_fields(json_format, ["consensus_reached", "final_decision"]):
            response_data["consensus_reached"] = "yes"
            response_data["final_decision"] = "Approved based on majority support"
            if "vote_summary" in json_format:
                response_data["vote_summary"] = (
                    "Majority of voters approved the proposal with high confidence."
                )

        # Decision/Consensus (generic)
        elif self._has_fields(json_format, ["decision"]):
            response_data["decision"] = "ACCEPT"
            if "rationale" in json_format:
                response_data["rationale"] = (
                    "Majority of reviewers approved the proposal."
                )
            if "consensus_level" in json_format:
                response_data["consensus_level"] = 0.75

        # Worker task execution
        elif self._has_fields(json_format, ["result", "status"]):
            response_data["result"] = (
                "Task completed successfully with expected output."
            )
            response_data["status"] = "completed"
            if "details" in json_format:
                response_data["details"] = (
                    "Processing completed according to specifications."
                )

        # Document analysis
        elif self._has_fields(json_format, ["analysis"]) and "document" in user_lower:
            response_data["analysis"] = (
                "The documents contain key information about market trends and customer preferences."
            )
            if "key_points" in json_format:
                response_data["key_points"] = [
                    "Market growth trends",
                    "Customer behavior patterns",
                    "Competitive landscape",
                ]
            if "summary" in json_format:
                response_data["summary"] = (
                    "Comprehensive analysis reveals positive market conditions."
                )

        # Source coordination (federated RAG)
        elif self._has_fields(json_format, ["selected_sources"]):
            response_data["selected_sources"] = json.dumps(
                [
                    {"source_id": "source_1", "priority": 1, "reason": "Most relevant"},
                    {
                        "source_id": "source_2",
                        "priority": 2,
                        "reason": "Complementary info",
                    },
                ]
            )
            if "selection_reasoning" in json_format:
                response_data["selection_reasoning"] = (
                    "Sources selected based on relevance and diversity."
                )

        # Query decomposition (multi-hop RAG)
        elif self._has_fields(json_format, ["sub_questions"]):
            response_data["sub_questions"] = json.dumps(
                [
                    "What is the main topic being discussed?",
                    "What are the key details and supporting information?",
                    "How do these elements relate to each other?",
                ]
            )
            if "reasoning" in json_format or "reasoning_steps" in json_format:
                reasoning_text = "Complex question broken into logical sub-components."
                if "reasoning" in json_format:
                    response_data["reasoning"] = reasoning_text
                if "reasoning_steps" in json_format:
                    response_data["reasoning_steps"] = json.dumps(
                        [
                            "Step 1: Identify main topic",
                            "Step 2: Extract key details",
                            "Step 3: Analyze relationships",
                        ]
                    )

        # Code generation
        elif self._has_fields(json_format, ["code"]):
            response_data["code"] = "def example_function(x, y):\n    return x + y"
            if "explanation" in json_format:
                response_data["explanation"] = "Simple function that adds two numbers."
            if "test_cases" in json_format:
                response_data["test_cases"] = [
                    "test_positive_numbers",
                    "test_zero",
                    "test_negative_numbers",
                ]
            if "documentation" in json_format:
                response_data["documentation"] = (
                    "Function documentation explaining parameters and return value."
                )
            if "confidence" in json_format:
                response_data["confidence"] = 0.9

        # Debate pattern - Argument construction
        elif self._has_fields(json_format, ["argument", "key_points"]):
            response_data["argument"] = (
                "This is a well-reasoned argument supporting the position."
            )
            response_data["key_points"] = json.dumps(
                [
                    "Point 1: Strong evidence supporting this position",
                    "Point 2: Historical precedent backs this view",
                    "Point 3: Practical considerations favor this approach",
                ]
            )
            if "evidence" in json_format:
                response_data["evidence"] = (
                    "Multiple studies and expert opinions support this position."
                )

        # Debate pattern - Rebuttal
        elif self._has_fields(json_format, ["rebuttal", "counterpoints"]):
            response_data["rebuttal"] = (
                "The opponent's argument has several flaws that undermine their position."
            )
            response_data["counterpoints"] = json.dumps(
                [
                    "Counterpoint 1: Opposing view lacks empirical support",
                    "Counterpoint 2: Logic is flawed in key areas",
                    "Counterpoint 3: Alternative explanation is more plausible",
                ]
            )
            if "strength" in json_format:
                response_data["strength"] = 0.75

        # Debate pattern - Judgment
        elif self._has_fields(json_format, ["decision", "winner"]):
            response_data["decision"] = "for"
            response_data["winner"] = "Proponent (FOR)"
            if "reasoning" in json_format:
                response_data["reasoning"] = (
                    "The proponent presented stronger evidence and more logical arguments."
                )
            if "confidence" in json_format:
                response_data["confidence"] = 0.82

        # Fill any missing fields with generic values
        if json_format:
            # Check if there are any fields in json_format that are not in response_data
            missing_fields = {
                k: v for k, v in json_format.items() if k not in response_data
            }
            if missing_fields:
                # Generate generic values for missing fields
                generic_values = self._fill_generic_response(missing_fields)
                response_data.update(generic_values)

        # If no specific pattern matched at all, fill with generic values
        if not response_data and json_format:
            response_data = self._fill_generic_response(json_format)

        # If still empty, provide minimal answer
        if not response_data:
            response_data = {"answer": "Mock response to the query."}

        return response_data

    def _extract_signature_outputs(self, system_message: str) -> Dict[str, Any]:
        """Extract output fields from Kaizen signature format in system message.

        Signature format looks like:
        "Outputs: proposal, reasoning"

        Returns a dictionary with those fields as keys (empty string values).
        """
        # Look for "Outputs:" line
        if "Outputs:" not in system_message:
            return {}

        try:
            # Extract the outputs line
            for line in system_message.split("\n"):
                if line.strip().startswith("Outputs:"):
                    # Get the part after "Outputs:"
                    outputs_str = line.split("Outputs:", 1)[1].strip()
                    # Split by comma to get individual fields
                    fields = [f.strip() for f in outputs_str.split(",")]
                    # Create dictionary with empty values
                    return {field: "" for field in fields if field}
        except Exception:
            pass

        return {}

    def _extract_json_format(self, message: str) -> Dict[str, Any]:
        """Extract JSON format specification from message."""
        # Look for ```json blocks
        if "```json" in message:
            try:
                json_start = message.index("```json") + 7
                json_end = message.index("```", json_start)
                json_str = message[json_start:json_end].strip()
                return json.loads(json_str)
            except (ValueError, json.JSONDecodeError):
                pass

        # Look for JSON-like structures in the message
        try:
            # Try to find anything that looks like JSON
            matches = re.findall(r"\{[^}]+\}", message)
            if matches:
                for match in matches:
                    try:
                        return json.loads(match)
                    except json.JSONDecodeError:
                        continue
        except:
            pass

        return {}

    def _has_fields(self, json_format: Dict, fields: List[str]) -> bool:
        """Check if JSON format has all specified fields."""
        return all(field in json_format for field in fields)

    def _fill_generic_response(self, json_format: Dict[str, Any]) -> Dict[str, Any]:
        """Fill response with generic values based on field names and types."""
        response = {}

        for key in json_format.keys():
            key_lower = key.lower()

            # Numeric fields (scores, confidence, quality, etc.)
            if any(
                term in key_lower
                for term in [
                    "score",
                    "confidence",
                    "quality",
                    "consistency",
                    "strength",
                ]
            ):
                response[key] = 0.85
            elif any(
                term in key_lower for term in ["count", "number", "deduplication"]
            ):
                response[key] = 3

            # Boolean-like fields
            elif any(term in key_lower for term in ["needs_", "is_", "has_", "can_"]):
                response[key] = "false"

            # List/array fields (returned as JSON strings)
            elif any(
                term in key_lower
                for term in [
                    "documents",
                    "articles",
                    "solutions",
                    "sources",
                    "keywords",
                    "violations",
                    "topics",
                    "entities",
                    "key_points",
                    "key_findings",
                    "sub_questions",
                    "reasoning_steps",
                    "chain_steps",
                    "supporting_evidence",
                    "selected_sources",
                    "conflicts",
                    "passed_checks",
                    "recommendations",
                    "charts",
                    "sections",
                    "counterpoints",
                ]
            ):
                if "questions" in key_lower:
                    response[key] = json.dumps(
                        [
                            "What is the main topic?",
                            "What are the key details?",
                            "How do they relate?",
                        ]
                    )
                elif "documents" in key_lower or "articles" in key_lower:
                    response[key] = json.dumps(
                        [
                            {
                                "id": "doc_1",
                                "content": "Document content 1",
                                "relevance": 0.9,
                            },
                            {
                                "id": "doc_2",
                                "content": "Document content 2",
                                "relevance": 0.8,
                            },
                        ]
                    )
                elif "violations" in key_lower:
                    response[key] = json.dumps(
                        [
                            {
                                "rule": "Rule 1",
                                "severity": "high",
                                "description": "Violation description",
                            }
                        ]
                    )
                elif "sections" in key_lower:
                    response[key] = json.dumps(
                        [
                            {"title": "Section 1", "content": "Section content"},
                            {"title": "Section 2", "content": "Section content"},
                        ]
                    )
                else:
                    response[key] = json.dumps(["item_1", "item_2", "item_3"])

            # Dict/object fields (returned as JSON strings)
            elif any(
                term in key_lower
                for term in [
                    "metadata",
                    "parsed_policies",
                    "rules",
                    "statistics",
                    "aggregations",
                    "retrieval_metadata",
                    "risk_assessment",
                ]
            ):
                if "policies" in key_lower or "rules" in key_lower:
                    response[key] = json.dumps(
                        {
                            "policy_1": {
                                "type": "security",
                                "rules": ["rule_1", "rule_2"],
                            },
                            "policy_2": {"type": "compliance", "rules": ["rule_3"]},
                        }
                    )
                elif "metadata" in key_lower:
                    response[key] = json.dumps(
                        {
                            "source": "mock_source",
                            "timestamp": "2025-10-03",
                            "confidence": 0.9,
                        }
                    )
                elif "statistics" in key_lower or "aggregations" in key_lower:
                    response[key] = json.dumps(
                        {"count": 100, "average": 75.5, "max": 95, "min": 50}
                    )
                else:
                    response[key] = json.dumps(
                        {"status": "success", "data": "mock_data"}
                    )

            # Status/category fields
            elif any(
                term in key_lower
                for term in [
                    "status",
                    "category",
                    "priority",
                    "urgency",
                    "tone",
                    "sentiment",
                    "strategy",
                    "routing_decision",
                    "assigned_team",
                    "decision",
                    "compliance_status",
                    "winner",
                ]
            ):
                if "priority" in key_lower or "urgency" in key_lower:
                    response[key] = "high"
                elif "status" in key_lower or "compliance" in key_lower:
                    response[key] = "compliant"
                elif "decision" in key_lower:
                    response[key] = "for"
                elif "winner" in key_lower:
                    response[key] = "Proponent (FOR)"
                elif "category" in key_lower:
                    response[key] = "general"
                elif "sentiment" in key_lower:
                    response[key] = "positive"
                elif "tone" in key_lower:
                    response[key] = "professional"
                else:
                    response[key] = "completed"

            # Long text fields
            elif any(
                term in key_lower
                for term in [
                    "answer",
                    "response",
                    "summary",
                    "report",
                    "reasoning",
                    "feedback",
                    "analysis",
                    "description",
                    "explanation",
                    "rationale",
                    "final_answer",
                    "aggregated_context",
                    "reasoning_chain",
                    "source_attribution",
                    "selection_reasoning",
                    "merged_documents",
                    "collected_data",
                    "processed_data",
                    "parsed_text",
                    "result",
                ]
            ):
                if "answer" in key_lower:
                    response[key] = (
                        "This is a comprehensive answer based on the available context and analysis."
                    )
                elif "report" in key_lower:
                    response[key] = (
                        "# Mock Report\n\nThis is a generated report with key findings and analysis."
                    )
                elif "reasoning" in key_lower or "rationale" in key_lower:
                    response[key] = (
                        "This decision is based on careful analysis of the available data and requirements."
                    )
                elif "summary" in key_lower:
                    response[key] = (
                        "Summary of key points and findings from the analysis."
                    )
                elif "feedback" in key_lower:
                    response[key] = (
                        "Positive feedback with suggestions for improvement."
                    )
                elif "analysis" in key_lower:
                    response[key] = (
                        "Comprehensive analysis reveals important patterns and insights."
                    )
                else:
                    response[key] = f"Mock {key.replace('_', ' ')} content"

            # Default string value
            else:
                response[key] = f"Mock {key.replace('_', ' ')}"

        return response


# Singleton instance for import
mock_provider = KaizenMockProvider()
