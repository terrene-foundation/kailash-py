"""Export functionality for converting Kailash Python SDK workflows to Kailash-compatible formats."""

import json
import logging
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from pydantic import BaseModel, Field, ValidationError

from kailash.nodes import Node
from kailash.sdk_exceptions import (
    ConfigurationException,
    ExportException,
    ImportException,
)
from kailash.workflow import Workflow

logger = logging.getLogger(__name__)


class ResourceSpec(BaseModel):
    """Resource specifications for a node."""

    cpu: str = Field("100m", description="CPU request")
    memory: str = Field("128Mi", description="Memory request")
    cpu_limit: Optional[str] = Field(None, description="CPU limit")
    memory_limit: Optional[str] = Field(None, description="Memory limit")
    gpu: Optional[int] = Field(None, description="Number of GPUs")


class ContainerMapping(BaseModel):
    """Mapping from Python node to Kailash container."""

    python_node: str = Field(..., description="Python node class name")
    container_image: str = Field(..., description="Docker container image")
    command: List[str] = Field(default_factory=list, description="Container command")
    args: List[str] = Field(default_factory=list, description="Container arguments")
    env: Dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    resources: ResourceSpec = Field(
        default_factory=ResourceSpec, description="Resource specs"
    )
    mount_paths: Dict[str, str] = Field(
        default_factory=dict, description="Volume mount paths"
    )


class ExportConfig(BaseModel):
    """Configuration for export process."""

    version: str = Field("1.0", description="Export format version")
    namespace: str = Field("default", description="Kubernetes namespace")
    include_metadata: bool = Field(True, description="Include metadata in export")
    include_resources: bool = Field(True, description="Include resource specifications")
    validate_output: bool = Field(True, description="Validate exported format")
    container_registry: str = Field("", description="Container registry URL")
    partial_export: Set[str] = Field(default_factory=set, description="Nodes to export")


class NodeMapper:
    """Maps Python nodes to Kailash containers."""

    def __init__(self):
        """Initialize the node mapper with default mappings.

        Raises:
            ConfigurationException: If initialization fails
        """
        try:
            self.mappings: Dict[str, ContainerMapping] = {}
            self._initialize_default_mappings()
        except Exception as e:
            raise ConfigurationException(
                f"Failed to initialize node mapper: {e}"
            ) from e

    def _initialize_default_mappings(self):
        """Set up default mappings for common node types."""
        # Data reader nodes
        self.mappings["FileReader"] = ContainerMapping(
            python_node="FileReader",
            container_image="kailash/file-reader:latest",
            command=["python", "-m", "kailash.nodes.data.reader"],
            resources=ResourceSpec(cpu="100m", memory="256Mi"),
        )

        self.mappings["CSVReader"] = ContainerMapping(
            python_node="CSVReader",
            container_image="kailash/csv-reader:latest",
            command=["python", "-m", "kailash.nodes.data.csv_reader"],
            resources=ResourceSpec(cpu="100m", memory="512Mi"),
        )

        # Data writer nodes
        self.mappings["FileWriter"] = ContainerMapping(
            python_node="FileWriter",
            container_image="kailash/file-writer:latest",
            command=["python", "-m", "kailash.nodes.data.writer"],
            resources=ResourceSpec(cpu="100m", memory="256Mi"),
        )

        # Transform nodes
        self.mappings["DataTransform"] = ContainerMapping(
            python_node="DataTransform",
            container_image="kailash/data-transform:latest",
            command=["python", "-m", "kailash.nodes.transform.processor"],
            resources=ResourceSpec(cpu="200m", memory="512Mi"),
        )

        # AI nodes
        self.mappings["LLMNode"] = ContainerMapping(
            python_node="LLMNode",
            container_image="kailash/llm-node:latest",
            command=["python", "-m", "kailash.nodes.ai.llm"],
            resources=ResourceSpec(cpu="500m", memory="2Gi", gpu=1),
            env={"MODEL_TYPE": "gpt-3.5", "MAX_TOKENS": "1000"},
        )

        # Logic nodes
        self.mappings["ConditionalNode"] = ContainerMapping(
            python_node="ConditionalNode",
            container_image="kailash/conditional:latest",
            command=["python", "-m", "kailash.nodes.logic.conditional"],
            resources=ResourceSpec(cpu="50m", memory="128Mi"),
        )

    def register_mapping(self, mapping: ContainerMapping):
        """Register a custom node mapping.

        Args:
            mapping: Container mapping to register

        Raises:
            ConfigurationException: If mapping is invalid
        """
        try:
            if not mapping.python_node:
                raise ConfigurationException("Python node name is required")
            if not mapping.container_image:
                raise ConfigurationException("Container image is required")

            self.mappings[mapping.python_node] = mapping
            logger.info(f"Registered mapping for node '{mapping.python_node}'")
        except ValidationError as e:
            raise ConfigurationException(f"Invalid container mapping: {e}") from e

    def get_mapping(self, node_type: str) -> ContainerMapping:
        """Get container mapping for a node type.

        Args:
            node_type: Python node type name

        Returns:
            Container mapping

        Raises:
            ConfigurationException: If mapping cannot be created
        """
        if not node_type:
            raise ConfigurationException("Node type is required")

        if node_type not in self.mappings:
            logger.warning(
                f"No mapping found for node type '{node_type}', creating default"
            )
            try:
                # Try to create a default mapping
                return ContainerMapping(
                    python_node=node_type,
                    container_image=f"kailash/{node_type.lower()}:latest",
                    command=["python", "-m", f"kailash.nodes.{node_type.lower()}"],
                )
            except Exception as e:
                raise ConfigurationException(
                    f"Failed to create default mapping for node '{node_type}': {e}"
                ) from e
        return self.mappings[node_type]

    def update_registry(self, registry_url: str):
        """Update container image URLs with registry prefix.

        Args:
            registry_url: Container registry URL
        """
        if not registry_url:
            return

        for mapping in self.mappings.values():
            if not mapping.container_image.startswith(registry_url):
                mapping.container_image = f"{registry_url}/{mapping.container_image}"


class ExportValidator:
    """Validates exported workflow formats."""

    @staticmethod
    def validate_yaml(data: Dict[str, Any]) -> bool:
        """Validate YAML export format.

        Args:
            data: Exported data to validate

        Returns:
            True if valid

        Raises:
            ExportException: If validation fails
        """
        if not isinstance(data, dict):
            raise ExportException("Export data must be a dictionary")

        required_fields = ["metadata", "nodes", "connections"]

        for field in required_fields:
            if field not in data:
                raise ExportException(
                    f"Missing required field: '{field}'. "
                    f"Required fields: {required_fields}"
                )

        # Validate metadata
        metadata = data["metadata"]
        if not isinstance(metadata, dict):
            raise ExportException("Metadata must be a dictionary")

        if "name" not in metadata:
            raise ExportException("Metadata must contain 'name' field")

        # Validate nodes
        nodes = data["nodes"]
        if not isinstance(nodes, dict):
            raise ExportException("Nodes must be a dictionary")

        if not nodes:
            logger.warning("No nodes found in export data")

        for node_id, node_data in nodes.items():
            if not isinstance(node_data, dict):
                raise ExportException(f"Node '{node_id}' must be a dictionary")

            if "type" not in node_data:
                raise ExportException(
                    f"Node '{node_id}' missing 'type' field. "
                    f"Available fields: {list(node_data.keys())}"
                )
            if "config" not in node_data:
                raise ExportException(
                    f"Node '{node_id}' missing 'config' field. "
                    f"Available fields: {list(node_data.keys())}"
                )

        # Validate connections
        connections = data["connections"]
        if not isinstance(connections, list):
            raise ExportException("Connections must be a list")

        for i, conn in enumerate(connections):
            if not isinstance(conn, dict):
                raise ExportException(f"Connection {i} must be a dictionary")

            if "from" not in conn or "to" not in conn:
                raise ExportException(
                    f"Connection {i} missing 'from' or 'to' field. "
                    f"Connection data: {conn}"
                )

        return True

    @staticmethod
    def validate_json(data: Dict[str, Any]) -> bool:
        """Validate JSON export format.

        Args:
            data: Exported data to validate

        Returns:
            True if valid

        Raises:
            ExportException: If validation fails
        """
        # JSON validation is the same as YAML for our purposes
        return ExportValidator.validate_yaml(data)


class ManifestGenerator:
    """Generates deployment manifests for Kailash workflows."""

    def __init__(self, config: ExportConfig):
        """Initialize the manifest generator.

        Args:
            config: Export configuration
        """
        self.config = config

    def generate_manifest(
        self, workflow: Workflow, node_mapper: NodeMapper
    ) -> Dict[str, Any]:
        """Generate deployment manifest for a workflow.

        Args:
            workflow: Workflow to generate manifest for
            node_mapper: Node mapper for container mappings

        Returns:
            Deployment manifest

        Raises:
            ExportException: If manifest generation fails
        """
        try:
            manifest = {
                "apiVersion": "kailash.io/v1",
                "kind": "Workflow",
                "metadata": {
                    "name": self._sanitize_name(workflow.metadata.name),
                    "namespace": self.config.namespace,
                    "labels": {
                        "app": "kailash",
                        "workflow": self._sanitize_name(workflow.metadata.name),
                        "version": workflow.metadata.version,
                    },
                    "annotations": {
                        "description": workflow.metadata.description,
                        "author": workflow.metadata.author,
                        "created_at": workflow.metadata.created_at.isoformat(),
                    },
                },
                "spec": {"nodes": [], "edges": []},
            }
        except Exception as e:
            raise ExportException(f"Failed to create manifest structure: {e}") from e

        # Add nodes
        for node_id, node_instance in workflow.nodes.items():
            if self.config.partial_export and node_id not in self.config.partial_export:
                continue

            try:
                node_spec = self._generate_node_spec(
                    node_id,
                    node_instance,
                    workflow._node_instances[node_id],
                    node_mapper,
                )
                manifest["spec"]["nodes"].append(node_spec)
            except Exception as e:
                raise ExportException(
                    f"Failed to generate spec for node '{node_id}': {e}"
                ) from e

        # Add connections
        for connection in workflow.connections:
            if self.config.partial_export:
                if (
                    connection.source_node not in self.config.partial_export
                    or connection.target_node not in self.config.partial_export
                ):
                    continue

            edge_spec = {
                "from": f"{connection.source_node}.{connection.source_output}",
                "to": f"{connection.target_node}.{connection.target_input}",
            }
            manifest["spec"]["edges"].append(edge_spec)

        return manifest

    def _generate_node_spec(
        self, node_id: str, node_instance, node: Node, node_mapper: NodeMapper
    ) -> Dict[str, Any]:
        """Generate node specification for manifest.

        Args:
            node_id: Node identifier
            node_instance: Node instance from workflow
            node: Actual node object
            node_mapper: Node mapper for container info

        Returns:
            Node specification

        Raises:
            ExportException: If node spec generation fails
        """
        try:
            mapping = node_mapper.get_mapping(node_instance.node_type)
        except Exception as e:
            raise ExportException(
                f"Failed to get mapping for node '{node_id}': {e}"
            ) from e

        node_spec = {
            "name": node_id,
            "type": node_instance.node_type,
            "container": {
                "image": mapping.container_image,
                "command": mapping.command,
                "args": mapping.args,
                "env": [],
            },
        }

        # Add environment variables
        for key, value in mapping.env.items():
            node_spec["container"]["env"].append({"name": key, "value": str(value)})

        # Add config as environment variables
        for key, value in node_instance.config.items():
            node_spec["container"]["env"].append(
                {"name": f"CONFIG_{key.upper()}", "value": str(value)}
            )

        # Add resources if enabled
        if self.config.include_resources:
            node_spec["container"]["resources"] = {
                "requests": {
                    "cpu": mapping.resources.cpu,
                    "memory": mapping.resources.memory,
                }
            }

            limits = {}
            if mapping.resources.cpu_limit:
                limits["cpu"] = mapping.resources.cpu_limit
            if mapping.resources.memory_limit:
                limits["memory"] = mapping.resources.memory_limit
            if mapping.resources.gpu:
                limits["nvidia.com/gpu"] = str(mapping.resources.gpu)

            if limits:
                node_spec["container"]["resources"]["limits"] = limits

        # Add volume mounts
        if mapping.mount_paths:
            node_spec["container"]["volumeMounts"] = []
            for name, path in mapping.mount_paths.items():
                node_spec["container"]["volumeMounts"].append(
                    {"name": name, "mountPath": path}
                )

        return node_spec

    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for Kubernetes compatibility.

        Args:
            name: Name to sanitize

        Returns:
            Sanitized name
        """
        if not name:
            raise ExportException("Name cannot be empty")

        # Replace non-alphanumeric characters with hyphens
        sanitized = re.sub(r"[^a-zA-Z0-9-]", "-", name.lower())
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip("-")
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"w-{sanitized}"
        # Truncate to 63 characters (Kubernetes limit)
        sanitized = sanitized[:63]

        if not sanitized:
            raise ExportException(
                f"Name '{name}' cannot be sanitized to a valid Kubernetes name"
            )

        return sanitized


class WorkflowExporter:
    """Main exporter for Kailash workflows."""

    def __init__(self, config: Optional[ExportConfig] = None):
        """Initialize the workflow exporter.

        Args:
            config: Export configuration

        Raises:
            ConfigurationException: If initialization fails
        """
        try:
            self.config = config or ExportConfig()
            self.node_mapper = NodeMapper()
            self.validator = ExportValidator()
            self.manifest_generator = ManifestGenerator(self.config)

            # Update registry if provided
            if self.config.container_registry:
                self.node_mapper.update_registry(self.config.container_registry)

            self.pre_export_hook = None
            self.post_export_hook = None

        except Exception as e:
            raise ConfigurationException(
                f"Failed to initialize workflow exporter: {e}"
            ) from e

    def to_yaml(self, workflow: Workflow, output_path: Optional[str] = None) -> str:
        """Export workflow to YAML format.

        Args:
            workflow: Workflow to export
            output_path: Optional path to write YAML file

        Returns:
            YAML string

        Raises:
            ExportException: If export fails
        """
        if not workflow:
            raise ExportException("Workflow is required")

        try:
            if self.pre_export_hook:
                self.pre_export_hook(workflow, "yaml")

            data = self._prepare_export_data(workflow)

            if self.config.validate_output:
                self.validator.validate_yaml(data)

            yaml_str = yaml.dump(data, default_flow_style=False, sort_keys=False)

            if output_path:
                try:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(output_path).write_text(yaml_str)
                except Exception as e:
                    raise ExportException(
                        f"Failed to write YAML to '{output_path}': {e}"
                    ) from e

            if self.post_export_hook:
                self.post_export_hook(workflow, "yaml", yaml_str)

            return yaml_str

        except ExportException:
            raise
        except Exception as e:
            raise ExportException(f"Failed to export workflow to YAML: {e}") from e

    def to_json(self, workflow: Workflow, output_path: Optional[str] = None) -> str:
        """Export workflow to JSON format.

        Args:
            workflow: Workflow to export
            output_path: Optional path to write JSON file

        Returns:
            JSON string

        Raises:
            ExportException: If export fails
        """
        if not workflow:
            raise ExportException("Workflow is required")

        try:
            if self.pre_export_hook:
                self.pre_export_hook(workflow, "json")

            data = self._prepare_export_data(workflow)

            if self.config.validate_output:
                self.validator.validate_json(data)

            json_str = json.dumps(data, indent=2, default=str)

            if output_path:
                try:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(output_path).write_text(json_str)
                except Exception as e:
                    raise ExportException(
                        f"Failed to write JSON to '{output_path}': {e}"
                    ) from e

            if self.post_export_hook:
                self.post_export_hook(workflow, "json", json_str)

            return json_str

        except ExportException:
            raise
        except Exception as e:
            raise ExportException(f"Failed to export workflow to JSON: {e}") from e

    def to_manifest(self, workflow: Workflow, output_path: Optional[str] = None) -> str:
        """Export workflow as deployment manifest.

        Args:
            workflow: Workflow to export
            output_path: Optional path to write manifest file

        Returns:
            Manifest YAML string

        Raises:
            ExportException: If export fails
        """
        if not workflow:
            raise ExportException("Workflow is required")

        try:
            if self.pre_export_hook:
                self.pre_export_hook(workflow, "manifest")

            manifest = self.manifest_generator.generate_manifest(
                workflow, self.node_mapper
            )

            yaml_str = yaml.dump(manifest, default_flow_style=False, sort_keys=False)

            if output_path:
                try:
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    Path(output_path).write_text(yaml_str)
                except Exception as e:
                    raise ExportException(
                        f"Failed to write manifest to '{output_path}': {e}"
                    ) from e

            if self.post_export_hook:
                self.post_export_hook(workflow, "manifest", yaml_str)

            return yaml_str

        except ExportException:
            raise
        except Exception as e:
            raise ExportException(f"Failed to export workflow manifest: {e}") from e

    def export_with_templates(
        self, workflow: Workflow, template_name: str, output_dir: str
    ) -> Dict[str, str]:
        """Export workflow using predefined templates.

        Args:
            workflow: Workflow to export
            template_name: Name of template to use
            output_dir: Directory to write files

        Returns:
            Dictionary of file paths to content

        Raises:
            ExportException: If export fails
            ImportException: If template import fails
        """
        if not workflow:
            raise ExportException("Workflow is required")
        if not template_name:
            raise ExportException("Template name is required")
        if not output_dir:
            raise ExportException("Output directory is required")

        try:
            from kailash.utils.templates import TemplateManager
        except ImportError as e:
            raise ImportException(f"Failed to import template manager: {e}") from e

        try:
            template_manager = TemplateManager()
            template = template_manager.get_template(template_name)
        except Exception as e:
            raise ExportException(
                f"Failed to get template '{template_name}': {e}"
            ) from e

        output_dir = Path(output_dir)
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ExportException(
                f"Failed to create output directory '{output_dir}': {e}"
            ) from e

        exports = {}

        # Generate files based on template
        if template.get("yaml", True):
            yaml_path = output_dir / f"{workflow.metadata.name}.yaml"
            yaml_content = self.to_yaml(workflow, str(yaml_path))
            exports[str(yaml_path)] = yaml_content

        if template.get("json", False):
            json_path = output_dir / f"{workflow.metadata.name}.json"
            json_content = self.to_json(workflow, str(json_path))
            exports[str(json_path)] = json_content

        if template.get("manifest", True):
            manifest_path = output_dir / f"{workflow.metadata.name}-manifest.yaml"
            manifest_content = self.to_manifest(workflow, str(manifest_path))
            exports[str(manifest_path)] = manifest_content

        # Generate additional files from template
        for filename, content_template in template.get("files", {}).items():
            file_path = output_dir / filename
            try:
                content = content_template.format(
                    workflow_name=workflow.metadata.name,
                    workflow_version=workflow.metadata.version,
                    namespace=self.config.namespace,
                )
                file_path.write_text(content)
                exports[str(file_path)] = content
            except Exception as e:
                logger.warning(f"Failed to generate file '{filename}': {e}")

        return exports

    def _prepare_export_data(self, workflow: Workflow) -> Dict[str, Any]:
        """Prepare workflow data for export.

        Args:
            workflow: Workflow to prepare

        Returns:
            Export data dictionary

        Raises:
            ExportException: If preparation fails
        """
        data = {
            "version": self.config.version,
            "metadata": {},
            "nodes": {},
            "connections": [],
        }

        # Add metadata if enabled
        if self.config.include_metadata:
            try:
                # workflow.metadata is a dict, not a pydantic model
                data["metadata"] = {
                    "name": workflow.name,
                    "description": workflow.description,
                    "version": workflow.version,
                    "author": workflow.author,
                }
                # Add any additional metadata from the dict
                if workflow.metadata:
                    data["metadata"].update(workflow.metadata)

                # Convert datetime to string if present
                if "created_at" in data["metadata"] and hasattr(
                    data["metadata"]["created_at"], "isoformat"
                ):
                    data["metadata"]["created_at"] = data["metadata"][
                        "created_at"
                    ].isoformat()

                # Convert set to list for JSON serialization if present
                if "tags" in data["metadata"] and isinstance(
                    data["metadata"]["tags"], set
                ):
                    data["metadata"]["tags"] = list(data["metadata"]["tags"])
            except Exception as e:
                raise ExportException(f"Failed to export metadata: {e}") from e
        else:
            data["metadata"] = {"name": workflow.name}

        # Add nodes
        for node_id, node_instance in workflow.nodes.items():
            if self.config.partial_export and node_id not in self.config.partial_export:
                continue

            try:
                node_data = {
                    "type": node_instance.node_type,
                    "config": deepcopy(node_instance.config),
                }

                # Try to add container info
                try:
                    mapping = self.node_mapper.get_mapping(node_instance.node_type)
                    node_data["container"] = {
                        "image": mapping.container_image,
                        "command": mapping.command,
                        "args": mapping.args,
                        "env": mapping.env,
                    }

                    # Add resources if enabled
                    if self.config.include_resources:
                        node_data["resources"] = mapping.resources.model_dump()
                except Exception as e:
                    logger.warning(
                        f"No container mapping for node type '{node_instance.node_type}': {e}"
                    )

                # Add position for visualization
                node_data["position"] = {
                    "x": node_instance.position[0],
                    "y": node_instance.position[1],
                }

                data["nodes"][node_id] = node_data

            except Exception as e:
                raise ExportException(f"Failed to export node '{node_id}': {e}") from e

        # Add connections
        for connection in workflow.connections:
            if self.config.partial_export:
                if (
                    connection.source_node not in self.config.partial_export
                    or connection.target_node not in self.config.partial_export
                ):
                    continue

            try:
                conn_data = {
                    "from": connection.source_node,
                    "to": connection.target_node,
                    "from_output": connection.source_output,
                    "to_input": connection.target_input,
                }
                data["connections"].append(conn_data)
            except Exception as e:
                raise ExportException(f"Failed to export connection: {e}") from e

        return data

    def register_custom_mapping(self, node_type: str, container_image: str, **kwargs):
        """Register a custom node to container mapping.

        Args:
            node_type: Python node type name
            container_image: Docker container image
            **kwargs: Additional mapping configuration

        Raises:
            ConfigurationException: If registration fails
        """
        if not node_type:
            raise ConfigurationException("Node type is required")
        if not container_image:
            raise ConfigurationException("Container image is required")

        try:
            mapping = ContainerMapping(
                python_node=node_type, container_image=container_image, **kwargs
            )
            self.node_mapper.register_mapping(mapping)
        except Exception as e:
            raise ConfigurationException(
                f"Failed to register custom mapping: {e}"
            ) from e

    def set_export_hooks(self, pre_export=None, post_export=None):
        """Set custom hooks for export process.

        Args:
            pre_export: Function to call before export
            post_export: Function to call after export
        """
        self.pre_export_hook = pre_export
        self.post_export_hook = post_export


# Convenience functions
def export_workflow(
    workflow: Workflow,
    format: str = "yaml",
    output_path: Optional[str] = None,
    **config,
) -> str:
    """Export a workflow to specified format.

    Args:
        workflow: Workflow to export
        format: Export format (yaml, json, manifest)
        output_path: Optional output file path
        **config: Export configuration options

    Returns:
        Exported content as string

    Raises:
        ExportException: If export fails
    """
    if not workflow:
        raise ExportException("Workflow is required")

    supported_formats = ["yaml", "json", "manifest"]
    if format not in supported_formats:
        raise ExportException(
            f"Unknown export format: '{format}'. "
            f"Supported formats: {supported_formats}"
        )

    try:
        export_config = ExportConfig(**config)
        exporter = WorkflowExporter(export_config)

        if format == "yaml":
            return exporter.to_yaml(workflow, output_path)
        elif format == "json":
            return exporter.to_json(workflow, output_path)
        elif format == "manifest":
            return exporter.to_manifest(workflow, output_path)

    except Exception as e:
        if isinstance(e, ExportException):
            raise
        raise ExportException(f"Failed to export workflow: {e}") from e


# Legacy compatibility aliases
KailashExporter = WorkflowExporter
