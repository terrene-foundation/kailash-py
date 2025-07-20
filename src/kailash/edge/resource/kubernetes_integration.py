"""Kubernetes integration for edge resource management."""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import yaml

try:
    from kubernetes import client, config, watch
    from kubernetes.client.rest import ApiException

    KUBERNETES_AVAILABLE = True
except ImportError:
    KUBERNETES_AVAILABLE = False


class KubernetesResourceType(Enum):
    """Kubernetes resource types."""

    DEPLOYMENT = "deployment"
    SERVICE = "service"
    CONFIGMAP = "configmap"
    SECRET = "secret"
    POD = "pod"
    PERSISTENT_VOLUME = "persistent_volume"
    PERSISTENT_VOLUME_CLAIM = "persistent_volume_claim"
    INGRESS = "ingress"
    HORIZONTAL_POD_AUTOSCALER = "horizontal_pod_autoscaler"
    CUSTOM_RESOURCE = "custom_resource"


class ScalingPolicy(Enum):
    """Pod scaling policies."""

    MANUAL = "manual"
    HORIZONTAL_POD_AUTOSCALER = "hpa"
    VERTICAL_POD_AUTOSCALER = "vpa"
    PREDICTIVE = "predictive"
    REACTIVE = "reactive"


@dataclass
class KubernetesResource:
    """Kubernetes resource definition."""

    name: str
    namespace: str
    resource_type: KubernetesResourceType
    spec: Dict[str, Any]
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None
    edge_node: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
        if self.labels is None:
            self.labels = {}
        if self.annotations is None:
            self.annotations = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["resource_type"] = self.resource_type.value
        data["created_at"] = self.created_at.isoformat()
        data["updated_at"] = self.updated_at.isoformat()
        return data

    def to_k8s_manifest(self) -> Dict[str, Any]:
        """Convert to Kubernetes manifest."""
        api_version, kind = self._get_api_version_kind()

        manifest = {
            "apiVersion": api_version,
            "kind": kind,
            "metadata": {
                "name": self.name,
                "namespace": self.namespace,
                "labels": self.labels.copy(),
                "annotations": self.annotations.copy(),
            },
            "spec": self.spec.copy(),
        }

        # Add edge node selector if specified
        if self.edge_node:
            if (
                "spec" in manifest
                and "template" in manifest["spec"]
                and "spec" in manifest["spec"]["template"]
            ):
                # For Deployments and similar resources
                node_selector = manifest["spec"]["template"]["spec"].get(
                    "nodeSelector", {}
                )
                node_selector["edge-node"] = self.edge_node
                manifest["spec"]["template"]["spec"]["nodeSelector"] = node_selector
            elif "spec" in manifest:
                # For other resources
                node_selector = manifest["spec"].get("nodeSelector", {})
                node_selector["edge-node"] = self.edge_node
                manifest["spec"]["nodeSelector"] = node_selector

        return manifest

    def _get_api_version_kind(self) -> tuple[str, str]:
        """Get API version and kind for resource type."""
        mapping = {
            KubernetesResourceType.DEPLOYMENT: ("apps/v1", "Deployment"),
            KubernetesResourceType.SERVICE: ("v1", "Service"),
            KubernetesResourceType.CONFIGMAP: ("v1", "ConfigMap"),
            KubernetesResourceType.SECRET: ("v1", "Secret"),
            KubernetesResourceType.POD: ("v1", "Pod"),
            KubernetesResourceType.PERSISTENT_VOLUME: ("v1", "PersistentVolume"),
            KubernetesResourceType.PERSISTENT_VOLUME_CLAIM: (
                "v1",
                "PersistentVolumeClaim",
            ),
            KubernetesResourceType.INGRESS: ("networking.k8s.io/v1", "Ingress"),
            KubernetesResourceType.HORIZONTAL_POD_AUTOSCALER: (
                "autoscaling/v2",
                "HorizontalPodAutoscaler",
            ),
        }
        return mapping.get(self.resource_type, ("v1", "Unknown"))


@dataclass
class PodScalingSpec:
    """Pod scaling specification."""

    min_replicas: int
    max_replicas: int
    target_cpu_utilization: float
    target_memory_utilization: Optional[float] = None
    scale_up_policy: Optional[Dict[str, Any]] = None
    scale_down_policy: Optional[Dict[str, Any]] = None
    behavior: Optional[Dict[str, Any]] = None

    def to_hpa_spec(self) -> Dict[str, Any]:
        """Convert to HPA specification."""
        spec = {
            "minReplicas": self.min_replicas,
            "maxReplicas": self.max_replicas,
            "metrics": [
                {
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": int(
                                self.target_cpu_utilization * 100
                            ),
                        },
                    },
                }
            ],
        }

        if self.target_memory_utilization:
            spec["metrics"].append(
                {
                    "type": "Resource",
                    "resource": {
                        "name": "memory",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": int(
                                self.target_memory_utilization * 100
                            ),
                        },
                    },
                }
            )

        if self.behavior:
            spec["behavior"] = self.behavior

        return spec


class KubernetesIntegration:
    """Kubernetes integration for edge resource management."""

    def __init__(
        self,
        kubeconfig_path: Optional[str] = None,
        context_name: Optional[str] = None,
        namespace: str = "default",
    ):
        """Initialize Kubernetes integration.

        Args:
            kubeconfig_path: Path to kubeconfig file
            context_name: Kubernetes context to use
            namespace: Default namespace
        """
        if not KUBERNETES_AVAILABLE:
            raise ImportError(
                "Kubernetes client not available. Install with: pip install kubernetes"
            )

        self.kubeconfig_path = kubeconfig_path
        self.context_name = context_name
        self.namespace = namespace

        # Kubernetes clients
        self.core_v1 = None
        self.apps_v1 = None
        self.autoscaling_v2 = None
        self.custom_objects = None

        # Resource cache
        self.resources: Dict[str, KubernetesResource] = {}
        self.resource_status: Dict[str, Dict[str, Any]] = {}

        # Scaling management
        self.scaling_policies: Dict[str, PodScalingSpec] = {}
        self.autoscalers: Dict[str, str] = {}  # deployment -> hpa name

        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._scaling_task: Optional[asyncio.Task] = None

        # Configuration
        self.monitoring_interval = 30  # seconds
        self.scaling_check_interval = 60  # seconds
        self.default_scaling_policy = ScalingPolicy.MANUAL

    async def initialize(self) -> None:
        """Initialize Kubernetes clients."""
        try:
            if self.kubeconfig_path:
                config.load_kube_config(
                    config_file=self.kubeconfig_path, context=self.context_name
                )
            else:
                # Try in-cluster config first, then kubeconfig
                try:
                    config.load_incluster_config()
                except config.ConfigException:
                    config.load_kube_config(context=self.context_name)

            # Initialize clients
            self.core_v1 = client.CoreV1Api()
            self.apps_v1 = client.AppsV1Api()
            self.autoscaling_v2 = client.AutoscalingV2Api()
            self.custom_objects = client.CustomObjectsApi()

            # Test connection
            await asyncio.to_thread(self.core_v1.list_namespace)

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Kubernetes client: {e}")

    async def create_resource(self, resource: KubernetesResource) -> Dict[str, Any]:
        """Create Kubernetes resource.

        Args:
            resource: Resource to create

        Returns:
            Creation result
        """
        if not self.core_v1:
            await self.initialize()

        try:
            manifest = resource.to_k8s_manifest()

            if resource.resource_type == KubernetesResourceType.DEPLOYMENT:
                result = await asyncio.to_thread(
                    self.apps_v1.create_namespaced_deployment,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.SERVICE:
                result = await asyncio.to_thread(
                    self.core_v1.create_namespaced_service,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.CONFIGMAP:
                result = await asyncio.to_thread(
                    self.core_v1.create_namespaced_config_map,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.SECRET:
                result = await asyncio.to_thread(
                    self.core_v1.create_namespaced_secret,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.POD:
                result = await asyncio.to_thread(
                    self.core_v1.create_namespaced_pod,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif (
                resource.resource_type
                == KubernetesResourceType.HORIZONTAL_POD_AUTOSCALER
            ):
                result = await asyncio.to_thread(
                    self.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler,
                    namespace=resource.namespace,
                    body=manifest,
                )
            else:
                raise ValueError(f"Unsupported resource type: {resource.resource_type}")

            # Store resource
            resource_key = f"{resource.namespace}/{resource.name}"
            self.resources[resource_key] = resource

            return {
                "status": "created",
                "name": resource.name,
                "namespace": resource.namespace,
                "resource_type": resource.resource_type.value,
                "uid": getattr(result.metadata, "uid", None),
                "creation_timestamp": getattr(
                    result.metadata, "creation_timestamp", None
                ),
            }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to create resource: {e}"}

    async def update_resource(self, resource: KubernetesResource) -> Dict[str, Any]:
        """Update Kubernetes resource.

        Args:
            resource: Resource to update

        Returns:
            Update result
        """
        if not self.core_v1:
            await self.initialize()

        try:
            manifest = resource.to_k8s_manifest()

            if resource.resource_type == KubernetesResourceType.DEPLOYMENT:
                result = await asyncio.to_thread(
                    self.apps_v1.patch_namespaced_deployment,
                    name=resource.name,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.SERVICE:
                result = await asyncio.to_thread(
                    self.core_v1.patch_namespaced_service,
                    name=resource.name,
                    namespace=resource.namespace,
                    body=manifest,
                )
            elif resource.resource_type == KubernetesResourceType.CONFIGMAP:
                result = await asyncio.to_thread(
                    self.core_v1.patch_namespaced_config_map,
                    name=resource.name,
                    namespace=resource.namespace,
                    body=manifest,
                )
            else:
                raise ValueError(
                    f"Update not supported for resource type: {resource.resource_type}"
                )

            # Update stored resource
            resource_key = f"{resource.namespace}/{resource.name}"
            resource.updated_at = datetime.now()
            self.resources[resource_key] = resource

            return {
                "status": "updated",
                "name": resource.name,
                "namespace": resource.namespace,
                "resource_type": resource.resource_type.value,
                "updated_at": resource.updated_at.isoformat(),
            }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to update resource: {e}"}

    async def delete_resource(
        self, name: str, namespace: str, resource_type: KubernetesResourceType
    ) -> Dict[str, Any]:
        """Delete Kubernetes resource.

        Args:
            name: Resource name
            namespace: Resource namespace
            resource_type: Type of resource

        Returns:
            Deletion result
        """
        if not self.core_v1:
            await self.initialize()

        try:
            if resource_type == KubernetesResourceType.DEPLOYMENT:
                await asyncio.to_thread(
                    self.apps_v1.delete_namespaced_deployment,
                    name=name,
                    namespace=namespace,
                )
            elif resource_type == KubernetesResourceType.SERVICE:
                await asyncio.to_thread(
                    self.core_v1.delete_namespaced_service,
                    name=name,
                    namespace=namespace,
                )
            elif resource_type == KubernetesResourceType.CONFIGMAP:
                await asyncio.to_thread(
                    self.core_v1.delete_namespaced_config_map,
                    name=name,
                    namespace=namespace,
                )
            elif resource_type == KubernetesResourceType.SECRET:
                await asyncio.to_thread(
                    self.core_v1.delete_namespaced_secret,
                    name=name,
                    namespace=namespace,
                )
            elif resource_type == KubernetesResourceType.POD:
                await asyncio.to_thread(
                    self.core_v1.delete_namespaced_pod, name=name, namespace=namespace
                )
            else:
                raise ValueError(
                    f"Delete not supported for resource type: {resource_type}"
                )

            # Remove from cache
            resource_key = f"{namespace}/{name}"
            self.resources.pop(resource_key, None)
            self.resource_status.pop(resource_key, None)

            return {
                "status": "deleted",
                "name": name,
                "namespace": namespace,
                "resource_type": resource_type.value,
            }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to delete resource: {e}"}

    async def get_resource_status(
        self, name: str, namespace: str, resource_type: KubernetesResourceType
    ) -> Dict[str, Any]:
        """Get Kubernetes resource status.

        Args:
            name: Resource name
            namespace: Resource namespace
            resource_type: Type of resource

        Returns:
            Resource status
        """
        if not self.core_v1:
            await self.initialize()

        try:
            if resource_type == KubernetesResourceType.DEPLOYMENT:
                result = await asyncio.to_thread(
                    self.apps_v1.read_namespaced_deployment_status,
                    name=name,
                    namespace=namespace,
                )
                return {
                    "status": (
                        "ready"
                        if result.status.ready_replicas == result.status.replicas
                        else "not_ready"
                    ),
                    "replicas": result.status.replicas or 0,
                    "ready_replicas": result.status.ready_replicas or 0,
                    "available_replicas": result.status.available_replicas or 0,
                    "updated_replicas": result.status.updated_replicas or 0,
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                        for condition in (result.status.conditions or [])
                    ],
                }
            elif resource_type == KubernetesResourceType.POD:
                result = await asyncio.to_thread(
                    self.core_v1.read_namespaced_pod_status,
                    name=name,
                    namespace=namespace,
                )
                return {
                    "status": result.status.phase,
                    "node_name": result.spec.node_name,
                    "pod_ip": result.status.pod_ip,
                    "start_time": (
                        result.status.start_time.isoformat()
                        if result.status.start_time
                        else None
                    ),
                    "conditions": [
                        {
                            "type": condition.type,
                            "status": condition.status,
                            "reason": condition.reason,
                            "message": condition.message,
                        }
                        for condition in (result.status.conditions or [])
                    ],
                    "container_statuses": [
                        {
                            "name": container.name,
                            "ready": container.ready,
                            "restart_count": container.restart_count,
                            "state": (
                                container.state.to_dict() if container.state else None
                            ),
                        }
                        for container in (result.status.container_statuses or [])
                    ],
                }
            else:
                return {
                    "status": "unknown",
                    "message": f"Status not implemented for resource type: {resource_type.value}",
                }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to get resource status: {e}"}

    async def list_resources(
        self,
        namespace: Optional[str] = None,
        resource_type: Optional[KubernetesResourceType] = None,
        labels: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """List Kubernetes resources.

        Args:
            namespace: Filter by namespace (all if None)
            resource_type: Filter by resource type (all if None)
            labels: Label selector

        Returns:
            List of resources
        """
        if not self.core_v1:
            await self.initialize()

        resources = []
        label_selector = ",".join([f"{k}={v}" for k, v in (labels or {}).items()])
        target_namespace = namespace or self.namespace

        try:
            if not resource_type or resource_type == KubernetesResourceType.DEPLOYMENT:
                deployments = await asyncio.to_thread(
                    self.apps_v1.list_namespaced_deployment,
                    namespace=target_namespace,
                    label_selector=label_selector,
                )
                for deployment in deployments.items:
                    resources.append(
                        {
                            "name": deployment.metadata.name,
                            "namespace": deployment.metadata.namespace,
                            "resource_type": "deployment",
                            "labels": deployment.metadata.labels or {},
                            "annotations": deployment.metadata.annotations or {},
                            "created_at": deployment.metadata.creation_timestamp.isoformat(),
                            "replicas": deployment.status.replicas or 0,
                            "ready_replicas": deployment.status.ready_replicas or 0,
                        }
                    )

            if not resource_type or resource_type == KubernetesResourceType.SERVICE:
                services = await asyncio.to_thread(
                    self.core_v1.list_namespaced_service,
                    namespace=target_namespace,
                    label_selector=label_selector,
                )
                for service in services.items:
                    resources.append(
                        {
                            "name": service.metadata.name,
                            "namespace": service.metadata.namespace,
                            "resource_type": "service",
                            "labels": service.metadata.labels or {},
                            "annotations": service.metadata.annotations or {},
                            "created_at": service.metadata.creation_timestamp.isoformat(),
                            "cluster_ip": service.spec.cluster_ip,
                            "external_ips": service.spec.external_i_ps or [],
                            "ports": [
                                {
                                    "name": port.name,
                                    "port": port.port,
                                    "target_port": str(port.target_port),
                                    "protocol": port.protocol,
                                }
                                for port in (service.spec.ports or [])
                            ],
                        }
                    )

            if not resource_type or resource_type == KubernetesResourceType.POD:
                pods = await asyncio.to_thread(
                    self.core_v1.list_namespaced_pod,
                    namespace=target_namespace,
                    label_selector=label_selector,
                )
                for pod in pods.items:
                    resources.append(
                        {
                            "name": pod.metadata.name,
                            "namespace": pod.metadata.namespace,
                            "resource_type": "pod",
                            "labels": pod.metadata.labels or {},
                            "annotations": pod.metadata.annotations or {},
                            "created_at": pod.metadata.creation_timestamp.isoformat(),
                            "phase": pod.status.phase,
                            "node_name": pod.spec.node_name,
                            "pod_ip": pod.status.pod_ip,
                        }
                    )

            return resources

        except ApiException as e:
            raise RuntimeError(f"Kubernetes API error: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to list resources: {e}")

    async def create_autoscaler(
        self, deployment_name: str, namespace: str, scaling_spec: PodScalingSpec
    ) -> Dict[str, Any]:
        """Create Horizontal Pod Autoscaler for deployment.

        Args:
            deployment_name: Target deployment name
            namespace: Namespace
            scaling_spec: Scaling specification

        Returns:
            Creation result
        """
        if not self.autoscaling_v2:
            await self.initialize()

        hpa_name = f"{deployment_name}-hpa"

        try:
            # Create HPA manifest
            hpa_manifest = {
                "apiVersion": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "metadata": {
                    "name": hpa_name,
                    "namespace": namespace,
                    "labels": {"app": deployment_name, "component": "autoscaler"},
                },
                "spec": scaling_spec.to_hpa_spec(),
            }

            # Add scale target reference
            hpa_manifest["spec"]["scaleTargetRef"] = {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": deployment_name,
            }

            # Create HPA
            result = await asyncio.to_thread(
                self.autoscaling_v2.create_namespaced_horizontal_pod_autoscaler,
                namespace=namespace,
                body=hpa_manifest,
            )

            # Store scaling policy and autoscaler reference
            self.scaling_policies[f"{namespace}/{deployment_name}"] = scaling_spec
            self.autoscalers[f"{namespace}/{deployment_name}"] = hpa_name

            return {
                "status": "created",
                "hpa_name": hpa_name,
                "deployment_name": deployment_name,
                "namespace": namespace,
                "min_replicas": scaling_spec.min_replicas,
                "max_replicas": scaling_spec.max_replicas,
                "target_cpu_utilization": scaling_spec.target_cpu_utilization,
            }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to create autoscaler: {e}"}

    async def scale_deployment(
        self, deployment_name: str, namespace: str, replicas: int
    ) -> Dict[str, Any]:
        """Scale deployment to specified replica count.

        Args:
            deployment_name: Deployment name
            namespace: Namespace
            replicas: Target replica count

        Returns:
            Scaling result
        """
        if not self.apps_v1:
            await self.initialize()

        try:
            # Update deployment replica count
            await asyncio.to_thread(
                self.apps_v1.patch_namespaced_deployment_scale,
                name=deployment_name,
                namespace=namespace,
                body={"spec": {"replicas": replicas}},
            )

            return {
                "status": "scaled",
                "deployment_name": deployment_name,
                "namespace": namespace,
                "target_replicas": replicas,
                "scaled_at": datetime.now().isoformat(),
            }

        except ApiException as e:
            return {
                "status": "error",
                "error": f"Kubernetes API error: {e}",
                "reason": getattr(e, "reason", "Unknown"),
                "code": getattr(e, "status", 500),
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to scale deployment: {e}"}

    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster information.

        Returns:
            Cluster information
        """
        if not self.core_v1:
            await self.initialize()

        try:
            # Get cluster version
            version = await asyncio.to_thread(
                self.core_v1.api_client.call_api, "/version", "GET"
            )
            version_info = json.loads(version[0])

            # Get nodes
            nodes = await asyncio.to_thread(self.core_v1.list_node)

            node_info = []
            for node in nodes.items:
                node_data = {
                    "name": node.metadata.name,
                    "labels": node.metadata.labels or {},
                    "ready": False,
                    "allocatable": {},
                    "capacity": {},
                }

                # Check node ready status
                for condition in node.status.conditions or []:
                    if condition.type == "Ready" and condition.status == "True":
                        node_data["ready"] = True
                        break

                # Get resource info
                if node.status.allocatable:
                    node_data["allocatable"] = {
                        "cpu": node.status.allocatable.get("cpu", "0"),
                        "memory": node.status.allocatable.get("memory", "0"),
                        "storage": node.status.allocatable.get(
                            "ephemeral-storage", "0"
                        ),
                    }

                if node.status.capacity:
                    node_data["capacity"] = {
                        "cpu": node.status.capacity.get("cpu", "0"),
                        "memory": node.status.capacity.get("memory", "0"),
                        "storage": node.status.capacity.get("ephemeral-storage", "0"),
                    }

                node_info.append(node_data)

            return {
                "cluster_version": version_info,
                "nodes": node_info,
                "total_nodes": len(node_info),
                "ready_nodes": sum(1 for node in node_info if node["ready"]),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to get cluster info: {e}"}

    async def start_monitoring(self) -> None:
        """Start resource monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            return

        self._monitoring_task = asyncio.create_task(self._monitor_resources())

    async def stop_monitoring(self) -> None:
        """Stop resource monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

    async def _monitor_resources(self) -> None:
        """Monitor resources continuously."""
        while True:
            try:
                # Update status for all tracked resources
                for resource_key, resource in self.resources.items():
                    status = await self.get_resource_status(
                        resource.name, resource.namespace, resource.resource_type
                    )
                    self.resource_status[resource_key] = {
                        "timestamp": datetime.now().isoformat(),
                        "status": status,
                    }

                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue monitoring
                print(f"Monitoring error: {e}")
                await asyncio.sleep(self.monitoring_interval)
