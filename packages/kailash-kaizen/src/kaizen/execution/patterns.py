"""
Pattern-specific execution logic for agent execution patterns.

This module provides specialized executors for different execution patterns
like Chain-of-Thought and ReAct, integrating with the signature system.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from .parser import StructuredOutputParser

logger = logging.getLogger(__name__)


class PatternExecutor(ABC):
    """Base class for pattern-specific execution logic."""

    def __init__(self, name: str):
        self.name = name
        self.parser = StructuredOutputParser()

    @abstractmethod
    def generate_enhanced_prompt(self, signature: Any, inputs: Dict[str, Any]) -> str:
        """Generate pattern-specific enhanced prompt."""
        pass

    @abstractmethod
    def get_enhanced_parameters(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """Get pattern-specific workflow parameters."""
        pass

    def parse_pattern_response(
        self, llm_result: Dict[str, Any], signature: Any
    ) -> Dict[str, Any]:
        """Parse LLM response for this pattern."""
        return self.parser.parse_signature_response(llm_result, signature)


class ChainOfThoughtExecutor(PatternExecutor):
    """Executor for Chain-of-Thought reasoning pattern."""

    def __init__(self):
        super().__init__("chain_of_thought")

    def generate_enhanced_prompt(self, signature: Any, inputs: Dict[str, Any]) -> str:
        """Generate CoT-enhanced prompt."""
        input_text = self._format_inputs(inputs)
        output_fields = self._get_output_fields(signature)

        template = f"""Think step by step to solve this problem carefully and systematically.

{input_text}

I need to provide structured output with these fields: {', '.join(output_fields)}

Let me work through this step by step:

Step 1: Problem Analysis
First, I'll carefully analyze what is being asked and identify the key requirements.
Analysis: Let me understand the core question and what type of response is needed...

Step 2: Information Gathering
I'll organize the relevant information and context needed to answer.
Information: Based on the input, the key information I need to consider is...

Step 3: Systematic Reasoning
I'll work through the problem using logical reasoning and clear steps.
Reasoning: Let me think through this systematically:
- First consideration: ...
- Second consideration: ...
- Logical progression: ...

Step 4: Solution Development
I'll develop a comprehensive solution based on my reasoning.
Solution: Based on my analysis and reasoning...

Step 5: Verification and Finalization
I'll verify my answer is complete and accurate for all required outputs.
Verification: Let me check that my response addresses all requirements...

Now I'll provide the structured response:

{self._generate_output_template(output_fields)}"""

        return template

    def get_enhanced_parameters(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """Get CoT-specific workflow parameters."""
        enhanced_params = base_params.copy()

        # Ensure generation_config exists
        if "generation_config" not in enhanced_params:
            enhanced_params["generation_config"] = {}

        # Update generation_config with CoT-specific LLM parameters
        enhanced_params["generation_config"].update(
            {
                "temperature": min(
                    base_params.get("generation_config", {}).get("temperature", 0.7),
                    0.3,
                ),  # Lower temperature for reasoning
                "max_tokens": max(
                    base_params.get("generation_config", {}).get("max_tokens", 1000),
                    1200,
                ),  # More tokens for reasoning
            }
        )

        # Pattern-specific metadata (these are NOT passed to LLMAgentNode, just for internal tracking)
        enhanced_params.update(
            {
                "execution_pattern": "chain_of_thought",
                "reasoning_required": True,
                "step_by_step": True,
                "intermediate_outputs": True,
                "verification_enabled": True,
            }
        )
        return enhanced_params

    def _format_inputs(self, inputs: Dict[str, Any]) -> str:
        """Format inputs for CoT prompt."""
        formatted_lines = []
        for key, value in inputs.items():
            formatted_lines.append(f"{key.title()}: {value}")
        return "\n".join(formatted_lines)

    def _get_output_fields(self, signature: Any) -> List[str]:
        """Get output field names from signature."""
        if hasattr(signature, "outputs"):
            outputs = []
            for output in signature.outputs:
                if isinstance(output, str):
                    outputs.append(output)
                elif isinstance(output, list):
                    outputs.extend(output)
            return outputs
        return ["response"]

    def _generate_output_template(self, output_fields: List[str]) -> str:
        """Generate structured output template."""
        template_lines = []
        for field in output_fields:
            field_title = field.replace("_", " ").title()
            if "reasoning" in field.lower() or "steps" in field.lower():
                template_lines.append(
                    f"{field_title}: [Detailed step-by-step reasoning process]"
                )
            elif "answer" in field.lower() or "result" in field.lower():
                template_lines.append(f"{field_title}: [Final comprehensive answer]")
            else:
                template_lines.append(f"{field_title}: [Specific response for {field}]")
        return "\n".join(template_lines)


class ReActExecutor(PatternExecutor):
    """Executor for ReAct (Reasoning + Acting) pattern."""

    def __init__(self):
        super().__init__("react")

    def generate_enhanced_prompt(self, signature: Any, inputs: Dict[str, Any]) -> str:
        """Generate ReAct-enhanced prompt."""
        input_text = self._format_inputs(inputs)
        output_fields = self._get_output_fields(signature)

        template = f"""I need to solve this task using the ReAct pattern (Reasoning + Acting).

{input_text}

I need to provide structured output with these fields: {', '.join(output_fields)}

I'll work through this using Thought, Action, Observation cycles:

Thought 1: I need to understand the task and plan my approach.
Let me analyze what's required: I need to examine the input and determine what actions would be most effective. The key challenge here is to break down the problem systematically.

Action 1: I'll start by identifying the core requirements and planning my response.
Action: Analyze the input requirements and identify the key components that need to be addressed.

Observation 1: Based on my analysis, I can see that the task requires structured thinking and clear action planning.
Observation: The input provides clear context, and I need to address specific output fields systematically.

Thought 2: Now I need to evaluate my progress and determine the next steps.
Let me assess what I've learned and plan the main processing action. I should focus on providing comprehensive responses for each required output field.

Action 2: I'll process the main task and generate responses for all required fields.
Action: Generate comprehensive responses addressing all aspects of the task based on the analysis.

Observation 2: I can now provide structured responses that address all requirements.
Observation: My analysis and processing have given me sufficient insight to provide complete responses.

Thought 3: Let me synthesize my findings and provide the final structured output.
Final synthesis: I can now combine my reasoning and actions to provide comprehensive responses for all required fields.

Now I'll provide the structured response:

{self._generate_output_template(output_fields)}"""

        return template

    def get_enhanced_parameters(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """Get ReAct-specific workflow parameters."""
        enhanced_params = base_params.copy()

        # Ensure generation_config exists
        if "generation_config" not in enhanced_params:
            enhanced_params["generation_config"] = {}

        # Update generation_config with ReAct-specific LLM parameters
        enhanced_params["generation_config"].update(
            {
                "temperature": base_params.get("generation_config", {}).get(
                    "temperature", 0.7
                ),  # Keep normal temperature for creativity
                "max_tokens": max(
                    base_params.get("generation_config", {}).get("max_tokens", 1000),
                    1500,
                ),  # More tokens for cycles
            }
        )

        # Pattern-specific metadata (these are NOT passed to LLMAgentNode, just for internal tracking)
        enhanced_params.update(
            {
                "execution_pattern": "react",
                "interactive_mode": True,
                "action_oriented": True,
                "observation_processing": True,
                "cycle_management": True,
            }
        )
        return enhanced_params

    def _format_inputs(self, inputs: Dict[str, Any]) -> str:
        """Format inputs for ReAct prompt."""
        formatted_lines = []
        for key, value in inputs.items():
            if "tool" in key.lower() or "action" in key.lower():
                formatted_lines.append(f"Available {key}: {value}")
            elif "task" in key.lower():
                formatted_lines.append(f"Task: {value}")
            else:
                formatted_lines.append(f"{key.title()}: {value}")
        return "\n".join(formatted_lines)

    def _get_output_fields(self, signature: Any) -> List[str]:
        """Get output field names from signature."""
        if hasattr(signature, "outputs"):
            outputs = []
            for output in signature.outputs:
                if isinstance(output, str):
                    outputs.append(output)
                elif isinstance(output, list):
                    outputs.extend(output)
            return outputs
        return ["response"]

    def _generate_output_template(self, output_fields: List[str]) -> str:
        """Generate structured output template for ReAct."""
        template_lines = []
        for field in output_fields:
            field_title = field.replace("_", " ").title()
            if "thought" in field.lower() or "reasoning" in field.lower():
                template_lines.append(
                    f"{field_title}: [Summary of key reasoning and thought process]"
                )
            elif "action" in field.lower():
                template_lines.append(
                    f"{field_title}: [Summary of main actions taken or planned]"
                )
            elif "observation" in field.lower():
                template_lines.append(
                    f"{field_title}: [Key observations and insights gained]"
                )
            elif "answer" in field.lower() or "result" in field.lower():
                template_lines.append(
                    f"{field_title}: [Final comprehensive answer based on ReAct process]"
                )
            else:
                template_lines.append(f"{field_title}: [Specific response for {field}]")
        return "\n".join(template_lines)


class DefaultExecutor(PatternExecutor):
    """Default executor for standard signature execution."""

    def __init__(self):
        super().__init__("default")

    def generate_enhanced_prompt(self, signature: Any, inputs: Dict[str, Any]) -> str:
        """Generate standard enhanced prompt."""
        input_text = self._format_inputs(inputs)
        output_fields = self._get_output_fields(signature)

        template = f"""Please provide a structured response to this request.

{input_text}

I need to provide responses for these specific fields: {', '.join(output_fields)}

Let me address each field systematically:

{self._generate_output_template(output_fields)}"""

        return template

    def get_enhanced_parameters(self, base_params: Dict[str, Any]) -> Dict[str, Any]:
        """Get standard workflow parameters."""
        enhanced_params = base_params.copy()
        enhanced_params.update(
            {
                "execution_pattern": "standard",
                "structured_output": True,
            }
        )
        return enhanced_params

    def _format_inputs(self, inputs: Dict[str, Any]) -> str:
        """Format inputs for standard prompt."""
        formatted_lines = []
        for key, value in inputs.items():
            formatted_lines.append(f"{key.title()}: {value}")
        return "\n".join(formatted_lines)

    def _get_output_fields(self, signature: Any) -> List[str]:
        """Get output field names from signature."""
        if hasattr(signature, "outputs"):
            outputs = []
            for output in signature.outputs:
                if isinstance(output, str):
                    outputs.append(output)
                elif isinstance(output, list):
                    outputs.extend(output)
            return outputs
        return ["response"]

    def _generate_output_template(self, output_fields: List[str]) -> str:
        """Generate structured output template."""
        template_lines = []
        for field in output_fields:
            field_title = field.replace("_", " ").title()
            template_lines.append(
                f"{field_title}: [Comprehensive response for {field}]"
            )
        return "\n".join(template_lines)


class PatternExecutorRegistry:
    """Registry for pattern executors."""

    def __init__(self):
        self.executors = {
            "chain_of_thought": ChainOfThoughtExecutor(),
            "react": ReActExecutor(),
            "default": DefaultExecutor(),
        }

    def get_executor(self, pattern: str) -> PatternExecutor:
        """Get executor for specific pattern."""
        return self.executors.get(pattern, self.executors["default"])

    def register_executor(self, pattern: str, executor: PatternExecutor):
        """Register a new pattern executor."""
        self.executors[pattern] = executor
        logger.info(f"Registered pattern executor: {pattern}")

    def list_patterns(self) -> List[str]:
        """List available execution patterns."""
        return list(self.executors.keys())


# Global registry instance
pattern_executor_registry = PatternExecutorRegistry()
