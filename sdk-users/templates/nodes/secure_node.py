"""
Secure Node Template

This template demonstrates how to create a custom node with integrated security features
using the SecurityMixin and following security best practices.

Usage:
    from kailash.nodes.custom.secure_node import SecureDataProcessorNode

    node = SecureDataProcessorNode()
    result = node.run(input_data=[1, 2, 3])
"""

from typing import Any

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.mixins import SecurityMixin
from kailash.security import SecurityError


class SecureDataProcessorNode(SecurityMixin, Node):
    """
    Template for creating secure custom nodes.

    This node demonstrates:
    - Integration with SecurityMixin
    - Input validation and sanitization
    - Security event logging
    - Safe data processing patterns
    """

    def get_parameters(self) -> dict[str, NodeParameter]:
        """Define node parameters with security considerations."""
        return {
            "input_data": NodeParameter(
                type=list, description="Data to process securely", required=True
            ),
            "max_items": NodeParameter(
                type=int,
                description="Maximum number of items to process",
                required=False,
                default=1000,
            ),
            "filter_dangerous": NodeParameter(
                type=bool,
                description="Whether to filter out potentially dangerous content",
                required=False,
                default=True,
            ),
        }

    def run(self, **kwargs) -> dict[str, Any]:
        """
        Securely process input data.

        Args:
            **kwargs: Node parameters including input_data

        Returns:
            Dict containing processed data and security metrics

        Raises:
            SecurityError: If security validation fails
        """
        # Step 1: Validate and sanitize all inputs
        safe_params = self.validate_and_sanitize_inputs(kwargs)

        # Step 2: Log security event
        self.log_security_event(
            f"Processing {len(safe_params['input_data'])} items", level="INFO"
        )

        # Step 3: Additional security checks
        self._validate_data_size(safe_params["input_data"], safe_params["max_items"])

        # Step 4: Process data securely
        processed_data = self._secure_process(
            safe_params["input_data"], safe_params["filter_dangerous"]
        )

        # Step 5: Log completion
        self.log_security_event(
            f"Processed {len(processed_data)} items successfully", level="INFO"
        )

        return {
            "processed_data": processed_data,
            "security_metrics": {
                "input_count": len(safe_params["input_data"]),
                "output_count": len(processed_data),
                "filtered_count": len(safe_params["input_data"]) - len(processed_data),
            },
        }

    def _validate_data_size(self, data: list[Any], max_items: int) -> None:
        """
        Validate data size against security limits.

        Args:
            data: Input data list
            max_items: Maximum allowed items

        Raises:
            SecurityError: If data exceeds size limits
        """
        if len(data) > max_items:
            self.log_security_event(
                f"Data size violation: {len(data)} > {max_items}", level="ERROR"
            )
            raise SecurityError(
                f"Data too large: {len(data)} items > {max_items} limit"
            )

    def _secure_process(self, data: list[Any], filter_dangerous: bool) -> list[Any]:
        """
        Process data with security filtering.

        Args:
            data: Input data to process
            filter_dangerous: Whether to filter dangerous content

        Returns:
            Processed and filtered data
        """
        processed = []

        for item in data:
            # Convert to string for safety checks
            item_str = str(item)

            # Apply security filtering if enabled
            if filter_dangerous and self._is_dangerous_content(item_str):
                self.log_security_event(
                    f"Filtered dangerous content: {item_str[:50]}...", level="WARNING"
                )
                continue

            # Apply your custom processing logic here
            processed_item = self._process_item(item)
            processed.append(processed_item)

        return processed

    def _is_dangerous_content(self, content: str) -> bool:
        """
        Check if content contains potentially dangerous patterns.

        Args:
            content: Content to check

        Returns:
            True if content appears dangerous
        """
        dangerous_patterns = [
            "<script>",
            "javascript:",
            "eval(",
            "exec(",
            "__import__",
            "os.system",
            "subprocess.",
            "rm -rf",
            "DROP TABLE",
            "DELETE FROM",
        ]

        content_lower = content.lower()
        return any(pattern.lower() in content_lower for pattern in dangerous_patterns)

    def _process_item(self, item: Any) -> Any:
        """
        Process a single item safely.

        This is where you'd implement your custom business logic.

        Args:
            item: Item to process

        Returns:
            Processed item
        """
        # Example processing: convert to uppercase if string
        if isinstance(item, str):
            return item.upper()
        elif isinstance(item, (int, float)):
            return item * 2
        else:
            return str(item)


# Example usage
if __name__ == "__main__":
    from kailash.security import SecurityConfig, set_security_config

    # Configure security for testing
    config = SecurityConfig(
        enable_audit_logging=True,
        max_file_size=1024 * 1024,  # 1MB
        execution_timeout=30.0,  # 30 seconds
    )
    set_security_config(config)

    # Create and test the secure node
    node = SecureDataProcessorNode()

    # Test with safe data
    safe_result = node.run(
        input_data=[1, 2, "hello", 4.5], max_items=10, filter_dangerous=True
    )
    print("Safe processing result:", safe_result)

    # Test with potentially dangerous data
    dangerous_result = node.run(
        input_data=["normal", "<script>alert('xss')</script>", "safe"],
        max_items=10,
        filter_dangerous=True,
    )
    print("Filtered processing result:", dangerous_result)
