"""
Enhanced AI nodes with signature integration.

This module provides the enhanced node system for Kaizen, extending Core SDK nodes
with signature-based programming capabilities, automatic optimization hooks,
and enterprise AI features.
"""

import logging
import uuid
from typing import Any, Dict, Optional

from kailash.nodes.base import NodeParameter, register_node

from ..signatures import Signature
from .base_advanced import AINodeBase

logger = logging.getLogger(__name__)


@register_node()
class KaizenNode(AINodeBase):
    """
    Enhanced AI node with signature integration and optimization.

    Extends Core SDK Node with Kaizen-specific capabilities:
    - Signature-based programming
    - Automatic optimization hooks
    - Memory integration
    - Enterprise AI features

    Examples:
        Basic usage:
        >>> node = KaizenNode(model="gpt-4", temperature=0.7)
        >>> result = node.execute(prompt="Hello world")

        With signature:
        >>> signature = MySignature("text_processor")
        >>> node = KaizenNode(signature=signature, model="gpt-4")
        >>> result = node.execute(input_text="Process this")
    """

    def __init__(
        self,
        signature: Optional[Signature] = None,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        timeout: int = 30,
        optimization_enabled: bool = False,
        memory_enabled: bool = False,
        id: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize enhanced AI node.

        Args:
            signature: Optional signature for declarative programming
            model: LLM model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            optimization_enabled: Enable automatic optimization
            memory_enabled: Enable memory integration
            id: Optional node identifier (auto-generated if not provided)
            **kwargs: Additional configuration parameters
        """
        # Store Kaizen-specific configuration
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._optimization_enabled = optimization_enabled
        self._memory_enabled = memory_enabled

        # Generate id if not provided
        node_id = id or f"kaizen_node_{uuid.uuid4().hex[:8]}"

        # Initialize parent with signature
        super().__init__(
            id=node_id,
            signature=signature,
            optimization_enabled=optimization_enabled,
            memory_enabled=memory_enabled,
            **kwargs,
        )

        logger.info(f"Initialized KaizenNode with model: {model}")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """
        Define node parameters with signature awareness.

        Returns:
            Dictionary of parameter definitions
        """
        params = {
            "prompt": NodeParameter(
                name="prompt",
                type=str,
                description="Input prompt for the AI model",
                required=True,
                auto_map_primary=True,
            ),
            "model": NodeParameter(
                name="model",
                type=str,
                description="LLM model to use",
                required=False,
                default=self.model,
            ),
            "temperature": NodeParameter(
                name="temperature",
                type=float,
                description="Sampling temperature (0.0 to 2.0)",
                required=False,
                default=self.temperature,
            ),
            "max_tokens": NodeParameter(
                name="max_tokens",
                type=int,
                description="Maximum tokens to generate",
                required=False,
                default=self.max_tokens,
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                description="Request timeout in seconds",
                required=False,
                default=self.timeout,
            ),
        }

        # Add signature-specific parameters if available
        if self.signature:
            signature_inputs = self.signature.define_inputs()
            for name, type_def in signature_inputs.items():
                if name not in params:
                    params[name] = NodeParameter(
                        name=name,
                        type=type_def,
                        description=f"Signature input: {name}",
                        required=True,
                    )

        return params

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute node with signature validation and optimization hooks.

        Args:
            **kwargs: Input parameters including prompt and model config

        Returns:
            Dictionary containing the AI model response

        Raises:
            NodeExecutionError: If execution fails
        """
        # Pre-execution hook for optimization/validation
        inputs = self.pre_execution_hook(kwargs)

        # Extract parameters
        prompt = inputs.get("prompt", "")
        model = inputs.get("model", self.model)
        temperature = inputs.get("temperature", self.temperature)
        max_tokens = inputs.get("max_tokens", self.max_tokens)
        timeout = inputs.get("timeout", self.timeout)

        # Log execution
        self.logger.info(f"Executing KaizenNode with model: {model}")
        self.logger.debug(
            f"Prompt: {prompt[:100]}..." if len(prompt) > 100 else f"Prompt: {prompt}"
        )

        try:
            # Simulate AI model execution
            # In a real implementation, this would call the actual LLM
            response = self._execute_ai_model(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )

            # Prepare outputs
            outputs = {
                "response": response,
                "model_used": model,
                "prompt_length": len(prompt),
                "response_length": len(response),
            }

            # Post-execution hook for optimization/validation
            outputs = self.post_execution_hook(outputs)

            return outputs

        except Exception as e:
            self.logger.error(f"KaizenNode execution failed: {e}")
            raise

    def _execute_ai_model(
        self, prompt: str, model: str, temperature: float, max_tokens: int, timeout: int
    ) -> str:
        """
        Execute the AI model (placeholder implementation).

        In a real implementation, this would integrate with actual LLM providers
        like OpenAI, Anthropic, or local models.

        Args:
            prompt: Input prompt
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            timeout: Timeout in seconds

        Returns:
            AI model response
        """
        # Placeholder implementation for foundation
        # Real implementation would use LangChain, direct API calls, etc.

        response = f"AI Response to: '{prompt[:50]}...' using {model}"

        self.logger.debug(f"Generated response: {response}")
        return response

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Public execution method with full validation and error handling.

        This is the method users call to execute the node.

        Args:
            **kwargs: Input parameters

        Returns:
            Dictionary containing execution results
        """
        try:
            return self.run(**kwargs)
        except Exception as e:
            self.logger.error(f"Node execution failed: {e}")
            return {"error": str(e), "status": "failed"}

    def pre_execution_hook(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-execution hook with signature validation.

        Args:
            inputs: Input parameters for the node

        Returns:
            Processed input parameters
        """
        # Call signature validation if signature is present
        if self.signature and hasattr(self.signature, "validate_inputs"):
            self.signature.validate_inputs(inputs)
        return inputs

    def post_execution_hook(self, outputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Post-execution hook with signature validation.

        Args:
            outputs: Output results from the node

        Returns:
            Processed output results
        """
        # Call signature validation if signature is present
        if self.signature and hasattr(self.signature, "validate_outputs"):
            self.signature.validate_outputs(outputs)
        return outputs


@register_node()
class KaizenLLMAgentNode(KaizenNode):
    """
    Specialized Kaizen node that wraps Core SDK LLMAgentNode.

    This node provides seamless integration between Kaizen's signature-based
    programming and the existing LLMAgentNode functionality.
    """

    def __init__(self, **kwargs):
        """Initialize Kaizen LLM Agent node."""
        super().__init__(**kwargs)
        self.logger.info("Initialized KaizenLLMAgentNode")

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get parameters compatible with LLMAgentNode."""
        params = super().get_parameters()

        # Add LLMAgentNode-specific parameters
        params.update(
            {
                "system_message": NodeParameter(
                    name="system_message",
                    type=str,
                    description="System message for the AI agent",
                    required=False,
                    default="",
                ),
                "user_message": NodeParameter(
                    name="user_message",
                    type=str,
                    description="User message for the AI agent",
                    required=False,
                    default="",
                ),
                "provider": NodeParameter(
                    name="provider",
                    type=str,
                    description="AI provider (openai, anthropic, etc.)",
                    required=False,
                    default="openai",
                ),
            }
        )

        return params

    def run(self, **kwargs) -> Dict[str, Any]:
        """Execute using LLMAgentNode compatibility."""
        # Map Kaizen parameters to LLMAgentNode format
        mapped_inputs = self._map_to_llm_agent_format(kwargs)

        # Execute with parent implementation
        return super().run(**mapped_inputs)

    def _map_to_llm_agent_format(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map Kaizen inputs to LLMAgentNode format.

        Args:
            inputs: Kaizen-style inputs

        Returns:
            LLMAgentNode-compatible inputs
        """
        mapped = inputs.copy()

        # Handle prompt mapping
        if "prompt" in inputs and "user_message" not in inputs:
            mapped["user_message"] = inputs["prompt"]

        return mapped
