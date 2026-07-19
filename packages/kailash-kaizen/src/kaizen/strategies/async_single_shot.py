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
from typing import Any, Dict, List, Optional

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.core.deprecation import deprecated
from kaizen.nodes.ai.audio_utils import (
    encode_audio,
    get_audio_media_type,
    validate_audio_size,
)
from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error
from kaizen.nodes.ai.vision_utils import (
    encode_image,
    get_media_type,
    validate_image_size,
)

logger = logging.getLogger(__name__)

# File-path keys a high-level multimodal input dict may carry (a local path,
# NOT a data-URI or remote URL).
_FILE_PATH_KEYS = (
    "path",
    "file_path",
    "file",
    "image_path",
    "audio_path",
    "image",
    "audio",
)

# Allowlist regex for MCP tool names — validates before execution
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.:-]{0,127}$")


def _classify_input_value(
    value: Any, desc: str, field_info: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Classify an input value as a multimodal content part, or None for text.

    Returns a content-part dict (e.g. ``{"type": "image_url", ...}``) when the
    value is binary data or an already-structured content part.  Returns None
    when the value should be rendered as plain text.

    This function is provider-agnostic -- it produces the multimodal content
    list format understood by all major LLM providers.
    """
    import base64

    # Structured content-part dict. Three cases handled here:
    #  1. file-path / high-level image dict -> normalize to an image_url data-URI
    #  2. file-path / high-level audio dict -> normalize to an input_audio block
    #  3. already-wire-shaped dict (no file-path key) -> pass through verbatim
    # Delegates ALL encoding/validation to the surviving vision/audio primitives.
    if isinstance(value, dict) and "type" in value:
        dtype = value.get("type")

        # Locate a local file path (a str that is not a data-URI / remote URL).
        file_path = None
        for _k in _FILE_PATH_KEYS:
            _v = value.get(_k)
            if (
                isinstance(_v, str)
                and _v
                and not _v.startswith(("data:", "http://", "https://"))
            ):
                file_path = _v
                break

        if file_path is not None and dtype in ("image", "image_url"):
            ok, err = validate_image_size(file_path)
            if not ok:
                raise ValueError(
                    f"image input {file_path!r} failed size validation: {err}"
                )
            b64_data = encode_image(file_path)
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{get_media_type(file_path)};base64,{b64_data}",
                },
            }

        if file_path is not None and dtype in ("audio", "input_audio"):
            ok, err = validate_audio_size(file_path)
            if not ok:
                raise ValueError(
                    f"audio input {file_path!r} failed size validation: {err}"
                )
            b64_data = encode_audio(file_path)
            # Normalize the media-type subtype to the provider wire format
            # (input_audio expects e.g. mp3 / wav / m4a, not the MIME subtype
            # mpeg / mp4).
            subtype = get_audio_media_type(file_path).split("/", 1)[-1]
            wire_format = {
                "mpeg": "mp3",
                "mp4": "m4a",
                "x-ms-wma": "wma",
            }.get(subtype, subtype)
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": b64_data,
                    "format": wire_format,
                },
            }

        # Already-wire-shaped (or otherwise pre-built) content part.
        return value

    # Raw bytes -- detect media type and build a content part
    if isinstance(value, (bytes, bytearray)):
        media_type = (
            field_info.get("media_type", "") if isinstance(field_info, dict) else ""
        )
        if not media_type:
            media_type = _guess_media_type(value)

        b64_data = base64.b64encode(value).decode("ascii")

        if media_type.startswith("audio/"):
            return {
                "type": "input_audio",
                "input_audio": {
                    "data": b64_data,
                    "format": media_type.split("/", 1)[1],
                },
            }
        # Images (and unknown binary) use the image_url data-URI form
        return {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{b64_data}",
            },
        }

    return None


def _guess_media_type(data: bytes) -> str:
    """Best-effort media type detection from magic bytes.

    Falls back to ``application/octet-stream`` when the format is unknown.
    """
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    # MP3 sync word (0xFFE0-0xFFFF) or ID3 tag
    if data[:3] == b"ID3" or (
        len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
    ):
        return "audio/mpeg"
    # OGG container (Vorbis / Opus)
    if data[:4] == b"OggS":
        return "audio/ogg"
    # WAV
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    # FLAC
    if data[:4] == b"fLaC":
        return "audio/flac"
    return "application/octet-stream"


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
            # Use AsyncLocalRuntime for true async execution (no thread pool).
            # `async with` invokes __aenter__/__aexit__ so the runtime is closed
            # cleanly on every exit path, including the inner break out of the
            # tool-call loop and exception propagation up to the outer `except`.
            async with AsyncLocalRuntime() as runtime:
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
                    async with AsyncLocalRuntime() as runtime_next:
                        results, run_id = await runtime_next.execute_workflow_async(
                            workflow.build(), inputs=workflow_params
                        )

                    # Update messages for potential next round
                    messages = updated_messages

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
            # (workflow generation can invoke an LLM whose error carries a
            # credential; sanitize + drop exc_info — #1720 creds-in-logs sweep).
            logger.error(
                "Workflow generation failed: %s", sanitize_provider_error(e, "LLM")
            )
            return None

    @deprecated(
        "Use composition wrappers (MonitoredAgent, GovernedAgent, StreamingAgent) instead.",
        since="2.5.0",
    )
    def pre_execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Preprocess inputs before execution.

        .. deprecated:: 2.5.0
            Use composition wrappers (MonitoredAgent, GovernedAgent, StreamingAgent) instead.
        """
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

    @deprecated(
        "Use composition wrappers (MonitoredAgent, GovernedAgent, StreamingAgent) instead.",
        since="2.5.0",
    )
    def post_execute(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process final result.

        .. deprecated:: 2.5.0
            Use composition wrappers (MonitoredAgent, GovernedAgent, StreamingAgent) instead.
        """
        return result

    def _create_messages_from_inputs(
        self, agent: Any, inputs: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Transform signature inputs into OpenAI message format.

        Handles both text-only inputs (flat string content) and multimodal
        inputs containing bytes or structured content parts (content list).
        Binary data (bytes) is converted to the provider-agnostic multimodal
        content list format rather than being coerced to a string
        representation like ``b'\\xff\\xfb...'``.
        """
        text_parts: List[str] = []
        multimodal_parts: List[Dict[str, Any]] = []
        has_multimodal = False

        if hasattr(agent.signature, "input_fields"):
            for field_name, field_info in agent.signature.input_fields.items():
                if field_name in inputs and inputs[field_name] is not None:
                    desc = field_info.get("desc", field_name.title())
                    value = inputs[field_name]
                    content_part = _classify_input_value(value, desc, field_info)
                    if content_part is not None:
                        has_multimodal = True
                        multimodal_parts.append(content_part)
                    else:
                        text_parts.append(f"{desc}: {value}")
        else:
            for k, v in inputs.items():
                if v is not None:
                    content_part = _classify_input_value(v, k.title(), {})
                    if content_part is not None:
                        has_multimodal = True
                        multimodal_parts.append(content_part)
                    else:
                        text_parts.append(f"{k}: {v}")

        # Build the json_object suffix if needed
        json_suffix = ""
        if hasattr(agent, "config") and hasattr(agent.config, "response_format"):
            response_format = agent.config.response_format
            if (
                isinstance(response_format, dict)
                and response_format.get("type") == "json_object"
            ):
                json_suffix = "\n\nPlease respond in JSON format."

        if has_multimodal:
            # Build a content list combining text and multimodal parts
            content_list: List[Dict[str, Any]] = []
            if text_parts:
                combined_text = "\n\n".join(text_parts) + json_suffix
                content_list.append({"type": "text", "text": combined_text})
            elif json_suffix:
                content_list.append(
                    {"type": "text", "text": "No text input provided" + json_suffix}
                )
            content_list.extend(multimodal_parts)
            return [{"role": "user", "content": content_list}]

        # Common case: all inputs are text — flat string content
        content = "\n\n".join(text_parts) if text_parts else "No input provided"
        content += json_suffix

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
