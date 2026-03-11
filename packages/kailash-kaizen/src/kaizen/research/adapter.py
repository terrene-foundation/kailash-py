"""
ResearchAdapter - Wrap research implementations as Kaizen signatures

Adapts research code to Kaizen's signature-based programming system (TODO-142):
- Creates signature classes from research implementations
- Maps parameters between research code and signatures
- Integrates with Core SDK workflow execution

Performance Target: <1 second per adaptation
"""

import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Type

from kaizen.signatures import Signature

from .parser import ResearchPaper


@dataclass
class SignatureAdapter:
    """Wrapper that adapts research implementation to signature interface."""

    paper: ResearchPaper
    implementation_func: Callable
    parameter_mapping: Optional[Dict[str, str]] = None

    def execute(self, **kwargs) -> Any:
        """
        Execute research implementation.

        Args:
            **kwargs: Input parameters

        Returns:
            Implementation result
        """
        # Apply parameter mapping if provided
        if self.parameter_mapping:
            mapped_kwargs = {}
            for key, value in kwargs.items():
                mapped_key = self.parameter_mapping.get(key, key)
                mapped_kwargs[mapped_key] = value
        else:
            mapped_kwargs = kwargs

        # Call implementation function
        result = self.implementation_func(**mapped_kwargs)

        return result


class ResearchAdapter:
    """Adapt research implementations to Kaizen signature system."""

    def __init__(self):
        """Initialize adapter."""
        pass

    def create_signature_adapter(
        self,
        paper: ResearchPaper,
        implementation_module: str,
        main_function: str,
        parameter_mapping: Optional[Dict[str, str]] = None,
    ) -> Type[Signature]:
        """
        Create signature class from research implementation.

        Args:
            paper: Research paper metadata
            implementation_module: Python module containing implementation
            main_function: Main function to wrap
            parameter_mapping: Optional parameter name mapping

        Returns:
            Signature subclass wrapping the implementation

        Raises:
            ImportError: If module not found
            AttributeError: If function not found in module
        """
        # Import the implementation module
        module = importlib.import_module(implementation_module)

        # Get the main function
        if not hasattr(module, main_function):
            raise AttributeError(
                f"Function '{main_function}' not found in module '{implementation_module}'"
            )

        implementation_func = getattr(module, main_function)

        # Inspect function signature to determine input/output fields
        sig = inspect.signature(implementation_func)

        # Extract parameter names from function signature
        param_names = list(sig.parameters.keys())

        # Create dynamic signature class with fields
        class ResearchSignature(Signature):
            """Dynamically created signature for research implementation."""

            # Define a generic input field (will be filled by execute kwargs)
            input_data: str = ""  # Generic input placeholder
            result: str = ""  # Generic output placeholder

            def __init__(self):
                """Initialize with paper metadata."""
                # Initialize with inputs/outputs to satisfy Signature requirements
                inputs = (
                    {name: f"Input {name}" for name in param_names}
                    if param_names
                    else {"input": "Input data"}
                )
                outputs = {"result": "Research result"}
                super().__init__(inputs=inputs, outputs=outputs)

                self.paper_id = paper.arxiv_id
                self.metadata = {
                    "paper_title": paper.title,
                    "paper_authors": paper.authors,
                    "implementation_module": implementation_module,
                    "implementation_function": main_function,
                }

            def execute(self, **kwargs) -> Any:
                """Execute research implementation."""
                # Apply parameter mapping if needed
                if parameter_mapping:
                    mapped_kwargs = {}
                    for key, value in kwargs.items():
                        mapped_key = parameter_mapping.get(key, key)
                        mapped_kwargs[mapped_key] = value
                else:
                    mapped_kwargs = kwargs

                # Call implementation
                return implementation_func(**mapped_kwargs)

        # Set signature class name
        ResearchSignature.__name__ = f"{paper.title.replace(' ', '')}Signature"

        return ResearchSignature

    def adapt_to_signature(
        self,
        paper: ResearchPaper,
        implementation_func: Callable,
        parameter_mapping: Optional[Dict[str, str]] = None,
    ) -> SignatureAdapter:
        """
        Create signature adapter directly from function.

        Args:
            paper: Research paper metadata
            implementation_func: Function to adapt
            parameter_mapping: Optional parameter mapping

        Returns:
            SignatureAdapter instance
        """
        return SignatureAdapter(
            paper=paper,
            implementation_func=implementation_func,
            parameter_mapping=parameter_mapping,
        )

    def _create_signature_definition(
        self, paper: ResearchPaper, function_signature: inspect.Signature
    ) -> str:
        """Create signature definition string from function signature."""
        # Extract parameter names
        params = list(function_signature.parameters.keys())

        # Simple signature: params -> output
        input_part = ", ".join(params)
        return f"{input_part} -> output"

    def _parse_signature_spec(self, spec: str) -> Dict[str, Any]:
        """Parse signature specification string."""
        # Split on '->'
        parts = spec.split("->")

        if len(parts) != 2:
            raise ValueError(f"Invalid signature spec: {spec}")

        input_part = parts[0].strip()
        output_part = parts[1].strip()

        return {
            "inputs": [p.strip() for p in input_part.split(",")],
            "outputs": [p.strip() for p in output_part.split(",")],
        }
