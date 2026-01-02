"""Docker integration for edge resource management."""

import asyncio
import base64
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Union

try:
    import docker
    from docker.types import EndpointSpec, LogConfig, RestartPolicy, UpdateConfig

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False


class ContainerState(Enum):
    """Container states."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    RESTARTING = "restarting"
    REMOVING = "removing"
    EXITED = "exited"
    DEAD = "dead"


class RestartPolicyType(Enum):
    """Container restart policies."""

    NONE = "no"
    ALWAYS = "always"
    UNLESS_STOPPED = "unless-stopped"
    ON_FAILURE = "on-failure"


class NetworkMode(Enum):
    """Docker network modes."""

    BRIDGE = "bridge"
    HOST = "host"
    NONE = "none"
    CONTAINER = "container"
    CUSTOM = "custom"


@dataclass
class ContainerSpec:
    """Docker container specification."""

    name: str
    image: str
    command: Optional[List[str]] = None
    environment: Optional[Dict[str, str]] = None
    ports: Optional[Dict[str, int]] = None  # container_port -> host_port
    volumes: Optional[Dict[str, str]] = None  # host_path -> container_path
    restart_policy: RestartPolicyType = RestartPolicyType.UNLESS_STOPPED
    memory_limit: Optional[str] = None  # e.g., "512m", "1g"
    cpu_limit: Optional[float] = None  # CPU cores
    network_mode: NetworkMode = NetworkMode.BRIDGE
    labels: Optional[Dict[str, str]] = None
    edge_node: Optional[str] = None
    healthcheck: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = {}
        if self.volumes is None:
            self.volumes = {}
        if self.labels is None:
            self.labels = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["restart_policy"] = self.restart_policy.value
        data["network_mode"] = self.network_mode.value
        return data

    def to_docker_config(self) -> Dict[str, Any]:
        """Convert to Docker API configuration."""
        config = {
            "image": self.image,
            "name": self.name,
            "environment": list(f"{k}={v}" for k, v in self.environment.items()),
            "labels": self.labels.copy(),
        }

        # Add edge node label if specified
        if self.edge_node:
            config["labels"]["edge-node"] = self.edge_node

        # Command
        if self.command:
            config["command"] = self.command

        # Port bindings
        if self.ports:
            config["ports"] = self.ports
            config["host_config"] = config.get("host_config", {})
            config["host_config"]["port_bindings"] = {
                f"{container_port}/tcp": host_port
                for container_port, host_port in self.ports.items()
            }

        # Volume bindings
        if self.volumes:
            config["host_config"] = config.get("host_config", {})
            config["host_config"]["binds"] = [
                f"{host_path}:{container_path}"
                for host_path, container_path in self.volumes.items()
            ]

        # Restart policy
        if self.restart_policy != RestartPolicyType.NONE:
            config["host_config"] = config.get("host_config", {})
            config["host_config"]["restart_policy"] = {
                "Name": self.restart_policy.value
            }

        # Resource limits
        if self.memory_limit or self.cpu_limit:
            config["host_config"] = config.get("host_config", {})
            if self.memory_limit:
                config["host_config"]["mem_limit"] = self.memory_limit
            if self.cpu_limit:
                config["host_config"]["nano_cpus"] = int(self.cpu_limit * 1e9)

        # Network mode
        if self.network_mode != NetworkMode.BRIDGE:
            config["host_config"] = config.get("host_config", {})
            config["host_config"]["network_mode"] = self.network_mode.value

        # Health check
        if self.healthcheck:
            config["healthcheck"] = self.healthcheck

        return config


@dataclass
class ServiceSpec:
    """Docker Swarm service specification."""

    name: str
    image: str
    replicas: int = 1
    command: Optional[List[str]] = None
    environment: Optional[Dict[str, str]] = None
    ports: Optional[List[Dict[str, Any]]] = None
    volumes: Optional[List[Dict[str, str]]] = None
    constraints: Optional[List[str]] = None
    placement_preferences: Optional[List[Dict[str, Any]]] = None
    restart_policy: Optional[Dict[str, Any]] = None
    update_config: Optional[Dict[str, Any]] = None
    rollback_config: Optional[Dict[str, Any]] = None
    labels: Optional[Dict[str, str]] = None
    edge_node: Optional[str] = None

    def __post_init__(self):
        if self.environment is None:
            self.environment = {}
        if self.ports is None:
            self.ports = []
        if self.volumes is None:
            self.volumes = []
        if self.constraints is None:
            self.constraints = []
        if self.placement_preferences is None:
            self.placement_preferences = []
        if self.labels is None:
            self.labels = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_docker_service_spec(self) -> Dict[str, Any]:
        """Convert to Docker service specification."""
        task_template = {
            "ContainerSpec": {
                "Image": self.image,
                "Env": [f"{k}={v}" for k, v in self.environment.items()],
                "Labels": self.labels.copy(),
            },
            "Placement": {
                "Constraints": self.constraints.copy(),
                "Preferences": self.placement_preferences.copy(),
            },
        }

        # Add edge node constraint if specified
        if self.edge_node:
            task_template["Placement"]["Constraints"].append(
                f"node.labels.edge-node=={self.edge_node}"
            )

        # Command
        if self.command:
            task_template["ContainerSpec"]["Command"] = self.command

        # Restart policy
        if self.restart_policy:
            task_template["RestartPolicy"] = self.restart_policy

        spec = {
            "Name": self.name,
            "TaskTemplate": task_template,
            "Mode": {"Replicated": {"Replicas": self.replicas}},
            "Labels": self.labels.copy(),
        }

        # Update configuration
        if self.update_config:
            spec["UpdateConfig"] = self.update_config

        # Rollback configuration
        if self.rollback_config:
            spec["RollbackConfig"] = self.rollback_config

        # Endpoint spec for ports
        if self.ports:
            spec["EndpointSpec"] = {"Ports": self.ports}

        return spec


@dataclass
class ContainerMetrics:
    """Container resource metrics."""

    container_id: str
    container_name: str
    timestamp: datetime
    cpu_usage_percent: float
    memory_usage_bytes: int
    memory_limit_bytes: int
    network_rx_bytes: int
    network_tx_bytes: int
    block_read_bytes: int
    block_write_bytes: int

    @property
    def memory_usage_percent(self) -> float:
        """Calculate memory usage percentage."""
        if self.memory_limit_bytes > 0:
            return (self.memory_usage_bytes / self.memory_limit_bytes) * 100
        return 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        data["memory_usage_percent"] = self.memory_usage_percent
        return data


class DockerIntegration:
    """Docker integration for edge resource management."""

    def __init__(
        self,
        docker_host: Optional[str] = None,
        api_version: str = "auto",
        timeout: int = 60,
    ):
        """Initialize Docker integration.

        Args:
            docker_host: Docker daemon socket (default: system default)
            api_version: Docker API version
            timeout: API timeout in seconds
        """
        if not DOCKER_AVAILABLE:
            raise ImportError(
                "Docker client not available. Install with: pip install docker"
            )

        self.docker_host = docker_host
        self.api_version = api_version
        self.timeout = timeout

        # Docker clients
        self.docker_client: Optional[docker.DockerClient] = None
        self.swarm_enabled = False

        # Container tracking
        self.containers: Dict[str, ContainerSpec] = {}
        self.services: Dict[str, ServiceSpec] = {}
        self.container_metrics: Dict[str, ContainerMetrics] = {}

        # Background tasks
        self._monitoring_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None

        # Configuration
        self.monitoring_interval = 30  # seconds
        self.metrics_interval = 10  # seconds
        self.auto_pull_images = True

    async def initialize(self) -> None:
        """Initialize Docker client."""
        try:
            if self.docker_host:
                self.docker_client = docker.DockerClient(
                    base_url=self.docker_host,
                    version=self.api_version,
                    timeout=self.timeout,
                )
            else:
                self.docker_client = docker.from_env(
                    version=self.api_version, timeout=self.timeout
                )

            # Test connection
            await asyncio.to_thread(self.docker_client.ping)

            # Check if Swarm is enabled
            try:
                swarm_info = await asyncio.to_thread(self.docker_client.swarm.attrs)
                self.swarm_enabled = True
            except:
                self.swarm_enabled = False

        except Exception as e:
            raise RuntimeError(f"Failed to initialize Docker client: {e}")

    async def create_container(self, container_spec: ContainerSpec) -> Dict[str, Any]:
        """Create Docker container.

        Args:
            container_spec: Container specification

        Returns:
            Creation result
        """
        if not self.docker_client:
            await self.initialize()

        try:
            # Pull image if auto-pull is enabled
            if self.auto_pull_images:
                try:
                    await asyncio.to_thread(
                        self.docker_client.images.pull, container_spec.image
                    )
                except Exception as e:
                    # Continue if image already exists locally
                    pass

            # Create container
            docker_config = container_spec.to_docker_config()
            container = await asyncio.to_thread(
                self.docker_client.containers.create, **docker_config
            )

            # Store container spec
            self.containers[container.id] = container_spec

            return {
                "status": "created",
                "container_id": container.id,
                "container_name": container_spec.name,
                "image": container_spec.image,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to create container: {e}"}

    async def start_container(self, container_id: str) -> Dict[str, Any]:
        """Start Docker container.

        Args:
            container_id: Container ID or name

        Returns:
            Start result
        """
        if not self.docker_client:
            await self.initialize()

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get, container_id
            )
            await asyncio.to_thread(container.start)

            return {
                "status": "started",
                "container_id": container.id,
                "container_name": container.name,
                "started_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to start container: {e}"}

    async def stop_container(
        self, container_id: str, timeout: int = 10
    ) -> Dict[str, Any]:
        """Stop Docker container.

        Args:
            container_id: Container ID or name
            timeout: Stop timeout in seconds

        Returns:
            Stop result
        """
        if not self.docker_client:
            await self.initialize()

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get, container_id
            )
            await asyncio.to_thread(container.stop, timeout=timeout)

            return {
                "status": "stopped",
                "container_id": container.id,
                "container_name": container.name,
                "stopped_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to stop container: {e}"}

    async def remove_container(
        self, container_id: str, force: bool = False
    ) -> Dict[str, Any]:
        """Remove Docker container.

        Args:
            container_id: Container ID or name
            force: Force removal

        Returns:
            Removal result
        """
        if not self.docker_client:
            await self.initialize()

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get, container_id
            )
            await asyncio.to_thread(container.remove, force=force)

            # Remove from tracking
            self.containers.pop(container.id, None)
            self.container_metrics.pop(container.id, None)

            return {
                "status": "removed",
                "container_id": container.id,
                "container_name": container.name,
                "removed_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to remove container: {e}"}

    async def get_container_status(self, container_id: str) -> Dict[str, Any]:
        """Get container status.

        Args:
            container_id: Container ID or name

        Returns:
            Container status
        """
        if not self.docker_client:
            await self.initialize()

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get, container_id
            )
            await asyncio.to_thread(container.reload)

            return {
                "container_id": container.id,
                "container_name": container.name,
                "status": container.status,
                "state": container.attrs["State"],
                "image": (
                    container.image.tags[0]
                    if container.image.tags
                    else container.image.id
                ),
                "created_at": container.attrs["Created"],
                "started_at": container.attrs["State"].get("StartedAt"),
                "finished_at": container.attrs["State"].get("FinishedAt"),
                "ports": container.ports,
                "labels": container.labels,
                "mounts": [
                    {
                        "source": mount["Source"],
                        "destination": mount["Destination"],
                        "mode": mount["Mode"],
                        "type": mount["Type"],
                    }
                    for mount in container.attrs.get("Mounts", [])
                ],
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to get container status: {e}"}

    async def list_containers(
        self, all_containers: bool = False, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """List Docker containers.

        Args:
            all_containers: Include stopped containers
            filters: Container filters

        Returns:
            List of containers
        """
        if not self.docker_client:
            await self.initialize()

        try:
            containers = await asyncio.to_thread(
                self.docker_client.containers.list,
                all=all_containers,
                filters=filters or {},
            )

            container_list = []
            for container in containers:
                container_info = {
                    "container_id": container.id,
                    "container_name": container.name,
                    "status": container.status,
                    "image": (
                        container.image.tags[0]
                        if container.image.tags
                        else container.image.id
                    ),
                    "created_at": container.attrs["Created"],
                    "labels": container.labels,
                    "ports": container.ports,
                }
                container_list.append(container_info)

            return container_list

        except Exception as e:
            raise RuntimeError(f"Failed to list containers: {e}")

    async def create_service(self, service_spec: ServiceSpec) -> Dict[str, Any]:
        """Create Docker Swarm service.

        Args:
            service_spec: Service specification

        Returns:
            Creation result
        """
        if not self.docker_client:
            await self.initialize()

        if not self.swarm_enabled:
            return {"status": "error", "error": "Docker Swarm is not enabled"}

        try:
            # Pull image if auto-pull is enabled
            if self.auto_pull_images:
                try:
                    await asyncio.to_thread(
                        self.docker_client.images.pull, service_spec.image
                    )
                except Exception:
                    pass

            # Create service
            docker_spec = service_spec.to_docker_service_spec()
            service = await asyncio.to_thread(
                self.docker_client.services.create, **docker_spec
            )

            # Store service spec
            self.services[service.id] = service_spec

            return {
                "status": "created",
                "service_id": service.id,
                "service_name": service_spec.name,
                "image": service_spec.image,
                "replicas": service_spec.replicas,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to create service: {e}"}

    async def update_service(
        self, service_id: str, service_spec: ServiceSpec
    ) -> Dict[str, Any]:
        """Update Docker Swarm service.

        Args:
            service_id: Service ID or name
            service_spec: Updated service specification

        Returns:
            Update result
        """
        if not self.docker_client:
            await self.initialize()

        if not self.swarm_enabled:
            return {"status": "error", "error": "Docker Swarm is not enabled"}

        try:
            service = await asyncio.to_thread(
                self.docker_client.services.get, service_id
            )
            docker_spec = service_spec.to_docker_service_spec()

            await asyncio.to_thread(service.update, **docker_spec)

            # Update stored spec
            self.services[service.id] = service_spec

            return {
                "status": "updated",
                "service_id": service.id,
                "service_name": service_spec.name,
                "updated_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to update service: {e}"}

    async def scale_service(self, service_id: str, replicas: int) -> Dict[str, Any]:
        """Scale Docker Swarm service.

        Args:
            service_id: Service ID or name
            replicas: Target replica count

        Returns:
            Scaling result
        """
        if not self.docker_client:
            await self.initialize()

        if not self.swarm_enabled:
            return {"status": "error", "error": "Docker Swarm is not enabled"}

        try:
            service = await asyncio.to_thread(
                self.docker_client.services.get, service_id
            )
            await asyncio.to_thread(service.scale, replicas)

            return {
                "status": "scaled",
                "service_id": service.id,
                "service_name": service.name,
                "target_replicas": replicas,
                "scaled_at": datetime.now().isoformat(),
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to scale service: {e}"}

    async def get_service_status(self, service_id: str) -> Dict[str, Any]:
        """Get service status.

        Args:
            service_id: Service ID or name

        Returns:
            Service status
        """
        if not self.docker_client:
            await self.initialize()

        if not self.swarm_enabled:
            return {"status": "error", "error": "Docker Swarm is not enabled"}

        try:
            service = await asyncio.to_thread(
                self.docker_client.services.get, service_id
            )
            tasks = await asyncio.to_thread(service.tasks)

            running_tasks = sum(
                1 for task in tasks if task.get("Status", {}).get("State") == "running"
            )
            total_tasks = len(tasks)

            return {
                "service_id": service.id,
                "service_name": service.name,
                "mode": service.attrs["Spec"]["Mode"],
                "replicas": service.attrs["Spec"]["Mode"]
                .get("Replicated", {})
                .get("Replicas", 0),
                "running_tasks": running_tasks,
                "total_tasks": total_tasks,
                "image": service.attrs["Spec"]["TaskTemplate"]["ContainerSpec"][
                    "Image"
                ],
                "created_at": service.attrs["CreatedAt"],
                "updated_at": service.attrs["UpdatedAt"],
                "labels": service.attrs["Spec"].get("Labels", {}),
                "tasks": [
                    {
                        "id": task["ID"],
                        "state": task.get("Status", {}).get("State"),
                        "desired_state": task.get("DesiredState"),
                        "node_id": task.get("NodeID"),
                        "timestamp": task.get("Status", {}).get("Timestamp"),
                    }
                    for task in tasks
                ],
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to get service status: {e}"}

    async def collect_container_metrics(
        self, container_id: str
    ) -> Optional[ContainerMetrics]:
        """Collect container resource metrics.

        Args:
            container_id: Container ID

        Returns:
            Container metrics or None if failed
        """
        if not self.docker_client:
            await self.initialize()

        try:
            container = await asyncio.to_thread(
                self.docker_client.containers.get, container_id
            )
            stats = await asyncio.to_thread(container.stats, stream=False)

            # Calculate CPU usage percentage
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )

            cpu_usage_percent = 0.0
            if system_delta > 0:
                cpu_usage_percent = (
                    (cpu_delta / system_delta)
                    * len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
                    * 100
                )

            # Memory usage
            memory_usage = stats["memory_stats"]["usage"]
            memory_limit = stats["memory_stats"]["limit"]

            # Network I/O
            networks = stats.get("networks", {})
            network_rx = sum(net["rx_bytes"] for net in networks.values())
            network_tx = sum(net["tx_bytes"] for net in networks.values())

            # Block I/O
            blkio_stats = stats.get("blkio_stats", {}).get(
                "io_service_bytes_recursive", []
            )
            block_read = sum(
                entry["value"] for entry in blkio_stats if entry["op"] == "Read"
            )
            block_write = sum(
                entry["value"] for entry in blkio_stats if entry["op"] == "Write"
            )

            metrics = ContainerMetrics(
                container_id=container.id,
                container_name=container.name,
                timestamp=datetime.now(),
                cpu_usage_percent=cpu_usage_percent,
                memory_usage_bytes=memory_usage,
                memory_limit_bytes=memory_limit,
                network_rx_bytes=network_rx,
                network_tx_bytes=network_tx,
                block_read_bytes=block_read,
                block_write_bytes=block_write,
            )

            # Store metrics
            self.container_metrics[container_id] = metrics

            return metrics

        except Exception:
            return None

    async def get_system_info(self) -> Dict[str, Any]:
        """Get Docker system information.

        Returns:
            System information
        """
        if not self.docker_client:
            await self.initialize()

        try:
            info = await asyncio.to_thread(self.docker_client.info)
            version = await asyncio.to_thread(self.docker_client.version)

            return {
                "system_info": {
                    "containers": info.get("Containers", 0),
                    "containers_running": info.get("ContainersRunning", 0),
                    "containers_paused": info.get("ContainersPaused", 0),
                    "containers_stopped": info.get("ContainersStopped", 0),
                    "images": info.get("Images", 0),
                    "driver": info.get("Driver"),
                    "memory_limit": info.get("MemoryLimit"),
                    "swap_limit": info.get("SwapLimit"),
                    "cpus": info.get("NCPU", 0),
                    "memory": info.get("MemTotal", 0),
                    "docker_root_dir": info.get("DockerRootDir"),
                    "swarm": info.get("Swarm", {}),
                },
                "version_info": version,
                "swarm_enabled": self.swarm_enabled,
            }

        except Exception as e:
            return {"status": "error", "error": f"Failed to get system info: {e}"}

    async def start_monitoring(self) -> None:
        """Start container monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            return

        self._monitoring_task = asyncio.create_task(self._monitor_containers())
        self._metrics_task = asyncio.create_task(self._collect_metrics())

    async def stop_monitoring(self) -> None:
        """Stop container monitoring."""
        if self._monitoring_task and not self._monitoring_task.done():
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass

        if self._metrics_task and not self._metrics_task.done():
            self._metrics_task.cancel()
            try:
                await self._metrics_task
            except asyncio.CancelledError:
                pass

    async def _monitor_containers(self) -> None:
        """Monitor containers continuously."""
        while True:
            try:
                # Get list of running containers
                containers = await self.list_containers(all_containers=False)

                # Update container status for tracked containers
                for container_id in list(self.containers.keys()):
                    try:
                        status = await self.get_container_status(container_id)
                        # Update internal tracking based on status
                    except Exception:
                        # Container might have been removed
                        self.containers.pop(container_id, None)

                await asyncio.sleep(self.monitoring_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue monitoring
                print(f"Container monitoring error: {e}")
                await asyncio.sleep(self.monitoring_interval)

    async def _collect_metrics(self) -> None:
        """Collect container metrics continuously."""
        while True:
            try:
                # Collect metrics for all running containers
                containers = await self.list_containers(all_containers=False)

                for container_info in containers:
                    container_id = container_info["container_id"]
                    if container_info["status"] == "running":
                        await self.collect_container_metrics(container_id)

                await asyncio.sleep(self.metrics_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error and continue collecting
                print(f"Metrics collection error: {e}")
                await asyncio.sleep(self.metrics_interval)
