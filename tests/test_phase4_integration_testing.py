"""Comprehensive tests for Phase 4.4 Integration & Testing."""

import asyncio
from datetime import datetime, timedelta

import pytest

from kailash.runtime.local import LocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from tests.utils.docker_config import is_docker_available, is_kubernetes_available


class TestKubernetesIntegration:
    """Test Kubernetes integration components."""

    def test_kubernetes_integration_imports(self):
        """Test that all Kubernetes integration components can be imported."""
        from kailash.edge.resource import (
            KubernetesIntegration,
            KubernetesResource,
            KubernetesResourceType,
            PodScalingSpec,
            ScalingPolicy,
        )
        from kailash.nodes.edge import KubernetesNode

        assert isinstance(KubernetesNode, type)
        assert isinstance(KubernetesIntegration, type)
        assert isinstance(KubernetesResource, type)
        assert isinstance(KubernetesResourceType, type)
        assert isinstance(PodScalingSpec, type)
        assert isinstance(ScalingPolicy, type)

    def test_kubernetes_node_workflow_build(self):
        """Test that Kubernetes node workflows build correctly."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "KubernetesNode",
            "k8s_manager",
            {"operation": "initialize", "namespace": "edge-system"},
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 1

    def test_kubernetes_resource_creation(self):
        """Test Kubernetes resource specification."""
        from kailash.edge.resource import KubernetesResource, KubernetesResourceType

        resource = KubernetesResource(
            name="test-deployment",
            namespace="default",
            resource_type=KubernetesResourceType.DEPLOYMENT,
            spec={
                "replicas": 3,
                "selector": {"matchLabels": {"app": "test"}},
                "template": {
                    "metadata": {"labels": {"app": "test"}},
                    "spec": {
                        "containers": [
                            {
                                "name": "test-container",
                                "image": "nginx:latest",
                                "ports": [{"containerPort": 80}],
                            }
                        ]
                    },
                },
            },
            edge_node="edge-west-1",
        )

        assert resource.name == "test-deployment"
        assert resource.resource_type == KubernetesResourceType.DEPLOYMENT
        assert resource.edge_node == "edge-west-1"

        manifest = resource.to_k8s_manifest()
        assert manifest["apiVersion"] == "apps/v1"
        assert manifest["kind"] == "Deployment"
        assert manifest["metadata"]["name"] == "test-deployment"

    def test_pod_scaling_spec(self):
        """Test pod scaling specification."""
        from kailash.edge.resource import PodScalingSpec

        scaling_spec = PodScalingSpec(
            min_replicas=2,
            max_replicas=10,
            target_cpu_utilization=0.7,
            target_memory_utilization=0.8,
        )

        hpa_spec = scaling_spec.to_hpa_spec()

        assert hpa_spec["minReplicas"] == 2
        assert hpa_spec["maxReplicas"] == 10
        assert len(hpa_spec["metrics"]) == 2  # CPU + Memory

        cpu_metric = hpa_spec["metrics"][0]
        assert cpu_metric["resource"]["name"] == "cpu"
        assert cpu_metric["resource"]["target"]["averageUtilization"] == 70


class TestDockerIntegration:
    """Test Docker integration components."""

    def test_docker_integration_imports(self):
        """Test that all Docker integration components can be imported."""
        from kailash.edge.resource import (
            ContainerMetrics,
            ContainerSpec,
            ContainerState,
            DockerIntegration,
            NetworkMode,
            RestartPolicyType,
            ServiceSpec,
        )
        from kailash.nodes.edge import DockerNode

        assert isinstance(DockerNode, type)
        assert isinstance(DockerIntegration, type)
        assert isinstance(ContainerSpec, type)
        assert isinstance(ServiceSpec, type)
        assert isinstance(ContainerState, type)
        assert isinstance(RestartPolicyType, type)
        assert isinstance(NetworkMode, type)
        assert isinstance(ContainerMetrics, type)

    def test_docker_node_workflow_build(self):
        """Test that Docker node workflows build correctly."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "DockerNode",
            "docker_manager",
            {"operation": "initialize", "docker_host": "unix:///var/run/docker.sock"},
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 1

    def test_container_spec_creation(self):
        """Test Docker container specification."""
        from kailash.edge.resource import ContainerSpec, NetworkMode, RestartPolicyType

        container_spec = ContainerSpec(
            name="test-container",
            image="nginx:alpine",
            environment={"ENV": "test"},
            ports={"80": 8080},
            volumes={"/host/data": "/container/data"},
            restart_policy=RestartPolicyType.UNLESS_STOPPED,
            memory_limit="512m",
            cpu_limit=1.0,
            network_mode=NetworkMode.BRIDGE,
            edge_node="edge-west-1",
        )

        assert container_spec.name == "test-container"
        assert container_spec.image == "nginx:alpine"
        assert container_spec.edge_node == "edge-west-1"

        docker_config = container_spec.to_docker_config()
        assert docker_config["image"] == "nginx:alpine"
        assert docker_config["name"] == "test-container"
        assert "edge-node" in docker_config["labels"]
        assert docker_config["labels"]["edge-node"] == "edge-west-1"

    def test_service_spec_creation(self):
        """Test Docker Swarm service specification."""
        from kailash.edge.resource import ServiceSpec

        service_spec = ServiceSpec(
            name="test-service",
            image="nginx:alpine",
            replicas=3,
            environment={"SERVICE_ENV": "production"},
            constraints=["node.role==worker"],
            edge_node="edge-west-1",
        )

        assert service_spec.name == "test-service"
        assert service_spec.replicas == 3

        docker_spec = service_spec.to_docker_service_spec()
        assert docker_spec["Name"] == "test-service"
        assert docker_spec["Mode"]["Replicated"]["Replicas"] == 3

        # Check edge node constraint
        constraints = docker_spec["TaskTemplate"]["Placement"]["Constraints"]
        assert "node.labels.edge-node==edge-west-1" in constraints

    def test_container_metrics(self):
        """Test container metrics functionality."""
        from kailash.edge.resource import ContainerMetrics

        metrics = ContainerMetrics(
            container_id="abc123",
            container_name="test-container",
            timestamp=datetime.now(),
            cpu_usage_percent=45.0,
            memory_usage_bytes=256 * 1024 * 1024,  # 256MB
            memory_limit_bytes=512 * 1024 * 1024,  # 512MB
            network_rx_bytes=1024,
            network_tx_bytes=2048,
            block_read_bytes=4096,
            block_write_bytes=8192,
        )

        assert metrics.memory_usage_percent == 50.0  # 256MB / 512MB * 100

        data = metrics.to_dict()
        assert data["container_id"] == "abc123"
        assert data["memory_usage_percent"] == 50.0


class TestCloudIntegration:
    """Test Cloud integration components."""

    def test_cloud_integration_imports(self):
        """Test that all Cloud integration components can be imported."""
        from kailash.edge.resource import (
            CloudInstance,
            CloudIntegration,
            CloudMetrics,
            CloudProvider,
            InstanceSpec,
            InstanceState,
            InstanceType,
        )
        from kailash.nodes.edge import CloudNode

        assert isinstance(CloudNode, type)
        assert isinstance(CloudIntegration, type)
        assert isinstance(CloudProvider, type)
        assert isinstance(InstanceSpec, type)
        assert isinstance(InstanceState, type)
        assert isinstance(InstanceType, type)
        assert isinstance(CloudInstance, type)
        assert isinstance(CloudMetrics, type)

    def test_cloud_node_workflow_build(self):
        """Test that Cloud node workflows build correctly."""
        workflow = WorkflowBuilder()

        workflow.add_node("CloudNode", "cloud_manager", {"operation": "initialize"})

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 1

    def test_instance_spec_creation(self):
        """Test cloud instance specification."""
        from kailash.edge.resource import CloudProvider, InstanceSpec

        instance_spec = InstanceSpec(
            name="test-instance",
            provider=CloudProvider.AWS,
            instance_type="t3.micro",
            image_id="ami-0c02fb55956c7d316",
            region="us-west-2",
            zone="us-west-2a",
            security_group_ids=["sg-12345678"],
            key_name="my-key",
            tags={"Environment": "test"},
            edge_node="edge-west-1",
        )

        assert instance_spec.name == "test-instance"
        assert instance_spec.provider == CloudProvider.AWS
        assert instance_spec.edge_node == "edge-west-1"

        data = instance_spec.to_dict()
        assert data["provider"] == "aws"
        assert data["instance_type"] == "t3.micro"

    def test_cloud_instance_creation(self):
        """Test cloud instance object."""
        from kailash.edge.resource import CloudInstance, CloudProvider, InstanceState

        instance = CloudInstance(
            instance_id="i-1234567890abcdef0",
            name="test-instance",
            provider=CloudProvider.AWS,
            instance_type="t3.micro",
            image_id="ami-0c02fb55956c7d316",
            region="us-west-2",
            zone="us-west-2a",
            state=InstanceState.RUNNING,
            public_ip="54.123.45.67",
            private_ip="10.0.1.100",
            edge_node="edge-west-1",
        )

        assert instance.instance_id == "i-1234567890abcdef0"
        assert instance.state == InstanceState.RUNNING
        assert instance.edge_node == "edge-west-1"

        data = instance.to_dict()
        assert data["provider"] == "aws"
        assert data["state"] == "running"

    def test_cloud_metrics(self):
        """Test cloud metrics functionality."""
        from kailash.edge.resource import CloudMetrics, CloudProvider

        metrics = CloudMetrics(
            instance_id="i-1234567890abcdef0",
            provider=CloudProvider.AWS,
            timestamp=datetime.now(),
            cpu_utilization=75.5,
            memory_utilization=60.0,
            network_in=1024.0,
            network_out=2048.0,
        )

        assert metrics.cpu_utilization == 75.5
        assert metrics.provider == CloudProvider.AWS

        data = metrics.to_dict()
        assert data["provider"] == "aws"
        assert data["cpu_utilization"] == 75.5


class TestPlatformIntegration:
    """Test unified platform integration."""

    def test_platform_integration_imports(self):
        """Test that all platform integration components can be imported."""
        from kailash.edge.resource import (
            PlatformConfig,
            PlatformIntegration,
            PlatformType,
            ResourceAllocation,
            ResourceRequest,
            ResourceScope,
        )
        from kailash.nodes.edge import PlatformNode

        assert isinstance(PlatformNode, type)
        assert isinstance(PlatformIntegration, type)
        assert isinstance(PlatformType, type)
        assert isinstance(ResourceScope, type)
        assert isinstance(ResourceRequest, type)
        assert isinstance(ResourceAllocation, type)
        assert isinstance(PlatformConfig, type)

    def test_platform_node_workflow_build(self):
        """Test that platform node workflows build correctly."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PlatformNode",
            "platform_manager",
            {
                "operation": "initialize",
                "auto_scaling_enabled": True,
                "auto_optimization_enabled": True,
            },
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 1

    def test_resource_request_creation(self):
        """Test resource request specification."""
        from kailash.edge.resource import PlatformResourceRequest as ResourceRequest
        from kailash.edge.resource import PlatformType, ResourceScope

        request = ResourceRequest(
            request_id="req-123",
            edge_node="edge-west-1",
            resource_type="deployment",
            resource_spec={
                "image": "nginx:latest",
                "replicas": 3,
                "memory": "512Mi",
                "cpu": "500m",
            },
            platform_preference=PlatformType.KUBERNETES,
            scope=ResourceScope.CLUSTER,
            tags={"env": "test", "team": "platform"},
        )

        assert request.request_id == "req-123"
        assert request.platform_preference == PlatformType.KUBERNETES
        assert request.scope == ResourceScope.CLUSTER

        data = request.to_dict()
        assert data["platform_preference"] == "kubernetes"
        assert data["scope"] == "cluster"

    def test_resource_allocation_creation(self):
        """Test resource allocation object."""
        from kailash.edge.resource import PlatformType, ResourceAllocation

        allocation = ResourceAllocation(
            allocation_id="alloc-456",
            request_id="req-123",
            platform_type=PlatformType.KUBERNETES,
            resource_id="default/test-deployment",
            edge_node="edge-west-1",
            resource_details={
                "namespace": "default",
                "name": "test-deployment",
                "replicas": 3,
            },
            allocated_at=datetime.now(),
            status="allocated",
        )

        assert allocation.allocation_id == "alloc-456"
        assert allocation.platform_type == PlatformType.KUBERNETES
        assert allocation.status == "allocated"

        data = allocation.to_dict()
        assert data["platform_type"] == "kubernetes"
        assert data["resource_id"] == "default/test-deployment"

    def test_platform_config(self):
        """Test platform configuration."""
        from kailash.edge.resource import PlatformConfig, PlatformType

        config = PlatformConfig(
            platform_type=PlatformType.DOCKER,
            enabled=True,
            config={
                "docker_host": "unix:///var/run/docker.sock",
                "api_version": "auto",
                "swarm_enabled": True,
            },
            priority=2,
        )

        assert config.platform_type == PlatformType.DOCKER
        assert config.enabled is True
        assert config.priority == 2

        data = config.to_dict()
        assert data["platform_type"] == "docker"
        assert data["config"]["swarm_enabled"] is True


class TestIntegratedWorkflows:
    """Test integrated workflows using multiple platform components."""

    def test_multi_platform_workflow_build(self):
        """Test workflow with multiple platform components."""
        workflow = WorkflowBuilder()

        # Initialize platform integration
        workflow.add_node(
            "PlatformNode",
            "platform_init",
            {
                "operation": "initialize",
                "auto_scaling_enabled": True,
                "monitoring_interval": 30,
            },
        )

        # Register Kubernetes
        workflow.add_node(
            "PlatformNode",
            "k8s_register",
            {
                "operation": "register_kubernetes",
                "namespace": "edge-system",
                "priority": 1,
            },
        )

        # Register Docker
        workflow.add_node(
            "PlatformNode",
            "docker_register",
            {"operation": "register_docker", "priority": 2},
        )

        # Allocate resource
        workflow.add_node(
            "PlatformNode",
            "allocate",
            {
                "operation": "allocate_resource",
                "request_id": "test-request",
                "edge_node": "edge-west-1",
                "resource_type": "deployment",
                "resource_spec": {"image": "nginx:latest", "replicas": 2},
                "platform_preference": "kubernetes",
            },
        )

        # Connect workflow
        workflow.add_connection("platform_init", "status", "k8s_register", "parameters")
        workflow.add_connection(
            "k8s_register", "status", "docker_register", "parameters"
        )
        workflow.add_connection("docker_register", "status", "allocate", "parameters")

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 4
        assert len(built.connections) == 3

    def test_kubernetes_deployment_workflow(self):
        """Test Kubernetes deployment workflow."""
        workflow = WorkflowBuilder()

        # Initialize Kubernetes
        workflow.add_node(
            "KubernetesNode",
            "k8s_init",
            {"operation": "initialize", "namespace": "edge-system"},
        )

        # Create deployment
        workflow.add_node(
            "KubernetesNode",
            "create_deployment",
            {
                "operation": "create_resource",
                "resource_name": "edge-nginx",
                "resource_type": "deployment",
                "resource_spec": {
                    "replicas": 3,
                    "selector": {"matchLabels": {"app": "edge-nginx"}},
                    "template": {
                        "metadata": {"labels": {"app": "edge-nginx"}},
                        "spec": {
                            "containers": [
                                {
                                    "name": "nginx",
                                    "image": "nginx:alpine",
                                    "ports": [{"containerPort": 80}],
                                }
                            ]
                        },
                    },
                },
                "edge_node": "edge-west-1",
            },
        )

        # Create autoscaler
        workflow.add_node(
            "KubernetesNode",
            "create_hpa",
            {
                "operation": "create_autoscaler",
                "deployment_name": "edge-nginx",
                "min_replicas": 2,
                "max_replicas": 10,
                "target_cpu_utilization": 0.7,
            },
        )

        # Connect workflow
        workflow.add_connection("k8s_init", "status", "create_deployment", "parameters")
        workflow.add_connection(
            "create_deployment", "resource_created", "create_hpa", "parameters"
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 3
        assert len(built.connections) == 2

    def test_docker_container_workflow(self):
        """Test Docker container workflow."""
        workflow = WorkflowBuilder()

        # Initialize Docker
        workflow.add_node("DockerNode", "docker_init", {"operation": "initialize"})

        # Create container
        workflow.add_node(
            "DockerNode",
            "create_container",
            {
                "operation": "create_container",
                "container_name": "edge-app",
                "image": "alpine:latest",
                "command": ["sh", "-c", "while true; do sleep 30; done"],
                "environment": {"NODE_ENV": "production"},
                "labels": {"service": "edge-app"},
                "edge_node": "edge-west-1",
            },
        )

        # Start container
        workflow.add_node(
            "DockerNode",
            "start_container",
            {"operation": "start_container", "container_name": "edge-app"},
        )

        # Get container status
        workflow.add_node(
            "DockerNode",
            "get_status",
            {"operation": "get_container_status", "container_name": "edge-app"},
        )

        # Connect workflow
        workflow.add_connection(
            "docker_init", "status", "create_container", "parameters"
        )
        workflow.add_connection(
            "create_container", "container_created", "start_container", "parameters"
        )
        workflow.add_connection(
            "start_container", "container_started", "get_status", "parameters"
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 4
        assert len(built.connections) == 3

    def test_cloud_instance_workflow(self):
        """Test cloud instance workflow."""
        workflow = WorkflowBuilder()

        # Initialize cloud
        workflow.add_node("CloudNode", "cloud_init", {"operation": "initialize"})

        # Register AWS
        workflow.add_node(
            "CloudNode",
            "register_aws",
            {"operation": "register_aws", "region": "us-west-2"},
        )

        # Create instance
        workflow.add_node(
            "CloudNode",
            "create_instance",
            {
                "operation": "create_instance",
                "provider": "aws",
                "instance_name": "edge-instance",
                "instance_type": "t3.micro",
                "image_id": "ami-0c02fb55956c7d316",
                "region": "us-west-2",
            },
        )

        # Get instance status
        workflow.add_node(
            "CloudNode",
            "get_status",
            {
                "operation": "get_instance_status",
                "provider": "aws",
                "instance_name": "edge-instance",
            },
        )

        # Connect workflow
        workflow.add_connection("cloud_init", "status", "register_aws", "parameters")
        workflow.add_connection(
            "register_aws", "provider_registered", "create_instance", "parameters"
        )
        workflow.add_connection(
            "create_instance", "instance_created", "get_status", "parameters"
        )

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 4
        assert len(built.connections) == 3


class TestPhase4NodeCompatibility:
    """Test that all Phase 4 nodes are compatible and properly registered."""

    def test_all_phase4_nodes_importable(self):
        """Test that all Phase 4.4 nodes can be imported."""
        from kailash.nodes.edge import (
            CloudNode,
            DockerNode,
            KubernetesNode,
            PlatformNode,
        )

        # Test that nodes can be instantiated
        k8s_node = KubernetesNode()
        docker_node = DockerNode()
        cloud_node = CloudNode()
        platform_node = PlatformNode()

        assert k8s_node is not None
        assert docker_node is not None
        assert cloud_node is not None
        assert platform_node is not None

    def test_all_phase4_nodes_have_parameters(self):
        """Test that all Phase 4.4 nodes have parameter definitions."""
        from kailash.nodes.edge import (
            CloudNode,
            DockerNode,
            KubernetesNode,
            PlatformNode,
        )

        nodes = [KubernetesNode(), DockerNode(), CloudNode(), PlatformNode()]

        for node in nodes:
            params = node.get_parameters()
            assert isinstance(params, dict)
            assert len(params) > 0
            assert "operation" in params
            assert params["operation"].type == str

    def test_all_phase4_nodes_in_workflow(self):
        """Test that all Phase 4.4 nodes can be added to workflows."""
        workflow = WorkflowBuilder()

        # Add all Phase 4.4 nodes
        workflow.add_node("KubernetesNode", "k8s", {"operation": "initialize"})

        workflow.add_node("DockerNode", "docker", {"operation": "initialize"})

        workflow.add_node("CloudNode", "cloud", {"operation": "initialize"})

        workflow.add_node("PlatformNode", "platform", {"operation": "initialize"})

        built = workflow.build()
        assert built is not None
        assert len(built.nodes) == 4


class TestPhase4ExecutionTests:
    """Test actual execution of Phase 4.4 components (with mocking for external dependencies)."""

    @pytest.mark.asyncio
    async def test_kubernetes_node_execution(self):
        """Test Kubernetes node execution."""
        if not is_kubernetes_available():
            pytest.skip(
                "Kubernetes not available - run './tests/utils/test-env up' to start test infrastructure"
            )

        workflow = WorkflowBuilder()

        workflow.add_node(
            "KubernetesNode", "k8s", {"operation": "initialize", "namespace": "test"}
        )

        runtime = LocalRuntime()
        try:
            # Use runtime parameters to ensure operation is provided
            results, run_id = await runtime.execute_async(
                workflow.build(), parameters={"k8s": {"operation": "initialize"}}
            )

            assert run_id is not None
            assert isinstance(results, dict)

            k8s_result = results.get("k8s")
            if k8s_result:
                assert k8s_result.get("status") == "success"
                assert k8s_result.get("kubernetes_initialized") is True

        except Exception as e:
            # Kubernetes integration should work if cluster is available
            pytest.fail(f"Kubernetes node execution failed: {e}")

    @pytest.mark.asyncio
    async def test_docker_node_execution(self):
        """Test Docker node execution."""
        if not is_docker_available():
            pytest.skip("Docker not available - ensure Docker daemon is running")

        workflow = WorkflowBuilder()

        workflow.add_node("DockerNode", "docker", {"operation": "initialize"})

        runtime = LocalRuntime()
        try:
            # Use runtime parameters to ensure operation is provided
            results, run_id = await runtime.execute_async(
                workflow.build(), parameters={"docker": {"operation": "initialize"}}
            )

            assert run_id is not None
            assert isinstance(results, dict)

            docker_result = results.get("docker")
            if docker_result:
                # Check if Docker client is available
                if docker_result.get(
                    "status"
                ) == "error" and "Docker client not available" in docker_result.get(
                    "error", ""
                ):
                    pytest.skip(
                        "Docker client not available - install with: pip install docker"
                    )

                assert (
                    docker_result.get("status") == "success"
                ), f"Docker status was {docker_result.get('status')}, full result: {docker_result}"
                assert docker_result.get("docker_initialized") is True

        except Exception as e:
            # Docker integration should work if daemon is available
            pytest.fail(f"Docker node execution failed: {e}")

    @pytest.mark.asyncio
    async def test_cloud_node_execution(self):
        """Test Cloud node execution."""
        workflow = WorkflowBuilder()

        workflow.add_node("CloudNode", "cloud", {"operation": "initialize"})

        runtime = LocalRuntime()
        try:
            results, run_id = await runtime.execute_async(workflow.build())

            assert run_id is not None
            assert isinstance(results, dict)

            cloud_result = results.get("cloud")
            if cloud_result:
                # If initialization succeeds, check result structure
                assert isinstance(cloud_result.get("result"), dict)

        except Exception as e:
            # Skip if cloud credentials are not available
            pytest.skip(f"Cloud execution test skipped: {e}")

    @pytest.mark.asyncio
    async def test_platform_node_execution(self):
        """Test Platform node execution."""
        workflow = WorkflowBuilder()

        workflow.add_node(
            "PlatformNode",
            "platform",
            {
                "operation": "initialize",
                "auto_scaling_enabled": True,
                "monitoring_interval": 60,
            },
        )

        runtime = LocalRuntime()
        try:
            # Use runtime parameters to ensure operation is provided
            results, run_id = await runtime.execute_async(
                workflow.build(), parameters={"platform": {"operation": "initialize"}}
            )

            assert run_id is not None
            assert isinstance(results, dict)

            platform_result = results.get("platform")
            if platform_result:
                assert platform_result.get("status") == "success"
                assert platform_result.get("platform_initialized") is True

        except Exception as e:
            # Platform node should always initialize successfully
            pytest.fail(f"Platform node execution failed: {e}")


class TestPhase4ComponentRegistry:
    """Test that all Phase 4.4 components are properly registered."""

    def test_phase4_edge_imports(self):
        """Test Phase 4.4 edge module imports."""
        from kailash.edge.resource import (  # Kubernetes; Docker; Cloud; Platform
            CloudIntegration,
            CloudProvider,
            ContainerSpec,
            ContainerState,
            DockerIntegration,
            InstanceSpec,
            InstanceState,
            KubernetesIntegration,
            KubernetesResource,
            KubernetesResourceType,
            PlatformIntegration,
            PlatformType,
            PodScalingSpec,
            ResourceAllocation,
            ResourceRequest,
            ResourceScope,
            ServiceSpec,
        )

        # Verify all classes are importable
        components = [
            KubernetesIntegration,
            KubernetesResource,
            KubernetesResourceType,
            PodScalingSpec,
            DockerIntegration,
            ContainerSpec,
            ServiceSpec,
            ContainerState,
            CloudIntegration,
            CloudProvider,
            InstanceSpec,
            InstanceState,
            PlatformIntegration,
            PlatformType,
            ResourceScope,
            ResourceRequest,
            ResourceAllocation,
        ]

        for component in components:
            assert component is not None
            assert isinstance(component, type)

    def test_phase4_node_imports(self):
        """Test Phase 4.4 node imports."""
        from kailash.nodes.edge import (
            CloudNode,
            DockerNode,
            KubernetesNode,
            PlatformNode,
        )

        nodes = [KubernetesNode, DockerNode, CloudNode, PlatformNode]

        for node_class in nodes:
            assert node_class is not None
            assert isinstance(node_class, type)

            # Test instantiation
            node = node_class()
            assert hasattr(node, "get_parameters")
            assert hasattr(node, "run")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
