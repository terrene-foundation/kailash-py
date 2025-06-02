"""
Workflow composition system for building complex workflows from templates.

This module provides tools for composing workflow templates into larger,
more complex workflows. It enables template reuse through SubWorkflow nodes
and provides utilities for connecting templates together.

Design Philosophy:
    Templates should be composable building blocks that can be combined
    to create sophisticated workflows. This enables reuse at the workflow
    level, not just the node level.

Example:
    >>> # Compose a multi-stage document processing pipeline
    >>> composer = WorkflowComposer()
    >>>
    >>> pipeline = composer.compose([
    ...     {
    ...         "template_id": "document_extraction",
    ...         "params": {"source": "pdf", "ocr_enabled": True}
    ...     },
    ...     {
    ...         "template_id": "hierarchical_rag",
    ...         "params": {"max_iterations": 4, "query": "Key findings"},
    ...         "connections": [{
    ...             "from_node": "sub_0_document_extraction",
    ...             "from_output": "text",
    ...             "to_node": "sub_1_hierarchical_rag",
    ...             "to_input": "document_content"
    ...         }]
    ...     },
    ...     {
    ...         "template_id": "report_generator",
    ...         "params": {"format": "pdf"},
    ...         "connections": [{
    ...             "from_node": "sub_1_hierarchical_rag",
    ...             "from_output": "response",
    ...             "to_node": "sub_2_report_generator",
    ...             "to_input": "content"
    ...         }]
    ...     }
    ... ])
"""

from typing import Any, Dict, List, Optional

from kailash.nodes.base import Node, NodeMetadata
from kailash.sdk_exceptions import KailashWorkflowException
from kailash.workflow.builder import WorkflowBuilder
from kailash.workflow.graph import Workflow
from kailash.workflow.runner import WorkflowRunner
from kailash.workflow.templates.base import WorkflowTemplate
from kailash.workflow.templates.registry import WorkflowTemplateRegistry


class SubWorkflow(Node):
    """
    Node that encapsulates an entire workflow as a reusable component.

    SubWorkflow allows embedding complete workflows within other workflows,
    enabling hierarchical composition and template reuse. The sub-workflow
    executes as a single node from the parent workflow's perspective.

    Design Features:
        1. Workflow encapsulation as a node
        2. Parameter mapping from node to workflow
        3. Output extraction and mapping
        4. Isolated execution context
        5. Error propagation with context

    Example:
        >>> # Create a sub-workflow from a template
        >>> registry = WorkflowTemplateRegistry()
        >>> rag_template = registry.get("hierarchical_rag")
        >>>
        >>> # Instantiate as a sub-workflow node
        >>> sub_node = SubWorkflow(
        ...     workflow_template=rag_template,
        ...     document_content="Long document text...",
        ...     query="What are the main points?",
        ...     max_iterations=3
        ... )
        >>>
        >>> # Use in a parent workflow
        >>> builder = WorkflowBuilder()
        >>> builder.add_node("rag_processor", sub_node)
        >>> builder.add_node("formatter", "OutputFormatter")
        >>> builder.add_connection("rag_processor", "response", "formatter", "input")
        >>>
        >>> parent_workflow = builder.build()

        >>> # Direct execution of sub-workflow
        >>> inputs = {
        ...     "document": "Technical specification...",
        ...     "question": "What are the requirements?"
        ... }
        >>>
        >>> # Map inputs to sub-workflow parameters
        >>> sub_node.set_input_mapping({
        ...     "document": "document_content",
        ...     "question": "query"
        ... })
        >>>
        >>> result = sub_node.run(**inputs)
        >>> print(result["response"])
    """

    def __init__(
        self,
        workflow_template: WorkflowTemplate,
        node_id: Optional[str] = None,
        **template_params,
    ):
        """
        Initialize SubWorkflow node.

        Args:
            workflow_template: Template to instantiate as sub-workflow
            node_id: Optional node identifier
            **template_params: Parameters for template instantiation
        """
        super().__init__()
        self.template = workflow_template
        self.template_params = template_params
        self.sub_workflow = None
        self._input_mapping: Dict[str, str] = {}
        self._output_mapping: Dict[str, str] = {}
        self._node_id = node_id or f"sub_{workflow_template.template_id}"

        # Create the sub-workflow instance
        self._initialize_workflow()

    def _initialize_workflow(self) -> None:
        """Initialize the sub-workflow from template."""
        try:
            self.sub_workflow = self.template.instantiate(**self.template_params)
        except Exception as e:
            raise KailashWorkflowException(
                f"Failed to initialize sub-workflow from template "
                f"'{self.template.template_id}': {e}"
            )

    def set_input_mapping(self, mapping: Dict[str, str]) -> None:
        """
        Set input parameter mapping.

        Maps parent workflow outputs to sub-workflow inputs.

        Args:
            mapping: Dict mapping parent keys to sub-workflow parameter names

        Example:
            >>> sub_node.set_input_mapping({
            ...     "document_text": "document_content",
            ...     "user_query": "query"
            ... })
        """
        self._input_mapping = mapping

    def set_output_mapping(self, mapping: Dict[str, str]) -> None:
        """
        Set output parameter mapping.

        Maps sub-workflow outputs to parent workflow keys.

        Args:
            mapping: Dict mapping sub-workflow outputs to parent keys

        Example:
            >>> sub_node.set_output_mapping({
            ...     "response": "processed_text",
            ...     "metadata": "processing_info"
            ... })
        """
        self._output_mapping = mapping

    def get_metadata(self) -> NodeMetadata:
        """Get node metadata."""
        # Extract parameters from sub-workflow entry nodes
        entry_params = self._get_entry_parameters()
        exit_outputs = self._get_exit_outputs()

        return NodeMetadata(
            display_name=f"SubWorkflow: {self.template.name}",
            description=self.template.description,
            category="workflow/composite",
            parameters=entry_params,
            inputs=entry_params,  # Same as parameters for sub-workflows
            outputs=exit_outputs,
        )

    def _get_entry_parameters(self) -> Dict[str, Any]:
        """Get parameters from sub-workflow entry nodes."""
        if not self.sub_workflow:
            return {}

        # Find entry nodes (nodes with no predecessors)
        entry_nodes = []
        for node_id in self.sub_workflow.graph.nodes():
            if self.sub_workflow.graph.in_degree(node_id) == 0:
                entry_nodes.append(node_id)

        # Collect parameters from entry nodes
        parameters = {}
        for node_id in entry_nodes:
            node = self.sub_workflow.get_node(node_id)
            if hasattr(node, "get_metadata"):
                node_params = node.get_metadata().parameters or {}
                parameters.update(node_params)

        return parameters

    def _get_exit_outputs(self) -> Dict[str, Any]:
        """Get outputs from sub-workflow exit nodes."""
        if not self.sub_workflow:
            return {}

        # Find exit nodes (nodes with no successors)
        exit_nodes = []
        for node_id in self.sub_workflow.graph.nodes():
            if self.sub_workflow.graph.out_degree(node_id) == 0:
                exit_nodes.append(node_id)

        # Collect outputs from exit nodes
        outputs = {}
        for node_id in exit_nodes:
            node = self.sub_workflow.get_node(node_id)
            if hasattr(node, "get_metadata"):
                node_outputs = node.get_metadata().outputs or {}
                # Prefix with node_id to avoid conflicts
                for key, value in node_outputs.items():
                    outputs[f"{node_id}.{key}"] = value

        return outputs

    def run(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the sub-workflow.

        Args:
            **kwargs: Input parameters for the sub-workflow

        Returns:
            Dict of outputs from the sub-workflow
        """
        # Apply input mapping
        mapped_inputs = {}
        for parent_key, sub_key in self._input_mapping.items():
            if parent_key in kwargs:
                mapped_inputs[sub_key] = kwargs[parent_key]

        # Add any unmapped inputs directly
        for key, value in kwargs.items():
            if key not in self._input_mapping and key not in mapped_inputs:
                mapped_inputs[key] = value

        # Execute sub-workflow
        try:
            runner = WorkflowRunner()
            results = runner.run(self.sub_workflow, inputs=mapped_inputs)

            # Extract outputs from results
            outputs = self._extract_outputs(results)

            # Apply output mapping
            if self._output_mapping:
                mapped_outputs = {}
                for sub_key, parent_key in self._output_mapping.items():
                    if sub_key in outputs:
                        mapped_outputs[parent_key] = outputs[sub_key]
                return mapped_outputs
            else:
                return outputs

        except Exception as e:
            raise KailashWorkflowException(
                f"Sub-workflow '{self.template.template_id}' execution failed: {e}"
            )

    def _extract_outputs(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Extract outputs from workflow execution results."""
        outputs = {}

        # Get outputs from exit nodes
        exit_nodes = []
        for node_id in self.sub_workflow.graph.nodes():
            if self.sub_workflow.graph.out_degree(node_id) == 0:
                exit_nodes.append(node_id)

        # Extract outputs from results
        for node_id in exit_nodes:
            if node_id in results:
                node_result = results[node_id]
                if isinstance(node_result, dict):
                    # Flatten the outputs
                    for key, value in node_result.items():
                        outputs[f"{node_id}.{key}"] = value
                else:
                    outputs[node_id] = node_result

        return outputs

    def __repr__(self) -> str:
        return f"SubWorkflow(template='{self.template.template_id}', node_id='{self._node_id}')"


class WorkflowComposer:
    """
    Utility for composing workflows from templates.

    The WorkflowComposer simplifies the process of building complex workflows
    by combining multiple templates with automatic connection management.

    Example:
        >>> composer = WorkflowComposer()
        >>>
        >>> # Define a multi-stage pipeline
        >>> workflow = composer.compose([
        ...     {
        ...         "template_id": "data_ingestion",
        ...         "node_id": "ingest",  # Optional custom ID
        ...         "params": {
        ...             "source": "database",
        ...             "query": "SELECT * FROM customers"
        ...         }
        ...     },
        ...     {
        ...         "template_id": "data_cleaning",
        ...         "params": {
        ...             "remove_nulls": True,
        ...             "normalize": True
        ...         },
        ...         "connections": [{
        ...             "from_node": "ingest",
        ...             "from_output": "data",
        ...             "to_input": "raw_data"
        ...         }]
        ...     },
        ...     {
        ...         "template_id": "hierarchical_rag",
        ...         "params": {
        ...             "query": "Summarize customer segments",
        ...             "max_iterations": 4
        ...         },
        ...         "connections": [{
        ...             "from_output": "cleaned_data",
        ...             "to_input": "document_content"
        ...         }]
        ...     }
        ... ])
        >>>
        >>> # Execute the composed workflow
        >>> runtime = LocalRuntime()
        >>> results = runtime.execute_workflow(workflow)

        >>> # Compose with error handling
        >>> try:
        ...     workflow = composer.compose(pipeline_config)
        ... except WorkflowCompositionException as e:
        ...     print(f"Composition failed: {e}")
        ...     print(f"Missing templates: {e.missing_templates}")
        ...     print(f"Invalid connections: {e.invalid_connections}")
    """

    def __init__(self, registry: Optional[WorkflowTemplateRegistry] = None):
        """
        Initialize composer.

        Args:
            registry: Template registry to use (defaults to singleton)
        """
        self.registry = registry or WorkflowTemplateRegistry()

    def compose(
        self,
        templates: List[Dict[str, Any]],
        workflow_name: str = "Composed Workflow",
        workflow_description: str = "Workflow composed from templates",
    ) -> Workflow:
        """
        Compose multiple templates into a single workflow.

        Args:
            templates: List of template configurations
            workflow_name: Name for the composed workflow
            workflow_description: Description for the composed workflow

        Returns:
            Composed Workflow instance

        Raises:
            WorkflowCompositionException: If composition fails

        Example:
            >>> templates = [
            ...     {
            ...         "template_id": "etl_pipeline",
            ...         "params": {"source": "csv", "target": "database"}
            ...     },
            ...     {
            ...         "template_id": "ml_training",
            ...         "params": {"model": "random_forest"},
            ...         "connections": [{
            ...             "from_output": "processed_data",
            ...             "to_input": "training_data"
            ...         }]
            ...     }
            ... ]
            >>> workflow = composer.compose(templates)
        """
        builder = WorkflowBuilder()
        node_mapping = {}  # Maps node IDs to SubWorkflow instances

        # Validate all templates exist
        self._validate_templates(templates)

        # Create sub-workflow nodes
        for i, template_config in enumerate(templates):
            template_id = template_config["template_id"]
            params = template_config.get("params", {})
            node_id = template_config.get("node_id", f"sub_{i}_{template_id}")

            # Get template
            template = self.registry.get(template_id)

            # Create sub-workflow node
            sub_node = SubWorkflow(template, node_id=node_id, **params)

            # Add input/output mappings if specified
            if "input_mapping" in template_config:
                sub_node.set_input_mapping(template_config["input_mapping"])
            if "output_mapping" in template_config:
                sub_node.set_output_mapping(template_config["output_mapping"])

            # Add to workflow
            builder.add_node(node_id=node_id, node_or_type=sub_node)
            node_mapping[node_id] = sub_node

            # Add connections
            connections = template_config.get("connections", [])
            for conn in connections:
                self._add_connection(builder, conn, i, node_id, templates)

        # Build and return workflow
        return builder.build(name=workflow_name, description=workflow_description)

    def _validate_templates(self, templates: List[Dict[str, Any]]) -> None:
        """Validate that all required templates exist."""
        missing = []
        for config in templates:
            template_id = config.get("template_id")
            if not template_id:
                raise ValueError("Template configuration missing 'template_id'")
            if not self.registry.has_template(template_id):
                missing.append(template_id)

        if missing:
            raise KailashWorkflowException(
                f"Missing templates: {missing}. "
                f"Available templates: {list(self.registry.templates.keys())}"
            )

    def _add_connection(
        self,
        builder: WorkflowBuilder,
        connection: Dict[str, Any],
        current_index: int,
        current_node_id: str,
        all_templates: List[Dict[str, Any]],
    ) -> None:
        """Add a connection between nodes."""
        # Determine source node
        if "from_node" in connection:
            from_node = connection["from_node"]
        else:
            # Default to previous node
            if current_index > 0:
                prev_config = all_templates[current_index - 1]
                from_node = prev_config.get(
                    "node_id", f"sub_{current_index-1}_{prev_config['template_id']}"
                )
            else:
                raise ValueError(
                    "Connection for first template must specify 'from_node'"
                )

        # Get connection details
        from_output = connection["from_output"]
        to_node = connection.get("to_node", current_node_id)
        to_input = connection["to_input"]

        # Add connection
        try:
            builder.add_connection(from_node, from_output, to_node, to_input)
        except Exception as e:
            raise KailashWorkflowException(
                f"Failed to add connection from {from_node}.{from_output} "
                f"to {to_node}.{to_input}: {e}"
            )


class WorkflowCompositionException(KailashWorkflowException):
    """Exception raised during workflow composition."""

    def __init__(
        self,
        message: str,
        missing_templates: Optional[List[str]] = None,
        invalid_connections: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(message)
        self.missing_templates = missing_templates or []
        self.invalid_connections = invalid_connections or []
