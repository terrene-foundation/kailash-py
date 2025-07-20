"""Unified platform integration node for edge resource management."""

from typing import Any, Dict, List, Optional

from kailash.edge.resource.cloud_integration import CloudProvider
from kailash.edge.resource.platform_integration import (
    PlatformConfig,
    PlatformIntegration,
    PlatformType,
    ResourceRequest,
    ResourceScope,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class PlatformNode(AsyncNode):
    """Node for unified platform integration and resource management."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.platform_integration: Optional[PlatformIntegration] = None

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
                    "register_kubernetes",
                    "register_docker",
                    "register_cloud_provider",
                    "allocate_resource",
                    "deallocate_resource",
                    "get_resource_status",
                    "list_allocations",
                    "optimize_resources",
                    "scale_resources",
                    "get_platform_status",
                    "start_monitoring",
                    "stop_monitoring",
                ],
            ),
            # Platform registration
            "platform_type": NodeParameter(
                name="platform_type",
                type=str,
                required=False,
                description="Platform type",
                enum=["kubernetes", "docker", "cloud", "edge_local"],
            ),
            "priority": NodeParameter(
                name="priority",
                type=int,
                required=False,
                description="Platform priority (lower = higher priority)",
            ),
            # Kubernetes registration
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
                description="Kubernetes context name",
            ),
            "namespace": NodeParameter(
                name="namespace",
                type=str,
                required=False,
                description="Kubernetes namespace",
            ),
            # Docker registration
            "docker_host": NodeParameter(
                name="docker_host",
                type=str,
                required=False,
                description="Docker daemon socket URL",
            ),
            "api_version": NodeParameter(
                name="api_version",
                type=str,
                required=False,
                description="Docker API version",
            ),
            "timeout": NodeParameter(
                name="timeout",
                type=int,
                required=False,
                description="API timeout in seconds",
            ),
            # Cloud provider registration
            "cloud_provider": NodeParameter(
                name="cloud_provider",
                type=str,
                required=False,
                description="Cloud provider",
                enum=["aws", "gcp", "azure", "alibaba_cloud", "digital_ocean"],
            ),
            "region": NodeParameter(
                name="region", type=str, required=False, description="Cloud region"
            ),
            "zone": NodeParameter(
                name="zone",
                type=str,
                required=False,
                description="Cloud availability zone",
            ),
            "profile_name": NodeParameter(
                name="profile_name",
                type=str,
                required=False,
                description="AWS profile name",
            ),
            "project_id": NodeParameter(
                name="project_id",
                type=str,
                required=False,
                description="GCP project ID",
            ),
            "credentials_path": NodeParameter(
                name="credentials_path",
                type=str,
                required=False,
                description="Path to credentials file",
            ),
            "subscription_id": NodeParameter(
                name="subscription_id",
                type=str,
                required=False,
                description="Azure subscription ID",
            ),
            "resource_group": NodeParameter(
                name="resource_group",
                type=str,
                required=False,
                description="Azure resource group",
            ),
            # Resource operations
            "request_id": NodeParameter(
                name="request_id",
                type=str,
                required=False,
                description="Resource request ID",
            ),
            "allocation_id": NodeParameter(
                name="allocation_id",
                type=str,
                required=False,
                description="Resource allocation ID",
            ),
            "edge_node": NodeParameter(
                name="edge_node", type=str, required=False, description="Edge node name"
            ),
            "resource_type": NodeParameter(
                name="resource_type",
                type=str,
                required=False,
                description="Resource type",
            ),
            "resource_spec": NodeParameter(
                name="resource_spec",
                type=dict,
                required=False,
                description="Resource specification",
            ),
            "platform_preference": NodeParameter(
                name="platform_preference",
                type=str,
                required=False,
                description="Preferred platform for allocation",
                enum=["kubernetes", "docker", "cloud", "edge_local"],
            ),
            "scope": NodeParameter(
                name="scope",
                type=str,
                required=False,
                description="Resource scope",
                enum=["node", "cluster", "region", "global"],
            ),
            "tags": NodeParameter(
                name="tags", type=dict, required=False, description="Resource tags"
            ),
            # Scaling operations
            "target_scale": NodeParameter(
                name="target_scale",
                type=int,
                required=False,
                description="Target scale for resources",
            ),
            # Configuration
            "auto_scaling_enabled": NodeParameter(
                name="auto_scaling_enabled",
                type=bool,
                required=False,
                description="Enable automatic scaling",
            ),
            "auto_optimization_enabled": NodeParameter(
                name="auto_optimization_enabled",
                type=bool,
                required=False,
                description="Enable automatic optimization",
            ),
            "monitoring_interval": NodeParameter(
                name="monitoring_interval",
                type=int,
                required=False,
                description="Monitoring interval in seconds",
            ),
            "optimization_interval": NodeParameter(
                name="optimization_interval",
                type=int,
                required=False,
                description="Optimization interval in seconds",
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
            "allocations": NodeParameter(
                name="allocations",
                type=list,
                description="List of resource allocations",
            ),
            "platform_status": NodeParameter(
                name="platform_status",
                type=dict,
                description="Platform status information",
            ),
            "optimization_results": NodeParameter(
                name="optimization_results",
                type=dict,
                description="Resource optimization results",
            ),
            "platform_initialized": NodeParameter(
                name="platform_initialized",
                type=bool,
                description="Whether platform integration was initialized",
            ),
            "platform_registered": NodeParameter(
                name="platform_registered",
                type=bool,
                description="Whether platform was registered",
            ),
            "resource_allocated": NodeParameter(
                name="resource_allocated",
                type=bool,
                description="Whether resource was allocated",
            ),
            "resource_deallocated": NodeParameter(
                name="resource_deallocated",
                type=bool,
                description="Whether resource was deallocated",
            ),
            "resource_scaled": NodeParameter(
                name="resource_scaled",
                type=bool,
                description="Whether resource was scaled",
            ),
            "resources_optimized": NodeParameter(
                name="resources_optimized",
                type=bool,
                description="Whether resources were optimized",
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
        """Execute platform operation.

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
                return await self._initialize_platform(**kwargs)
            elif operation == "register_kubernetes":
                return await self._register_kubernetes(**kwargs)
            elif operation == "register_docker":
                return await self._register_docker(**kwargs)
            elif operation == "register_cloud_provider":
                return await self._register_cloud_provider(**kwargs)
            elif operation == "allocate_resource":
                return await self._allocate_resource(**kwargs)
            elif operation == "deallocate_resource":
                return await self._deallocate_resource(**kwargs)
            elif operation == "get_resource_status":
                return await self._get_resource_status(**kwargs)
            elif operation == "list_allocations":
                return await self._list_allocations(**kwargs)
            elif operation == "optimize_resources":
                return await self._optimize_resources(**kwargs)
            elif operation == "scale_resources":
                return await self._scale_resources(**kwargs)
            elif operation == "get_platform_status":
                return await self._get_platform_status(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                return {"status": "error", "error": f"Unknown operation: {operation}"}

        except Exception as e:
            return {"status": "error", "error": f"Platform operation failed: {str(e)}"}

    async def _initialize_platform(self, **kwargs) -> Dict[str, Any]:
        """Initialize platform integration."""
        try:
            self.platform_integration = PlatformIntegration()

            # Configure platform integration
            if kwargs.get("auto_scaling_enabled") is not None:
                self.platform_integration.auto_scaling_enabled = kwargs[
                    "auto_scaling_enabled"
                ]
            if kwargs.get("auto_optimization_enabled") is not None:
                self.platform_integration.auto_optimization_enabled = kwargs[
                    "auto_optimization_enabled"
                ]
            if kwargs.get("monitoring_interval"):
                self.platform_integration.monitoring_interval = kwargs[
                    "monitoring_interval"
                ]
            if kwargs.get("optimization_interval"):
                self.platform_integration.optimization_interval = kwargs[
                    "optimization_interval"
                ]

            result = await self.platform_integration.initialize()

            return {
                "status": result.get("status", "unknown"),
                "platform_initialized": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform_initialized": False,
                "error": f"Failed to initialize platform integration: {str(e)}",
            }

    async def _register_kubernetes(self, **kwargs) -> Dict[str, Any]:
        """Register Kubernetes platform."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        kubeconfig_path = kwargs.get("kubeconfig_path")
        context_name = kwargs.get("context_name")
        namespace = kwargs.get("namespace", "default")
        priority = kwargs.get("priority", 1)

        try:
            result = await self.platform_integration.register_kubernetes(
                kubeconfig_path=kubeconfig_path,
                context_name=context_name,
                namespace=namespace,
                priority=priority,
            )

            return {
                "status": result.get("status", "unknown"),
                "platform_registered": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform_registered": False,
                "error": f"Failed to register Kubernetes: {str(e)}",
            }

    async def _register_docker(self, **kwargs) -> Dict[str, Any]:
        """Register Docker platform."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        docker_host = kwargs.get("docker_host")
        api_version = kwargs.get("api_version", "auto")
        timeout = kwargs.get("timeout", 60)
        priority = kwargs.get("priority", 2)

        try:
            result = await self.platform_integration.register_docker(
                docker_host=docker_host,
                api_version=api_version,
                timeout=timeout,
                priority=priority,
            )

            return {
                "status": result.get("status", "unknown"),
                "platform_registered": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform_registered": False,
                "error": f"Failed to register Docker: {str(e)}",
            }

    async def _register_cloud_provider(self, **kwargs) -> Dict[str, Any]:
        """Register cloud provider."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        cloud_provider = kwargs.get("cloud_provider")
        priority = kwargs.get("priority", 3)

        if not cloud_provider:
            return {
                "status": "error",
                "platform_registered": False,
                "error": "cloud_provider is required",
            }

        try:
            # Build provider configuration
            config = {}

            if cloud_provider == "aws":
                config["region"] = kwargs.get("region", "us-west-2")
                config["profile_name"] = kwargs.get("profile_name")
            elif cloud_provider == "gcp":
                config["project_id"] = kwargs.get("project_id")
                config["zone"] = kwargs.get("zone", "us-central1-a")
                config["credentials_path"] = kwargs.get("credentials_path")

                if not config["project_id"]:
                    return {
                        "status": "error",
                        "platform_registered": False,
                        "error": "project_id is required for GCP",
                    }
            elif cloud_provider == "azure":
                config["subscription_id"] = kwargs.get("subscription_id")
                config["resource_group"] = kwargs.get("resource_group")

                if not config["subscription_id"] or not config["resource_group"]:
                    return {
                        "status": "error",
                        "platform_registered": False,
                        "error": "subscription_id and resource_group are required for Azure",
                    }

            result = await self.platform_integration.register_cloud_provider(
                CloudProvider(cloud_provider), config, priority
            )

            return {
                "status": result.get("status", "unknown"),
                "platform_registered": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform_registered": False,
                "error": f"Failed to register cloud provider: {str(e)}",
            }

    async def _allocate_resource(self, **kwargs) -> Dict[str, Any]:
        """Allocate resource."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        request_id = kwargs.get("request_id")
        edge_node = kwargs.get("edge_node")
        resource_type = kwargs.get("resource_type")
        resource_spec = kwargs.get("resource_spec", {})

        if not all([request_id, edge_node, resource_type]):
            return {
                "status": "error",
                "resource_allocated": False,
                "error": "request_id, edge_node, and resource_type are required",
            }

        try:
            # Create resource request
            platform_preference = None
            if kwargs.get("platform_preference"):
                platform_preference = PlatformType(kwargs["platform_preference"])

            scope = ResourceScope.NODE
            if kwargs.get("scope"):
                scope = ResourceScope(kwargs["scope"])

            request = ResourceRequest(
                request_id=request_id,
                edge_node=edge_node,
                resource_type=resource_type,
                resource_spec=resource_spec,
                platform_preference=platform_preference,
                scope=scope,
                tags=kwargs.get("tags", {}),
            )

            result = await self.platform_integration.allocate_resource(request)

            return {
                "status": result.get("status", "unknown"),
                "resource_allocated": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_allocated": False,
                "error": f"Failed to allocate resource: {str(e)}",
            }

    async def _deallocate_resource(self, **kwargs) -> Dict[str, Any]:
        """Deallocate resource."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        allocation_id = kwargs.get("allocation_id")

        if not allocation_id:
            return {
                "status": "error",
                "resource_deallocated": False,
                "error": "allocation_id is required",
            }

        try:
            result = await self.platform_integration.deallocate_resource(allocation_id)

            return {
                "status": result.get("status", "unknown"),
                "resource_deallocated": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_deallocated": False,
                "error": f"Failed to deallocate resource: {str(e)}",
            }

    async def _get_resource_status(self, **kwargs) -> Dict[str, Any]:
        """Get resource status."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        allocation_id = kwargs.get("allocation_id")

        if not allocation_id:
            return {"status": "error", "error": "allocation_id is required"}

        try:
            result = await self.platform_integration.get_resource_status(allocation_id)

            return {"status": result.get("status", "unknown"), "result": result}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get resource status: {str(e)}",
            }

    async def _list_allocations(self, **kwargs) -> Dict[str, Any]:
        """List resource allocations."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        edge_node = kwargs.get("edge_node")
        platform_type = None
        if kwargs.get("platform_type"):
            platform_type = PlatformType(kwargs["platform_type"])

        try:
            allocations = await self.platform_integration.list_allocations(
                edge_node=edge_node, platform_type=platform_type
            )

            return {
                "status": "success",
                "allocations": allocations,
                "result": {
                    "allocation_count": len(allocations),
                    "allocations": allocations,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "allocations": [],
                "error": f"Failed to list allocations: {str(e)}",
            }

    async def _optimize_resources(self, **kwargs) -> Dict[str, Any]:
        """Optimize resources."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        scope = ResourceScope.CLUSTER
        if kwargs.get("scope"):
            scope = ResourceScope(kwargs["scope"])

        try:
            result = await self.platform_integration.optimize_resources(scope)

            return {
                "status": result.get("status", "unknown"),
                "resources_optimized": result.get("status") == "success",
                "optimization_results": result,
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resources_optimized": False,
                "optimization_results": {},
                "error": f"Failed to optimize resources: {str(e)}",
            }

    async def _scale_resources(self, **kwargs) -> Dict[str, Any]:
        """Scale resources."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        allocation_id = kwargs.get("allocation_id")
        target_scale = kwargs.get("target_scale")

        if not allocation_id or target_scale is None:
            return {
                "status": "error",
                "resource_scaled": False,
                "error": "allocation_id and target_scale are required",
            }

        try:
            result = await self.platform_integration.scale_resources(
                allocation_id, target_scale
            )

            return {
                "status": result.get("status", "unknown"),
                "resource_scaled": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "resource_scaled": False,
                "error": f"Failed to scale resources: {str(e)}",
            }

    async def _get_platform_status(self, **kwargs) -> Dict[str, Any]:
        """Get platform status."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        try:
            result = await self.platform_integration.get_platform_status()

            return {
                "status": result.get("status", "unknown"),
                "platform_status": result.get("platforms", {}),
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform_status": {},
                "error": f"Failed to get platform status: {str(e)}",
            }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start platform monitoring."""
        if not self.platform_integration:
            await self._initialize_platform(**kwargs)

        try:
            result = await self.platform_integration.start_monitoring()

            return {
                "status": result.get("status", "unknown"),
                "monitoring_started": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_started": False,
                "error": f"Failed to start monitoring: {str(e)}",
            }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop platform monitoring."""
        if not self.platform_integration:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": "Platform integration not initialized",
            }

        try:
            result = await self.platform_integration.stop_monitoring()

            return {
                "status": result.get("status", "unknown"),
                "monitoring_stopped": result.get("status") == "success",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": f"Failed to stop monitoring: {str(e)}",
            }
