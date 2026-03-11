"""
DataFlow Dynamic Update Node - Optimal Architectural Solution

This node provides a clean, intuitive API for dynamic updates by combining:
1. Python code execution for data preparation
2. Automatic UpdateNode execution
3. Zero boilerplate for common patterns

This is the architecturally correct solution that avoids patching and provides
optimal developer experience.
"""

import logging
from typing import Any, Dict

from kailash.nodes.base import Node, NodeParameter
from kailash.sdk_exceptions import NodeExecutionError

from dataflow.core.async_utils import async_safe_run  # Phase 6: Async-safe execution

logger = logging.getLogger(__name__)


class DynamicUpdateNode(Node):
    """
        A DataFlow-specific node that provides intuitive dynamic update patterns.

        This node solves the ergonomics problem by combining code execution and
        update logic into a single, clean API. It's architecturally superior to
        patching either PythonCodeNode or UpdateNode.

        **Design Philosophy**:
        - Developers think in terms of "prepare data, then update"
        - This node makes that mental model explicit
        - Zero boilerplate, maximum clarity

        **Usage Examples**:

        Example 1: Simple field updates
        ```python
        workflow.add_node("DynamicUpdateNode", "update_user", {
            "model_name": "User",
            "filter": {"id": user_id},
            "prepare_code": '''
    name = f"Updated: {name}"
    status = "active"
    ''',
            "dataflow_instance": db
        })
        ```

        Example 2: Complex business logic
        ```python
        workflow.add_node("DynamicUpdateNode", "update_summary", {
            "model_name": "ConversationSummary",
            "filter": {"id": summary_id},
            "prepare_code": '''
    # Complex data preparation
    summary_markdown = generate_markdown(raw_text)
    topics_json = json.dumps(extract_topics(raw_text))
    edited_by_user = True
    confidence_score = calculate_confidence(raw_text)
    ''',
            "dataflow_instance": db
        })
        ```

        Example 3: Conditional updates
        ```python
        workflow.add_node("DynamicUpdateNode", "conditional_update", {
            "model_name": "Order",
            "filter": {"id": order_id},
            "prepare_code": '''
    if total_amount > 1000:
        status = "vip"
        discount = 0.15
    else:
        status = "standard"
        discount = 0.05
    ''',
            "dataflow_instance": db
        })
        ```
    """

    def __init__(
        self,
        model_name: str,
        dataflow_instance: "DataFlow",
        prepare_code: str | None = None,
        filter_code: str | None = None,
        **kwargs,
    ):
        """
        Initialize DynamicUpdateNode.

        Args:
            model_name: Name of the DataFlow model to update
            dataflow_instance: DataFlow instance containing the model
            prepare_code: Python code to prepare update fields
            filter_code: Python code to prepare filter criteria (optional)
            **kwargs: Additional node configuration
        """
        self.model_name = model_name
        self.dataflow_instance = dataflow_instance
        self.prepare_code = prepare_code or ""
        self.filter_code = filter_code or ""

        # Get model fields for validation
        self.model_fields = dataflow_instance.get_model_fields(model_name)

        super().__init__(**kwargs)

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """
        Define parameters based on the model fields.

        Returns dict parameters for:
        - filter: Dict for WHERE clause
        - All model fields as optional parameters (for input data)
        """
        from typing import Any

        params = {
            "filter": NodeParameter(
                name="filter",
                type=dict,
                required=False,
                default={},
                description="Filter criteria for selecting record(s) to update",
            ),
        }

        # Add all model fields as optional input parameters
        # These can be passed in and used in prepare_code
        for field_name, field_info in self.model_fields.items():
            if field_name not in ["id", "created_at", "updated_at"]:
                params[field_name] = NodeParameter(
                    name=field_name,
                    type=Any,  # Accept any type for flexibility
                    required=False,
                    description=f"Input data for {field_name} (available in prepare_code)",
                )

        return params

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the dynamic update.

        Flow:
        1. Execute filter_code if provided (prepare filter criteria)
        2. Execute prepare_code (prepare field updates)
        3. Call UpdateNode with prepared data
        4. Return update result

        Args:
            **kwargs: Input parameters including filter and field data

        Returns:
            Update result from UpdateNode
        """
        try:
            # Step 1: Prepare execution namespace with inputs
            namespace = {}
            namespace.update(kwargs)  # All inputs available in code

            # Step 2: Execute filter code if provided
            filter_criteria = kwargs.get("filter", {})

            if self.filter_code.strip():
                exec(self.filter_code, {}, namespace)
                # Collect filter variables
                filter_criteria = {
                    k: v
                    for k, v in namespace.items()
                    if k in ["id"] or k.endswith("_id")  # Common filter patterns
                }

            # Step 3: Execute prepare code
            if self.prepare_code.strip():
                exec(self.prepare_code, {}, namespace)

            # Step 4: Collect updated fields from namespace
            # Only include fields that are in the model AND were set in prepare_code
            updated_fields = {}
            for field_name in self.model_fields.keys():
                if field_name in namespace and field_name not in [
                    "id",
                    "created_at",
                    "updated_at",
                ]:
                    updated_fields[field_name] = namespace[field_name]

            # Step 5: Execute UpdateNode
            update_node_class = self.dataflow_instance._nodes[
                f"{self.model_name}UpdateNode"
            ]
            update_node = update_node_class()

            result = await update_node.async_run(
                filter=filter_criteria, fields=updated_fields
            )

            logger.info(
                f"DynamicUpdateNode '{self.metadata.name}': Updated {self.model_name} "
                f"with filter={filter_criteria}, fields={list(updated_fields.keys())}"
            )

            return result

        except Exception as e:
            logger.error(f"DynamicUpdateNode execution failed: {e}")
            raise NodeExecutionError(f"Dynamic update failed: {e}") from e

    def run(self, **kwargs) -> Dict[str, Any]:
        """Synchronous run - delegates to async_run via event loop.

        Phase 6: Uses async_safe_run for transparent sync/async bridging.
        Works correctly in FastAPI, Docker, Jupyter, and traditional scripts.
        """
        # Phase 6: Use async_safe_run for proper event loop handling
        return async_safe_run(self.async_run(**kwargs))
