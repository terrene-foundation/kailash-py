"""Kubernetes integration node for edge resource management."""

from typing import Any, Dict, List, Optional

from kailash.edge.resource.kubernetes_integration import (
    KubernetesIntegration,
    KubernetesResource,
    KubernetesResourceType,
    PodScalingSpec,
    ScalingPolicy,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class KubernetesNode(AsyncNode):
    """Node for Kubernetes resource management and integration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.kubernetes_integration: Optional[KubernetesIntegration] = None

    @property
    def input_parameters(self) -> Dict[str, NodeParameter]:
        """Define input parameters."""
        return {
            "operation": NodeParameter(
                name="operation",
                type=str,
                required=True,
                description="Operation to perform",
                enum=[
                    "initialize",
                    "create_resource",
                    "update_resource",
                    "delete_resource",
                    "get_status",
                    "list_resources",
                    "scale_deployment",
                    "create_autoscaler",
                    "get_cluster_info",
                    "start_monitoring",
                    "stop_monitoring",
                ],
            ),
            "kubeconfig_path": NodeParameter(
                name="kubeconfig_path",
                type=str,
                required=False,
                description="Path to kubeconfig file",
            ),
            "context_name": NodeParameter(
                name="context_name",
                type=str,
                required=False,
                description="Kubernetes context to use",
            ),
            "namespace": NodeParameter(
                name="namespace",
                type=str,
                required=False,
                description="Kubernetes namespace",
            ),
            # Resource operations
            "resource_name": NodeParameter(
                name="resource_name",
                type=str,
                required=False,
                description="Kubernetes resource name",
            ),
            "resource_type": NodeParameter(
                name="resource_type",
                type=str,
                required=False,
                description="Kubernetes resource type",
                enum=[
                    "deployment",
                    "service",
                    "configmap",
                    "secret",
                    "pod",
                    "persistent_volume",
                    "persistent_volume_claim",
                    "ingress",
                    "horizontal_pod_autoscaler",
                ],
            ),
            "resource_spec": NodeParameter(
                name="resource_spec",
                type=dict,
                required=False,
                description="Kubernetes resource specification",
            ),
            "labels": NodeParameter(
                name="labels", type=dict, required=False, description="Resource labels"
            ),
            "annotations": NodeParameter(
                name="annotations",
                type=dict,
                required=False,
                description="Resource annotations",
            ),
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Target edge node for resource placement",
            ),
            # Scaling operations
            "deployment_name": NodeParameter(
                name="deployment_name",
                type=str,
                required=False,
                description="Deployment name for scaling",
            ),
            "replicas": NodeParameter(
                name="replicas",
                type=int,
                required=False,
                description="Target replica count",
            ),
            "min_replicas": NodeParameter(
                name="min_replicas",
                type=int,
                required=False,
                description="Minimum replica count for autoscaling",
            ),
            "max_replicas": NodeParameter(
                name="max_replicas",
                type=int,
                required=False,
                description="Maximum replica count for autoscaling",
            ),
            "target_cpu_utilization": NodeParameter(
                name="target_cpu_utilization",
                type=float,
                required=False,
                description="Target CPU utilization for autoscaling (0.0-1.0)",
            ),
            "target_memory_utilization": NodeParameter(
                name="target_memory_utilization",
                type=float,
                required=False,
                description="Target memory utilization for autoscaling (0.0-1.0)",
            ),
            # List operations
            "label_selector": NodeParameter(
                name="label_selector",
                type=dict,
                required=False,
                description="Label selector for filtering resources",
            ),
        }

    @property
    def output_parameters(self) -> Dict[str, NodeParameter]:
        """Define output parameters."""
        return {
            "status": NodeParameter(
                name="status", type=str, description="Operation status"
            ),
            "result": NodeParameter(
                name="result", type=dict, description="Operation result"
            ),
            "resources": NodeParameter(
                name="resources", type=list, description="List of resources"
            ),
            "cluster_info": NodeParameter(
                name="cluster_info", type=dict, description="Cluster information"
            ),
            "resource_created": NodeParameter(
                name="resource_created",
                type=bool,
                description="Whether resource was created",
            ),
            "resource_updated": NodeParameter(
                name="resource_updated",
                type=bool,
                description="Whether resource was updated",
            ),
            "resource_deleted": NodeParameter(
                name="resource_deleted",
                type=bool,
                description="Whether resource was deleted",
            ),
            "deployment_scaled": NodeParameter(
                name="deployment_scaled",
                type=bool,
                description="Whether deployment was scaled",
            ),
            "autoscaler_created": NodeParameter(
                name="autoscaler_created",
                type=bool,
                description="Whether autoscaler was created",
            ),
            "monitoring_started": NodeParameter(
                name="monitoring_started",
                type=bool,
                description="Whether monitoring was started",
            ),
            "monitoring_stopped": NodeParameter(
                name="monitoring_stopped",
                type=bool,
                description="Whether monitoring was stopped",
            ),
        }

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """Get all parameters for this node."""
        return self.input_parameters

    async def async_run(self, **kwargs) -> Dict[str, Any]:
        """Execute Kubernetes operation.

        Args:
            **kwargs: Operation parameters

        Returns:
            Operation result
        """
        operation = kwargs.get("operation")

        if not operation:
            return {"status": "error", "error": "Operation is required"}

        try:
            if operation == "initialize":
                return await self._initialize_kubernetes(**kwargs)
            elif operation == "create_resource":
                return await self._create_resource(**kwargs)
            elif operation == "update_resource":
                return await self._update_resource(**kwargs)
            elif operation == "delete_resource":
                return await self._delete_resource(**kwargs)
            elif operation == "get_status":
                return await self._get_resource_status(**kwargs)
            elif operation == "list_resources":
                return await self._list_resources(**kwargs)
            elif operation == "scale_deployment":
                return await self._scale_deployment(**kwargs)
            elif operation == "create_autoscaler":
                return await self._create_autoscaler(**kwargs)
            elif operation == "get_cluster_info":
                return await self._get_cluster_info(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                return {"status": "error", "error": f"Unknown operation: {operation}"}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Kubernetes operation failed: {str(e)}",
            }

    async def _initialize_kubernetes(self, **kwargs) -> Dict[str, Any]:
        """Initialize Kubernetes integration."""
        kubeconfig_path = kwargs.get("kubeconfig_path")
        context_name = kwargs.get("context_name")
        namespace = kwargs.get("namespace", "default")

        try:
            self.kubernetes_integration = KubernetesIntegration(
                kubeconfig_path=kubeconfig_path,
                context_name=context_name,
                namespace=namespace,
            )

            await self.kubernetes_integration.initialize()

            return {
                "status": "success",
                "kubernetes_initialized": True,
                "namespace": namespace,
                "result": {
                    "message": "Kubernetes integration initialized successfully",
                    "namespace": namespace,
                    "kubeconfig_path": kubeconfig_path,
                    "context_name": context_name,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "kubernetes_initialized": False,
                "error": f"Failed to initialize Kubernetes: {str(e)}",
            }

    async def _create_resource(self, **kwargs) -> Dict[str, Any]:
        """Create Kubernetes resource."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        resource_name = kwargs.get("resource_name")
        resource_type = kwargs.get("resource_type")
        resource_spec = kwargs.get("resource_spec", {})
        namespace = kwargs.get("namespace", "default")
        labels = kwargs.get("labels", {})
        annotations = kwargs.get("annotations", {})
        edge_node = kwargs.get("edge_node")

        if not resource_name or not resource_type or not resource_spec:
            return {
                "status": "error",
                "resource_created": False,
                "error": "resource_name, resource_type, and resource_spec are required",
            }

        try:
            # Convert string type to enum
            k8s_resource_type = KubernetesResourceType(resource_type)

            # Create resource object
            resource = KubernetesResource(
                name=resource_name,
                namespace=namespace,
                resource_type=k8s_resource_type,
                spec=resource_spec,
                labels=labels,
                annotations=annotations,
                edge_node=edge_node,
            )

            # Create resource in cluster
            result = await self.kubernetes_integration.create_resource(resource)

            return {
                "status": result.get("status", "unknown"),
                "resource_created": result.get("status") == "created",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_created": False,
                "error": f"Failed to create resource: {str(e)}",
            }

    async def _update_resource(self, **kwargs) -> Dict[str, Any]:
        """Update Kubernetes resource."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        resource_name = kwargs.get("resource_name")
        resource_type = kwargs.get("resource_type")
        resource_spec = kwargs.get("resource_spec", {})
        namespace = kwargs.get("namespace", "default")
        labels = kwargs.get("labels", {})
        annotations = kwargs.get("annotations", {})
        edge_node = kwargs.get("edge_node")

        if not resource_name or not resource_type:
            return {
                "status": "error",
                "resource_updated": False,
                "error": "resource_name and resource_type are required",
            }

        try:
            # Convert string type to enum
            k8s_resource_type = KubernetesResourceType(resource_type)

            # Create resource object
            resource = KubernetesResource(
                name=resource_name,
                namespace=namespace,
                resource_type=k8s_resource_type,
                spec=resource_spec,
                labels=labels,
                annotations=annotations,
                edge_node=edge_node,
            )

            # Update resource in cluster
            result = await self.kubernetes_integration.update_resource(resource)

            return {
                "status": result.get("status", "unknown"),
                "resource_updated": result.get("status") == "updated",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_updated": False,
                "error": f"Failed to update resource: {str(e)}",
            }

    async def _delete_resource(self, **kwargs) -> Dict[str, Any]:
        """Delete Kubernetes resource."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        resource_name = kwargs.get("resource_name")
        resource_type = kwargs.get("resource_type")
        namespace = kwargs.get("namespace", "default")

        if not resource_name or not resource_type:
            return {
                "status": "error",
                "resource_deleted": False,
                "error": "resource_name and resource_type are required",
            }

        try:
            # Convert string type to enum
            k8s_resource_type = KubernetesResourceType(resource_type)

            # Delete resource from cluster
            result = await self.kubernetes_integration.delete_resource(
                resource_name, namespace, k8s_resource_type
            )

            return {
                "status": result.get("status", "unknown"),
                "resource_deleted": result.get("status") == "deleted",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_deleted": False,
                "error": f"Failed to delete resource: {str(e)}",
            }

    async def _get_resource_status(self, **kwargs) -> Dict[str, Any]:
        """Get Kubernetes resource status."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        resource_name = kwargs.get("resource_name")
        resource_type = kwargs.get("resource_type")
        namespace = kwargs.get("namespace", "default")

        if not resource_name or not resource_type:
            return {
                "status": "error",
                "error": "resource_name and resource_type are required",
            }

        try:
            # Convert string type to enum
            k8s_resource_type = KubernetesResourceType(resource_type)

            # Get resource status
            status = await self.kubernetes_integration.get_resource_status(
                resource_name, namespace, k8s_resource_type
            )

            return {"status": "success", "result": status}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get resource status: {str(e)}",
            }

    async def _list_resources(self, **kwargs) -> Dict[str, Any]:
        """List Kubernetes resources."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        namespace = kwargs.get("namespace")
        resource_type = kwargs.get("resource_type")
        label_selector = kwargs.get("label_selector", {})

        try:
            # Convert string type to enum if provided
            k8s_resource_type = None
            if resource_type:
                k8s_resource_type = KubernetesResourceType(resource_type)

            # List resources
            resources = await self.kubernetes_integration.list_resources(
                namespace=namespace,
                resource_type=k8s_resource_type,
                labels=label_selector,
            )

            return {
                "status": "success",
                "resources": resources,
                "result": {"resource_count": len(resources), "resources": resources},
            }

        except Exception as e:
            return {
                "status": "error",
                "resources": [],
                "error": f"Failed to list resources: {str(e)}",
            }

    async def _scale_deployment(self, **kwargs) -> Dict[str, Any]:
        """Scale Kubernetes deployment."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        deployment_name = kwargs.get("deployment_name")
        replicas = kwargs.get("replicas")
        namespace = kwargs.get("namespace", "default")

        if not deployment_name or replicas is None:
            return {
                "status": "error",
                "deployment_scaled": False,
                "error": "deployment_name and replicas are required",
            }

        try:
            # Scale deployment
            result = await self.kubernetes_integration.scale_deployment(
                deployment_name, namespace, replicas
            )

            return {
                "status": result.get("status", "unknown"),
                "deployment_scaled": result.get("status") == "scaled",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "deployment_scaled": False,
                "error": f"Failed to scale deployment: {str(e)}",
            }

    async def _create_autoscaler(self, **kwargs) -> Dict[str, Any]:
        """Create Kubernetes autoscaler."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        deployment_name = kwargs.get("deployment_name")
        namespace = kwargs.get("namespace", "default")
        min_replicas = kwargs.get("min_replicas", 1)
        max_replicas = kwargs.get("max_replicas", 10)
        target_cpu_utilization = kwargs.get("target_cpu_utilization", 0.8)
        target_memory_utilization = kwargs.get("target_memory_utilization")

        if not deployment_name:
            return {
                "status": "error",
                "autoscaler_created": False,
                "error": "deployment_name is required",
            }

        try:
            # Create scaling specification
            scaling_spec = PodScalingSpec(
                min_replicas=min_replicas,
                max_replicas=max_replicas,
                target_cpu_utilization=target_cpu_utilization,
                target_memory_utilization=target_memory_utilization,
            )

            # Create autoscaler
            result = await self.kubernetes_integration.create_autoscaler(
                deployment_name, namespace, scaling_spec
            )

            return {
                "status": result.get("status", "unknown"),
                "autoscaler_created": result.get("status") == "created",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "autoscaler_created": False,
                "error": f"Failed to create autoscaler: {str(e)}",
            }

    async def _get_cluster_info(self, **kwargs) -> Dict[str, Any]:
        """Get Kubernetes cluster information."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        try:
            # Get cluster info
            cluster_info = await self.kubernetes_integration.get_cluster_info()

            return {
                "status": "success",
                "cluster_info": cluster_info,
                "result": cluster_info,
            }

        except Exception as e:
            return {
                "status": "error",
                "cluster_info": {},
                "error": f"Failed to get cluster info: {str(e)}",
            }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start Kubernetes resource monitoring."""
        if not self.kubernetes_integration:
            await self._initialize_kubernetes(**kwargs)

        try:
            # Start monitoring
            await self.kubernetes_integration.start_monitoring()

            return {
                "status": "success",
                "monitoring_started": True,
                "result": {
                    "message": "Kubernetes resource monitoring started",
                    "monitoring_interval": self.kubernetes_integration.monitoring_interval,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_started": False,
                "error": f"Failed to start monitoring: {str(e)}",
            }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop Kubernetes resource monitoring."""
        if not self.kubernetes_integration:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": "Kubernetes integration not initialized",
            }

        try:
            # Stop monitoring
            await self.kubernetes_integration.stop_monitoring()

            return {
                "status": "success",
                "monitoring_stopped": True,
                "result": {"message": "Kubernetes resource monitoring stopped"},
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": f"Failed to stop monitoring: {str(e)}",
            }
