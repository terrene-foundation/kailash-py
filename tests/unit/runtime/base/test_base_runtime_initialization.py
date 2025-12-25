"""Unit tests for BaseRuntime initialization.

Tests BaseRuntime.__init__() configuration validation and attribute initialization.
"""

import pytest
from kailash.runtime.base import BaseRuntime
from kailash.sdk_exceptions import RuntimeExecutionError
from kailash.workflow import Workflow


class ConcreteRuntime(BaseRuntime):
    """Concrete implementation for testing abstract base."""

    def execute(self, workflow: Workflow, **kwargs):
        """Minimal execute implementation."""
        return {}, "test-run-id"


class TestBaseRuntimeInitialization:
    """Test BaseRuntime initialization and configuration."""

    def test_default_initialization(self):
        """Test initialization with all default parameters."""
        runtime = ConcreteRuntime()

        # Core configuration defaults
        assert runtime.debug is False
        assert runtime.enable_cycles is True
        assert runtime.enable_async is True
        assert runtime.max_concurrency == 10
        assert runtime.user_context is None
        assert runtime.secret_provider is None
        assert runtime.enable_monitoring is True
        assert runtime.enable_security is False
        assert runtime.enable_audit is False
        assert runtime.resource_limits == {}
        assert runtime.connection_validation == "warn"
        assert runtime.conditional_execution == "route_data"
        assert runtime.content_aware_success_detection is True

        # Persistent mode defaults
        assert runtime._persistent_mode is False
        assert runtime._enable_connection_sharing is True
        assert runtime._max_concurrent_workflows == 10
        assert runtime._connection_pool_size == 20

        # Enterprise configuration defaults
        assert runtime._enable_enterprise_monitoring is False
        assert runtime._enable_health_monitoring is False
        assert runtime._enable_resource_coordination is True
        assert runtime._circuit_breaker_config == {}
        assert runtime._retry_policy_config == {}
        assert runtime._connection_pool_config == {}

        # State management initialization
        assert len(runtime._workflow_cache) == 0
        assert len(runtime._execution_metadata) == 0
        assert runtime._is_persistent_started is False
        assert runtime._runtime_id is not None
        assert "runtime_" in runtime._runtime_id

    def test_debug_mode_initialization(self):
        """Test initialization with debug mode enabled."""
        runtime = ConcreteRuntime(debug=True)

        assert runtime.debug is True
        # Logger should be configured for debug
        assert runtime.logger is not None

    def test_cycle_configuration(self):
        """Test cycle configuration parameters."""
        runtime = ConcreteRuntime(enable_cycles=False)

        # Note: BaseRuntime doesn't store max_cycle_iterations and
        # cycle_convergence_threshold (those are in LocalRuntime)
        # But enable_cycles initialization should succeed
        assert runtime.enable_cycles is False

    def test_async_configuration(self):
        """Test async execution configuration."""
        runtime = ConcreteRuntime(enable_async=False, max_concurrency=20)

        assert runtime.enable_async is False
        assert runtime.max_concurrency == 20

    def test_enterprise_configuration(self):
        """Test enterprise feature configuration."""
        circuit_breaker_config = {
            "failure_threshold": 5,
            "timeout": 60,
            "half_open_timeout": 30,
        }
        retry_policy_config = {"max_retries": 3, "backoff_factor": 2.0}

        runtime = ConcreteRuntime(
            enable_enterprise_monitoring=True,
            enable_health_monitoring=True,
            enable_resource_coordination=False,
            circuit_breaker_config=circuit_breaker_config,
            retry_policy_config=retry_policy_config,
        )

        assert runtime._enable_enterprise_monitoring is True
        assert runtime._enable_health_monitoring is True
        assert runtime._enable_resource_coordination is False
        assert runtime._circuit_breaker_config == circuit_breaker_config
        assert runtime._retry_policy_config == retry_policy_config

    def test_persistent_mode_configuration(self):
        """Test persistent mode configuration."""
        runtime = ConcreteRuntime(
            persistent_mode=True,
            enable_connection_sharing=False,
            max_concurrent_workflows=50,
            connection_pool_size=100,
        )

        assert runtime._persistent_mode is True
        assert runtime._enable_connection_sharing is False
        assert runtime._max_concurrent_workflows == 50
        assert runtime._connection_pool_size == 100
        assert runtime._is_persistent_started is False
        assert runtime._persistent_event_loop is None
        assert isinstance(runtime._active_workflows, dict)

    def test_security_and_audit_configuration(self):
        """Test security and audit configuration."""
        user_context = {"user_id": "test_user", "role": "admin"}

        runtime = ConcreteRuntime(
            enable_security=True, enable_audit=True, user_context=user_context
        )

        assert runtime.enable_security is True
        assert runtime.enable_audit is True
        assert runtime.user_context == user_context

    def test_resource_limits_configuration(self):
        """Test resource limits configuration."""
        resource_limits = {
            "max_memory_mb": 1024,
            "max_cpu_percent": 80,
            "max_connections": 50,
        }

        runtime = ConcreteRuntime(resource_limits=resource_limits)

        assert runtime.resource_limits == resource_limits
        assert runtime._resource_limits == resource_limits  # Alias

    def test_connection_validation_modes(self):
        """Test connection_validation parameter validation."""
        # Valid modes
        runtime_off = ConcreteRuntime(connection_validation="off")
        assert runtime_off.connection_validation == "off"

        runtime_warn = ConcreteRuntime(connection_validation="warn")
        assert runtime_warn.connection_validation == "warn"

        runtime_strict = ConcreteRuntime(connection_validation="strict")
        assert runtime_strict.connection_validation == "strict"

        # Invalid mode
        with pytest.raises(ValueError, match="Invalid connection_validation mode"):
            ConcreteRuntime(connection_validation="invalid_mode")

    def test_conditional_execution_modes(self):
        """Test conditional_execution parameter validation."""
        # Valid modes
        runtime_route = ConcreteRuntime(conditional_execution="route_data")
        assert runtime_route.conditional_execution == "route_data"

        runtime_skip = ConcreteRuntime(conditional_execution="skip_branches")
        assert runtime_skip.conditional_execution == "skip_branches"

        # Invalid mode
        with pytest.raises(ValueError, match="Invalid conditional_execution mode"):
            ConcreteRuntime(conditional_execution="invalid_mode")

    def test_invalid_resource_limits(self):
        """Test validation of invalid resource limits."""
        # Negative values should raise error
        with pytest.raises(
            RuntimeExecutionError, match="Resource limit .* cannot be negative"
        ):
            ConcreteRuntime(resource_limits={"max_memory_mb": -1024})

        with pytest.raises(
            RuntimeExecutionError, match="Resource limit .* cannot be negative"
        ):
            ConcreteRuntime(resource_limits={"max_cpu_percent": -50})

    def test_persistent_mode_negative_values(self):
        """Test persistent mode handles negative values gracefully."""
        # Negative values should be corrected to defaults
        runtime = ConcreteRuntime(max_concurrent_workflows=-1, connection_pool_size=-10)

        # Should be set to reasonable defaults
        assert runtime._max_concurrent_workflows == 10  # Default
        assert runtime._connection_pool_size == 20  # Default

    def test_attribute_initialization_count(self):
        """Test that all 29 expected attributes are initialized."""
        runtime = ConcreteRuntime()

        # Count core runtime attributes (excluding private/dunder)
        expected_attributes = [
            # Core configuration (14)
            "debug",
            "enable_cycles",
            "enable_async",
            "max_concurrency",
            "user_context",
            "secret_provider",
            "enable_monitoring",
            "enable_security",
            "enable_audit",
            "resource_limits",
            "connection_validation",
            "conditional_execution",
            "content_aware_success_detection",
            "logger",
            # Persistent mode (4)
            "_persistent_mode",
            "_enable_connection_sharing",
            "_max_concurrent_workflows",
            "_connection_pool_size",
            # Enterprise (6)
            "_enable_enterprise_monitoring",
            "_enable_health_monitoring",
            "_enable_resource_coordination",
            "_circuit_breaker_config",
            "_retry_policy_config",
            "_connection_pool_config",
            # State management (3)
            "_is_persistent_started",
            "_persistent_event_loop",
            "_active_workflows",
            "_runtime_id",
            # Resource components (9)
            "_resource_coordinator",
            "_pool_coordinator",
            "_resource_monitor",
            "_runtime_monitor",
            "_health_monitor",
            "_metrics_collector",
            "_audit_logger",
            "_resource_enforcer",
            "_lifecycle_manager",
            "_access_control_manager",
            # Runtime state (3)
            "_workflow_cache",
            "_execution_metadata",
            "_resource_limits",
        ]

        # Check that key attributes exist
        for attr in expected_attributes:
            assert hasattr(runtime, attr), f"Missing attribute: {attr}"

    def test_mixin_initialization_with_super(self):
        """Test that super().__init__() is called for MRO chain."""

        # This test verifies the mixin pattern works correctly
        class TestMixin:
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.mixin_initialized = True

        class MixedRuntime(TestMixin, BaseRuntime):
            def execute(self, workflow, **kwargs):
                return {}, "test-run-id"

        runtime = MixedRuntime()

        # Both BaseRuntime and TestMixin should be initialized
        assert hasattr(runtime, "debug")  # BaseRuntime attribute
        assert hasattr(runtime, "mixin_initialized")  # TestMixin attribute
        assert runtime.mixin_initialized is True

    def test_repr_string_representation(self):
        """Test __repr__ string representation."""
        runtime = ConcreteRuntime(debug=True, enable_cycles=False)

        repr_str = repr(runtime)

        assert "ConcreteRuntime" in repr_str
        assert "runtime_" in repr_str  # Contains runtime_id
        assert "debug=True" in repr_str
        assert "cycles=False" in repr_str

    def test_resource_components_lazy_initialization(self):
        """Test that resource components are initialized as None."""
        runtime = ConcreteRuntime()

        # All resource components should start as None (lazy loading)
        assert runtime._resource_coordinator is None
        assert runtime._pool_coordinator is None
        assert runtime._resource_monitor is None
        assert runtime._runtime_monitor is None
        assert runtime._health_monitor is None
        assert runtime._metrics_collector is None
        assert runtime._audit_logger is None
        assert runtime._resource_enforcer is None
        assert runtime._lifecycle_manager is None
        assert runtime._access_control_manager is None


class TestBaseRuntimeConfigurationHelpers:
    """Test BaseRuntime configuration helper methods."""

    def test_should_auto_enable_resources_persistent_mode(self):
        """Test auto-enable resources in persistent mode."""
        runtime = ConcreteRuntime(persistent_mode=True)
        assert runtime._should_auto_enable_resources() is True

    def test_should_auto_enable_resources_enterprise_monitoring(self):
        """Test auto-enable resources with enterprise monitoring."""
        runtime = ConcreteRuntime(enable_enterprise_monitoring=True)
        assert runtime._should_auto_enable_resources() is True

    def test_should_auto_enable_resources_health_monitoring(self):
        """Test auto-enable resources with health monitoring."""
        runtime = ConcreteRuntime(enable_health_monitoring=True)
        assert runtime._should_auto_enable_resources() is True

    def test_should_auto_enable_resources_with_resource_limits(self):
        """Test auto-enable resources when resource limits provided."""
        runtime = ConcreteRuntime(resource_limits={"max_memory_mb": 1024})
        assert runtime._should_auto_enable_resources() is True

    def test_should_auto_enable_resources_disabled(self):
        """Test auto-enable resources returns False when not needed."""
        runtime = ConcreteRuntime(
            persistent_mode=False,
            enable_enterprise_monitoring=False,
            enable_health_monitoring=False,
            resource_limits={},
        )
        assert runtime._should_auto_enable_resources() is False

    def test_get_default_resource_limits(self):
        """Test default resource limits configuration."""
        runtime = ConcreteRuntime()
        defaults = runtime._get_default_resource_limits()

        # Check expected keys and values
        assert defaults["max_memory_mb"] == 2048
        assert defaults["max_connections"] == 100
        assert defaults["max_cpu_percent"] == 80
        assert defaults["enforcement_policy"] == "adaptive"
        assert defaults["degradation_strategy"] == "defer"
        assert defaults["monitoring_interval"] == 1.0
        assert defaults["enable_alerts"] is True
        assert defaults["memory_alert_threshold"] == 0.8
        assert defaults["cpu_alert_threshold"] == 0.7
        assert defaults["connection_alert_threshold"] == 0.9
        assert defaults["enable_metrics_history"] is True

    def test_check_workflow_access_security_disabled(self):
        """Test workflow access check when security is disabled."""
        from tests.unit.runtime.helpers_runtime import create_valid_workflow

        runtime = ConcreteRuntime(enable_security=False)
        workflow = create_valid_workflow()

        # Should not raise any error
        runtime._check_workflow_access(workflow)

    def test_check_workflow_access_no_user_context(self):
        """Test workflow access check without user context."""
        from tests.unit.runtime.helpers_runtime import create_valid_workflow

        runtime = ConcreteRuntime(enable_security=True, user_context=None)
        workflow = create_valid_workflow()

        # Should not raise any error (no user context to check)
        runtime._check_workflow_access(workflow)

    def test_should_skip_audit(self):
        """Test audit skip check."""
        runtime_audit_off = ConcreteRuntime(enable_audit=False)
        assert runtime_audit_off._should_skip_audit() is True

        runtime_audit_on = ConcreteRuntime(enable_audit=True)
        assert runtime_audit_on._should_skip_audit() is False


class TestBaseRuntimeAbstractMethods:
    """Test BaseRuntime abstract method enforcement."""

    def test_cannot_instantiate_base_runtime_directly(self):
        """Test that BaseRuntime cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseRuntime()

    def test_execute_must_be_implemented(self):
        """Test that execute() must be implemented by subclasses."""
        # ConcreteRuntime implements execute(), so it should work
        runtime = ConcreteRuntime()
        workflow = Workflow(workflow_id="test", name="Test")

        results, run_id = runtime.execute(workflow)
        assert results == {}
        assert run_id == "test-run-id"

    def test_execute_signature_flexible(self):
        """Test that execute() signature is flexible for sync/async."""

        class SyncRuntime(BaseRuntime):
            def execute(self, workflow, parameters=None, **kwargs):
                return {"sync": True}, "sync-run-id"

        class AsyncRuntime(BaseRuntime):
            async def execute(self, workflow, parameters=None, **kwargs):
                return {"async": True}, "async-run-id"

        # Both should instantiate successfully
        sync_runtime = SyncRuntime()
        async_runtime = AsyncRuntime()

        assert sync_runtime is not None
        assert async_runtime is not None
