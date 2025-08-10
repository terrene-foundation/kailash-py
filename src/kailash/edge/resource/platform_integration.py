"""Unified platform integration for edge resource management."""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from .cloud_integration import (
    CloudIntegration,
    CloudProvider,
    InstanceSpec,
    InstanceState,
)
from .cost_optimizer import CloudProvider as CostCloudProvider
from .cost_optimizer import CostOptimizer, OptimizationStrategy
from .docker_integration import (
    ContainerSpec,
    ContainerState,
    DockerIntegration,
    ServiceSpec,
)
from .kubernetes_integration import (
    KubernetesIntegration,
    KubernetesResource,
    KubernetesResourceType,
)
from .predictive_scaler import PredictionHorizon, PredictiveScaler, ScalingStrategy
from .resource_analyzer import ResourceAnalyzer, ResourceMetric, ResourceType


class PlatformType(Enum):
    """Supported platform types."""

    KUBERNETES = "kubernetes"
    DOCKER = "docker"
    CLOUD = "cloud"
    EDGE_LOCAL = "edge_local"


class ResourceScope(Enum):
    """Resource scope levels."""

    NODE = "node"  # Single edge node
    CLUSTER = "cluster"  # Edge cluster
    REGION = "region"  # Geographic region
    GLOBAL = "global"  # All edge infrastructure


@dataclass
class PlatformConfig:
    """Platform configuration."""

    platform_type: PlatformType
    enabled: bool = True
    config: Optional[Dict[str, Any]] = None
    priority: int = 1  # Lower numbers = higher priority

    def __post_init__(self):
        if self.config is None:
            self.config = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["platform_type"] = self.platform_type.value
        return data


@dataclass
class ResourceRequest:
    """Unified resource request."""

    request_id: str
    edge_node: str
    resource_type: str
    resource_spec: Dict[str, Any]
    platform_preference: Optional[PlatformType] = None
    scope: ResourceScope = ResourceScope.NODE
    tags: Optional[Dict[str, str]] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.tags is None:
            self.tags = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        if self.platform_preference:
            data["platform_preference"] = self.platform_preference.value
        data["scope"] = self.scope.value
        data["created_at"] = self.created_at.isoformat()
        return data


@dataclass
class ResourceAllocation:
    """Resource allocation result."""

    allocation_id: str
    request_id: str
    platform_type: PlatformType
    resource_id: str
    edge_node: str
    resource_details: Dict[str, Any]
    allocated_at: datetime
    status: str = "allocated"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["platform_type"] = self.platform_type.value
        data["allocated_at"] = self.allocated_at.isoformat()
        return data


class PlatformIntegration:
    """Unified platform integration for edge resource management."""

    def __init__(self):
        # Platform integrations
        self.kubernetes_integration: Optional[KubernetesIntegration] = None
        self.docker_integration: Optional[DockerIntegration] = None
        self.cloud_integration: Optional[CloudIntegration] = None

        # Resource management
        self.resource_analyzer: Optional[ResourceAnalyzer] = None
        self.predictive_scaler: Optional[PredictiveScaler] = None
        self.cost_optimizer: Optional[CostOptimizer] = None

        # Platform configuration
        self.platform_configs: Dict[PlatformType, PlatformConfig] = {}

        # Resource tracking
        self.resource_requests: Dict[str, ResourceRequest] = {}
        self.resource_allocations: Dict[str, ResourceAllocation] = {}

        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._optimization_task: Optional[asyncio.Task] = None

        # Configuration
        self.monitoring_interval = 30  # seconds
        self.optimization_interval = 300  # 5 minutes
        self.auto_scaling_enabled = True
        self.auto_optimization_enabled = True

        # Event handlers
        self.event_handlers: Dict[str, List[Callable]] = {}

    async def initialize(self) -> Dict[str, Any]:
        """Initialize platform integration."""
        try:
            # Initialize resource management components
            self.resource_analyzer = ResourceAnalyzer()
            self.predictive_scaler = PredictiveScaler()
            self.cost_optimizer = CostOptimizer()

            # Start resource management services
            await self.resource_analyzer.start()
            await self.predictive_scaler.start()
            await self.cost_optimizer.start()

            return {
                "status": "success",
                "message": "Platform integration initialized successfully",
                "initialized_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to initialize platform integration: {str(e)}",
            }

    async def register_kubernetes(
        self,
        kubeconfig_path: Optional[str] = None,
        context_name: Optional[str] = None,
        namespace: str = "default",
        priority: int = 1,
    ) -> Dict[str, Any]:
        """Register Kubernetes platform."""
        try:
            self.kubernetes_integration = KubernetesIntegration(
                kubeconfig_path=kubeconfig_path,
                context_name=context_name,
                namespace=namespace,
            )

            await self.kubernetes_integration.initialize()

            self.platform_configs[PlatformType.KUBERNETES] = PlatformConfig(
                platform_type=PlatformType.KUBERNETES,
                enabled=True,
                config={
                    "kubeconfig_path": kubeconfig_path,
                    "context_name": context_name,
                    "namespace": namespace,
                },
                priority=priority,
            )

            return {
                "status": "success",
                "platform": "kubernetes",
                "message": "Kubernetes platform registered successfully",
            }

        except Exception as e:
            return {
                "status": "error",
                "platform": "kubernetes",
                "error": f"Failed to register Kubernetes: {str(e)}",
            }

    async def register_docker(
        self,
        docker_host: Optional[str] = None,
        api_version: str = "auto",
        timeout: int = 60,
        priority: int = 2,
    ) -> Dict[str, Any]:
        """Register Docker platform."""
        try:
            self.docker_integration = DockerIntegration(
                docker_host=docker_host, api_version=api_version, timeout=timeout
            )

            await self.docker_integration.initialize()

            self.platform_configs[PlatformType.DOCKER] = PlatformConfig(
                platform_type=PlatformType.DOCKER,
                enabled=True,
                config={
                    "docker_host": docker_host,
                    "api_version": api_version,
                    "timeout": timeout,
                    "swarm_enabled": self.docker_integration.swarm_enabled,
                },
                priority=priority,
            )

            return {
                "status": "success",
                "platform": "docker",
                "message": "Docker platform registered successfully",
                "swarm_enabled": self.docker_integration.swarm_enabled,
            }

        except Exception as e:
            return {
                "status": "error",
                "platform": "docker",
                "error": f"Failed to register Docker: {str(e)}",
            }

    async def register_cloud_provider(
        self, provider: CloudProvider, config: Dict[str, Any], priority: int = 3
    ) -> Dict[str, Any]:
        """Register cloud platform."""
        try:
            if not self.cloud_integration:
                self.cloud_integration = CloudIntegration()

            if provider == CloudProvider.AWS:
                self.cloud_integration.register_aws(
                    region=config.get("region", "us-west-2"),
                    profile_name=config.get("profile_name"),
                )
            elif provider == CloudProvider.GCP:
                self.cloud_integration.register_gcp(
                    project_id=config["project_id"],
                    zone=config.get("zone", "us-central1-a"),
                    credentials_path=config.get("credentials_path"),
                )
            elif provider == CloudProvider.AZURE:
                self.cloud_integration.register_azure(
                    subscription_id=config["subscription_id"],
                    resource_group=config["resource_group"],
                )
            else:
                raise ValueError(f"Unsupported cloud provider: {provider}")

            platform_config = PlatformConfig(
                platform_type=PlatformType.CLOUD,
                enabled=True,
                config={"provider": provider.value, **config},
                priority=priority,
            )

            # Store cloud provider-specific config
            if PlatformType.CLOUD not in self.platform_configs:
                self.platform_configs[PlatformType.CLOUD] = platform_config
            else:
                # Merge with existing cloud config
                existing_config = self.platform_configs[PlatformType.CLOUD].config
                existing_config[f"{provider.value}_config"] = config

            return {
                "status": "success",
                "platform": "cloud",
                "provider": provider.value,
                "message": f"Cloud provider {provider.value} registered successfully",
            }

        except Exception as e:
            return {
                "status": "error",
                "platform": "cloud",
                "provider": provider.value if provider else "unknown",
                "error": f"Failed to register cloud provider: {str(e)}",
            }

    async def allocate_resource(self, request: ResourceRequest) -> Dict[str, Any]:
        """Allocate resource using best available platform."""
        try:
            # Store request
            self.resource_requests[request.request_id] = request

            # Determine best platform for allocation
            platform = await self._select_platform(request)

            if not platform:
                return {
                    "status": "error",
                    "error": "No suitable platform available for resource allocation",
                }

            # Allocate resource on selected platform
            allocation_result = await self._allocate_on_platform(platform, request)

            if allocation_result.get("status") == "success":
                # Create allocation record
                allocation = ResourceAllocation(
                    allocation_id=f"alloc-{request.request_id}",
                    request_id=request.request_id,
                    platform_type=platform,
                    resource_id=allocation_result.get("resource_id", "unknown"),
                    edge_node=request.edge_node,
                    resource_details=allocation_result.get("details", {}),
                    allocated_at=datetime.now(),
                )

                self.resource_allocations[allocation.allocation_id] = allocation

                # Emit allocation event
                await self._emit_event(
                    "resource_allocated",
                    {"allocation": allocation.to_dict(), "request": request.to_dict()},
                )

                return {
                    "status": "success",
                    "allocation_id": allocation.allocation_id,
                    "platform": platform.value,
                    "resource_id": allocation.resource_id,
                    "details": allocation_result,
                }
            else:
                return allocation_result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to allocate resource: {str(e)}",
            }

    async def deallocate_resource(self, allocation_id: str) -> Dict[str, Any]:
        """Deallocate resource."""
        try:
            allocation = self.resource_allocations.get(allocation_id)
            if not allocation:
                return {
                    "status": "error",
                    "error": f"Allocation {allocation_id} not found",
                }

            # Deallocate on platform
            result = await self._deallocate_on_platform(allocation)

            if result.get("status") == "success":
                # Remove allocation record
                del self.resource_allocations[allocation_id]

                # Emit deallocation event
                await self._emit_event(
                    "resource_deallocated",
                    {
                        "allocation_id": allocation_id,
                        "allocation": allocation.to_dict(),
                    },
                )

                return {
                    "status": "success",
                    "allocation_id": allocation_id,
                    "message": "Resource deallocated successfully",
                }
            else:
                return result

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to deallocate resource: {str(e)}",
            }

    async def get_resource_status(self, allocation_id: str) -> Dict[str, Any]:
        """Get resource status."""
        try:
            allocation = self.resource_allocations.get(allocation_id)
            if not allocation:
                return {
                    "status": "error",
                    "error": f"Allocation {allocation_id} not found",
                }

            # Get status from platform
            status = await self._get_platform_resource_status(allocation)

            return {
                "status": "success",
                "allocation_id": allocation_id,
                "platform": allocation.platform_type.value,
                "resource_id": allocation.resource_id,
                "resource_status": status,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get resource status: {str(e)}",
            }

    async def list_allocations(
        self,
        edge_node: Optional[str] = None,
        platform_type: Optional[PlatformType] = None,
    ) -> List[Dict[str, Any]]:
        """List resource allocations."""
        try:
            allocations = []

            for allocation in self.resource_allocations.values():
                # Apply filters
                if edge_node and allocation.edge_node != edge_node:
                    continue
                if platform_type and allocation.platform_type != platform_type:
                    continue

                allocations.append(allocation.to_dict())

            return allocations

        except Exception as e:
            raise RuntimeError(f"Failed to list allocations: {str(e)}")

    async def optimize_resources(
        self, scope: ResourceScope = ResourceScope.CLUSTER
    ) -> Dict[str, Any]:
        """Optimize resources across platforms."""
        try:
            if not self.cost_optimizer:
                return {"status": "error", "error": "Cost optimizer not initialized"}

            # Get optimization recommendations
            optimizations = await self.cost_optimizer.optimize_costs(
                strategy=OptimizationStrategy.BALANCE_COST_PERFORMANCE
            )

            optimization_results = []
            for opt in optimizations:
                # Apply optimization if beneficial
                if opt.savings_percentage > 10:  # 10% minimum savings
                    # Implementation would depend on optimization type
                    optimization_results.append(
                        {
                            "optimization_id": opt.optimization_id,
                            "savings": opt.estimated_savings,
                            "savings_percentage": opt.savings_percentage,
                            "applied": True,
                        }
                    )

            return {
                "status": "success",
                "scope": scope.value,
                "optimizations_applied": len(optimization_results),
                "total_savings": sum(opt["savings"] for opt in optimization_results),
                "details": optimization_results,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to optimize resources: {str(e)}",
            }

    async def scale_resources(
        self, allocation_id: str, target_scale: int
    ) -> Dict[str, Any]:
        """Scale allocated resources."""
        try:
            allocation = self.resource_allocations.get(allocation_id)
            if not allocation:
                return {
                    "status": "error",
                    "error": f"Allocation {allocation_id} not found",
                }

            # Scale on platform
            result = await self._scale_on_platform(allocation, target_scale)

            if result.get("status") == "success":
                # Emit scaling event
                await self._emit_event(
                    "resource_scaled",
                    {
                        "allocation_id": allocation_id,
                        "target_scale": target_scale,
                        "platform": allocation.platform_type.value,
                    },
                )

            return result

        except Exception as e:
            return {"status": "error", "error": f"Failed to scale resource: {str(e)}"}

    async def get_platform_status(self) -> Dict[str, Any]:
        """Get status of all registered platforms."""
        try:
            platform_status = {}

            for platform_type, config in self.platform_configs.items():
                status = {
                    "enabled": config.enabled,
                    "priority": config.priority,
                    "config": config.config,
                }

                # Get platform-specific status
                if (
                    platform_type == PlatformType.KUBERNETES
                    and self.kubernetes_integration
                ):
                    cluster_info = await self.kubernetes_integration.get_cluster_info()
                    status["cluster_info"] = cluster_info
                elif platform_type == PlatformType.DOCKER and self.docker_integration:
                    system_info = await self.docker_integration.get_system_info()
                    status["system_info"] = system_info
                elif platform_type == PlatformType.CLOUD and self.cloud_integration:
                    providers = await self.cloud_integration.get_supported_providers()
                    status["supported_providers"] = providers

                platform_status[platform_type.value] = status

            return {
                "status": "success",
                "platforms": platform_status,
                "total_platforms": len(platform_status),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get platform status: {str(e)}",
            }

    async def start_monitoring(self) -> Dict[str, Any]:
        """Start platform monitoring."""
        try:
            if self._monitoring_task and not self._monitoring_task.done():
                return {"status": "success", "message": "Monitoring already running"}

            self._monitoring_task = asyncio.create_task(self._monitor_platforms())

            if self.auto_optimization_enabled:
                self._optimization_task = asyncio.create_task(
                    self._optimize_continuously()
                )

            return {
                "status": "success",
                "message": "Platform monitoring started",
                "monitoring_interval": self.monitoring_interval,
                "auto_optimization": self.auto_optimization_enabled,
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to start monitoring: {str(e)}"}

    async def stop_monitoring(self) -> Dict[str, Any]:
        """Stop platform monitoring."""
        try:
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass

            if self._optimization_task and not self._optimization_task.done():
                self._optimization_task.cancel()
                try:
                    await self._optimization_task
                except asyncio.CancelledError:
                    pass

            return {"status": "success", "message": "Platform monitoring stopped"}

        except Exception as e:
            return {"status": "error", "error": f"Failed to stop monitoring: {str(e)}"}

    def add_event_handler(self, event_type: str, handler: Callable) -> None:
        """Add event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)

    def remove_event_handler(self, event_type: str, handler: Callable) -> None:
        """Remove event handler."""
        if event_type in self.event_handlers:
            self.event_handlers[event_type].remove(handler)

    async def _select_platform(
        self, request: ResourceRequest
    ) -> Optional[PlatformType]:
        """Select best platform for resource allocation."""
        # Check platform preference
        if (
            request.platform_preference
            and request.platform_preference in self.platform_configs
        ):
            config = self.platform_configs[request.platform_preference]
            if config.enabled:
                return request.platform_preference

        # Select by priority (lower number = higher priority)
        available_platforms = [
            (platform, config)
            for platform, config in self.platform_configs.items()
            if config.enabled
        ]

        if not available_platforms:
            return None

        # Sort by priority
        available_platforms.sort(key=lambda x: x[1].priority)

        # For now, return highest priority platform
        # In production, this would include resource availability checks
        return available_platforms[0][0]

    async def _allocate_on_platform(
        self, platform: PlatformType, request: ResourceRequest
    ) -> Dict[str, Any]:
        """Allocate resource on specific platform."""
        if platform == PlatformType.KUBERNETES and self.kubernetes_integration:
            return await self._allocate_kubernetes_resource(request)
        elif platform == PlatformType.DOCKER and self.docker_integration:
            return await self._allocate_docker_resource(request)
        elif platform == PlatformType.CLOUD and self.cloud_integration:
            return await self._allocate_cloud_resource(request)
        else:
            return {
                "status": "error",
                "error": f"Platform {platform.value} not available or not supported",
            }

    async def _allocate_kubernetes_resource(
        self, request: ResourceRequest
    ) -> Dict[str, Any]:
        """Allocate Kubernetes resource."""
        try:
            # Create Kubernetes resource from request
            resource = KubernetesResource(
                name=f"{request.edge_node}-{request.resource_type}",
                namespace="default",
                resource_type=KubernetesResourceType(request.resource_type),
                spec=request.resource_spec,
                edge_node=request.edge_node,
                labels=request.tags,
            )

            result = await self.kubernetes_integration.create_resource(resource)

            return {
                "status": result.get("status", "unknown"),
                "resource_id": f"{resource.namespace}/{resource.name}",
                "details": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to allocate Kubernetes resource: {str(e)}",
            }

    async def _allocate_docker_resource(
        self, request: ResourceRequest
    ) -> Dict[str, Any]:
        """Allocate Docker resource."""
        try:
            # Create Docker container from request
            container_spec = ContainerSpec(
                name=f"{request.edge_node}-{request.resource_type}",
                image=request.resource_spec.get("image", "alpine:latest"),
                environment=request.resource_spec.get("environment", {}),
                ports=request.resource_spec.get("ports", {}),
                volumes=request.resource_spec.get("volumes", {}),
                labels=request.tags,
                edge_node=request.edge_node,
            )

            result = await self.docker_integration.create_container(container_spec)

            return {
                "status": result.get("status", "unknown"),
                "resource_id": result.get("container_id", "unknown"),
                "details": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to allocate Docker resource: {str(e)}",
            }

    async def _allocate_cloud_resource(
        self, request: ResourceRequest
    ) -> Dict[str, Any]:
        """Allocate cloud resource."""
        try:
            # Create cloud instance from request
            spec = InstanceSpec(
                name=f"{request.edge_node}-{request.resource_type}",
                provider=CloudProvider.AWS,  # Default, should be configurable
                instance_type=request.resource_spec.get("instance_type", "t3.micro"),
                image_id=request.resource_spec.get("image_id", "ami-0c02fb55956c7d316"),
                region=request.resource_spec.get("region", "us-west-2"),
                tags=request.tags,
                edge_node=request.edge_node,
            )

            result = await self.cloud_integration.create_instance(spec)

            return {
                "status": result.get("status", "unknown"),
                "resource_id": result.get("instance_id", "unknown"),
                "details": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to allocate cloud resource: {str(e)}",
            }

    async def _deallocate_on_platform(
        self, allocation: ResourceAllocation
    ) -> Dict[str, Any]:
        """Deallocate resource on platform."""
        if (
            allocation.platform_type == PlatformType.KUBERNETES
            and self.kubernetes_integration
        ):
            # Parse resource ID to get namespace and name
            namespace, name = allocation.resource_id.split("/", 1)
            return await self.kubernetes_integration.delete_resource(
                name,
                namespace,
                KubernetesResourceType.DEPLOYMENT,  # Should be stored in allocation
            )
        elif (
            allocation.platform_type == PlatformType.DOCKER and self.docker_integration
        ):
            return await self.docker_integration.remove_container(
                allocation.resource_id
            )
        elif allocation.platform_type == PlatformType.CLOUD and self.cloud_integration:
            return await self.cloud_integration.terminate_instance(
                CloudProvider.AWS,  # Should be stored in allocation
                allocation.resource_id,
            )
        else:
            return {
                "status": "error",
                "error": f"Platform {allocation.platform_type.value} not available",
            }

    async def _get_platform_resource_status(
        self, allocation: ResourceAllocation
    ) -> Dict[str, Any]:
        """Get resource status from platform."""
        if (
            allocation.platform_type == PlatformType.KUBERNETES
            and self.kubernetes_integration
        ):
            namespace, name = allocation.resource_id.split("/", 1)
            return await self.kubernetes_integration.get_resource_status(
                name, namespace, KubernetesResourceType.DEPLOYMENT
            )
        elif (
            allocation.platform_type == PlatformType.DOCKER and self.docker_integration
        ):
            return await self.docker_integration.get_container_status(
                allocation.resource_id
            )
        elif allocation.platform_type == PlatformType.CLOUD and self.cloud_integration:
            return await self.cloud_integration.get_instance_status(
                CloudProvider.AWS, allocation.resource_id
            )
        else:
            return {
                "status": "error",
                "error": f"Platform {allocation.platform_type.value} not available",
            }

    async def _scale_on_platform(
        self, allocation: ResourceAllocation, target_scale: int
    ) -> Dict[str, Any]:
        """Scale resource on platform."""
        if (
            allocation.platform_type == PlatformType.KUBERNETES
            and self.kubernetes_integration
        ):
            namespace, name = allocation.resource_id.split("/", 1)
            return await self.kubernetes_integration.scale_deployment(
                name, namespace, target_scale
            )
        elif (
            allocation.platform_type == PlatformType.DOCKER and self.docker_integration
        ):
            # Docker scaling would require service mode (Swarm)
            return await self.docker_integration.scale_service(
                allocation.resource_id, target_scale
            )
        elif allocation.platform_type == PlatformType.CLOUD and self.cloud_integration:
            # Cloud scaling would require auto-scaling groups or similar
            return {
                "status": "not_implemented",
                "message": "Cloud instance scaling not implemented",
            }
        else:
            return {
                "status": "error",
                "error": f"Platform {allocation.platform_type.value} not available",
            }

    async def _emit_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Emit event to registered handlers."""
        if event_type in self.event_handlers:
            for handler in self.event_handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event_data)
                    else:
                        handler(event_data)
                except Exception as e:
                    # Log error but don't stop other handlers
                    print(f"Event handler error: {e}")

    async def _monitor_platforms(self) -> None:
        """Monitor platforms continuously."""
        while True:
            try:
                # Monitor platform health
                platform_status = await self.get_platform_status()

                # Monitor allocations
                for allocation_id, allocation in list(
                    self.resource_allocations.items()
                ):
                    try:
                        status = await self._get_platform_resource_status(allocation)
                        # Update allocation status based on platform status
                        allocation.status = status.get("status", "unknown")
                    except Exception:
                        # Resource might have been deleted
                        pass

                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Platform monitoring error: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _optimize_continuously(self) -> None:
        """Optimize resources continuously."""
        while True:
            try:
                if self.auto_optimization_enabled:
                    await self.optimize_resources(ResourceScope.CLUSTER)

                await asyncio.sleep(self.optimization_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Optimization error: {e}")
                await asyncio.sleep(self.optimization_interval)
