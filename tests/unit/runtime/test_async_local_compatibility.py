#!/usr/bin/env python3
"""
Test AsyncLocalRuntime Compatibility Wrapper

This test specifically validates that the AsyncLocalRuntime wrapper
maintains backward compatibility for existing code that imports and
uses AsyncLocalRuntime.
"""
import pytest
import asyncio
from kailash.runtime.local import LocalRuntime
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow import Workflow
from kailash.nodes.code.python import PythonCodeNode


class TestAsyncLocalRuntimeCompatibility:
    """Test AsyncLocalRuntime compatibility wrapper."""
    
    def test_import_compatibility(self):
        """Test that LocalRuntime supports async operations."""
        # LocalRuntime now includes async capabilities
        runtime = LocalRuntime(enable_async=True)
        assert runtime.enable_async is True
        
    def test_instance_creation(self):
        """Test creating LocalRuntime instances with async enabled."""
        # Basic instantiation with async
        runtime = LocalRuntime(enable_async=True)
        assert isinstance(runtime, LocalRuntime)
        assert runtime.enable_async is True
        
        # With parameters
        runtime_debug = LocalRuntime(debug=True, max_concurrency=5, enable_async=True)
        assert runtime_debug.debug is True
        assert runtime_debug.max_concurrency == 5
        assert runtime_debug.enable_async is True
        
    @pytest.mark.asyncio
    async def test_backward_compatible_execution(self):
        """Test that LocalRuntime with async enabled executes workflows correctly."""
        # Create simple workflow
        workflow = Workflow(workflow_id="test", name="Test")
        
        def processor():
            return {"result": {"status": "success", "data": [1, 2, 3]}}
        
        node = PythonCodeNode.from_function(func=processor, name="processor")
        workflow.add_node("processor", node)
        
        # Execute with LocalRuntime async enabled (current pattern)
        runtime = LocalRuntime(enable_async=True)
        results, run_id = await runtime.execute_async(workflow)
        
        assert results["processor"]["result"]["result"]["status"] == "success"
        assert results["processor"]["result"]["result"]["data"] == [1, 2, 3]
        assert run_id is not None
        
    @pytest.mark.asyncio
    async def test_async_execution_methods(self):
        """Test that async execution methods work correctly."""
        workflow = Workflow(workflow_id="test", name="Test")
        
        def async_processor():
            return {"result": "async processed"}
        
        node = PythonCodeNode.from_function(func=async_processor, name="proc")
        workflow.add_node("proc", node)
        
        runtime = LocalRuntime(debug=True, enable_async=True)
        
        # Test execute method (async)
        results1, run_id1 = await runtime.execute_async(workflow)
        assert results1["proc"]["result"]["result"] == "async processed"
        
        # Test execute_async method
        results2, run_id2 = await runtime.execute_async(workflow)
        assert results2["proc"]["result"]["result"] == "async processed"
        
    def test_compatibility_wrapper_attributes(self):
        """Test that all LocalRuntime attributes are accessible."""
        runtime = AsyncLocalRuntime(
            debug=True,
            max_concurrency=20,
            enable_monitoring=True,
            enable_audit=False
        )
        
        # Check all attributes
        assert runtime.debug is True
        assert runtime.enable_async is True  # Always true for AsyncLocalRuntime
        assert runtime.max_concurrency == 20
        assert runtime.enable_monitoring is True
        assert runtime.enable_audit is False
        assert runtime.enable_cycles is True  # Default
        
    def test_alias_behavior(self):
        """Test that AsyncLocalRuntime behaves as an alias."""
        # Both should create similar instances
        async_runtime = AsyncLocalRuntime()
        local_runtime = LocalRuntime(enable_async=True)
        
        # Should have same capabilities
        assert type(async_runtime).__bases__[0] == type(local_runtime)
        assert async_runtime.enable_async == local_runtime.enable_async
        
    @pytest.mark.asyncio 
    async def test_enterprise_features_available(self):
        """Test that enterprise features work with AsyncLocalRuntime."""
        from kailash.access_control import UserContext
        
        user_context = UserContext(
            user_id="test_user",
            tenant_id="test_tenant",
            email="test@example.com",
            roles=["viewer"]
        )
        
        # Should be able to use enterprise features
        runtime = AsyncLocalRuntime(
            enable_monitoring=True,
            enable_audit=True,
            user_context=user_context
        )
        
        assert runtime.enable_monitoring is True
        assert runtime.enable_audit is True
        assert runtime.user_context == user_context
        
        # Create workflow
        workflow = Workflow(workflow_id="enterprise_test", name="Enterprise Test")
        
        def enterprise_processor():
            return {"result": {"enterprise": True}}
        
        node = PythonCodeNode.from_function(func=enterprise_processor, name="ep")
        workflow.add_node("ep", node)
        
        # Should execute with enterprise features
        results, run_id = await runtime.execute(workflow)
        assert results["ep"]["result"]["result"]["enterprise"] is True