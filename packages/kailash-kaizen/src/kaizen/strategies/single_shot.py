"""
SingleShotStrategy - One-pass execution strategy.

This module implements the SingleShotStrategy for agents that execute in
a single pass without feedback loops or iterations.

Use Cases:
- Q&A agents: Answer question in one pass
- Chain-of-Thought: Generate reasoning and answer in one pass
- Simple classification/extraction tasks

References:
- ADR-006: Agent Base Architecture design (Strategy Pattern section)
- TODO-157: Task 1.5, Phase 2 Tasks 2.7-2.11
- Existing patterns: SimpleQA, ChainOfThought agents

Author: Kaizen Framework Team
Created: 2025-10-01
Updated: 2025-10-01 (Phase 2 Implementation)
"""

from typing import Any, Dict, List

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder


class SingleShotStrategy:
    """
    Single-pass execution strategy.

    Executes the agent in one pass:
    1. Pre-execution hook (extension point)
    2. Single LLM call via workflow
    3. Parse result (extension point)
    4. Post-execution hook (extension point)
    5. Return result

    No feedback loops, no iterations, no cycles.

    Extension Points:
    - pre_execute(inputs): Preprocess inputs before execution
    - parse_result(raw_result): Parse raw LLM output
    - post_execute(result): Post-process final result

    Example Usage:
        >>> from kaizen.strategies.single_shot import SingleShotStrategy
        >>> from kaizen.core.base_agent import BaseAgent
        >>> from kaizen.core.config import BaseAgentConfig
        >>>
        >>> config = BaseAgentConfig(strategy_type="single_shot")
        >>> strategy = SingleShotStrategy()
        >>> agent = BaseAgent(config=config, strategy=strategy)
        >>>
        >>> result = strategy.execute(agent, {'question': 'What is 2+2?'})
        >>> print(result)
        {'answer': '4'}

    Notes:
    - Full implementation (Phase 2, Tasks 2.7-2.11)
    - Uses WorkflowGenerator for Core SDK integration
    - Supports Q&A and Chain-of-Thought patterns
    """

    def __init__(self):
        """Initialize SingleShotStrategy."""
        pass

    def execute(
        self,
        agent: Any,  # BaseAgent when fully implemented
        inputs: Dict[str, Any],
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Execute single-pass strategy.

        Execution Flow:
        1. Call pre_execute() extension point
        2. Build workflow using build_workflow()
        3. Execute workflow via LocalRuntime
        4. Call parse_result() extension point
        5. Call post_execute() extension point
        6. Return final result

        Args:
            agent: The agent instance
            inputs: Input parameters
            **kwargs: Additional parameters

        Returns:
            Dict[str, Any]: Execution results

        Example:
            >>> result = strategy.execute(agent, {'question': 'What is AI?'})
            >>> print(result['answer'])
            'Artificial Intelligence is...'
        """
        # Task 2.10: Extension point - pre-execution
        preprocessed_inputs = self.pre_execute(inputs)

        # Task 2.7: Build workflow
        workflow = self.build_workflow(agent)
        if workflow is None:
            # Fallback for skeleton mode
            return self._generate_skeleton_result(agent, inputs)

        # Task 2.9: Execute workflow via Core SDK
        try:
            # Transform signature inputs into LLMAgentNode format
            # LLMAgentNode expects "messages" parameter in OpenAI format
            messages = self._create_messages_from_inputs(agent, preprocessed_inputs)

            # Prepare parameters for workflow execution
            workflow_params = {
                "agent_exec": {"messages": messages}  # node_id from workflow generation
            }

            # Execute workflow with context manager for proper resource cleanup
            with LocalRuntime() as runtime:
                results, run_id = runtime.execute(
                    workflow.build(), parameters=workflow_params
                )

            # Task 2.10: Extension point - parse result
            parsed_result = self.parse_result(results)

            # Task 2.11: Extension point - post-execution
            final_result = self.post_execute(parsed_result)

            # Task 2.10: Extract signature output fields
            if hasattr(agent.signature, "output_fields"):
                output_result = {}
                for field_name in agent.signature.output_fields:
                    if field_name in final_result:
                        output_result[field_name] = final_result[field_name]
                    elif "response" in final_result and isinstance(
                        final_result["response"], dict
                    ):
                        # Try to extract from nested response
                        if field_name in final_result["response"]:
                            output_result[field_name] = final_result["response"][
                                field_name
                            ]

                # If we extracted fields, use them; otherwise return full result
                if output_result:
                    return output_result

            return final_result

        except Exception as e:
            # Task 2.10: Error handling - propagate real errors, only use skeleton for missing providers
            error_msg = str(e)

            # Only use skeleton fallback for truly missing providers (e.g., in unit tests without API keys)
            # NOT for API errors which should be propagated to reveal real issues
            is_api_error = any(
                term in error_msg.lower()
                for term in ["api error", "api key", "401", "403", "400", "500"]
            )
            is_missing_provider = (
                "not available" in error_msg and "Provider" not in error_msg
            )

            if is_missing_provider and not is_api_error:
                # Provider genuinely not configured (e.g., unit test without API key)
                import logging

                logging.getLogger(__name__).warning(
                    f"Using skeleton result due to missing provider: {error_msg}"
                )
                return self._generate_skeleton_result(agent, inputs)

            # For all other errors (including API errors), return error info to reveal issues
            return {"error": error_msg, "status": "failed"}

    def build_workflow(self, agent: Any) -> WorkflowBuilder:
        """
        Build workflow for single-shot execution.

        Creates a simple workflow with:
        1. LLMAgentNode for agent execution
        2. Input/output mapping from signature
        3. No cycles or feedback loops

        Args:
            agent: The agent instance

        Returns:
            WorkflowBuilder: Single-shot workflow

        Core SDK Pattern:
            Uses WorkflowGenerator.generate_signature_workflow() which creates:
            workflow.add_node('LLMAgentNode', 'agent_exec', {
                'model': agent.config.model,
                'provider': agent.config.llm_provider,
                'temperature': agent.config.temperature,
                'system_prompt': self._generate_system_prompt(),
            })

        Example:
            >>> workflow = strategy.build_workflow(agent)
            >>> built = workflow.build()
            >>> from kailash.runtime.local import LocalRuntime
            >>> runtime = LocalRuntime()
            >>> results, run_id = runtime.execute(built)
        """
        # Task 2.7: Use WorkflowGenerator for signature-based workflow
        if not hasattr(agent, "workflow_generator"):
            return None

        try:
            # Use the agent's workflow generator
            workflow = agent.workflow_generator.generate_signature_workflow()
            return workflow
        except Exception as e:
            # Log the actual error to prevent silent failures
            import logging

            logging.getLogger(__name__).error(f"Workflow generation failed: {e}")
            return None

    # Task 2.11: Extension Points

    def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extension point: Preprocess inputs before execution.

        Override in subclasses to customize input preprocessing.

        Args:
            inputs: Raw input parameters

        Returns:
            Dict[str, Any]: Preprocessed inputs

        Example:
            >>> class CustomStrategy(SingleShotStrategy):
            ...     def pre_execute(self, inputs):
            ...         inputs['timestamp'] = time.time()
            ...         return inputs
        """
        return inputs

    def parse_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extension point: Parse raw LLM output.

        Extracts and parses the JSON response from LLMAgentNode output.

        Args:
            raw_result: Raw result from workflow execution (from LLMAgentNode)

        Returns:
            Dict[str, Any]: Parsed result matching signature output fields

        Example:
            >>> class CustomStrategy(SingleShotStrategy):
            ...     def parse_result(self, raw_result):
            ...         # Extract JSON from text
            ...         return json.loads(raw_result['response'])
        """
        import json
        import re

        # Handle workflow execution results
        # LocalRuntime returns results as: {node_id: node_output, ...}
        # We need to extract the LLMAgentNode output
        if "agent_exec" in raw_result:
            llm_output = raw_result["agent_exec"]
        else:
            llm_output = raw_result

        # LLMAgentNode returns: {"success": bool, "response": {...}, ...}
        if isinstance(llm_output, dict) and "response" in llm_output:
            response = llm_output["response"]

            # Extract content from response
            content = None
            if isinstance(response, dict) and "content" in response:
                content = response["content"]
            elif isinstance(response, str):
                content = response
            else:
                content = str(response)

            # Try to parse JSON from content
            if content:
                # FIX: If content is already a dict (from OpenAI structured outputs),
                # check if it needs wrapping for validation bypass
                if isinstance(content, dict):
                    # FIX v0.9.6: If dict has ONLY a "content" key, it's a raw LLM response
                    # that doesn't match expected signature fields. Wrap it to bypass validation.
                    # This handles cases where LLM returns {"content": "..."} instead of {"answer": "..."}
                    if list(content.keys()) == ["content"]:
                        return {
                            "response": content["content"],
                            "raw_content": str(content),
                        }
                    return content

                # String content - clean and parse JSON
                # Remove markdown code blocks if present
                content = re.sub(r"```json\s*", "", content)
                content = re.sub(r"```\s*$", "", content)
                content = content.strip()

                try:
                    # Parse JSON
                    parsed = json.loads(content)
                    # FIX: If JSON parsing returns a primitive (int, str, bool, float, list),
                    # wrap it to ensure proper downstream handling. This handles cases where
                    # LLMs return simple values like "4" instead of {"answer": "4"}.
                    # The "response" key triggers validation bypass in base_agent.py.
                    if not isinstance(parsed, dict):
                        return {"response": parsed, "raw_content": content}
                    # FIX v0.9.6: If parsed dict has ONLY a "content" key, wrap it
                    # This handles JSON like '{"content": "The answer is 42"}'
                    if list(parsed.keys()) == ["content"]:
                        return {"response": parsed["content"], "raw_content": content}
                    return parsed
                except json.JSONDecodeError:
                    # If JSON parsing fails, return content as-is with fallback structure
                    return {"response": content, "error": "JSON_PARSE_FAILED"}

        # Fallback: return raw result
        return raw_result

    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extension point: Post-process final result.

        Override in subclasses to customize post-processing.

        Args:
            result: Parsed result

        Returns:
            Dict[str, Any]: Final result

        Example:
            >>> class CustomStrategy(SingleShotStrategy):
            ...     def post_execute(self, result):
            ...         result['strategy'] = 'single_shot'
            ...         return result
        """
        return result

    # Helper methods

    def _create_messages_from_inputs(
        self, agent: Any, inputs: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """
        Transform signature inputs into OpenAI message format.

        Converts structured signature inputs (like question, context, etc.) into
        the message format expected by LLMAgentNode.

        Args:
            agent: Agent instance with signature
            inputs: Dict of signature input values

        Returns:
            List[Dict[str, str]]: Messages in OpenAI format

        Example:
            >>> inputs = {"question": "What is AI?", "context": "Machine learning context"}
            >>> messages = strategy._create_messages_from_inputs(agent, inputs)
            >>> # Returns: [{"role": "user", "content": "Question: What is AI?\n\nContext: Machine learning context"}]
        """
        # Build user message content from signature inputs
        message_parts = []

        if hasattr(agent.signature, "input_fields"):
            for field_name, field_info in agent.signature.input_fields.items():
                if field_name in inputs and inputs[field_name]:
                    # Get field description for context
                    desc = field_info.get("desc", field_name.title())
                    value = inputs[field_name]

                    # Format field into message
                    message_parts.append(f"{desc}: {value}")
        else:
            # Fallback: just join all input values
            message_parts = [f"{k}: {v}" for k, v in inputs.items() if v]

        # Combine into single user message
        content = "\n\n".join(message_parts) if message_parts else "No input provided"

        # FIX: If using response_format with type=json_object (strict=False),
        # OpenAI requires "json" to be mentioned in messages
        # Check if agent config has provider_config with type: json_object
        if hasattr(agent, "config") and hasattr(agent.config, "provider_config"):
            provider_config = agent.config.provider_config
            if (
                isinstance(provider_config, dict)
                and provider_config.get("type") == "json_object"
            ):
                content += "\n\nPlease respond in JSON format."

        return [{"role": "user", "content": content}]

    def _generate_skeleton_result(
        self, agent: Any, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate skeleton result when workflow is unavailable.

        Creates properly typed placeholder values based on signature field types.
        """
        result = {}

        # For each output field in signature, create a typed placeholder response
        if hasattr(agent.signature, "output_fields"):
            for field_name, field_info in agent.signature.output_fields.items():
                # Get the field type
                field_type = field_info.get("type", str)

                # Generate typed placeholder based on field type
                if field_type == float:
                    result[field_name] = 0.0
                elif field_type == int:
                    result[field_name] = 0
                elif field_type == bool:
                    result[field_name] = False
                elif field_type == list:
                    result[field_name] = []
                elif field_type == dict:
                    result[field_name] = {}
                else:
                    # Default to string placeholder
                    result[field_name] = f"Placeholder result for {field_name}"
        else:
            # Try to extract from signature class attributes
            if hasattr(agent.signature, "__annotations__"):
                for attr_name, attr_type in agent.signature.__annotations__.items():
                    # Check if it's an OutputField
                    attr_value = getattr(agent.signature, attr_name, None)
                    if attr_value is not None and hasattr(attr_value, "__class__"):
                        if "OutputField" in str(attr_value.__class__):
                            # Generate typed placeholder
                            if attr_type == float:
                                result[attr_name] = 0.0
                            elif attr_type == int:
                                result[attr_name] = 0
                            elif attr_type == bool:
                                result[attr_name] = False
                            elif attr_type == list:
                                result[attr_name] = []
                            elif attr_type == dict:
                                result[attr_name] = {}
                            else:
                                result[attr_name] = (
                                    f"Placeholder result for {attr_name}"
                                )

            # Fallback
            if not result:
                result["answer"] = "Simple strategy execution"

        return result
