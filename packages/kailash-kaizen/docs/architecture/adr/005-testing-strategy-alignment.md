# ADR-005: Testing Strategy Alignment with Kailash 3-Tier Approach

## Status
**Proposed**

## Context

Kailash has established a rigorous 3-tier testing strategy that ensures high quality and reliability:

- **Tier 1 (Unit Tests)**: Fast, isolated testing with mocking where appropriate
- **Tier 2 (Integration Tests)**: Real infrastructure testing without mocks
- **Tier 3 (End-to-End Tests)**: Complete system testing with external services

The Kaizen AI framework introduces new complexity with:
- Signature programming model requiring compilation validation
- Automatic optimization algorithms needing ML validation
- Memory systems requiring distributed storage testing
- Multi-modal pipelines needing diverse data testing
- Enterprise features requiring security and compliance validation

We need a testing strategy that maintains Kailash's quality standards while addressing Kaizen's unique requirements.

## Decision

We will **extend the existing 3-tier testing strategy** with Kaizen-specific testing patterns while maintaining full compatibility with the current testing infrastructure.

### Enhanced 3-Tier Strategy for Kaizen

```
┌─────────────────────────────────────────────────────────────┐
│                   KAIZEN TESTING STRATEGY                  │
├─────────────────────────────────────────────────────────────┤
│  Tier 1: Unit Tests (Enhanced)                             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ Signature Tests │ │ Node Logic Tests│ │ Memory Unit Tests│
│  │ • Compilation   │ │ • Parameter Val │ │ • Cache Logic   ││
│  │ • Validation    │ │ • Error Handling│ │ • Lifecycle     ││
│  │ • Type Safety   │ │ • Backward Compat│ │ • Serialization││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Tier 2: Integration Tests (Real Infrastructure)           │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ Memory Systems  │ │ Model Providers │ │ Security Systems││
│  │ • Redis/Vector  │ │ • OpenAI/Anthro │ │ • Encryption    ││
│  │ • Data Tiering  │ │ • Ollama/Local  │ │ • Access Control││
│  │ • Multi-tenant  │ │ • Fallback      │ │ • Audit Trails  ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
├─────────────────────────────────────────────────────────────┤
│  Tier 3: End-to-End Tests (Complete Workflows)             │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐│
│  │ Signature E2E   │ │ Multi-Modal E2E │ │ Enterprise E2E  ││
│  │ • Full Pipelines│ │ • Text+Image+Audio│ • Multi-tenant  ││
│  │ • Optimization  │ │ • Cross-modal   │ │ • Compliance    ││
│  │ • Performance   │ │ • Real Data     │ │ • Disaster Rec  ││
│  └─────────────────┘ └─────────────────┘ └─────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Tier 1: Enhanced Unit Testing

#### Signature Programming Tests
```python
# tests/unit/kaizen/test_signature_compilation.py
class TestSignatureCompilation:
    def test_basic_signature_compilation(self):
        """Test signature compiles to valid workflow."""
        @signature
        class SimpleAnalysis:
            text: str = context.input()
            sentiment: float = context.output()

        compiled = SimpleAnalysis.compile()
        assert isinstance(compiled, WorkflowBuilder)
        assert compiled.validate()

    def test_signature_type_validation(self):
        """Test runtime type validation."""
        with pytest.raises(ValidationError):
            SimpleAnalysis.execute(text=123)  # Wrong type

    def test_signature_security_validation(self):
        """Test security constraint validation."""
        @signature
        class SecureAnalysis:
            sensitive_data: str = context.input(
                security=["pii_scan"]
            )

        with pytest.raises(SecurityViolation):
            SecureAnalysis.execute(sensitive_data="SSN: 123-45-6789")
```

#### Memory System Unit Tests
```python
# tests/unit/kaizen/test_memory_logic.py
class TestMemoryLogic:
    def test_memory_context_lifecycle(self):
        """Test memory context creation and cleanup."""
        context = MemoryContext("test", ttl="1h")
        assert context.is_valid()

        context.expire()
        assert not context.is_valid()

    def test_memory_tiering_logic(self):
        """Test data movement between tiers."""
        memory = MemoryManager()

        # Data starts in hot tier
        memory.store("key", "value", tier="hot")
        assert memory.get_tier("key") == "hot"

        # Simulate aging to warm tier
        memory.age_data("key", age_minutes=60)
        assert memory.get_tier("key") == "warm"
```

#### Optimization Algorithm Tests
```python
# tests/unit/kaizen/test_optimization.py
class TestOptimizationAlgorithms:
    def test_prompt_evolution_logic(self):
        """Test prompt optimization algorithm."""
        optimizer = PromptOptimizer()

        initial_prompt = "Analyze this text: {text}"
        training_data = [("sample text", "expected output")]

        optimized = optimizer.evolve(initial_prompt, training_data)
        assert optimized.score > initial_prompt.score

    def test_model_selection_logic(self):
        """Test model selection algorithm."""
        selector = ModelSelector()

        requirements = {"latency": "<100ms", "cost": "<$0.01"}
        selected = selector.select_best(requirements)

        assert selected.meets_requirements(requirements)
```

### Tier 2: Real Infrastructure Integration Testing

#### Memory System Integration
```python
# tests/integration/kaizen/test_memory_integration.py
class TestMemoryIntegration:
    @pytest.fixture
    def real_redis(self):
        """Real Redis instance for testing."""
        redis_client = redis.Redis(host='localhost', port=6379)
        yield redis_client
        redis_client.flushdb()

    @pytest.fixture
    def real_vector_db(self):
        """Real vector database for testing."""
        # Use actual Pinecone/Weaviate/Qdrant instance
        pass

    async def test_memory_persistence(self, real_redis, real_vector_db):
        """Test memory persists across system restarts."""
        memory_system = MemorySystem(
            hot_storage=real_redis,
            warm_storage=real_vector_db
        )

        # Store data
        await memory_system.store("session_1", {"conversation": "history"})

        # Simulate system restart
        memory_system.disconnect()
        memory_system.reconnect()

        # Verify data persists
        data = await memory_system.retrieve("session_1")
        assert data["conversation"] == "history"

    async def test_memory_encryption(self, real_redis):
        """Test memory encryption with real storage."""
        encrypted_memory = MemorySystem(
            hot_storage=real_redis,
            encryption_key="test-key-256-bits"
        )

        sensitive_data = "confidential information"
        await encrypted_memory.store("test", sensitive_data)

        # Verify data is encrypted in storage
        raw_data = real_redis.get("test")
        assert raw_data != sensitive_data.encode()

        # Verify decryption works
        retrieved = await encrypted_memory.retrieve("test")
        assert retrieved == sensitive_data
```

#### Model Provider Integration
```python
# tests/integration/kaizen/test_model_integration.py
class TestModelProviderIntegration:
    async def test_openai_integration(self):
        """Test OpenAI provider with real API."""
        provider = OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))

        response = await provider.complete(
            model="gpt-4",
            prompt="What is 2+2?",
            max_tokens=10
        )

        assert "4" in response.content
        assert response.usage.total_tokens > 0

    async def test_model_fallback(self):
        """Test model fallback with real providers."""
        orchestrator = ModelOrchestrator(
            primary="gpt-4",
            fallback="gpt-3.5-turbo"
        )

        # Simulate primary failure
        with patch_primary_model_failure():
            response = await orchestrator.complete("Test prompt")
            assert response.model == "gpt-3.5-turbo"
            assert response.fallback_used is True
```

### Tier 3: End-to-End Complete System Testing

#### Signature-Based Workflow E2E
```python
# tests/e2e/kaizen/test_signature_workflows.py
class TestSignatureWorkflowE2E:
    async def test_complete_document_analysis_pipeline(self):
        """Test complete document analysis with optimization."""

        @signature.workflow
        class DocumentAnalysisPipeline:
            document: str = context.input()
            summary: str = context.intermediate(
                signature=DocumentSummarization
            )
            insights: List[str] = context.intermediate(
                signature=InsightExtraction
            )
            report: Dict[str, Any] = context.output(
                signature=ReportGeneration
            )

        # Deploy to test environment
        pipeline = DocumentAnalysisPipeline()
        await pipeline.deploy_test_environment()

        # Test with real document
        real_document = load_test_document("10k_filing.pdf")
        result = await pipeline.execute(document=real_document)

        # Validate complete pipeline
        assert len(result.summary) > 100
        assert len(result.insights) >= 3
        assert "financial_metrics" in result.report
        assert result.execution_time < 30.0  # seconds

    async def test_automatic_optimization_e2e(self):
        """Test signature optimization with real feedback."""

        @signature
        @optimize(strategy="performance", iterations=5)
        class SentimentAnalysis:
            text: str = context.input()
            sentiment: Literal["positive", "negative", "neutral"] = context.output()
            confidence: float = context.output()

        # Provide training examples
        training_data = load_sentiment_training_data()

        # Run optimization
        optimized_signature = await SentimentAnalysis.optimize(
            training_data=training_data,
            validation_split=0.2
        )

        # Validate optimization improved performance
        baseline_accuracy = 0.75
        optimized_accuracy = await test_accuracy(optimized_signature)
        assert optimized_accuracy > baseline_accuracy + 0.05
```

#### Multi-Modal E2E Testing
```python
# tests/e2e/kaizen/test_multimodal.py
class TestMultiModalE2E:
    async def test_cross_modal_reasoning(self):
        """Test reasoning across text, image, and audio."""

        @signature
        class MultiModalAnalysis:
            text_description: str = context.input()
            image: bytes = context.input(format="image/jpeg")
            audio_transcript: str = context.input()

            consistency_score: float = context.output()
            combined_insights: List[str] = context.output()

        # Real multi-modal data
        test_data = {
            "text_description": "A presentation about quarterly results",
            "image": load_test_image("presentation_slide.jpg"),
            "audio_transcript": "Our Q3 revenue increased by 15%"
        }

        result = await MultiModalAnalysis.execute(**test_data)

        assert 0.0 <= result.consistency_score <= 1.0
        assert len(result.combined_insights) >= 2
        assert any("revenue" in insight.lower() for insight in result.combined_insights)
```

#### Enterprise E2E Testing
```python
# tests/e2e/kaizen/test_enterprise_features.py
class TestEnterpriseE2E:
    async def test_multi_tenant_isolation(self):
        """Test complete multi-tenant workflow isolation."""

        # Create two tenant environments
        tenant_a = await create_tenant_environment("company_a")
        tenant_b = await create_tenant_environment("company_b")

        # Deploy same signature to both tenants
        @signature
        class DataAnalysis:
            data: str = context.input()
            result: str = context.output()

        analysis_a = await tenant_a.deploy_signature(DataAnalysis)
        analysis_b = await tenant_b.deploy_signature(DataAnalysis)

        # Execute with tenant-specific data
        result_a = await analysis_a.execute(data="tenant A confidential data")
        result_b = await analysis_b.execute(data="tenant B confidential data")

        # Verify complete isolation
        assert not await tenant_a.can_access_data(tenant_b.data)
        assert not await tenant_b.can_access_data(tenant_a.data)

        # Verify separate optimization paths
        assert analysis_a.optimization_history != analysis_b.optimization_history

    async def test_compliance_audit_trail(self):
        """Test complete audit trail for compliance."""

        @signature
        class SensitiveDataProcessing:
            personal_data: str = context.input(
                security=["pii_detection", "gdpr_compliance"]
            )
            processed_data: str = context.output()

        # Execute with audit trail enabled
        with audit_context("GDPR_TEST"):
            result = await SensitiveDataProcessing.execute(
                personal_data="John Doe, SSN: 123-45-6789"
            )

        # Verify complete audit trail
        audit_trail = await get_audit_trail("GDPR_TEST")

        assert "pii_detected" in audit_trail.events
        assert "data_masked" in audit_trail.events
        assert "gdpr_compliance_verified" in audit_trail.events
        assert audit_trail.duration < 1.0  # Fast compliance checking
```

## Testing Infrastructure Requirements

### Continuous Integration
```yaml
# .github/workflows/kaizen-tests.yml
name: Kaizen Test Suite

on: [push, pull_request]

jobs:
  tier1-unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Unit Tests
        run: pytest tests/unit/kaizen/ -v --cov=kailash.kaizen

  tier2-integration-tests:
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:latest
      postgres:
        image: postgres:latest
    steps:
      - name: Run Integration Tests
        run: pytest tests/integration/kaizen/ -v --real-infrastructure

  tier3-e2e-tests:
    runs-on: ubuntu-latest
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - name: Run E2E Tests
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: pytest tests/e2e/kaizen/ -v --real-services
```

### Test Data Management
```python
# tests/conftest.py
@pytest.fixture(scope="session")
def test_data_manager():
    """Manage test data across all tiers."""
    return TestDataManager(
        synthetic_data=True,
        real_data_samples=load_anonymized_samples(),
        multi_modal_samples=load_media_samples()
    )

@pytest.fixture
def signature_test_cases():
    """Standard signature test cases."""
    return [
        SimpleTextSignature,
        ComplexMultiModalSignature,
        SecurityConstrainedSignature,
        PerformanceOptimizedSignature
    ]
```

## Consequences

### Positive
- **Quality Assurance**: Maintains Kailash's high quality standards
- **Comprehensive Coverage**: Tests all aspects of Kaizen functionality
- **Real-World Validation**: Integration and E2E tests with real infrastructure
- **Enterprise Ready**: Validates security, compliance, and multi-tenancy
- **Performance Validation**: Ensures performance targets are met

### Negative
- **Test Complexity**: More sophisticated testing infrastructure required
- **Resource Requirements**: Real infrastructure testing needs more resources
- **Maintenance Overhead**: More test cases to maintain and update
- **Execution Time**: Comprehensive testing takes longer to complete

## Success Criteria

### Coverage Metrics
- **Unit Tests**: 95%+ code coverage for Kaizen components
- **Integration Tests**: 100% coverage of external system integrations
- **E2E Tests**: 100% coverage of critical user workflows
- **Performance Tests**: All latency and throughput targets validated

### Quality Metrics
- **Test Reliability**: 99%+ test pass rate in CI/CD
- **Bug Detection**: 90%+ of bugs caught before production
- **Regression Prevention**: Zero regression incidents in production
- **Security Validation**: 100% security features tested

### Operational Metrics
- **Test Execution Time**: Tier 1 <5min, Tier 2 <30min, Tier 3 <2hrs
- **Infrastructure Costs**: Test infrastructure costs <10% of development costs
- **Developer Experience**: 90%+ developer satisfaction with testing tools

## Related ADRs
- ADR-001: Kaizen Framework Architecture
- ADR-002: Signature Programming Model Implementation
- ADR-003: Memory System Architecture
- ADR-004: Node Migration Strategy from Core SDK
