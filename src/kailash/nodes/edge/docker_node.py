"""Docker integration node for edge resource management."""

from typing import Any, Dict, List, Optional

from kailash.edge.resource.docker_integration import (
    ContainerSpec,
    ContainerState,
    DockerIntegration,
    NetworkMode,
    RestartPolicyType,
    ServiceSpec,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class DockerNode(AsyncNode):
    """Node for Docker container and service management."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docker_integration: Optional[DockerIntegration] = None

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
                    "create_container",
                    "start_container",
                    "stop_container",
                    "remove_container",
                    "get_container_status",
                    "list_containers",
                    "create_service",
                    "update_service",
                    "scale_service",
                    "get_service_status",
                    "collect_metrics",
                    "get_system_info",
                    "start_monitoring",
                    "stop_monitoring",
                ],
            ),
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
            # Container operations
            "container_name": NodeParameter(
                name="container_name",
                type=str,
                required=False,
                description="Container name",
            ),
            "container_id": NodeParameter(
                name="container_id",
                type=str,
                required=False,
                description="Container ID",
            ),
            "image": NodeParameter(
                name="image", type=str, required=False, description="Docker image"
            ),
            "command": NodeParameter(
                name="command",
                type=list,
                required=False,
                description="Container command",
            ),
            "environment": NodeParameter(
                name="environment",
                type=dict,
                required=False,
                description="Environment variables",
            ),
            "ports": NodeParameter(
                name="ports",
                type=dict,
                required=False,
                description="Port mappings (container_port -> host_port)",
            ),
            "volumes": NodeParameter(
                name="volumes",
                type=dict,
                required=False,
                description="Volume mappings (host_path -> container_path)",
            ),
            "restart_policy": NodeParameter(
                name="restart_policy",
                type=str,
                required=False,
                description="Container restart policy",
                enum=["no", "always", "unless-stopped", "on-failure"],
            ),
            "memory_limit": NodeParameter(
                name="memory_limit",
                type=str,
                required=False,
                description="Memory limit (e.g., '512m', '1g')",
            ),
            "cpu_limit": NodeParameter(
                name="cpu_limit",
                type=float,
                required=False,
                description="CPU limit in cores",
            ),
            "network_mode": NodeParameter(
                name="network_mode",
                type=str,
                required=False,
                description="Network mode",
                enum=["bridge", "host", "none", "container", "custom"],
            ),
            "labels": NodeParameter(
                name="labels", type=dict, required=False, description="Container labels"
            ),
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Target edge node for container placement",
            ),
            "healthcheck": NodeParameter(
                name="healthcheck",
                type=dict,
                required=False,
                description="Container health check configuration",
            ),
            # Service operations (Docker Swarm)
            "service_name": NodeParameter(
                name="service_name",
                type=str,
                required=False,
                description="Service name",
            ),
            "service_id": NodeParameter(
                name="service_id", type=str, required=False, description="Service ID"
            ),
            "replicas": NodeParameter(
                name="replicas",
                type=int,
                required=False,
                description="Number of service replicas",
            ),
            "constraints": NodeParameter(
                name="constraints",
                type=list,
                required=False,
                description="Service placement constraints",
            ),
            "placement_preferences": NodeParameter(
                name="placement_preferences",
                type=list,
                required=False,
                description="Service placement preferences",
            ),
            "update_config": NodeParameter(
                name="update_config",
                type=dict,
                required=False,
                description="Service update configuration",
            ),
            "rollback_config": NodeParameter(
                name="rollback_config",
                type=dict,
                required=False,
                description="Service rollback configuration",
            ),
            # List operations
            "all_containers": NodeParameter(
                name="all_containers",
                type=bool,
                required=False,
                description="Include stopped containers in list",
            ),
            "filters": NodeParameter(
                name="filters",
                type=dict,
                required=False,
                description="Container filters",
            ),
            # Control operations
            "force": NodeParameter(
                name="force", type=bool, required=False, description="Force operation"
            ),
            "stop_timeout": NodeParameter(
                name="stop_timeout",
                type=int,
                required=False,
                description="Container stop timeout in seconds",
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
            "containers": NodeParameter(
                name="containers", type=list, description="List of containers"
            ),
            "services": NodeParameter(
                name="services", type=list, description="List of services"
            ),
            "metrics": NodeParameter(
                name="metrics", type=dict, description="Container metrics"
            ),
            "system_info": NodeParameter(
                name="system_info", type=dict, description="Docker system information"
            ),
            "container_created": NodeParameter(
                name="container_created",
                type=bool,
                description="Whether container was created",
            ),
            "container_started": NodeParameter(
                name="container_started",
                type=bool,
                description="Whether container was started",
            ),
            "container_stopped": NodeParameter(
                name="container_stopped",
                type=bool,
                description="Whether container was stopped",
            ),
            "container_removed": NodeParameter(
                name="container_removed",
                type=bool,
                description="Whether container was removed",
            ),
            "service_created": NodeParameter(
                name="service_created",
                type=bool,
                description="Whether service was created",
            ),
            "service_updated": NodeParameter(
                name="service_updated",
                type=bool,
                description="Whether service was updated",
            ),
            "service_scaled": NodeParameter(
                name="service_scaled",
                type=bool,
                description="Whether service was scaled",
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
        """Execute Docker operation.

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
                return await self._initialize_docker(**kwargs)
            elif operation == "create_container":
                return await self._create_container(**kwargs)
            elif operation == "start_container":
                return await self._start_container(**kwargs)
            elif operation == "stop_container":
                return await self._stop_container(**kwargs)
            elif operation == "remove_container":
                return await self._remove_container(**kwargs)
            elif operation == "get_container_status":
                return await self._get_container_status(**kwargs)
            elif operation == "list_containers":
                return await self._list_containers(**kwargs)
            elif operation == "create_service":
                return await self._create_service(**kwargs)
            elif operation == "update_service":
                return await self._update_service(**kwargs)
            elif operation == "scale_service":
                return await self._scale_service(**kwargs)
            elif operation == "get_service_status":
                return await self._get_service_status(**kwargs)
            elif operation == "collect_metrics":
                return await self._collect_metrics(**kwargs)
            elif operation == "get_system_info":
                return await self._get_system_info(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                return {"status": "error", "error": f"Unknown operation: {operation}"}

        except Exception as e:
            return {"status": "error", "error": f"Docker operation failed: {str(e)}"}

    async def _initialize_docker(self, **kwargs) -> Dict[str, Any]:
        """Initialize Docker integration."""
        docker_host = kwargs.get("docker_host")
        api_version = kwargs.get("api_version", "auto")
        timeout = kwargs.get("timeout", 60)

        try:
            self.docker_integration = DockerIntegration(
                docker_host=docker_host, api_version=api_version, timeout=timeout
            )

            await self.docker_integration.initialize()

            return {
                "status": "success",
                "docker_initialized": True,
                "result": {
                    "message": "Docker integration initialized successfully",
                    "docker_host": docker_host,
                    "api_version": api_version,
                    "swarm_enabled": self.docker_integration.swarm_enabled,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "docker_initialized": False,
                "error": f"Failed to initialize Docker: {str(e)}",
            }

    async def _create_container(self, **kwargs) -> Dict[str, Any]:
        """Create Docker container."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_name = kwargs.get("container_name")
        image = kwargs.get("image")

        if not container_name or not image:
            return {
                "status": "error",
                "container_created": False,
                "error": "container_name and image are required",
            }

        try:
            # Create container specification
            container_spec = ContainerSpec(
                name=container_name,
                image=image,
                command=kwargs.get("command"),
                environment=kwargs.get("environment", {}),
                ports=kwargs.get("ports", {}),
                volumes=kwargs.get("volumes", {}),
                restart_policy=RestartPolicyType(
                    kwargs.get("restart_policy", "unless-stopped")
                ),
                memory_limit=kwargs.get("memory_limit"),
                cpu_limit=kwargs.get("cpu_limit"),
                network_mode=NetworkMode(kwargs.get("network_mode", "bridge")),
                labels=kwargs.get("labels", {}),
                edge_node=kwargs.get("edge_node"),
                healthcheck=kwargs.get("healthcheck"),
            )

            # Create container
            result = await self.docker_integration.create_container(container_spec)

            return {
                "status": result.get("status", "unknown"),
                "container_created": result.get("status") == "created",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "container_created": False,
                "error": f"Failed to create container: {str(e)}",
            }

    async def _start_container(self, **kwargs) -> Dict[str, Any]:
        """Start Docker container."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_id = kwargs.get("container_id") or kwargs.get("container_name")

        if not container_id:
            return {
                "status": "error",
                "container_started": False,
                "error": "container_id or container_name is required",
            }

        try:
            result = await self.docker_integration.start_container(container_id)

            return {
                "status": result.get("status", "unknown"),
                "container_started": result.get("status") == "started",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "container_started": False,
                "error": f"Failed to start container: {str(e)}",
            }

    async def _stop_container(self, **kwargs) -> Dict[str, Any]:
        """Stop Docker container."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_id = kwargs.get("container_id") or kwargs.get("container_name")
        stop_timeout = kwargs.get("stop_timeout", 10)

        if not container_id:
            return {
                "status": "error",
                "container_stopped": False,
                "error": "container_id or container_name is required",
            }

        try:
            result = await self.docker_integration.stop_container(
                container_id, stop_timeout
            )

            return {
                "status": result.get("status", "unknown"),
                "container_stopped": result.get("status") == "stopped",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "container_stopped": False,
                "error": f"Failed to stop container: {str(e)}",
            }

    async def _remove_container(self, **kwargs) -> Dict[str, Any]:
        """Remove Docker container."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_id = kwargs.get("container_id") or kwargs.get("container_name")
        force = kwargs.get("force", False)

        if not container_id:
            return {
                "status": "error",
                "container_removed": False,
                "error": "container_id or container_name is required",
            }

        try:
            result = await self.docker_integration.remove_container(container_id, force)

            return {
                "status": result.get("status", "unknown"),
                "container_removed": result.get("status") == "removed",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "container_removed": False,
                "error": f"Failed to remove container: {str(e)}",
            }

    async def _get_container_status(self, **kwargs) -> Dict[str, Any]:
        """Get Docker container status."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_id = kwargs.get("container_id") or kwargs.get("container_name")

        if not container_id:
            return {
                "status": "error",
                "error": "container_id or container_name is required",
            }

        try:
            status = await self.docker_integration.get_container_status(container_id)

            return {"status": "success", "result": status}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get container status: {str(e)}",
            }

    async def _list_containers(self, **kwargs) -> Dict[str, Any]:
        """List Docker containers."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        all_containers = kwargs.get("all_containers", False)
        filters = kwargs.get("filters", {})

        try:
            containers = await self.docker_integration.list_containers(
                all_containers, filters
            )

            return {
                "status": "success",
                "containers": containers,
                "result": {
                    "container_count": len(containers),
                    "containers": containers,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "containers": [],
                "error": f"Failed to list containers: {str(e)}",
            }

    async def _create_service(self, **kwargs) -> Dict[str, Any]:
        """Create Docker Swarm service."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        service_name = kwargs.get("service_name")
        image = kwargs.get("image")

        if not service_name or not image:
            return {
                "status": "error",
                "service_created": False,
                "error": "service_name and image are required",
            }

        try:
            # Create service specification
            service_spec = ServiceSpec(
                name=service_name,
                image=image,
                replicas=kwargs.get("replicas", 1),
                command=kwargs.get("command"),
                environment=kwargs.get("environment", {}),
                ports=kwargs.get("ports", []),
                volumes=kwargs.get("volumes", []),
                constraints=kwargs.get("constraints", []),
                placement_preferences=kwargs.get("placement_preferences", []),
                restart_policy=kwargs.get("restart_policy"),
                update_config=kwargs.get("update_config"),
                rollback_config=kwargs.get("rollback_config"),
                labels=kwargs.get("labels", {}),
                edge_node=kwargs.get("edge_node"),
            )

            # Create service
            result = await self.docker_integration.create_service(service_spec)

            return {
                "status": result.get("status", "unknown"),
                "service_created": result.get("status") == "created",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "service_created": False,
                "error": f"Failed to create service: {str(e)}",
            }

    async def _update_service(self, **kwargs) -> Dict[str, Any]:
        """Update Docker Swarm service."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        service_id = kwargs.get("service_id") or kwargs.get("service_name")

        if not service_id:
            return {
                "status": "error",
                "service_updated": False,
                "error": "service_id or service_name is required",
            }

        try:
            # Get current service spec and update it
            # For simplicity, we'll create a new spec with updated values
            service_spec = ServiceSpec(
                name=kwargs.get("service_name", service_id),
                image=kwargs.get("image", ""),
                replicas=kwargs.get("replicas", 1),
                command=kwargs.get("command"),
                environment=kwargs.get("environment", {}),
                labels=kwargs.get("labels", {}),
                edge_node=kwargs.get("edge_node"),
            )

            result = await self.docker_integration.update_service(
                service_id, service_spec
            )

            return {
                "status": result.get("status", "unknown"),
                "service_updated": result.get("status") == "updated",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "service_updated": False,
                "error": f"Failed to update service: {str(e)}",
            }

    async def _scale_service(self, **kwargs) -> Dict[str, Any]:
        """Scale Docker Swarm service."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        service_id = kwargs.get("service_id") or kwargs.get("service_name")
        replicas = kwargs.get("replicas")

        if not service_id or replicas is None:
            return {
                "status": "error",
                "service_scaled": False,
                "error": "service_id (or service_name) and replicas are required",
            }

        try:
            result = await self.docker_integration.scale_service(service_id, replicas)

            return {
                "status": result.get("status", "unknown"),
                "service_scaled": result.get("status") == "scaled",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "service_scaled": False,
                "error": f"Failed to scale service: {str(e)}",
            }

    async def _get_service_status(self, **kwargs) -> Dict[str, Any]:
        """Get Docker Swarm service status."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        service_id = kwargs.get("service_id") or kwargs.get("service_name")

        if not service_id:
            return {
                "status": "error",
                "error": "service_id or service_name is required",
            }

        try:
            status = await self.docker_integration.get_service_status(service_id)

            return {"status": "success", "result": status}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get service status: {str(e)}",
            }

    async def _collect_metrics(self, **kwargs) -> Dict[str, Any]:
        """Collect container metrics."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        container_id = kwargs.get("container_id") or kwargs.get("container_name")

        if not container_id:
            return {
                "status": "error",
                "error": "container_id or container_name is required",
            }

        try:
            metrics = await self.docker_integration.collect_container_metrics(
                container_id
            )

            if metrics:
                return {
                    "status": "success",
                    "metrics": metrics.to_dict(),
                    "result": metrics.to_dict(),
                }
            else:
                return {
                    "status": "error",
                    "metrics": {},
                    "error": "Failed to collect metrics",
                }

        except Exception as e:
            return {
                "status": "error",
                "metrics": {},
                "error": f"Failed to collect metrics: {str(e)}",
            }

    async def _get_system_info(self, **kwargs) -> Dict[str, Any]:
        """Get Docker system information."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        try:
            system_info = await self.docker_integration.get_system_info()

            return {
                "status": "success",
                "system_info": system_info,
                "result": system_info,
            }

        except Exception as e:
            return {
                "status": "error",
                "system_info": {},
                "error": f"Failed to get system info: {str(e)}",
            }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start Docker monitoring."""
        if not self.docker_integration:
            await self._initialize_docker(**kwargs)

        try:
            await self.docker_integration.start_monitoring()

            return {
                "status": "success",
                "monitoring_started": True,
                "result": {
                    "message": "Docker monitoring started",
                    "monitoring_interval": self.docker_integration.monitoring_interval,
                    "metrics_interval": self.docker_integration.metrics_interval,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_started": False,
                "error": f"Failed to start monitoring: {str(e)}",
            }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop Docker monitoring."""
        if not self.docker_integration:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": "Docker integration not initialized",
            }

        try:
            await self.docker_integration.stop_monitoring()

            return {
                "status": "success",
                "monitoring_stopped": True,
                "result": {"message": "Docker monitoring stopped"},
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": f"Failed to stop monitoring: {str(e)}",
            }
