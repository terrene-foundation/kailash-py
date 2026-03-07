"""Unit tests for Azure cloud integration."""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from kailash.edge.resource.cloud_integration import (
    AZURE_AVAILABLE,
    AzureIntegration,
    CloudInstance,
    CloudIntegration,
    CloudMetrics,
    CloudProvider,
    InstanceSpec,
    InstanceState,
)

# ---------------------------------------------------------------------------
# Helpers – fake Azure SDK objects returned by mocked clients
# ---------------------------------------------------------------------------


def _make_vm(
    name="test-vm",
    vm_id="vm-abc123",
    vm_size="Standard_B1s",
    location="eastus",
    provisioning_state="Succeeded",
    power_state="running",
    tags=None,
):
    """Build a fake VM object that mimics azure.mgmt.compute models."""
    status_obj = SimpleNamespace(
        code=f"PowerState/{power_state}", display_status="VM running"
    )
    instance_view = SimpleNamespace(
        statuses=[
            SimpleNamespace(code="ProvisioningState/succeeded", display_status=""),
            status_obj,
        ]
    )
    hardware = SimpleNamespace(vm_size=vm_size)
    nic_ref = SimpleNamespace(
        id="/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/networkInterfaces/nic1"
    )
    network = SimpleNamespace(network_interfaces=[nic_ref])
    return SimpleNamespace(
        name=name,
        vm_id=vm_id,
        hardware_profile=hardware,
        location=location,
        provisioning_state=provisioning_state,
        instance_view=instance_view,
        network_profile=network,
        tags=tags or {},
    )


def _make_poller(result_value):
    """Build a fake Azure long-running operation poller."""
    poller = MagicMock()
    poller.result.return_value = result_value
    return poller


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_azure_clients():
    """Patch Azure credential and management clients.

    Uses create=True so the attributes are created even when the Azure SDK
    packages are not installed (the conditional import sets AZURE_AVAILABLE=False
    and skips defining the names in the module namespace).
    """
    with (
        patch("kailash.edge.resource.cloud_integration.AZURE_AVAILABLE", True),
        patch(
            "kailash.edge.resource.cloud_integration.DefaultAzureCredential",
            create=True,
        ) as mock_cred,
        patch(
            "kailash.edge.resource.cloud_integration.ComputeManagementClient",
            create=True,
        ) as mock_compute_cls,
        patch(
            "kailash.edge.resource.cloud_integration.ResourceManagementClient",
            create=True,
        ) as mock_resource_cls,
    ):
        mock_compute = MagicMock()
        mock_resource = MagicMock()
        mock_compute_cls.return_value = mock_compute
        mock_resource_cls.return_value = mock_resource
        yield {
            "credential": mock_cred,
            "compute_client": mock_compute,
            "resource_client": mock_resource,
        }


@pytest.fixture
def azure(mock_azure_clients):
    """Create an AzureIntegration instance with mocked clients."""
    integration = AzureIntegration(
        subscription_id="test-sub-id",
        resource_group="test-rg",
        location="eastus",
    )
    return integration


@pytest.fixture
def instance_spec():
    """Standard InstanceSpec for Azure tests."""
    return InstanceSpec(
        name="test-vm",
        provider=CloudProvider.AZURE,
        instance_type="Standard_B1s",
        image_id="/subscriptions/sub/providers/Microsoft.Compute/images/my-image",
        region="eastus",
        tags={"env": "test"},
    )


# ---------------------------------------------------------------------------
# AzureIntegration class tests
# ---------------------------------------------------------------------------


class TestAzureIntegrationInit:
    """Test AzureIntegration initialization."""

    def test_init_creates_clients(self, mock_azure_clients):
        """Verify credential and clients are created during init."""
        integration = AzureIntegration("sub-123", "rg-test", "westus")
        assert integration.subscription_id == "sub-123"
        assert integration.resource_group == "rg-test"
        assert integration.location == "westus"
        mock_azure_clients["credential"].assert_called_once()

    def test_init_raises_when_sdk_missing(self):
        """Verify ImportError when Azure SDK is not installed."""
        with patch("kailash.edge.resource.cloud_integration.AZURE_AVAILABLE", False):
            with pytest.raises(ImportError, match="Azure SDK not available"):
                AzureIntegration("sub", "rg")

    def test_instance_type_map(self):
        """Verify common instance types are mapped to Azure VM sizes."""
        assert AzureIntegration.INSTANCE_TYPE_MAP["micro"] == "Standard_B1s"
        assert AzureIntegration.INSTANCE_TYPE_MAP["large"] == "Standard_D2s_v3"


class TestAzureCreateInstance:
    """Test AzureIntegration.create_instance."""

    @pytest.mark.asyncio
    async def test_create_instance_success(
        self, azure, mock_azure_clients, instance_spec
    ):
        """Verify successful VM creation returns expected result."""
        vm = _make_vm(name="test-vm", vm_id="vm-new-123")
        poller = _make_poller(vm)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.return_value = poller

        result = await azure.create_instance(instance_spec)

        assert result["status"] == "created"
        assert result["instance_id"] == "vm-new-123"
        assert result["instance_name"] == "test-vm"
        assert result["instance_type"] == "Standard_B1s"

    @pytest.mark.asyncio
    async def test_create_instance_with_user_data(
        self, azure, mock_azure_clients, instance_spec
    ):
        """Verify user_data is base64-encoded as custom_data."""
        instance_spec.user_data = "#!/bin/bash\necho hello"
        vm = _make_vm()
        poller = _make_poller(vm)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.return_value = poller

        result = await azure.create_instance(instance_spec)

        assert result["status"] == "created"
        call_args = mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.call_args
        vm_params = call_args[0][2]  # third positional arg is vm_parameters
        assert "custom_data" in vm_params["os_profile"]

    @pytest.mark.asyncio
    async def test_create_instance_with_edge_node(
        self, azure, mock_azure_clients, instance_spec
    ):
        """Verify edge_node is added as a tag."""
        instance_spec.edge_node = "edge-01"
        vm = _make_vm()
        poller = _make_poller(vm)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.return_value = poller

        result = await azure.create_instance(instance_spec)

        assert result["status"] == "created"
        call_args = mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.call_args
        vm_params = call_args[0][2]
        assert vm_params["tags"]["edge-node"] == "edge-01"

    @pytest.mark.asyncio
    async def test_create_instance_error(
        self, azure, mock_azure_clients, instance_spec
    ):
        """Verify error is returned when creation fails."""
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.side_effect = Exception(
            "quota exceeded"
        )

        result = await azure.create_instance(instance_spec)

        assert result["status"] == "error"
        assert "quota exceeded" in result["error"]


class TestAzureGetInstanceStatus:
    """Test AzureIntegration.get_instance_status."""

    @pytest.mark.asyncio
    async def test_get_status_running(self, azure, mock_azure_clients):
        """Verify status for a running VM."""
        vm = _make_vm(power_state="running")
        mock_azure_clients["compute_client"].virtual_machines.get.return_value = vm
        # Mock the resource client for NIC lookup
        mock_azure_clients["resource_client"].resources.get_by_id.side_effect = (
            Exception("skip")
        )

        result = await azure.get_instance_status("test-vm")

        assert result["state"] == "running"
        assert result["instance_name"] == "test-vm"
        assert result["instance_type"] == "Standard_B1s"

    @pytest.mark.asyncio
    async def test_get_status_deallocated(self, azure, mock_azure_clients):
        """Verify status for a deallocated VM."""
        vm = _make_vm(power_state="deallocated")
        mock_azure_clients["compute_client"].virtual_machines.get.return_value = vm
        mock_azure_clients["resource_client"].resources.get_by_id.side_effect = (
            Exception("skip")
        )

        result = await azure.get_instance_status("test-vm")

        assert result["state"] == "deallocated"

    @pytest.mark.asyncio
    async def test_get_status_error(self, azure, mock_azure_clients):
        """Verify error dict on failure."""
        mock_azure_clients["compute_client"].virtual_machines.get.side_effect = (
            Exception("not found")
        )

        result = await azure.get_instance_status("nonexistent-vm")

        assert result["status"] == "error"
        assert "not found" in result["error"]


class TestAzureTerminateInstance:
    """Test AzureIntegration.terminate_instance."""

    @pytest.mark.asyncio
    async def test_terminate_success(self, azure, mock_azure_clients):
        """Verify deallocate + delete sequence."""
        dealloc_poller = _make_poller(None)
        delete_poller = _make_poller(None)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_deallocate.return_value = dealloc_poller
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_delete.return_value = delete_poller

        result = await azure.terminate_instance("test-vm")

        assert result["status"] == "terminated"
        assert result["instance_name"] == "test-vm"
        assert result["resource_group"] == "test-rg"
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_deallocate.assert_called_once()
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_terminate_error(self, azure, mock_azure_clients):
        """Verify error on terminate failure."""
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_deallocate.side_effect = Exception("access denied")

        result = await azure.terminate_instance("test-vm")

        assert result["status"] == "error"
        assert "access denied" in result["error"]


class TestAzureListInstances:
    """Test AzureIntegration.list_instances."""

    @pytest.mark.asyncio
    async def test_list_instances_no_filter(self, azure, mock_azure_clients):
        """Verify listing all VMs in the resource group."""
        vm1 = _make_vm(name="vm-1", vm_id="id-1", tags={"env": "prod"})
        vm2 = _make_vm(name="vm-2", vm_id="id-2", tags={"env": "staging"})
        mock_azure_clients["compute_client"].virtual_machines.list.return_value = [
            vm1,
            vm2,
        ]

        instances = await azure.list_instances()

        assert len(instances) == 2
        assert instances[0]["instance_name"] == "vm-1"
        assert instances[1]["instance_name"] == "vm-2"

    @pytest.mark.asyncio
    async def test_list_instances_with_tag_filter(self, azure, mock_azure_clients):
        """Verify tag-based filtering."""
        vm1 = _make_vm(name="vm-1", vm_id="id-1", tags={"env": "prod"})
        vm2 = _make_vm(name="vm-2", vm_id="id-2", tags={"env": "staging"})
        mock_azure_clients["compute_client"].virtual_machines.list.return_value = [
            vm1,
            vm2,
        ]

        instances = await azure.list_instances(filters={"env": ["prod"]})

        assert len(instances) == 1
        assert instances[0]["instance_name"] == "vm-1"

    @pytest.mark.asyncio
    async def test_list_instances_error(self, azure, mock_azure_clients):
        """Verify RuntimeError on API failure."""
        mock_azure_clients["compute_client"].virtual_machines.list.side_effect = (
            Exception("unauthorized")
        )

        with pytest.raises(RuntimeError, match="Failed to list Azure VMs"):
            await azure.list_instances()


class TestAzureGetMetrics:
    """Test AzureIntegration.get_instance_metrics."""

    @pytest.mark.asyncio
    async def test_get_metrics_returns_cloud_metrics(self, azure, mock_azure_clients):
        """Verify metrics are returned as CloudMetrics objects."""
        vm = _make_vm(power_state="running")
        mock_azure_clients["compute_client"].virtual_machines.get.return_value = vm

        now = datetime.now()
        metrics = await azure.get_instance_metrics(
            "test-vm", now - timedelta(hours=1), now
        )

        assert len(metrics) == 1
        assert isinstance(metrics[0], CloudMetrics)
        assert metrics[0].provider == CloudProvider.AZURE

    @pytest.mark.asyncio
    async def test_get_metrics_error(self, azure, mock_azure_clients):
        """Verify RuntimeError on metrics failure."""
        mock_azure_clients["compute_client"].virtual_machines.get.side_effect = (
            Exception("VM not found")
        )

        now = datetime.now()
        with pytest.raises(RuntimeError, match="Failed to get Azure VM metrics"):
            await azure.get_instance_metrics("bad-vm", now - timedelta(hours=1), now)


# ---------------------------------------------------------------------------
# CloudIntegration manager tests (Azure wiring)
# ---------------------------------------------------------------------------


class TestCloudIntegrationAzureWiring:
    """Test that Azure is properly wired into the CloudIntegration manager."""

    @pytest.fixture
    def manager_with_azure(self, mock_azure_clients):
        """Create a CloudIntegration manager with Azure registered."""
        mgr = CloudIntegration()
        mgr.register_azure("sub-123", "rg-test", "eastus")
        return mgr

    def test_register_azure(self, manager_with_azure):
        """Verify Azure integration is stored in the integrations dict."""
        assert CloudProvider.AZURE in manager_with_azure.integrations
        azure_int = manager_with_azure.integrations[CloudProvider.AZURE]
        assert isinstance(azure_int, AzureIntegration)
        assert azure_int.subscription_id == "sub-123"

    def test_register_azure_without_sdk(self):
        """Verify RuntimeError when Azure SDK is missing."""
        with patch("kailash.edge.resource.cloud_integration.AZURE_AVAILABLE", False):
            mgr = CloudIntegration()
            with pytest.raises(RuntimeError, match="Failed to register Azure"):
                mgr.register_azure("sub", "rg")

    @pytest.mark.asyncio
    async def test_create_instance_via_manager(
        self, manager_with_azure, mock_azure_clients, instance_spec
    ):
        """Verify instance creation goes through the manager to Azure."""
        vm = _make_vm(name="test-vm", vm_id="vm-mgr-1")
        poller = _make_poller(vm)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_create_or_update.return_value = poller

        result = await manager_with_azure.create_instance(instance_spec)

        assert result["status"] == "created"
        assert result["instance_id"] == "vm-mgr-1"

    @pytest.mark.asyncio
    async def test_get_status_via_manager(self, manager_with_azure, mock_azure_clients):
        """Verify status check goes through the manager to Azure."""
        vm = _make_vm(power_state="running")
        mock_azure_clients["compute_client"].virtual_machines.get.return_value = vm
        mock_azure_clients["resource_client"].resources.get_by_id.side_effect = (
            Exception("skip")
        )

        result = await manager_with_azure.get_instance_status(
            CloudProvider.AZURE, "test-vm"
        )

        assert result["state"] == "running"

    @pytest.mark.asyncio
    async def test_terminate_via_manager(self, manager_with_azure, mock_azure_clients):
        """Verify terminate goes through the manager to Azure."""
        dealloc_poller = _make_poller(None)
        delete_poller = _make_poller(None)
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_deallocate.return_value = dealloc_poller
        mock_azure_clients[
            "compute_client"
        ].virtual_machines.begin_delete.return_value = delete_poller

        result = await manager_with_azure.terminate_instance(
            CloudProvider.AZURE, "test-vm"
        )

        assert result["status"] == "terminated"

    @pytest.mark.asyncio
    async def test_list_instances_via_manager(
        self, manager_with_azure, mock_azure_clients
    ):
        """Verify list goes through the manager to Azure."""
        vm = _make_vm(name="vm-1", vm_id="id-1")
        mock_azure_clients["compute_client"].virtual_machines.list.return_value = [vm]

        instances = await manager_with_azure.list_instances(CloudProvider.AZURE)

        assert len(instances) == 1
        assert instances[0]["instance_name"] == "vm-1"

    @pytest.mark.asyncio
    async def test_get_metrics_via_manager(
        self, manager_with_azure, mock_azure_clients
    ):
        """Verify metrics go through the manager to Azure."""
        vm = _make_vm(power_state="running")
        mock_azure_clients["compute_client"].virtual_machines.get.return_value = vm

        now = datetime.now()
        metrics = await manager_with_azure.get_instance_metrics(
            CloudProvider.AZURE, "test-vm", now - timedelta(hours=1), now
        )

        assert len(metrics) == 1
        assert metrics[0].provider == CloudProvider.AZURE

    @pytest.mark.asyncio
    async def test_get_provider_info_azure(self, manager_with_azure):
        """Verify provider info returns Azure details."""
        info = await manager_with_azure.get_provider_info(CloudProvider.AZURE)

        assert info["provider"] == "azure"
        assert info["registered"] is True
        assert "create_instance" in info["features"]
        assert "list_instances" in info["features"]
        assert info["subscription_id"] == "sub-123"
        assert info["resource_group"] == "rg-test"
        assert info["location"] == "eastus"

    @pytest.mark.asyncio
    async def test_supported_providers_includes_azure(self, manager_with_azure):
        """Verify Azure appears in supported providers list."""
        providers = await manager_with_azure.get_supported_providers()
        assert "azure" in providers
