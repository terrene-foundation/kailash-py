# Comprehensive Test Plan: Kailash Nexus Platform

## Executive Summary

This test plan ensures the Nexus platform delivers on its revolutionary promise as a **workflow-native, multi-channel, durable-by-design platform** while maintaining zero-configuration simplicity. The plan follows the 3-tier testing strategy with specific focus on validating the essential capabilities that differentiate Nexus from traditional frameworks.

**Testing Philosophy**: Validate the paradigm shift from request-response to workflow-native architecture while ensuring enterprise-grade reliability and zero-configuration promise.

## 🎯 Testing Objectives

### Primary Objectives
1. **Zero-Configuration Validation**: Ensure true zero-config operation with enterprise features
2. **Revolutionary Capabilities**: Validate durable-first, multi-channel, enterprise-default architecture
3. **Competitive Differentiation**: Prove superiority over Django/Temporal/Serverless approaches
4. **Enterprise Readiness**: Validate production-grade performance and reliability
5. **Developer Experience**: Ensure 1-minute from install to running workflow

### Strategic Validation Points
- **Durability by Design**: Request-level durability vs best-effort execution
- **Multi-Channel Native**: Unified API/CLI/MCP vs separate systems
- **Enterprise-Default**: Production features by default vs bolt-on approach
- **Workflow-Native**: Every operation part of durable workflow vs isolated requests

## 📋 3-Tier Testing Strategy

### Tier 1: Unit Tests (Fast, Isolated, <1s per test)
**Focus**: Component functionality and zero-configuration validation
**Policy**: Can use mocks, no external dependencies, no sleep statements

### Tier 2: Integration Tests (Real Services, Docker)
**Policy**: **NO MOCKING** - must use real Docker services
**Setup**: Always run `./tests/utils/test-env up && ./tests/utils/test-env status`

### Tier 3: E2E Tests (Complete User Flows)
**Policy**: **NO MOCKING** - complete scenarios with real infrastructure
**Focus**: End-to-end user workflows from install to production deployment

## 🔧 Tier 1: Unit Test Plan

### 1.1 Core Nexus Class Tests
**File**: `tests/unit/test_nexus_core.py`

```python
class TestNexusCore:
    def test_zero_parameter_initialization(self):
        """Validates true zero-configuration promise"""
        app = Nexus()
        assert app is not None
        assert app.api_port == 8000  # Smart default
        assert app.mcp_port == 3001  # Smart default
        assert app.enable_auth is False  # Optional by default

    def test_fastapi_style_explicit_instances(self):
        """Validates explicit instance ownership vs singleton anti-pattern"""
        app1 = Nexus(api_port=8000)
        app2 = Nexus(api_port=8001)
        assert app1 is not app2  # Different instances
        assert app1.api_port != app2.api_port  # Independent config

    def test_enterprise_constructor_options(self):
        """Validates enterprise features at construction"""
        app = Nexus(
            enable_auth=True,
            enable_monitoring=True,
            rate_limit=1000
        )
        assert app.enable_auth is True
        assert app.enable_monitoring is True
        assert app.rate_limit == 1000

    def test_progressive_enhancement_attributes(self):
        """Validates fine-tuning via attributes"""
        app = Nexus()
        app.auth.strategy = "rbac"
        app.monitoring.interval = 30
        assert app.auth.strategy == "rbac"
        assert app.monitoring.interval == 30
```

### 1.2 Workflow Registration Tests
**File**: `tests/unit/test_workflow_registration.py`

```python
class TestWorkflowRegistration:
    def test_single_registration_multi_channel_exposure(self):
        """Validates core multi-channel promise"""
        app = Nexus()
        workflow = MockWorkflow("test-workflow")

        app.register("data-processor", workflow)

        # Should be available across all channels
        assert "data-processor" in app._registry
        assert app._api_routes["data-processor"] is not None
        assert app._cli_commands["data-processor"] is not None
        assert app._mcp_tools["data-processor"] is not None

    def test_workflow_registration_validation(self):
        """Validates workflow object validation"""
        app = Nexus()

        # Valid workflow
        valid_workflow = MockWorkflow("valid")
        app.register("valid", valid_workflow)
        assert "valid" in app._registry

        # Invalid workflow
        with pytest.raises(ValueError, match="Invalid workflow"):
            app.register("invalid", "not-a-workflow")
```

### 1.3 Auto-Discovery Tests
**File**: `tests/unit/test_auto_discovery.py`

```python
class TestAutoDiscovery:
    def test_workflow_pattern_detection(self, tmp_path):
        """Validates auto-discovery patterns"""
        # Create test workflow files
        (tmp_path / "test.workflow.py").write_text(VALID_WORKFLOW_CODE)
        (tmp_path / "workflow_example.py").write_text(VALID_WORKFLOW_CODE)
        (tmp_path / "workflows" / "data.py").write_text(VALID_WORKFLOW_CODE)

        discovery = WorkflowDiscovery(str(tmp_path))
        workflows = discovery.discover()

        assert len(workflows) == 3
        assert "test" in workflows
        assert "example" in workflows
        assert "data" in workflows

    def test_import_error_handling(self, tmp_path):
        """Validates graceful handling of import errors"""
        # Create invalid workflow file
        (tmp_path / "broken.workflow.py").write_text("invalid python code")

        discovery = WorkflowDiscovery(str(tmp_path))
        workflows = discovery.discover()

        # Should skip broken file and continue
        assert "broken" not in workflows
        # Should log clear error message (verify via caplog)
```

### 1.4 Plugin System Tests
**File**: `tests/unit/test_plugin_system.py`

```python
class TestPluginSystem:
    def test_optional_plugin_loading(self):
        """Validates plugins are truly optional"""
        app = Nexus()

        # Core should work without any plugins
        assert app._auth_plugin is None
        assert app._monitoring_plugin is None

        # Should start successfully without plugins
        app._validate_configuration()  # Should not raise

    def test_plugin_isolation(self):
        """Validates plugin failures don't affect core"""
        app = Nexus(enable_auth=True)

        # Simulate auth plugin failure
        app._auth_plugin = None  # Plugin failed to load

        # Core functionality should still work
        workflow = MockWorkflow("test")
        app.register("test", workflow)
        assert "test" in app._registry

    def test_plugin_chaining(self):
        """Validates multiple plugins work together"""
        app = Nexus(
            enable_auth=True,
            enable_monitoring=True,
            rate_limit=100
        )

        assert app._auth_plugin is not None
        assert app._monitoring_plugin is not None
        assert app._rate_limit_plugin is not None
```

### 1.5 Configuration Validation Tests
**File**: `tests/unit/test_configuration.py`

```python
class TestConfiguration:
    def test_smart_defaults(self):
        """Validates intelligent default values"""
        app = Nexus()

        # Network defaults
        assert app.api_port == 8000
        assert app.mcp_port == 3001
        assert app.cors_origins == ["*"]  # Development default

        # Security defaults
        assert app.enable_auth is False  # Optional by default
        assert app.rate_limit is None    # No limit by default

        # Performance defaults
        assert app.max_workers == 20
        assert app.timeout == 30

    def test_port_conflict_resolution(self):
        """Validates automatic port resolution"""
        # Mock port 8000 as occupied
        with mock.patch('socket.socket') as mock_socket:
            mock_socket.return_value.connect_ex.return_value = 0  # Port in use

            app = Nexus()
            app._resolve_ports()

            # Should automatically use next available port
            assert app.api_port == 8001
```

## 🔗 Tier 2: Integration Test Plan

### 2.1 Multi-Channel Integration Tests
**File**: `tests/integration/test_multi_channel.py`

```python
class TestMultiChannelIntegration:
    @pytest.fixture(autouse=True)
    def setup_infrastructure(self):
        """Setup real Docker infrastructure"""
        subprocess.run(["./tests/utils/test-env", "up"], check=True)
        subprocess.run(["./tests/utils/test-env", "status"], check=True)
        yield
        subprocess.run(["./tests/utils/test-env", "down"], check=True)

    async def test_unified_workflow_execution(self):
        """Validates single workflow accessible via all channels"""
        # Setup real Nexus instance
        app = Nexus()
        workflow = RealDataProcessingWorkflow()
        app.register("data-processor", workflow)

        async with app.start() as server:
            # Test API access
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/workflows/data-processor",
                    json={"input": "test-data"}
                )
                assert response.status_code == 200
                api_result = response.json()

            # Test CLI access (real subprocess)
            cli_result = subprocess.run([
                "nexus", "run", "data-processor",
                "--param", "input=test-data"
            ], capture_output=True, text=True)
            assert cli_result.returncode == 0

            # Test MCP access (real MCP client)
            mcp_client = MCPClient("http://localhost:3001")
            mcp_result = await mcp_client.call_tool(
                "data-processor", {"input": "test-data"}
            )

            # All channels should return same result
            assert api_result["output"] == json.loads(cli_result.stdout)["output"]
            assert api_result["output"] == mcp_result["output"]
```

### 2.2 Cross-Channel Session Tests
**File**: `tests/integration/test_cross_channel_sessions.py`

```python
class TestCrossChannelSessions:
    async def test_session_synchronization(self):
        """Validates sessions persist across channels"""
        app = Nexus(enable_auth=True)

        async with app.start() as server:
            # Login via API
            async with httpx.AsyncClient() as client:
                auth_response = await client.post(
                    "http://localhost:8000/auth/login",
                    json={"username": "test", "password": "test"}
                )
                session_id = auth_response.json()["session_id"]

            # Use session in CLI
            cli_result = subprocess.run([
                "nexus", "run", "protected-workflow",
                "--session", session_id
            ], capture_output=True, text=True)
            assert cli_result.returncode == 0

            # Use session in MCP
            mcp_client = MCPClient("http://localhost:3001")
            mcp_result = await mcp_client.call_tool(
                "protected-workflow", {}, session_id=session_id
            )
            assert mcp_result["status"] == "success"

    async def test_real_time_event_sync(self):
        """Validates real-time events across channels"""
        app = Nexus()

        # Setup WebSocket listener
        websocket_events = []
        async with websockets.connect("ws://localhost:8000/ws") as ws:
            # Start workflow via CLI
            subprocess.run([
                "nexus", "run", "long-running-workflow"
            ], check=True)

            # Should receive events via WebSocket
            while True:
                try:
                    event = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    websocket_events.append(json.loads(event))
                    if event["type"] == "WORKFLOW_COMPLETED":
                        break
                except asyncio.TimeoutError:
                    break

        assert len(websocket_events) > 0
        assert any(e["type"] == "WORKFLOW_STARTED" for e in websocket_events)
        assert any(e["type"] == "WORKFLOW_COMPLETED" for e in websocket_events)
```

### 2.3 Durability Integration Tests
**File**: `tests/integration/test_durability.py`

```python
class TestDurabilityIntegration:
    async def test_request_level_durability(self):
        """Validates requests survive process restarts"""
        app = Nexus()

        # Start long-running workflow
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/workflows/long-runner",
                json={"duration": 10}
            )
            execution_id = response.json()["execution_id"]

        # Simulate server restart
        await app.stop()
        await asyncio.sleep(1)
        await app.start()

        # Workflow should resume from checkpoint
        async with httpx.AsyncClient() as client:
            status_response = await client.get(
                f"http://localhost:8000/executions/{execution_id}/status"
            )
            assert status_response.json()["status"] in ["RUNNING", "COMPLETED"]

    async def test_automatic_retry_with_backoff(self):
        """Validates automatic retry on failures"""
        app = Nexus()
        failing_workflow = FailingWorkflow(fail_times=2)
        app.register("failing", failing_workflow)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/workflows/failing",
                json={"input": "test"}
            )
            execution_id = response.json()["execution_id"]

            # Wait for retries and eventual success
            await asyncio.sleep(5)

            status_response = await client.get(
                f"http://localhost:8000/executions/{execution_id}/status"
            )
            assert status_response.json()["status"] == "COMPLETED"
            assert status_response.json()["retry_count"] == 2
```

### 2.4 Enterprise Features Integration Tests
**File**: `tests/integration/test_enterprise_features.py`

```python
class TestEnterpriseFeatures:
    async def test_enterprise_server_by_default(self):
        """Validates EnterpriseWorkflowServer used by default"""
        app = Nexus()

        # Should use enterprise server with production features
        assert isinstance(app._server, EnterpriseWorkflowServer)
        assert app._server.enable_durability is True
        assert app._server.enable_resource_management is True
        assert app._server.enable_async_execution is True
        assert app._server.enable_health_checks is True

    async def test_built_in_monitoring(self):
        """Validates automatic monitoring integration"""
        app = Nexus(enable_monitoring=True)

        async with app.start():
            # Prometheus metrics should be available
            async with httpx.AsyncClient() as client:
                metrics_response = await client.get(
                    "http://localhost:8000/metrics"
                )
                assert metrics_response.status_code == 200
                assert "workflow_executions_total" in metrics_response.text

    async def test_circuit_breaker_integration(self):
        """Validates built-in circuit breaker patterns"""
        app = Nexus()
        unreliable_workflow = UnreliableWorkflow()
        app.register("unreliable", unreliable_workflow)

        # Trigger circuit breaker
        for _ in range(5):
            async with httpx.AsyncClient() as client:
                await client.post(
                    "http://localhost:8000/workflows/unreliable",
                    json={"input": "test"}
                )

        # Circuit should be open
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/workflows/unreliable",
                json={"input": "test"}
            )
            assert response.status_code == 503  # Circuit breaker open
```

## 🚀 Tier 3: E2E Test Plan

### 3.1 Complete User Journey Tests
**File**: `tests/e2e/test_complete_user_journey.py`

```python
class TestCompleteUserJourney:
    def test_data_scientist_workflow(self):
        """Complete data scientist journey: install to API endpoint"""
        # Simulate fresh environment
        with temporary_directory() as workspace:
            os.chdir(workspace)

            # 1. Create workflow file
            (Path(workspace) / "data_analysis.workflow.py").write_text("""
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes.ai import LLMAgentNode

def create_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("LLMAgentNode", "analyzer", {
        "model": "gpt-4",
        "prompt": "Analyze the provided data"
    })
    return workflow.build()

workflow = create_workflow()
            """)

            # 2. Start Nexus (zero config)
            subprocess.run(["python", "-c", """
from nexus import Nexus
app = Nexus()
app.start()
            """], check=True, timeout=60)

            # 3. Verify workflow accessible via API
            response = requests.post(
                "http://localhost:8000/workflows/data_analysis",
                json={"data": "sample data"}
            )
            assert response.status_code == 200

            # Total time should be < 60 seconds

    def test_enterprise_deployment_journey(self):
        """Complete enterprise deployment with production features"""
        with temporary_directory() as workspace:
            os.chdir(workspace)

            # 1. Create enterprise configuration
            (Path(workspace) / "main.py").write_text("""
from nexus import Nexus

app = Nexus(
    enable_auth=True,
    enable_monitoring=True,
    rate_limit=1000
)

# Production workflows auto-discovered
app.start()
            """)

            # 2. Create production workflow
            (Path(workspace) / "workflows" / "production.py").write_text("""
# Production workflow with enterprise features
            """)

            # 3. Start with enterprise features
            process = subprocess.Popen([
                "python", "main.py"
            ])

            # Wait for startup
            time.sleep(5)

            try:
                # 4. Verify enterprise features active
                # Authentication required
                response = requests.post(
                    "http://localhost:8000/workflows/production",
                    json={"input": "test"}
                )
                assert response.status_code == 401  # Auth required

                # Monitoring available
                metrics_response = requests.get(
                    "http://localhost:8000/metrics"
                )
                assert metrics_response.status_code == 200

                # Health checks active
                health_response = requests.get(
                    "http://localhost:8000/health"
                )
                assert health_response.status_code == 200

            finally:
                process.terminate()
```

### 3.2 Performance Validation Tests
**File**: `tests/e2e/test_performance_validation.py`

```python
class TestPerformanceValidation:
    async def test_workflow_registration_performance(self):
        """Validates <1 second workflow registration target"""
        app = Nexus()

        start_time = time.time()

        # Register workflow
        workflow = ComplexWorkflow()
        app.register("complex", workflow)

        # Start server and verify all channels available
        async with app.start():
            # Verify API endpoint
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8000/workflows/complex"
                )
                assert response.status_code == 200

            # Verify CLI command
            cli_result = subprocess.run([
                "nexus", "list"
            ], capture_output=True, text=True)
            assert "complex" in cli_result.stdout

            # Verify MCP tool
            mcp_client = MCPClient("http://localhost:3001")
            tools = await mcp_client.list_tools()
            assert any(tool["name"] == "complex" for tool in tools)

        registration_time = time.time() - start_time
        assert registration_time < 1.0  # Must be under 1 second

    async def test_cross_channel_sync_performance(self):
        """Validates <50ms cross-channel synchronization target"""
        app = Nexus()

        async with app.start():
            # Measure session sync time
            start_time = time.time()

            # Create session via API
            async with httpx.AsyncClient() as client:
                auth_response = await client.post(
                    "http://localhost:8000/auth/login",
                    json={"username": "test", "password": "test"}
                )
                session_id = auth_response.json()["session_id"]

                # Immediately check session in other channels
                cli_check_time = time.time()
                cli_result = subprocess.run([
                    "nexus", "session", "status", session_id
                ], capture_output=True, text=True)

                mcp_check_time = time.time()
                mcp_client = MCPClient("http://localhost:3001")
                mcp_session = await mcp_client.get_session(session_id)

            sync_time = max(cli_check_time, mcp_check_time) - start_time
            assert sync_time < 0.05  # Must be under 50ms

    async def test_failure_recovery_performance(self):
        """Validates <5 second failure recovery target"""
        app = Nexus()

        # Start workflow that will fail
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "http://localhost:8000/workflows/failing-workflow",
                json={"input": "test"}
            )
            execution_id = response.json()["execution_id"]

        # Simulate server crash
        await app.stop()

        recovery_start = time.time()

        # Restart server
        await app.start()

        # Verify workflow resumed
        async with httpx.AsyncClient() as client:
            status_response = await client.get(
                f"http://localhost:8000/executions/{execution_id}/status"
            )
            if status_response.json()["status"] == "RUNNING":
                recovery_time = time.time() - recovery_start
                assert recovery_time < 5.0  # Must be under 5 seconds
```

### 3.3 Competitive Differentiation Tests
**File**: `tests/e2e/test_competitive_differentiation.py`

```python
class TestCompetitiveDifferentiation:
    def test_vs_django_durability(self):
        """Validates durability advantage over Django request-response"""
        # Django equivalent (best-effort)
        django_result = simulate_django_request_with_failure()
        assert django_result["status"] == "failed"  # Work lost

        # Nexus equivalent (durable)
        app = Nexus()

        with simulate_process_failure():
            response = requests.post(
                "http://localhost:8000/workflows/durable-process",
                json={"input": "test"}
            )
            execution_id = response.json()["execution_id"]

        # After restart, work should resume
        final_response = requests.get(
            f"http://localhost:8000/executions/{execution_id}/status"
        )
        assert final_response.json()["status"] == "COMPLETED"

    def test_vs_temporal_simplicity(self):
        """Validates simplicity advantage over Temporal external engine"""
        # Temporal equivalent (complex setup)
        temporal_setup_time = measure_temporal_setup()
        assert temporal_setup_time > 300  # > 5 minutes setup

        # Nexus equivalent (zero config)
        start_time = time.time()

        app = Nexus()
        workflow = SampleWorkflow()
        app.register("sample", workflow)
        app.start()

        setup_time = time.time() - start_time
        assert setup_time < 10  # < 10 seconds setup

    def test_vs_serverless_stateful_operations(self):
        """Validates stateful advantage over serverless timeout limits"""
        # Serverless simulation (15-minute timeout)
        with pytest.raises(TimeoutError):
            simulate_serverless_long_operation(duration=1800)  # 30 minutes

        # Nexus equivalent (hours-long operations)
        app = Nexus()

        response = requests.post(
            "http://localhost:8000/workflows/long-operation",
            json={"duration": 7200}  # 2 hours
        )

        # Should handle without timeout
        assert response.status_code == 202  # Accepted for long processing
```

## 🛡️ Quality Gates

### Pre-Release Validation Checklist

#### Zero-Configuration Gates
- [ ] `Nexus()` starts successfully with no parameters
- [ ] No configuration files required for basic operation
- [ ] No environment variables required for startup
- [ ] Auto-discovery works with 3+ workflow patterns
- [ ] Smart defaults handle 80% of use cases

#### Revolutionary Capability Gates
- [ ] Request-level durability working with checkpoint/resume
- [ ] Cross-channel session synchronization <50ms
- [ ] Multi-channel workflow exposure from single registration
- [ ] Enterprise features enabled by default
- [ ] Event-driven real-time communication across channels

#### Performance Gates
- [ ] Workflow registration: <1 second
- [ ] Cross-channel sync: <50ms
- [ ] Durability overhead: <10%
- [ ] Failure recovery: <5 seconds
- [ ] API latency: <100ms average
- [ ] Throughput: >1000 requests/second

#### Enterprise Readiness Gates
- [ ] EnterpriseWorkflowServer used by default
- [ ] Authentication/authorization working
- [ ] Monitoring and observability active
- [ ] Resource management preventing leaks
- [ ] Circuit breaker patterns functional

### Test Execution Requirements

#### Infrastructure
- **Docker Environment**: `./tests/utils/test-env up` must succeed
- **Real Services**: PostgreSQL, Redis, monitoring stack
- **Network Isolation**: Each test gets clean environment
- **Resource Cleanup**: Automatic cleanup after each test

#### Coverage Requirements
- **Unit Tests**: >95% line coverage
- **Integration Tests**: All critical paths covered
- **E2E Tests**: Complete user journeys validated
- **Performance Tests**: All targets met under load

#### Failure Handling
- **Graceful Degradation**: Core works when optional features fail
- **Error Messages**: Clear, actionable error messages
- **Recovery**: Automatic recovery from transient failures
- **Isolation**: One test failure doesn't affect others

## 📊 Success Metrics Dashboard

### Zero-Configuration Metrics
- **Setup Time**: Install to working endpoint <60 seconds
- **Configuration Lines**: 0 required configuration
- **Error Rate**: <1% for basic use cases
- **Documentation**: All examples <10 lines of code

### Performance Metrics
- **Registration Time**: <1 second (workflow → all channels)
- **Sync Latency**: <50ms (cross-channel session sync)
- **Recovery Time**: <5 seconds (failure → resumed execution)
- **Resource Efficiency**: >90% connection pool utilization

### Enterprise Metrics
- **Feature Coverage**: 100% of essential capabilities
- **Security Compliance**: All enterprise security features active
- **Monitoring Coverage**: Complete observability stack
- **Scalability**: Linear scaling to 10,000+ concurrent workflows

### Competitive Metrics
- **vs Django**: 100x better failure recovery (durable vs best-effort)
- **vs Temporal**: 30x faster setup (seconds vs minutes)
- **vs Serverless**: ∞x longer operations (hours vs 15 minutes)
- **vs API Gateways**: Complete business logic vs simple proxying

## 🎯 Implementation Priority

### Phase 1: Foundation (Critical)
1. **Unit Tests**: Core Nexus class, zero-config validation
2. **Basic Integration**: Multi-channel workflow exposure
3. **Performance Baseline**: Establish target measurements

### Phase 2: Revolutionary Features (Essential)
1. **Durability Tests**: Request-level persistence and recovery
2. **Cross-Channel Tests**: Session sync and real-time events
3. **Enterprise Tests**: Production-grade feature validation

### Phase 3: Competitive Validation (Important)
1. **Differentiation Tests**: vs Django/Temporal/Serverless
2. **Performance Tests**: Target achievement validation
3. **E2E Tests**: Complete user journey validation

## 📝 Test Maintenance

### Continuous Validation
- **CI Integration**: All tests run on every commit
- **Performance Monitoring**: Regression detection
- **Coverage Tracking**: Maintain >95% coverage
- **Documentation Sync**: Tests match documented examples

### Quality Assurance
- **Regular Review**: Monthly test plan review
- **Real-World Validation**: Customer scenario testing
- **Performance Tuning**: Optimize for target achievement
- **Failure Analysis**: Root cause analysis for all failures

---

**Document Version**: 1.0.0
**Date**: 2025-01-14
**Status**: Comprehensive Test Plan Complete
**Next**: Implementation with continuous validation
