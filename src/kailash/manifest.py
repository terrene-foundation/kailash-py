"""Workflow manifest generation for Kailash deployment."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field

from kailash.sdk_exceptions import ManifestError
from kailash.workflow import Workflow


class KailashManifest(BaseModel):
    """Represents a complete Kailash deployment manifest."""

    model_config = {"arbitrary_types_allowed": True}

    metadata: Dict[str, Any] = Field(..., description="Manifest metadata")
    workflow: Optional[Workflow] = Field(None, description="Associated workflow")
    resources: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Additional deployment resources"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert manifest to dictionary.

        Returns:
            Dictionary representation
        """
        result = {"metadata": self.metadata}

        if self.workflow:
            result["workflow"] = self.workflow.to_dict()

        if self.resources:
            result["resources"] = self.resources

        return result

    def to_yaml(self) -> str:
        """Convert manifest to YAML string.

        Returns:
            YAML representation
        """
        return yaml.dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    def to_json(self) -> str:
        """Convert manifest to JSON string.

        Returns:
            JSON representation
        """
        return json.dumps(self.to_dict(), indent=2)

    def save(self, path: Union[str, Path], format: str = "yaml") -> None:
        """Save manifest to file.

        Args:
            path: File path
            format: Output format (yaml or json)

        Raises:
            ValueError: If format is invalid
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "yaml":
            with open(output_path, "w") as f:
                f.write(self.to_yaml())
        elif format == "json":
            with open(output_path, "w") as f:
                f.write(self.to_json())
        else:
            raise ValueError(f"Unknown format: {format}")

    @classmethod
    def from_workflow(cls, workflow: Workflow, **metadata) -> "KailashManifest":
        """Create manifest from workflow.

        Args:
            workflow: Workflow to include
            **metadata: Additional metadata

        Returns:
            KailashManifest instance
        """
        # Default metadata
        default_metadata = {
            "id": workflow.metadata.name,
            "name": workflow.metadata.name,
            "version": workflow.metadata.version,
            "author": workflow.metadata.author,
            "description": workflow.metadata.description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Override defaults with provided metadata
        default_metadata.update(metadata)

        return cls(metadata=default_metadata, workflow=workflow)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KailashManifest":
        """Create manifest from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            KailashManifest instance

        Raises:
            ManifestError: If data is invalid
        """
        try:
            metadata = data.get("metadata", {})

            workflow = None
            if "workflow" in data:
                from kailash.workflow import Workflow

                workflow = Workflow.from_dict(data["workflow"])

            resources = data.get("resources", {})

            return cls(metadata=metadata, workflow=workflow, resources=resources)
        except Exception as e:
            raise ManifestError(f"Failed to create manifest from data: {e}") from e

    @classmethod
    def load(cls, path: Union[str, Path]) -> "KailashManifest":
        """Load manifest from file.

        Args:
            path: File path

        Returns:
            KailashManifest instance

        Raises:
            ManifestError: If loading fails
        """
        try:
            file_path = Path(path)
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")

            with open(file_path, "r") as f:
                content = f.read()

            # Parse based on file extension
            if file_path.suffix.lower() in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            elif file_path.suffix.lower() == ".json":
                data = json.loads(content)
            else:
                raise ValueError(f"Unsupported file format: {file_path.suffix}")

            return cls.from_dict(data)
        except Exception as e:
            raise ManifestError(f"Failed to load manifest from {path}: {e}") from e


class DeploymentConfig(BaseModel):
    """Configuration for deployment manifest."""

    name: str = Field(..., description="Deployment name")
    namespace: str = Field("default", description="Kubernetes namespace")
    replicas: int = Field(1, description="Number of replicas")
    strategy: str = Field("RollingUpdate", description="Deployment strategy")
    labels: Dict[str, str] = Field(
        default_factory=dict, description="Kubernetes labels"
    )
    annotations: Dict[str, str] = Field(
        default_factory=dict, description="Kubernetes annotations"
    )
    image_pull_policy: str = Field("IfNotPresent", description="Image pull policy")
    service_account: Optional[str] = Field(None, description="Service account name")
    node_selector: Dict[str, str] = Field(
        default_factory=dict, description="Node selector"
    )
    tolerations: List[Dict[str, Any]] = Field(
        default_factory=list, description="Pod tolerations"
    )
    affinity: Optional[Dict[str, Any]] = Field(None, description="Pod affinity rules")


class ServiceConfig(BaseModel):
    """Configuration for Kubernetes service."""

    name: str = Field(..., description="Service name")
    type: str = Field("ClusterIP", description="Service type")
    ports: List[Dict[str, Any]] = Field(
        default_factory=list, description="Service ports"
    )
    selector: Dict[str, str] = Field(default_factory=dict, description="Pod selector")
    labels: Dict[str, str] = Field(default_factory=dict, description="Service labels")


class VolumeConfig(BaseModel):
    """Configuration for volumes."""

    name: str = Field(..., description="Volume name")
    type: str = Field("configMap", description="Volume type")
    source: str = Field(..., description="Volume source")
    mount_path: str = Field(..., description="Mount path in container")
    read_only: bool = Field(True, description="Read-only mount")
    sub_path: Optional[str] = Field(None, description="Sub-path within volume")


class ConfigMapConfig(BaseModel):
    """Configuration for ConfigMap."""

    name: str = Field(..., description="ConfigMap name")
    namespace: str = Field("default", description="Namespace")
    data: Dict[str, str] = Field(default_factory=dict, description="ConfigMap data")
    binary_data: Dict[str, str] = Field(default_factory=dict, description="Binary data")
    labels: Dict[str, str] = Field(default_factory=dict, description="Labels")


class SecretConfig(BaseModel):
    """Configuration for Secret."""

    name: str = Field(..., description="Secret name")
    namespace: str = Field("default", description="Namespace")
    type: str = Field("Opaque", description="Secret type")
    data: Dict[str, str] = Field(default_factory=dict, description="Secret data")
    string_data: Dict[str, str] = Field(default_factory=dict, description="String data")
    labels: Dict[str, str] = Field(default_factory=dict, description="Labels")


class ManifestBuilder:
    """Builder for creating deployment manifests."""

    def __init__(self, workflow: Workflow):
        """Initialize the manifest builder.

        Args:
            workflow: Workflow to build manifest for
        """
        self.workflow = workflow
        self.deployment_config = None
        self.service_configs: List[ServiceConfig] = []
        self.volume_configs: List[VolumeConfig] = []
        self.configmap_configs: List[ConfigMapConfig] = []
        self.secret_configs: List[SecretConfig] = []

    def with_deployment(self, config: DeploymentConfig) -> "ManifestBuilder":
        """Add deployment configuration.

        Args:
            config: Deployment configuration

        Returns:
            Self for chaining
        """
        self.deployment_config = config
        return self

    def with_service(self, config: ServiceConfig) -> "ManifestBuilder":
        """Add service configuration.

        Args:
            config: Service configuration

        Returns:
            Self for chaining
        """
        self.service_configs.append(config)
        return self

    def with_volume(self, config: VolumeConfig) -> "ManifestBuilder":
        """Add volume configuration.

        Args:
            config: Volume configuration

        Returns:
            Self for chaining
        """
        self.volume_configs.append(config)
        return self

    def with_configmap(self, config: ConfigMapConfig) -> "ManifestBuilder":
        """Add ConfigMap configuration.

        Args:
            config: ConfigMap configuration

        Returns:
            Self for chaining
        """
        self.configmap_configs.append(config)
        return self

    def with_secret(self, config: SecretConfig) -> "ManifestBuilder":
        """Add Secret configuration.

        Args:
            config: Secret configuration

        Returns:
            Self for chaining
        """
        self.secret_configs.append(config)
        return self

    def build(self) -> Dict[str, Any]:
        """Build the complete manifest.

        Returns:
            Complete manifest dictionary
        """
        if not self.deployment_config:
            raise ManifestError("Deployment configuration is required")

        manifest = {"apiVersion": "v1", "kind": "List", "items": []}

        # Add ConfigMaps
        for configmap in self.configmap_configs:
            manifest["items"].append(self._build_configmap(configmap))

        # Add Secrets
        for secret in self.secret_configs:
            manifest["items"].append(self._build_secret(secret))

        # Add Deployment
        manifest["items"].append(self._build_deployment())

        # Add Services
        for service in self.service_configs:
            manifest["items"].append(self._build_service(service))

        # Add Workflow CRD
        manifest["items"].append(self._build_workflow_crd())

        return manifest

    def _build_deployment(self) -> Dict[str, Any]:
        """Build deployment manifest."""
        config = self.deployment_config

        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": config.name,
                "namespace": config.namespace,
                "labels": config.labels,
                "annotations": config.annotations,
            },
            "spec": {
                "replicas": config.replicas,
                "strategy": {"type": config.strategy},
                "selector": {
                    "matchLabels": {
                        "app": config.name,
                        "workflow": self.workflow.metadata.name,
                    }
                },
                "template": {
                    "metadata": {
                        "labels": {
                            "app": config.name,
                            "workflow": self.workflow.metadata.name,
                            **config.labels,
                        }
                    },
                    "spec": {"containers": []},
                },
            },
        }

        # Add service account if specified
        if config.service_account:
            deployment["spec"]["template"]["spec"][
                "serviceAccountName"
            ] = config.service_account

        # Add node selector
        if config.node_selector:
            deployment["spec"]["template"]["spec"][
                "nodeSelector"
            ] = config.node_selector

        # Add tolerations
        if config.tolerations:
            deployment["spec"]["template"]["spec"]["tolerations"] = config.tolerations

        # Add affinity
        if config.affinity:
            deployment["spec"]["template"]["spec"]["affinity"] = config.affinity

        # Add volumes
        if self.volume_configs:
            volumes = []
            volume_mounts = []

            for vol_config in self.volume_configs:
                volume = {"name": vol_config.name}

                if vol_config.type == "configMap":
                    volume["configMap"] = {"name": vol_config.source}
                elif vol_config.type == "secret":
                    volume["secret"] = {"secretName": vol_config.source}
                elif vol_config.type == "persistentVolumeClaim":
                    volume["persistentVolumeClaim"] = {"claimName": vol_config.source}

                volumes.append(volume)

                mount = {
                    "name": vol_config.name,
                    "mountPath": vol_config.mount_path,
                    "readOnly": vol_config.read_only,
                }

                if vol_config.sub_path:
                    mount["subPath"] = vol_config.sub_path

                volume_mounts.append(mount)

            deployment["spec"]["template"]["spec"]["volumes"] = volumes

        # Add workflow controller container
        controller_container = {
            "name": "workflow-controller",
            "image": "kailash/workflow-controller:latest",
            "imagePullPolicy": config.image_pull_policy,
            "env": [
                {"name": "WORKFLOW_NAME", "value": self.workflow.metadata.name},
                {"name": "NAMESPACE", "value": config.namespace},
            ],
            "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}},
        }

        if hasattr(self, "volume_mounts"):
            controller_container["volumeMounts"] = volume_mounts

        deployment["spec"]["template"]["spec"]["containers"].append(
            controller_container
        )

        return deployment

    def _build_service(self, config: ServiceConfig) -> Dict[str, Any]:
        """Build service manifest."""
        service = {
            "apiVersion": "v1",
            "kind": "Service",
            "metadata": {
                "name": config.name,
                "namespace": self.deployment_config.namespace,
                "labels": config.labels,
            },
            "spec": {
                "type": config.type,
                "selector": config.selector
                or {
                    "app": self.deployment_config.name,
                    "workflow": self.workflow.metadata.name,
                },
                "ports": config.ports,
            },
        }

        return service

    def _build_configmap(self, config: ConfigMapConfig) -> Dict[str, Any]:
        """Build ConfigMap manifest."""
        configmap = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": config.name,
                "namespace": config.namespace,
                "labels": config.labels,
            },
            "data": config.data,
        }

        if config.binary_data:
            configmap["binaryData"] = config.binary_data

        return configmap

    def _build_secret(self, config: SecretConfig) -> Dict[str, Any]:
        """Build Secret manifest."""
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": config.name,
                "namespace": config.namespace,
                "labels": config.labels,
            },
            "type": config.type,
            "data": config.data,
        }

        if config.string_data:
            secret["stringData"] = config.string_data

        return secret

    def _build_workflow_crd(self) -> Dict[str, Any]:
        """Build workflow custom resource."""
        from kailash.utils.export import ExportConfig, WorkflowExporter

        # Use exporter to get workflow data
        export_config = ExportConfig(
            namespace=self.deployment_config.namespace,
            include_metadata=True,
            include_resources=True,
        )
        exporter = WorkflowExporter(export_config)

        return exporter.manifest_generator.generate_manifest(
            self.workflow, exporter.node_mapper
        )


class ManifestGenerator:
    """Generator for creating deployment manifests from workflows."""

    @staticmethod
    def generate_simple_manifest(
        workflow: Workflow, name: str, namespace: str = "default"
    ) -> Dict[str, Any]:
        """Generate a simple deployment manifest.

        Args:
            workflow: Workflow to deploy
            name: Deployment name
            namespace: Kubernetes namespace

        Returns:
            Deployment manifest
        """
        builder = ManifestBuilder(workflow)

        # Add deployment
        deployment_config = DeploymentConfig(
            name=name,
            namespace=namespace,
            labels={
                "app": name,
                "workflow": workflow.metadata.name,
                "version": workflow.metadata.version,
            },
        )
        builder.with_deployment(deployment_config)

        # Add service
        service_config = ServiceConfig(
            name=f"{name}-service",
            ports=[{"name": "http", "port": 80, "targetPort": 8080}],
        )
        builder.with_service(service_config)

        # Add workflow ConfigMap
        configmap_config = ConfigMapConfig(
            name=f"{name}-config",
            namespace=namespace,
            data={"workflow.yaml": yaml.dump(workflow.to_dict())},
        )
        builder.with_configmap(configmap_config)

        # Add volume for ConfigMap
        volume_config = VolumeConfig(
            name="workflow-config",
            type="configMap",
            source=f"{name}-config",
            mount_path="/config",
        )
        builder.with_volume(volume_config)

        return builder.build()

    @staticmethod
    def generate_advanced_manifest(
        workflow: Workflow,
        name: str,
        namespace: str = "default",
        replicas: int = 1,
        resources: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Generate an advanced deployment manifest with custom configuration.

        Args:
            workflow: Workflow to deploy
            name: Deployment name
            namespace: Kubernetes namespace
            replicas: Number of replicas
            resources: Resource requirements
            **kwargs: Additional configuration options

        Returns:
            Deployment manifest
        """
        builder = ManifestBuilder(workflow)

        # Add deployment with advanced configuration
        deployment_config = DeploymentConfig(
            name=name,
            namespace=namespace,
            replicas=replicas,
            labels=kwargs.get(
                "labels",
                {
                    "app": name,
                    "workflow": workflow.metadata.name,
                    "version": workflow.metadata.version,
                },
            ),
            annotations=kwargs.get("annotations", {}),
            node_selector=kwargs.get("node_selector", {}),
            tolerations=kwargs.get("tolerations", []),
            affinity=kwargs.get("affinity", None),
            service_account=kwargs.get("service_account", None),
        )
        builder.with_deployment(deployment_config)

        # Add services
        if kwargs.get("expose_external", False):
            service_config = ServiceConfig(
                name=f"{name}-external",
                type="LoadBalancer",
                ports=[{"name": "http", "port": 80, "targetPort": 8080}],
            )
            builder.with_service(service_config)

        # Internal service
        internal_service = ServiceConfig(
            name=f"{name}-internal",
            type="ClusterIP",
            ports=[
                {"name": "http", "port": 8080, "targetPort": 8080},
                {"name": "metrics", "port": 9090, "targetPort": 9090},
            ],
        )
        builder.with_service(internal_service)

        # Add ConfigMaps
        # Workflow config
        workflow_config = ConfigMapConfig(
            name=f"{name}-workflow",
            namespace=namespace,
            data={
                "workflow.yaml": yaml.dump(workflow.to_dict()),
                "workflow.json": json.dumps(workflow.to_dict(), indent=2),
            },
        )
        builder.with_configmap(workflow_config)

        # Runtime config
        runtime_config = ConfigMapConfig(
            name=f"{name}-runtime",
            namespace=namespace,
            data=kwargs.get(
                "runtime_config",
                {
                    "log_level": "INFO",
                    "metrics_enabled": "true",
                    "trace_enabled": "false",
                },
            ),
        )
        builder.with_configmap(runtime_config)

        # Add Secrets if provided
        if "secrets" in kwargs:
            for secret_name, secret_data in kwargs["secrets"].items():
                secret_config = SecretConfig(
                    name=f"{name}-{secret_name}", namespace=namespace, data=secret_data
                )
                builder.with_secret(secret_config)

        # Add Volumes
        # Workflow config volume
        workflow_volume = VolumeConfig(
            name="workflow-config",
            type="configMap",
            source=f"{name}-workflow",
            mount_path="/config/workflow",
        )
        builder.with_volume(workflow_volume)

        # Runtime config volume
        runtime_volume = VolumeConfig(
            name="runtime-config",
            type="configMap",
            source=f"{name}-runtime",
            mount_path="/config/runtime",
        )
        builder.with_volume(runtime_volume)

        # Data volume if specified
        if kwargs.get("persistent_storage", False):
            data_volume = VolumeConfig(
                name="data",
                type="persistentVolumeClaim",
                source=f"{name}-data",
                mount_path="/data",
                read_only=False,
            )
            builder.with_volume(data_volume)

        return builder.build()

    @staticmethod
    def save_manifest(manifest: Dict[str, Any], path: str, format: str = "yaml"):
        """Save manifest to file.

        Args:
            manifest: Manifest dictionary
            path: Output file path
            format: Output format (yaml or json)
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if format == "yaml":
            with open(output_path, "w") as f:
                yaml.dump(manifest, f, default_flow_style=False, sort_keys=False)
        elif format == "json":
            with open(output_path, "w") as f:
                json.dump(manifest, f, indent=2)
        else:
            raise ValueError(f"Unknown format: {format}")


# Convenience functions
def create_deployment_manifest(
    workflow: Workflow, deployment_name: str, **config
) -> Dict[str, Any]:
    """Create a deployment manifest for a workflow.

    Args:
        workflow: Workflow to deploy
        deployment_name: Name for the deployment
        **config: Additional configuration

    Returns:
        Deployment manifest
    """
    if config.get("advanced", False):
        return ManifestGenerator.generate_advanced_manifest(
            workflow, deployment_name, **config
        )
    else:
        return ManifestGenerator.generate_simple_manifest(
            workflow, deployment_name, namespace=config.get("namespace", "default")
        )


def save_deployment_manifest(
    workflow: Workflow,
    deployment_name: str,
    output_path: str,
    format: str = "yaml",
    **config,
):
    """Create and save a deployment manifest.

    Args:
        workflow: Workflow to deploy
        deployment_name: Name for the deployment
        output_path: Output file path
        format: Output format (yaml or json)
        **config: Additional configuration
    """
    manifest = create_deployment_manifest(workflow, deployment_name, **config)
    ManifestGenerator.save_manifest(manifest, output_path, format)
