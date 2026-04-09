"""
AsyncSingleShotStrategy - Async one-pass execution strategy.

Provides async execution for improved performance:
- Non-blocking LLM calls
- Parallel processing support
- Better resource utilization
"""

import json
import logging
import re
from typing import Any, Dict, List

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)

# Allowlist regex for MCP tool names — validates before execution
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.:-]{0,127}$")


class AsyncSingleShotStrategy:
    """
    Async version of SingleShotStrategy for improved performance.

    Key improvements:
    - Async workflow execution
    - Non-blocking LLM calls
    - Parallel processing support
    - ~2x faster for single operations
    - ~5-10x faster when batching multiple requests
    """

    async def execute(
        self, agent: Any, inputs: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Execute single-shot strategy asynchronously.

        Args:
            agent: Agent instance
            inputs: Input parameters
            **kwargs: Additional parameters

        Returns:
            Dict[str, Any]: Execution results

        Example:
            >>> strategy = AsyncSingleShotStrategy()
            >>> result = await strategy.execute(agent, {'question': 'What is AI?'})
        """
        # Pre-execution
        preprocessed_inputs = self.pre_execute(inputs)

        # Build workflow
        workflow = self.build_workflow(agent)
        if workflow is None:
            return self._generate_skeleton_result(agent, inputs)

        # Execute asynchronously
        try:
            # Use AsyncLocalRuntime for true async execution (no thread pool)
            runtime = AsyncLocalRuntime()

            try:
                # Transform inputs to messages
                messages = self._create_messages_from_inputs(agent, preprocessed_inputs)
                workflow_params = {"agent_exec": {"messages": messages}}

                # True async execution - uses AsyncLocalRuntime.execute_workflow_async()
                # This provides 10-100x speedup for concurrent requests
                results, run_id = await runtime.execute_workflow_async(
                    workflow.build(), inputs=workflow_params
                )

                # MCP tool-call execution loop (#339)
                # After the LLM responds, check if it requested tool calls.
                # If the agent has MCP support, execute them and re-submit
                # results to the LLM for a follow-up response.
                max_tool_rounds = 5
                tool_round = 0
                while tool_round < max_tool_rounds:
                    # Extract tool_calls from the LLM response
                    tool_calls = self._extract_tool_calls(results)
                    if not tool_calls:
                        break

                    # Agent must support MCP tool execution
                    if not (
                        hasattr(agent, "has_mcp_support")
                        and agent.has_mcp_support()
                        and hasattr(agent, "execute_mcp_tool")
                    ):
                        logger.debug(
                            "LLM requested tool calls but agent has no MCP support; "
                            "returning raw response"
                        )
                        break

                    tool_round += 1
                    logger.info(
                        "tool_call_loop.round",
                        extra={
                            "round": tool_round,
                            "tool_count": len(tool_calls),
                        },
                    )

                    # Execute each tool call via the agent's MCP client
                    tool_result_messages = []
                    assistant_content = self._extract_assistant_content(results)

                    for tc in tool_calls:
                        tc_id = tc.get("id", f"call_{tool_round}")
                        func_info = tc.get("function", {})
                        tool_name = func_info.get("name", "")

                        # Validate tool name to prevent path traversal or injection
                        if not _TOOL_NAME_RE.match(tool_name):
                            logger.warning(
                                "tool_call_loop.invalid_tool_name",
                                extra={"tool_name_length": len(tool_name)},
                            )
                            tool_result_messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc_id,
                                    "content": json.dumps(
                                        {
                                            "error": "Invalid tool name",
                                            "status": "failed",
                                        }
                                    ),
                                }
                            )
                            continue

                        try:
                            tool_args = json.loads(func_info.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            tool_args = {}

                        try:
                            tool_result = await agent.execute_mcp_tool(
                                tool_name, tool_args
                            )
                            tool_content = json.dumps(tool_result)
                        except Exception as exc:
                            logger.warning(
                                "tool_call_loop.tool_error",
                                extra={
                                    "tool": tool_name,
                                    "error": str(exc),
                                },
                            )
                            tool_content = json.dumps(
                                {"error": "Tool execution failed", "status": "failed"}
                            )

                        tool_result_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": tool_content,
                            }
                        )

                    # Build updated messages: original + assistant w/ tool_calls + tool results
                    updated_messages = list(messages)
                    updated_messages.append(
                        {
                            "role": "assistant",
                            "content": assistant_content,
                            "tool_calls": tool_calls,
                        }
                    )
                    updated_messages.extend(tool_result_messages)

                    # Re-execute workflow with updated conversation
                    workflow = self.build_workflow(agent)
                    if workflow is None:
                        break
                    workflow_params = {"agent_exec": {"messages": updated_messages}}
                    runtime_next = AsyncLocalRuntime()
                    try:
                        results, run_id = await runtime_next.execute_workflow_async(
                            workflow.build(), inputs=workflow_params
                        )
                    finally:
                        runtime_next.close()

                    # Update messages for potential next round
                    messages = updated_messages

            finally:
                runtime.close()

            # Parse result
            parsed_result = self.parse_result(results)

            # Post-execution
            final_result = self.post_execute(parsed_result)

            # Extract signature output fields
            if hasattr(agent.signature, "output_fields"):
                output_result = {}
                all_fields_found = True

                for field_name in agent.signature.output_fields:
                    if field_name in final_result:
                        output_result[field_name] = final_result[field_name]
                    elif "response" in final_result and isinstance(
                        final_result["response"], dict
                    ):
                        if field_name in final_result["response"]:
                            output_result[field_name] = final_result["response"][
                                field_name
                            ]
                        else:
                            all_fields_found = False
                    else:
                        all_fields_found = False

                # Only return extracted fields if ALL required fields were found
                # Otherwise return final_result (has "response" key, skips validation)
                if output_result and all_fields_found:
                    return output_result

            return final_result

        except Exception as e:
            # Error handling - propagate real errors, only use skeleton for missing providers
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
            return {
                "error": error_msg,
                "status": "failed",
                "recovery_suggestions": self._get_recovery_suggestions(error_msg),
            }

    def build_workflow(self, agent: Any) -> WorkflowBuilder:
        """Build workflow for execution."""
        if not hasattr(agent, "workflow_generator"):
            logger.warning("Agent missing workflow_generator attribute")
            return None

        try:
            workflow = agent.workflow_generator.generate_signature_workflow()
            return workflow
        except Exception as e:
            # FIX BUG #2: Log workflow generation failures instead of silently returning None
            logger.error(f"Workflow generation failed: {e}", exc_info=True)
            return None

    def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Preprocess inputs before execution."""
        return inputs

    def parse_result(self, raw_result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw LLM output."""
        import json
        import re

        if "agent_exec" in raw_result:
            llm_output = raw_result["agent_exec"]
        else:
            llm_output = raw_result

        if isinstance(llm_output, dict) and "response" in llm_output:
            response = llm_output["response"]

            content = None
            if isinstance(response, dict) and "content" in response:
                content = response["content"]
            elif isinstance(response, str):
                content = response
            else:
                content = str(response)

            if content:
                # FIX: If content is already a dict (from OpenAI structured outputs),
                # return it directly without attempting string operations
                if isinstance(content, dict):
                    return content

                # String content - clean and parse JSON
                content = re.sub(r"```json\s*", "", content)
                content = re.sub(r"```\s*$", "", content)
                content = content.strip()

                try:
                    parsed = json.loads(content)
                    # FIX: If JSON parsing returns a primitive (int, str, bool, float, list),
                    # wrap it to ensure proper downstream handling. This handles cases where
                    # LLMs return simple values like "4" instead of {"answer": "4"}.
                    # The "response" key triggers validation bypass in base_agent.py.
                    if not isinstance(parsed, dict):
                        return {"response": parsed, "raw_content": content}
                    return parsed
                except json.JSONDecodeError:
                    return {"response": content, "error": "JSON_PARSE_FAILED"}

        return raw_result

    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process final result."""
        return result

    def _create_messages_from_inputs(
        self, agent: Any, inputs: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Transform signature inputs into OpenAI message format."""
        message_parts = []

        if hasattr(agent.signature, "input_fields"):
            for field_name, field_info in agent.signature.input_fields.items():
                if field_name in inputs and inputs[field_name]:
                    desc = field_info.get("desc", field_name.title())
                    value = inputs[field_name]
                    message_parts.append(f"{desc}: {value}")
        else:
            message_parts = [f"{k}: {v}" for k, v in inputs.items() if v]

        content = "\n\n".join(message_parts) if message_parts else "No input provided"

        # FIX: If using response_format with type=json_object (strict=False),
        # OpenAI requires "json" to be mentioned in messages
        if hasattr(agent, "config") and hasattr(agent.config, "response_format"):
            response_format = agent.config.response_format
            if (
                isinstance(response_format, dict)
                and response_format.get("type") == "json_object"
            ):
                content += "\n\nPlease respond in JSON format."

        return [{"role": "user", "content": content}]

    def _generate_skeleton_result(
        self, agent: Any, inputs: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate typed skeleton result."""
        result = {}

        if hasattr(agent.signature, "output_fields"):
            for field_name, field_info in agent.signature.output_fields.items():
                field_type = field_info.get("type", str)

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
                    result[field_name] = f"Placeholder result for {field_name}"

        return result

    def _get_recovery_suggestions(self, error_msg: str) -> List[str]:
        """Get context-aware recovery suggestions."""
        suggestions = []

        if "Provider" in error_msg and "not available" in error_msg:
            if "openai" in error_msg.lower():
                suggestions.append("Install OpenAI: pip install openai")
                suggestions.append("Set API key: export OPENAI_API_KEY=your_key")
            elif "anthropic" in error_msg.lower():
                suggestions.append("Install Anthropic: pip install anthropic")
                suggestions.append("Set API key: export ANTHROPIC_API_KEY=your_key")

        if "timeout" in error_msg.lower():
            suggestions.append("Increase timeout in config")
            suggestions.append("Check network connectivity")

        if "rate limit" in error_msg.lower():
            suggestions.append("Wait before retrying")
            suggestions.append("Use exponential backoff")
            suggestions.append("Check your API usage limits")

        if not suggestions:
            suggestions.append("Check error logs for details")
            suggestions.append("Verify configuration settings")

        return suggestions

    # ------------------------------------------------------------------
    # Tool-call helpers (#339)
    # ------------------------------------------------------------------

    def _extract_tool_calls(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool_calls from workflow results if present.

        The LLMAgentNode stores its output under ``results["agent_exec"]``
        with the LLM response nested at ``["response"]``.  The response dict
        contains a ``tool_calls`` list when the model decides to invoke tools.

        Returns:
            List of tool-call dicts (OpenAI format), or empty list.
        """
        agent_output = results.get("agent_exec", {})
        if not isinstance(agent_output, dict):
            return []
        response = agent_output.get("response", {})
        if not isinstance(response, dict):
            return []
        tool_calls = response.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            return []
        return tool_calls

    def _extract_assistant_content(self, results: Dict[str, Any]) -> str:
        """Extract the assistant's text content from workflow results.

        Used when building the conversation history that includes the
        assistant message alongside its tool_calls.

        Returns:
            The content string, or empty string if absent.
        """
        agent_output = results.get("agent_exec", {})
        if not isinstance(agent_output, dict):
            return ""
        response = agent_output.get("response", {})
        if not isinstance(response, dict):
            return ""
        content = response.get("content", "")
        if content is None:
            return ""
        return str(content)
