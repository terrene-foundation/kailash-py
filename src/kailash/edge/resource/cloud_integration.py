"""Cloud API integration for edge resource management."""

import asyncio
import base64
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

try:
    from google.cloud import compute_v1
    from google.oauth2 import service_account

    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False

try:
    from azure.identity import DefaultAzureCredential
    from azure.mgmt.compute import ComputeManagementClient
    from azure.mgmt.resource import ResourceManagementClient

    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False


class CloudProvider(Enum):
    """Cloud providers."""

    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"
    ALIBABA_CLOUD = "alibaba_cloud"
    DIGITAL_OCEAN = "digital_ocean"


class InstanceState(Enum):
    """Instance states."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    TERMINATED = "terminated"
    UNKNOWN = "unknown"


class InstanceType(Enum):
    """Instance types."""

    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    XLARGE = "xlarge"
    CUSTOM = "custom"


@dataclass
class CloudInstance:
    """Cloud instance specification."""

    instance_id: str
    name: str
    provider: CloudProvider
    instance_type: str
    image_id: str
    region: str
    zone: Optional[str] = None
    state: InstanceState = InstanceState.PENDING
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    security_groups: Optional[List[str]] = None
    tags: Optional[Dict[str, str]] = None
    edge_node: Optional[str] = None
    created_at: Optional[datetime] = None
    launched_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.security_groups is None:
            self.security_groups = []
        if self.tags is None:
            self.tags = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["provider"] = self.provider.value
        data["state"] = self.state.value
        data["created_at"] = self.created_at.isoformat()
        if self.launched_at:
            data["launched_at"] = self.launched_at.isoformat()
        return data


@dataclass
class InstanceSpec:
    """Instance creation specification."""

    name: str
    provider: CloudProvider
    instance_type: str
    image_id: str
    region: str
    zone: Optional[str] = None
    subnet_id: Optional[str] = None
    security_group_ids: Optional[List[str]] = None
    key_name: Optional[str] = None
    user_data: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    edge_node: Optional[str] = None
    min_count: int = 1
    max_count: int = 1

    def __post_init__(self):
        if self.security_group_ids is None:
            self.security_group_ids = []
        if self.tags is None:
            self.tags = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["provider"] = self.provider.value
        return data


@dataclass
class CloudMetrics:
    """Cloud instance metrics."""

    instance_id: str
    provider: CloudProvider
    timestamp: datetime
    cpu_utilization: float
    memory_utilization: Optional[float] = None
    network_in: Optional[float] = None
    network_out: Optional[float] = None
    disk_read_ops: Optional[float] = None
    disk_write_ops: Optional[float] = None
    disk_read_bytes: Optional[float] = None
    disk_write_bytes: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["provider"] = self.provider.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


class AWSIntegration:
    """AWS cloud integration."""

    def __init__(self, region: str = "us-west-2", profile_name: Optional[str] = None):
        if not AWS_AVAILABLE:
            raise ImportError("AWS SDK not available. Install with: pip install boto3")

        self.region = region
        self.profile_name = profile_name

        # AWS clients
        if profile_name:
            session = boto3.Session(profile_name=profile_name)
            self.ec2_client = session.client("ec2", region_name=region)
            self.cloudwatch_client = session.client("cloudwatch", region_name=region)
        else:
            self.ec2_client = boto3.client("ec2", region_name=region)
            self.cloudwatch_client = boto3.client("cloudwatch", region_name=region)

    async def create_instance(self, spec: InstanceSpec) -> Dict[str, Any]:
        """Create AWS EC2 instance."""
        try:
            # Prepare launch parameters
            launch_params = {
                "ImageId": spec.image_id,
                "MinCount": spec.min_count,
                "MaxCount": spec.max_count,
                "InstanceType": spec.instance_type,
                "TagSpecifications": [
                    {
                        "ResourceType": "instance",
                        "Tags": [{"Key": k, "Value": v} for k, v in spec.tags.items()]
                        + [{"Key": "Name", "Value": spec.name}],
                    }
                ],
            }

            # Add optional parameters
            if spec.key_name:
                launch_params["KeyName"] = spec.key_name
            if spec.security_group_ids:
                launch_params["SecurityGroupIds"] = spec.security_group_ids
            if spec.subnet_id:
                launch_params["SubnetId"] = spec.subnet_id
            if spec.user_data:
                launch_params["UserData"] = base64.b64encode(
                    spec.user_data.encode()
                ).decode()
            if spec.zone:
                launch_params["Placement"] = {"AvailabilityZone": spec.zone}

            # Add edge node tag
            if spec.edge_node:
                launch_params["TagSpecifications"][0]["Tags"].append(
                    {"Key": "edge-node", "Value": spec.edge_node}
                )

            response = await asyncio.to_thread(
                self.ec2_client.run_instances, **launch_params
            )

            instance_data = response["Instances"][0]

            return {
                "status": "created",
                "instance_id": instance_data["InstanceId"],
                "instance_type": instance_data["InstanceType"],
                "image_id": instance_data["ImageId"],
                "state": instance_data["State"]["Name"],
                "launch_time": instance_data["LaunchTime"].isoformat(),
                "availability_zone": instance_data["Placement"]["AvailabilityZone"],
            }

        except ClientError as e:
            return {
                "status": "error",
                "error": f"AWS API error: {e.response['Error']['Message']}",
                "error_code": e.response["Error"]["Code"],
            }
        except Exception as e:
            return {"status": "error", "error": f"Failed to create instance: {str(e)}"}

    async def get_instance_status(self, instance_id: str) -> Dict[str, Any]:
        """Get AWS EC2 instance status."""
        try:
            response = await asyncio.to_thread(
                self.ec2_client.describe_instances, InstanceIds=[instance_id]
            )

            if not response["Reservations"]:
                return {"status": "error", "error": "Instance not found"}

            instance = response["Reservations"][0]["Instances"][0]

            return {
                "instance_id": instance["InstanceId"],
                "state": instance["State"]["Name"],
                "instance_type": instance["InstanceType"],
                "public_ip": instance.get("PublicIpAddress"),
                "private_ip": instance.get("PrivateIpAddress"),
                "launch_time": instance["LaunchTime"].isoformat(),
                "availability_zone": instance["Placement"]["AvailabilityZone"],
                "tags": {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])},
            }

        except ClientError as e:
            return {
                "status": "error",
                "error": f"AWS API error: {e.response['Error']['Message']}",
                "error_code": e.response["Error"]["Code"],
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get instance status: {str(e)}",
            }

    async def terminate_instance(self, instance_id: str) -> Dict[str, Any]:
        """Terminate AWS EC2 instance."""
        try:
            response = await asyncio.to_thread(
                self.ec2_client.terminate_instances, InstanceIds=[instance_id]
            )

            instance_data = response["TerminatingInstances"][0]

            return {
                "status": "terminating",
                "instance_id": instance_data["InstanceId"],
                "current_state": instance_data["CurrentState"]["Name"],
                "previous_state": instance_data["PreviousState"]["Name"],
            }

        except ClientError as e:
            return {
                "status": "error",
                "error": f"AWS API error: {e.response['Error']['Message']}",
                "error_code": e.response["Error"]["Code"],
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to terminate instance: {str(e)}",
            }

    async def list_instances(
        self, filters: Optional[Dict[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """List AWS EC2 instances."""
        try:
            params = {}
            if filters:
                params["Filters"] = [
                    {"Name": name, "Values": values} for name, values in filters.items()
                ]

            response = await asyncio.to_thread(
                self.ec2_client.describe_instances, **params
            )

            instances = []
            for reservation in response["Reservations"]:
                for instance in reservation["Instances"]:
                    instances.append(
                        {
                            "instance_id": instance["InstanceId"],
                            "state": instance["State"]["Name"],
                            "instance_type": instance["InstanceType"],
                            "public_ip": instance.get("PublicIpAddress"),
                            "private_ip": instance.get("PrivateIpAddress"),
                            "launch_time": instance["LaunchTime"].isoformat(),
                            "availability_zone": instance["Placement"][
                                "AvailabilityZone"
                            ],
                            "tags": {
                                tag["Key"]: tag["Value"]
                                for tag in instance.get("Tags", [])
                            },
                        }
                    )

            return instances

        except ClientError as e:
            raise RuntimeError(f"AWS API error: {e.response['Error']['Message']}")
        except Exception as e:
            raise RuntimeError(f"Failed to list instances: {str(e)}")

    async def get_instance_metrics(
        self, instance_id: str, start_time: datetime, end_time: datetime
    ) -> List[CloudMetrics]:
        """Get AWS CloudWatch metrics for instance."""
        try:
            # Get CPU utilization
            cpu_response = await asyncio.to_thread(
                self.cloudwatch_client.get_metric_statistics,
                Namespace="AWS/EC2",
                MetricName="CPUUtilization",
                Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5 minutes
                Statistics=["Average"],
            )

            metrics = []
            for datapoint in cpu_response["Datapoints"]:
                metrics.append(
                    CloudMetrics(
                        instance_id=instance_id,
                        provider=CloudProvider.AWS,
                        timestamp=datapoint["Timestamp"],
                        cpu_utilization=datapoint["Average"],
                    )
                )

            return sorted(metrics, key=lambda x: x.timestamp)

        except ClientError as e:
            raise RuntimeError(f"AWS API error: {e.response['Error']['Message']}")
        except Exception as e:
            raise RuntimeError(f"Failed to get metrics: {str(e)}")


class GCPIntegration:
    """Google Cloud Platform integration."""

    def __init__(
        self,
        project_id: str,
        zone: str = "us-central1-a",
        credentials_path: Optional[str] = None,
    ):
        if not GCP_AVAILABLE:
            raise ImportError(
                "GCP SDK not available. Install with: pip install google-cloud-compute"
            )

        self.project_id = project_id
        self.zone = zone

        # Initialize credentials
        if credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_path
            )
            self.instances_client = compute_v1.InstancesClient(credentials=credentials)
        else:
            self.instances_client = compute_v1.InstancesClient()

    async def create_instance(self, spec: InstanceSpec) -> Dict[str, Any]:
        """Create GCP Compute Engine instance."""
        try:
            # Prepare instance configuration
            instance_body = {
                "name": spec.name,
                "machine_type": f"zones/{spec.zone or self.zone}/machineTypes/{spec.instance_type}",
                "disks": [
                    {
                        "boot": True,
                        "auto_delete": True,
                        "initialize_params": {"source_image": spec.image_id},
                    }
                ],
                "network_interfaces": [
                    {
                        "network": "global/networks/default",
                        "access_configs": [
                            {"type": "ONE_TO_ONE_NAT", "name": "External NAT"}
                        ],
                    }
                ],
                "metadata": {"items": []},
                "labels": spec.tags.copy(),
            }

            # Add edge node label
            if spec.edge_node:
                instance_body["labels"]["edge-node"] = spec.edge_node.replace("_", "-")

            # Add user data if provided
            if spec.user_data:
                instance_body["metadata"]["items"].append(
                    {"key": "startup-script", "value": spec.user_data}
                )

            request = compute_v1.InsertInstanceRequest(
                project=self.project_id,
                zone=spec.zone or self.zone,
                instance_resource=instance_body,
            )

            operation = await asyncio.to_thread(
                self.instances_client.insert, request=request
            )

            return {
                "status": "created",
                "instance_name": spec.name,
                "operation_id": operation.name,
                "zone": spec.zone or self.zone,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to create GCP instance: {str(e)}",
            }

    async def get_instance_status(
        self, instance_name: str, zone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get GCP Compute Engine instance status."""
        try:
            request = compute_v1.GetInstanceRequest(
                project=self.project_id, zone=zone or self.zone, instance=instance_name
            )

            instance = await asyncio.to_thread(
                self.instances_client.get, request=request
            )

            return {
                "instance_name": instance.name,
                "status": instance.status,
                "machine_type": instance.machine_type.split("/")[-1],
                "zone": instance.zone.split("/")[-1],
                "creation_timestamp": instance.creation_timestamp,
                "labels": dict(instance.labels) if instance.labels else {},
                "network_interfaces": [
                    {
                        "network_ip": interface.network_i_p,
                        "access_configs": [
                            {"nat_ip": config.nat_i_p}
                            for config in interface.access_configs or []
                        ],
                    }
                    for interface in instance.network_interfaces or []
                ],
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to get GCP instance status: {str(e)}",
            }

    async def delete_instance(
        self, instance_name: str, zone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Delete GCP Compute Engine instance."""
        try:
            request = compute_v1.DeleteInstanceRequest(
                project=self.project_id, zone=zone or self.zone, instance=instance_name
            )

            operation = await asyncio.to_thread(
                self.instances_client.delete, request=request
            )

            return {
                "status": "deleting",
                "instance_name": instance_name,
                "operation_id": operation.name,
                "zone": zone or self.zone,
            }

        except Exception as e:
            return {
                "status": "error",
                "error": f"Failed to delete GCP instance: {str(e)}",
            }


class CloudIntegration:
    """Unified cloud integration for edge resource management."""

    def __init__(self):
        self.integrations: Dict[CloudProvider, Any] = {}
        self.instances: Dict[str, CloudInstance] = {}

        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None

        # Configuration
        self.monitoring_interval = 60  # seconds

    def register_aws(
        self, region: str = "us-west-2", profile_name: Optional[str] = None
    ) -> None:
        """Register AWS integration."""
        try:
            self.integrations[CloudProvider.AWS] = AWSIntegration(region, profile_name)
        except ImportError as e:
            raise RuntimeError(f"Failed to register AWS integration: {e}")

    def register_gcp(
        self,
        project_id: str,
        zone: str = "us-central1-a",
        credentials_path: Optional[str] = None,
    ) -> None:
        """Register GCP integration."""
        try:
            self.integrations[CloudProvider.GCP] = GCPIntegration(
                project_id, zone, credentials_path
            )
        except ImportError as e:
            raise RuntimeError(f"Failed to register GCP integration: {e}")

    def register_azure(self, subscription_id: str, resource_group: str) -> None:
        """Register Azure integration."""
        if not AZURE_AVAILABLE:
            raise ImportError(
                "Azure SDK not available. Install with: pip install azure-mgmt-compute azure-identity"
            )
        # Azure integration would be implemented here
        raise NotImplementedError("Azure integration not yet implemented")

    async def create_instance(self, spec: InstanceSpec) -> Dict[str, Any]:
        """Create cloud instance."""
        if spec.provider not in self.integrations:
            return {
                "status": "error",
                "error": f"Provider {spec.provider.value} not registered",
            }

        integration = self.integrations[spec.provider]
        result = await integration.create_instance(spec)

        if result.get("status") == "created":
            # Create instance tracking object
            instance = CloudInstance(
                instance_id=result.get("instance_id") or result.get("instance_name"),
                name=spec.name,
                provider=spec.provider,
                instance_type=spec.instance_type,
                image_id=spec.image_id,
                region=spec.region,
                zone=spec.zone,
                tags=spec.tags,
                edge_node=spec.edge_node,
            )

            self.instances[instance.instance_id] = instance

        return result

    async def get_instance_status(
        self, provider: CloudProvider, instance_id: str, zone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get cloud instance status."""
        if provider not in self.integrations:
            return {
                "status": "error",
                "error": f"Provider {provider.value} not registered",
            }

        integration = self.integrations[provider]

        if provider == CloudProvider.AWS:
            return await integration.get_instance_status(instance_id)
        elif provider == CloudProvider.GCP:
            return await integration.get_instance_status(instance_id, zone)
        else:
            return {
                "status": "error",
                "error": f"Status operation not implemented for {provider.value}",
            }

    async def terminate_instance(
        self, provider: CloudProvider, instance_id: str, zone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Terminate cloud instance."""
        if provider not in self.integrations:
            return {
                "status": "error",
                "error": f"Provider {provider.value} not registered",
            }

        integration = self.integrations[provider]

        if provider == CloudProvider.AWS:
            result = await integration.terminate_instance(instance_id)
        elif provider == CloudProvider.GCP:
            result = await integration.delete_instance(instance_id, zone)
        else:
            return {
                "status": "error",
                "error": f"Terminate operation not implemented for {provider.value}",
            }

        # Remove from tracking
        if result.get("status") in ["terminating", "deleting"]:
            self.instances.pop(instance_id, None)

        return result

    async def list_instances(
        self, provider: CloudProvider, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List cloud instances."""
        if provider not in self.integrations:
            raise RuntimeError(f"Provider {provider.value} not registered")

        integration = self.integrations[provider]

        if provider == CloudProvider.AWS:
            return await integration.list_instances(filters)
        else:
            raise NotImplementedError(
                f"List operation not implemented for {provider.value}"
            )

    async def get_instance_metrics(
        self,
        provider: CloudProvider,
        instance_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[CloudMetrics]:
        """Get cloud instance metrics."""
        if provider not in self.integrations:
            raise RuntimeError(f"Provider {provider.value} not registered")

        integration = self.integrations[provider]

        if provider == CloudProvider.AWS:
            return await integration.get_instance_metrics(
                instance_id, start_time, end_time
            )
        else:
            raise NotImplementedError(
                f"Metrics operation not implemented for {provider.value}"
            )

    async def get_supported_providers(self) -> List[str]:
        """Get list of registered cloud providers."""
        return [provider.value for provider in self.integrations.keys()]

    async def get_provider_info(self, provider: CloudProvider) -> Dict[str, Any]:
        """Get cloud provider information."""
        if provider not in self.integrations:
            return {
                "status": "error",
                "error": f"Provider {provider.value} not registered",
            }

        provider_info = {"provider": provider.value, "registered": True, "features": []}

        if provider == CloudProvider.AWS:
            provider_info["features"] = [
                "create_instance",
                "get_instance_status",
                "terminate_instance",
                "list_instances",
                "get_instance_metrics",
            ]
            provider_info["region"] = self.integrations[provider].region
        elif provider == CloudProvider.GCP:
            provider_info["features"] = [
                "create_instance",
                "get_instance_status",
                "delete_instance",
            ]
            provider_info["project_id"] = self.integrations[provider].project_id
            provider_info["zone"] = self.integrations[provider].zone

        return provider_info

    async def start_monitoring(self) -> None:
        """Start cloud instance monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            return

        self._monitoring_task = asyncio.create_task(self._monitor_instances())

    async def stop_monitoring(self) -> None:
        """Stop cloud instance monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

    async def _monitor_instances(self) -> None:
        """Monitor cloud instances continuously."""
        while True:
            try:
                # Update status for all tracked instances
                for instance_id, instance in list(self.instances.items()):
                    try:
                        status = await self.get_instance_status(
                            instance.provider, instance_id, instance.zone
                        )

                        # Update instance state based on status
                        if status.get("state"):
                            if status["state"] in ["running", "RUNNING"]:
                                instance.state = InstanceState.RUNNING
                            elif status["state"] in ["stopped", "TERMINATED"]:
                                instance.state = InstanceState.STOPPED
                            elif status["state"] in ["stopping", "STOPPING"]:
                                instance.state = InstanceState.STOPPING
                            elif status["state"] in ["pending", "PROVISIONING"]:
                                instance.state = InstanceState.PENDING
                            elif status["state"] in ["terminated", "TERMINATED"]:
                                instance.state = InstanceState.TERMINATED
                                # Remove terminated instances
                                del self.instances[instance_id]
                            else:
                                instance.state = InstanceState.UNKNOWN

                        # Update IP addresses
                        if status.get("public_ip"):
                            instance.public_ip = status["public_ip"]
                        if status.get("private_ip"):
                            instance.private_ip = status["private_ip"]

                    except Exception:
                        # Instance might have been deleted
                        pass

                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue monitoring
                print(f"Cloud monitoring error: {e}")
                await asyncio.sleep(self.monitoring_interval)
