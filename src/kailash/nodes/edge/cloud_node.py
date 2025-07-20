"""Cloud integration node for edge resource management."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from kailash.edge.resource.cloud_integration import (
    CloudIntegration,
    CloudProvider,
    InstanceSpec,
    InstanceState,
    InstanceType,
)
from kailash.nodes.base import NodeParameter, register_node
from kailash.nodes.base_async import AsyncNode


@register_node()
class CloudNode(AsyncNode):
    """Node for cloud resource management and integration."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cloud_integration: Optional[CloudIntegration] = None

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
                    "register_aws",
                    "register_gcp",
                    "register_azure",
                    "create_instance",
                    "get_instance_status",
                    "terminate_instance",
                    "list_instances",
                    "get_instance_metrics",
                    "get_supported_providers",
                    "get_provider_info",
                    "start_monitoring",
                    "stop_monitoring",
                ],
            ),
            # Provider registration
            "provider": NodeParameter(
                name="provider",
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
            # Instance operations
            "instance_name": NodeParameter(
                name="instance_name",
                type=str,
                required=False,
                description="Instance name",
            ),
            "instance_id": NodeParameter(
                name="instance_id", type=str, required=False, description="Instance ID"
            ),
            "instance_type": NodeParameter(
                name="instance_type",
                type=str,
                required=False,
                description="Instance type/size",
            ),
            "image_id": NodeParameter(
                name="image_id",
                type=str,
                required=False,
                description="Machine image ID",
            ),
            "subnet_id": NodeParameter(
                name="subnet_id", type=str, required=False, description="Subnet ID"
            ),
            "security_group_ids": NodeParameter(
                name="security_group_ids",
                type=list,
                required=False,
                description="Security group IDs",
            ),
            "key_name": NodeParameter(
                name="key_name", type=str, required=False, description="SSH key name"
            ),
            "user_data": NodeParameter(
                name="user_data",
                type=str,
                required=False,
                description="Instance user data script",
            ),
            "tags": NodeParameter(
                name="tags", type=dict, required=False, description="Instance tags"
            ),
            "edge_node": NodeParameter(
                name="edge_node",
                type=str,
                required=False,
                description="Target edge node for instance placement",
            ),
            "min_count": NodeParameter(
                name="min_count",
                type=int,
                required=False,
                description="Minimum instance count",
            ),
            "max_count": NodeParameter(
                name="max_count",
                type=int,
                required=False,
                description="Maximum instance count",
            ),
            # List and filter operations
            "filters": NodeParameter(
                name="filters",
                type=dict,
                required=False,
                description="Instance filters",
            ),
            # Metrics operations
            "start_time": NodeParameter(
                name="start_time",
                type=str,
                required=False,
                description="Metrics start time (ISO format)",
            ),
            "end_time": NodeParameter(
                name="end_time",
                type=str,
                required=False,
                description="Metrics end time (ISO format)",
            ),
            "metrics_hours": NodeParameter(
                name="metrics_hours",
                type=int,
                required=False,
                description="Hours of metrics to retrieve (from now)",
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
            "instances": NodeParameter(
                name="instances", type=list, description="List of instances"
            ),
            "metrics": NodeParameter(
                name="metrics", type=list, description="Instance metrics"
            ),
            "providers": NodeParameter(
                name="providers", type=list, description="Supported cloud providers"
            ),
            "provider_info": NodeParameter(
                name="provider_info",
                type=dict,
                description="Cloud provider information",
            ),
            "cloud_initialized": NodeParameter(
                name="cloud_initialized",
                type=bool,
                description="Whether cloud integration was initialized",
            ),
            "provider_registered": NodeParameter(
                name="provider_registered",
                type=bool,
                description="Whether cloud provider was registered",
            ),
            "instance_created": NodeParameter(
                name="instance_created",
                type=bool,
                description="Whether instance was created",
            ),
            "instance_terminated": NodeParameter(
                name="instance_terminated",
                type=bool,
                description="Whether instance was terminated",
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
        """Execute cloud operation.

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
                return await self._initialize_cloud(**kwargs)
            elif operation == "register_aws":
                return await self._register_aws(**kwargs)
            elif operation == "register_gcp":
                return await self._register_gcp(**kwargs)
            elif operation == "register_azure":
                return await self._register_azure(**kwargs)
            elif operation == "create_instance":
                return await self._create_instance(**kwargs)
            elif operation == "get_instance_status":
                return await self._get_instance_status(**kwargs)
            elif operation == "terminate_instance":
                return await self._terminate_instance(**kwargs)
            elif operation == "list_instances":
                return await self._list_instances(**kwargs)
            elif operation == "get_instance_metrics":
                return await self._get_instance_metrics(**kwargs)
            elif operation == "get_supported_providers":
                return await self._get_supported_providers(**kwargs)
            elif operation == "get_provider_info":
                return await self._get_provider_info(**kwargs)
            elif operation == "start_monitoring":
                return await self._start_monitoring(**kwargs)
            elif operation == "stop_monitoring":
                return await self._stop_monitoring(**kwargs)
            else:
                return {"status": "error", "error": f"Unknown operation: {operation}"}

        except Exception as e:
            return {"status": "error", "error": f"Cloud operation failed: {str(e)}"}

    async def _initialize_cloud(self, **kwargs) -> Dict[str, Any]:
        """Initialize cloud integration."""
        try:
            self.cloud_integration = CloudIntegration()

            return {
                "status": "success",
                "cloud_initialized": True,
                "result": {"message": "Cloud integration initialized successfully"},
            }

        except Exception as e:
            return {
                "status": "error",
                "cloud_initialized": False,
                "error": f"Failed to initialize cloud integration: {str(e)}",
            }

    async def _register_aws(self, **kwargs) -> Dict[str, Any]:
        """Register AWS provider."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        region = kwargs.get("region", "us-west-2")
        profile_name = kwargs.get("profile_name")

        try:
            self.cloud_integration.register_aws(region, profile_name)

            return {
                "status": "success",
                "provider_registered": True,
                "result": {
                    "provider": "aws",
                    "region": region,
                    "profile_name": profile_name,
                    "message": "AWS provider registered successfully",
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "provider_registered": False,
                "error": f"Failed to register AWS provider: {str(e)}",
            }

    async def _register_gcp(self, **kwargs) -> Dict[str, Any]:
        """Register GCP provider."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        project_id = kwargs.get("project_id")
        zone = kwargs.get("zone", "us-central1-a")
        credentials_path = kwargs.get("credentials_path")

        if not project_id:
            return {
                "status": "error",
                "provider_registered": False,
                "error": "project_id is required for GCP registration",
            }

        try:
            self.cloud_integration.register_gcp(project_id, zone, credentials_path)

            return {
                "status": "success",
                "provider_registered": True,
                "result": {
                    "provider": "gcp",
                    "project_id": project_id,
                    "zone": zone,
                    "credentials_path": credentials_path,
                    "message": "GCP provider registered successfully",
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "provider_registered": False,
                "error": f"Failed to register GCP provider: {str(e)}",
            }

    async def _register_azure(self, **kwargs) -> Dict[str, Any]:
        """Register Azure provider."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        subscription_id = kwargs.get("subscription_id")
        resource_group = kwargs.get("resource_group")

        if not subscription_id or not resource_group:
            return {
                "status": "error",
                "provider_registered": False,
                "error": "subscription_id and resource_group are required for Azure registration",
            }

        try:
            self.cloud_integration.register_azure(subscription_id, resource_group)

            return {
                "status": "success",
                "provider_registered": True,
                "result": {
                    "provider": "azure",
                    "subscription_id": subscription_id,
                    "resource_group": resource_group,
                    "message": "Azure provider registered successfully",
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "provider_registered": False,
                "error": f"Failed to register Azure provider: {str(e)}",
            }

    async def _create_instance(self, **kwargs) -> Dict[str, Any]:
        """Create cloud instance."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")
        instance_name = kwargs.get("instance_name")
        instance_type = kwargs.get("instance_type")
        image_id = kwargs.get("image_id")
        region = kwargs.get("region")

        if not all([provider, instance_name, instance_type, image_id, region]):
            return {
                "status": "error",
                "instance_created": False,
                "error": "provider, instance_name, instance_type, image_id, and region are required",
            }

        try:
            # Create instance specification
            spec = InstanceSpec(
                name=instance_name,
                provider=CloudProvider(provider),
                instance_type=instance_type,
                image_id=image_id,
                region=region,
                zone=kwargs.get("zone"),
                subnet_id=kwargs.get("subnet_id"),
                security_group_ids=kwargs.get("security_group_ids", []),
                key_name=kwargs.get("key_name"),
                user_data=kwargs.get("user_data"),
                tags=kwargs.get("tags", {}),
                edge_node=kwargs.get("edge_node"),
                min_count=kwargs.get("min_count", 1),
                max_count=kwargs.get("max_count", 1),
            )

            # Create instance
            result = await self.cloud_integration.create_instance(spec)

            return {
                "status": result.get("status", "unknown"),
                "instance_created": result.get("status") == "created",
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "instance_created": False,
                "error": f"Failed to create instance: {str(e)}",
            }

    async def _get_instance_status(self, **kwargs) -> Dict[str, Any]:
        """Get cloud instance status."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")
        instance_id = kwargs.get("instance_id") or kwargs.get("instance_name")

        if not provider or not instance_id:
            return {
                "status": "error",
                "error": "provider and instance_id (or instance_name) are required",
            }

        try:
            status = await self.cloud_integration.get_instance_status(
                CloudProvider(provider), instance_id, kwargs.get("zone")
            )

            return {"status": "success", "result": status}

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get instance status: {str(e)}",
            }

    async def _terminate_instance(self, **kwargs) -> Dict[str, Any]:
        """Terminate cloud instance."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")
        instance_id = kwargs.get("instance_id") or kwargs.get("instance_name")

        if not provider or not instance_id:
            return {
                "status": "error",
                "instance_terminated": False,
                "error": "provider and instance_id (or instance_name) are required",
            }

        try:
            result = await self.cloud_integration.terminate_instance(
                CloudProvider(provider), instance_id, kwargs.get("zone")
            )

            return {
                "status": result.get("status", "unknown"),
                "instance_terminated": result.get("status")
                in ["terminating", "deleting"],
                "result": result,
            }

        except Exception as e:
            return {
                "status": "error",
                "instance_terminated": False,
                "error": f"Failed to terminate instance: {str(e)}",
            }

    async def _list_instances(self, **kwargs) -> Dict[str, Any]:
        """List cloud instances."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")
        filters = kwargs.get("filters")

        if not provider:
            return {"status": "error", "instances": [], "error": "provider is required"}

        try:
            instances = await self.cloud_integration.list_instances(
                CloudProvider(provider), filters
            )

            return {
                "status": "success",
                "instances": instances,
                "result": {"instance_count": len(instances), "instances": instances},
            }

        except Exception as e:
            return {
                "status": "error",
                "instances": [],
                "error": f"Failed to list instances: {str(e)}",
            }

    async def _get_instance_metrics(self, **kwargs) -> Dict[str, Any]:
        """Get cloud instance metrics."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")
        instance_id = kwargs.get("instance_id") or kwargs.get("instance_name")

        if not provider or not instance_id:
            return {
                "status": "error",
                "metrics": [],
                "error": "provider and instance_id (or instance_name) are required",
            }

        try:
            # Determine time range
            if kwargs.get("start_time") and kwargs.get("end_time"):
                start_time = datetime.fromisoformat(
                    kwargs["start_time"].replace("Z", "+00:00")
                )
                end_time = datetime.fromisoformat(
                    kwargs["end_time"].replace("Z", "+00:00")
                )
            else:
                hours = kwargs.get("metrics_hours", 1)
                end_time = datetime.now()
                start_time = end_time - timedelta(hours=hours)

            metrics = await self.cloud_integration.get_instance_metrics(
                CloudProvider(provider), instance_id, start_time, end_time
            )

            metrics_data = [metric.to_dict() for metric in metrics]

            return {
                "status": "success",
                "metrics": metrics_data,
                "result": {
                    "metric_count": len(metrics_data),
                    "metrics": metrics_data,
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "metrics": [],
                "error": f"Failed to get instance metrics: {str(e)}",
            }

    async def _get_supported_providers(self, **kwargs) -> Dict[str, Any]:
        """Get supported cloud providers."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        try:
            providers = await self.cloud_integration.get_supported_providers()

            return {
                "status": "success",
                "providers": providers,
                "result": {"provider_count": len(providers), "providers": providers},
            }

        except Exception as e:
            return {
                "status": "error",
                "providers": [],
                "error": f"Failed to get supported providers: {str(e)}",
            }

    async def _get_provider_info(self, **kwargs) -> Dict[str, Any]:
        """Get cloud provider information."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        provider = kwargs.get("provider")

        if not provider:
            return {
                "status": "error",
                "provider_info": {},
                "error": "provider is required",
            }

        try:
            provider_info = await self.cloud_integration.get_provider_info(
                CloudProvider(provider)
            )

            return {
                "status": "success",
                "provider_info": provider_info,
                "result": provider_info,
            }

        except Exception as e:
            return {
                "status": "error",
                "provider_info": {},
                "error": f"Failed to get provider info: {str(e)}",
            }

    async def _start_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Start cloud monitoring."""
        if not self.cloud_integration:
            await self._initialize_cloud(**kwargs)

        try:
            await self.cloud_integration.start_monitoring()

            return {
                "status": "success",
                "monitoring_started": True,
                "result": {
                    "message": "Cloud monitoring started",
                    "monitoring_interval": self.cloud_integration.monitoring_interval,
                },
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_started": False,
                "error": f"Failed to start monitoring: {str(e)}",
            }

    async def _stop_monitoring(self, **kwargs) -> Dict[str, Any]:
        """Stop cloud monitoring."""
        if not self.cloud_integration:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": "Cloud integration not initialized",
            }

        try:
            await self.cloud_integration.stop_monitoring()

            return {
                "status": "success",
                "monitoring_stopped": True,
                "result": {"message": "Cloud monitoring stopped"},
            }

        except Exception as e:
            return {
                "status": "error",
                "monitoring_stopped": False,
                "error": f"Failed to stop monitoring: {str(e)}",
            }
