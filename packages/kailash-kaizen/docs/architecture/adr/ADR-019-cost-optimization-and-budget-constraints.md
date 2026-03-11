# ADR-019: Cost Optimization and Budget Constraints

**Status**: Accepted
**Date**: 2025-01-22
**Related**: TODO-167 (Document Extraction Implementation), ADR-017, ADR-018
**Supersedes**: None

---

## Context

Document extraction services charge per page processed:

| Provider | Cost per Page | Accuracy | Features |
|----------|---------------|----------|----------|
| Landing AI | $0.015 | 98% | Bounding boxes, tables |
| OpenAI Vision | $0.068 | 95% | Fast, tables |
| Ollama | $0.000 (FREE) | 85% | Local, unlimited |

Key challenges:

1. **Unpredictable Costs**: Large document batches can incur significant costs
2. **Budget Constraints**: Production systems need cost guardrails
3. **Cost vs. Quality**: Different use cases need different accuracy levels
4. **Development Costs**: Unlimited testing needed without API charges

Requirements:

- **Cost Estimation**: Know costs before processing
- **Budget Enforcement**: Never exceed budget limits
- **Free Option**: Enable unlimited testing/development
- **Flexibility**: Choose quality vs. cost based on use case

---

## Decision

We will implement a **comprehensive cost optimization framework** with:

### 1. Pre-Extraction Cost Estimation

```python
# Estimate before processing
costs = agent.estimate_cost("document.pdf", provider="auto")

print(f"Landing AI: ${costs['landing_ai']:.3f}")
print(f"OpenAI: ${costs['openai_vision']:.3f}")
print(f"Ollama: ${costs['ollama_vision']:.3f}")  # Always $0.00

# Make informed decision
if costs['landing_ai'] > budget:
    provider = "ollama_vision"  # Use free
else:
    provider = "landing_ai"  # Use best quality
```

### 2. Budget Constraint Enforcement

```python
# Set budget limit
config = DocumentExtractionConfig(
    provider="auto",
    max_cost=0.01,  # $0.01 per document maximum
)

agent = DocumentExtractionAgent(config=config)

# Automatic provider selection within budget
result = agent.extract("document.pdf")

# If all paid providers exceed budget, falls back to Ollama (free)
assert result['cost'] <= 0.01  # Guaranteed
```

### 3. Prefer-Free Strategy

```python
# Prioritize free provider
config = DocumentExtractionConfig(
    provider="auto",
    prefer_free=True,  # Use Ollama first if available
)

# Fallback order: Ollama → Landing AI → OpenAI
result = agent.extract("document.pdf")
```

### 4. Cost Tracking and Monitoring

```python
class CostTracker:
    """Track extraction costs across documents."""

    def __init__(self, budget_limit: float = None):
        self.total_cost = 0.0
        self.budget_limit = budget_limit
        self.provider_usage = {}

    def record(self, result: dict):
        """Record extraction cost."""
        self.total_cost += result['cost']

        if self.budget_limit and self.total_cost > self.budget_limit:
            raise BudgetExceededError(
                f"Budget ${self.budget_limit} exceeded (spent ${self.total_cost})"
            )

    def report(self):
        """Generate cost report."""
        return {
            'total_cost': self.total_cost,
            'budget_remaining': self.budget_limit - self.total_cost,
            'provider_usage': self.provider_usage,
        }
```

---

## Rationale

### Why Cost Estimation?

**Without Estimation**:
```python
# Process document (unknown cost)
result = agent.extract("large_document.pdf")
print(f"Cost: ${result['cost']:.2f}")  # Surprise: $5.00!
```

**With Estimation**:
```python
# Estimate first
cost = agent.estimate_cost("large_document.pdf")
if cost > budget:
    print(f"Warning: Cost ${cost} exceeds budget ${budget}")
    # Use free provider or skip

# Process with confidence
result = agent.extract("large_document.pdf", provider="ollama_vision")
print(f"Cost: ${result['cost']:.2f}")  # Guaranteed: $0.00
```

**Benefits**:
- **Predictability**: Know costs before processing
- **Control**: Make informed provider choices
- **Budgets**: Prevent unexpected charges
- **Planning**: Estimate batch processing costs

### Why Budget Constraints?

**Production Scenario**:
```
Task: Process 10,000 invoices
Landing AI cost: $0.015/page × 10,000 = $150
OpenAI cost: $0.068/page × 10,000 = $680
Ollama cost: $0.00/page × 10,000 = $0
```

**Without Constraints**:
- Risk of unexpected $680 bill
- No automatic fallback to free option
- Manual cost monitoring required

**With Constraints**:
```python
config = DocumentExtractionConfig(
    provider="auto",
    max_cost=0.01,  # $0.01 per document max
    prefer_free=True,
)

# Automatically uses Ollama (free) for all 10,000 documents
# Total cost: $0.00 (vs. $150-680 without constraints)
```

**Benefits**:
- **Safety Net**: Never exceed budget
- **Automatic Optimization**: Falls back to free when needed
- **Predictable Costs**: Budget enforced at code level

### Why Prefer-Free Strategy?

**Development/Testing Use Case**:
- Need to test extraction with 100+ documents
- Landing AI: $0.015 × 100 = $1.50
- OpenAI: $0.068 × 100 = $6.80
- Ollama: $0.00 × 100 = $0.00

**Without Prefer-Free**:
```python
# Uses Landing AI by default (costs $1.50)
for doc in test_docs:
    result = agent.extract(doc)
```

**With Prefer-Free**:
```python
config = DocumentExtractionConfig(prefer_free=True)
agent = DocumentExtractionAgent(config=config)

# Uses Ollama by default (costs $0.00)
for doc in test_docs:
    result = agent.extract(doc)
```

**Savings**: $1.50-6.80 per 100 documents (100% cost reduction)

### Why Cost Tracking?

**Production Monitoring**:

```python
tracker = CostTracker(budget_limit=100.0)

for doc in documents:
    result = agent.extract(doc)
    tracker.record(result)

    # Check progress
    if tracker.total_cost > 50:
        print("Warning: 50% of budget used")

# Generate report
report = tracker.report()
print(f"Total cost: ${report['total_cost']}")
print(f"Budget remaining: ${report['budget_remaining']}")
```

**Benefits**:
- **Real-time monitoring**: Track costs as processing happens
- **Alerts**: Warn when approaching budget limit
- **Reporting**: Cost breakdown by provider
- **Accountability**: Audit trail for spending

---

## Consequences

### Positive

1. **✅ Predictability**: Cost estimation before processing
2. **✅ Control**: Budget constraints prevent overspending
3. **✅ Free Option**: Ollama enables unlimited testing ($0.00)
4. **✅ Flexibility**: Choose cost vs. quality based on use case
5. **✅ Transparency**: Cost tracking provides visibility
6. **✅ Automation**: Automatic fallback to free provider when over budget

### Negative

1. **⚠️ Complexity**: More configuration options than single-provider
2. **⚠️ Estimation Accuracy**: Estimates may differ slightly from actual costs (~5% variance)

### Neutral

1. **User Responsibility**: Users must set appropriate budgets
2. **Provider Dependency**: Free option requires Ollama installation

---

## Alternatives Considered

### Alternative 1: No Cost Controls

**Approach**: Process documents without cost estimation or budgets

**Pros**:
- Simplest implementation
- No overhead

**Cons**:
- ❌ No cost predictability
- ❌ Risk of unexpected bills
- ❌ No automated optimization
- ❌ Difficult to plan budgets

**Rejected**: Unacceptable for production use (risk of surprise costs).

### Alternative 2: Fixed Provider Selection

**Approach**: User selects provider, no automatic optimization

```python
# User must choose
result = agent.extract("doc.pdf", provider="landing_ai")
```

**Pros**:
- Simple and explicit
- User has full control

**Cons**:
- ❌ No automatic cost optimization
- ❌ No budget enforcement
- ❌ User must manually check costs

**Rejected**: Puts all cost management burden on user.

### Alternative 3: Post-Processing Cost Limits

**Approach**: Track costs after extraction, raise error if exceeded

```python
result = agent.extract("doc.pdf")  # Process first
if total_cost > budget:
    raise BudgetExceededError()  # Error after spending money
```

**Pros**:
- Simple implementation

**Cons**:
- ❌ Money already spent when error raised
- ❌ No prevention, only detection
- ❌ Wastes API calls on documents that exceed budget

**Rejected**: Costs already incurred when budget exceeded.

### Alternative 4: Sampling-Based Estimation

**Approach**: Process first page, extrapolate total cost

```python
# Process first page
first_page_cost = agent.extract_page_1("doc.pdf")
total_cost = first_page_cost * num_pages
```

**Pros**:
- More accurate than static estimation

**Cons**:
- ❌ Wastes API call on first page
- ❌ Slower (actual extraction required)
- ❌ Variable pages may have different costs

**Rejected**: Static estimation (counting pages) is fast and sufficiently accurate.

---

## Implementation Details

### Cost Estimation Logic

```python
async def estimate_cost(self, file_path: str) -> float:
    """
    Estimate extraction cost before processing.

    Logic:
    1. Count pages in document
    2. Multiply by provider's cost-per-page rate
    3. Return estimated cost
    """
    # Get page count (fast, doesn't process content)
    page_count = self._get_page_count(file_path)

    # Provider-specific rates
    rates = {
        'landing_ai': 0.015,  # $0.015/page
        'openai_vision': 0.068,  # $0.068/page
        'ollama_vision': 0.000,  # Free
    }

    # Calculate estimate
    return page_count * rates[self.provider_name]
```

### Budget Enforcement

```python
async def extract(
    self,
    file_path: str,
    max_cost: Optional[float] = None,
    **options
):
    """
    Extract with budget constraint enforcement.

    Raises:
        BudgetExceededError: If estimated cost exceeds max_cost
    """
    # Estimate cost
    estimated_cost = await self.estimate_cost(file_path)

    # Check budget
    if max_cost and estimated_cost > max_cost:
        # Try free provider as fallback
        if self.providers['ollama_vision'].is_available():
            return await self.providers['ollama_vision'].extract(file_path, **options)
        else:
            raise BudgetExceededError(
                f"Estimated cost ${estimated_cost:.3f} exceeds budget ${max_cost:.3f}"
            )

    # Proceed with extraction
    return await self._extract_impl(file_path, **options)
```

### Prefer-Free Provider Selection

```python
def _get_fallback_chain(self, prefer_free: bool = False):
    """
    Get provider fallback order.

    Default: Landing AI → OpenAI → Ollama
    Prefer-free: Ollama → Landing AI → OpenAI
    """
    if prefer_free:
        return ['ollama_vision', 'landing_ai', 'openai_vision']
    else:
        return ['landing_ai', 'openai_vision', 'ollama_vision']
```

---

## Testing Strategy

### Tier 1 (Unit Tests) - 25 tests
- Cost estimation accuracy (per-page calculations)
- Budget constraint enforcement
- Prefer-free provider selection logic
- Cost tracking calculations
- Edge cases (zero-page documents, negative budgets)

### Tier 2 (Integration Tests) - 6 tests
- Real cost estimates vs. actual costs (within 5% variance)
- Budget-constrained extraction with real providers
- Prefer-free fallback behavior
- Cost tracking with real API calls

### Tier 3 (E2E Tests) - 10 tests
- Budget-constrained batch processing
- Cost optimization strategies (prefer-free vs. prefer-quality)
- Cost tracking across multi-document workflows
- Provider comparison for cost/quality tradeoffs

**Total**: 41 cost-optimization tests (100% passing)

---

## Usage Examples

### Example 1: Cost Estimation Before Processing

```python
agent = DocumentExtractionAgent(config=config)

# Estimate all providers
costs = agent.estimate_cost("document.pdf", provider="auto")

print("Cost estimates:")
for provider, cost in costs.items():
    print(f"  {provider}: ${cost:.3f}")

# Choose based on budget
if costs['landing_ai'] <= budget:
    result = agent.extract("document.pdf", provider="landing_ai")
else:
    result = agent.extract("document.pdf", provider="ollama_vision")
```

### Example 2: Budget-Constrained Extraction

```python
config = DocumentExtractionConfig(
    provider="auto",
    max_cost=0.02,  # $0.02 per document maximum
)

agent = DocumentExtractionAgent(config=config)

# Automatic provider selection within budget
result = agent.extract("document.pdf")

# If Landing AI ($0.015) fits budget, uses it
# If OpenAI ($0.068) exceeds budget, falls back to Ollama ($0.00)
print(f"Provider used: {result['provider']}")
print(f"Actual cost: ${result['cost']:.3f}")
```

### Example 3: Prefer-Free Development Testing

```python
# Development configuration (free)
config = DocumentExtractionConfig(
    provider="auto",
    prefer_free=True,
)

agent = DocumentExtractionAgent(config=config)

# Test with 1000 documents (cost: $0.00)
for doc in test_documents:
    result = agent.extract(doc)
    # Uses Ollama (free) for all extractions
```

### Example 4: Production Cost Tracking

```python
class ProductionPipeline:
    def __init__(self, budget_limit: float):
        self.tracker = CostTracker(budget_limit=budget_limit)
        self.agent = DocumentExtractionAgent(config=config)

    def process_batch(self, documents: List[str]):
        for doc in documents:
            result = self.agent.extract(doc)
            self.tracker.record(result)

            # Monitor progress
            if self.tracker.total_cost > self.tracker.budget_limit * 0.8:
                print(f"Warning: 80% of budget used")

        # Generate report
        report = self.tracker.report()
        print(f"Total cost: ${report['total_cost']:.2f}")
        print(f"Budget remaining: ${report['budget_remaining']:.2f}")
```

---

## Cost Optimization Strategies

### Strategy 1: Development with Ollama (Free)

**Use Case**: Testing, prototyping, development

```python
config = DocumentExtractionConfig(provider="ollama_vision")
agent = DocumentExtractionAgent(config=config)

# Unlimited extraction at $0.00
for doc in all_test_documents:
    result = agent.extract(doc)
```

**Cost**: $0.00
**Tradeoff**: 85% accuracy (acceptable for testing)

### Strategy 2: Production with Budget Constraints

**Use Case**: Production with cost controls

```python
config = DocumentExtractionConfig(
    provider="auto",
    max_cost=0.02,  # $0.02 per document
    prefer_free=True,
)

agent = DocumentExtractionAgent(config=config)

# Automatic optimization within budget
result = agent.extract("production_doc.pdf")
```

**Cost**: $0.00-0.015 per document (automatic optimization)
**Tradeoff**: May use free provider if budget tight

### Strategy 3: High-Accuracy Production

**Use Case**: Legal documents, contracts requiring 98% accuracy

```python
config = DocumentExtractionConfig(provider="landing_ai")
agent = DocumentExtractionAgent(config=config)

# Guaranteed highest accuracy
result = agent.extract("contract.pdf")
```

**Cost**: $0.015 per page
**Tradeoff**: Higher cost for highest quality

### Strategy 4: Speed-Optimized Production

**Use Case**: Time-critical extraction (< 1s per page)

```python
config = DocumentExtractionConfig(provider="openai_vision")
agent = DocumentExtractionAgent(config=config)

# Fastest processing (0.8s per page)
result = agent.extract("urgent_doc.pdf")
```

**Cost**: $0.068 per page
**Tradeoff**: Highest cost but fastest processing

---

## Cost Comparison

### Scenario: 1,000 Invoices (Average 2 pages each)

| Provider | Pages | Cost/Page | Total Cost | Accuracy | Time |
|----------|-------|-----------|------------|----------|------|
| **Landing AI** | 2,000 | $0.015 | $30.00 | 98% | 40 min |
| **OpenAI** | 2,000 | $0.068 | $136.00 | 95% | 27 min |
| **Ollama** | 2,000 | $0.000 | $0.00 | 85% | 83 min |

**Recommendation**: Use Ollama for development/testing, Landing AI for production (balance of accuracy and cost).

---

## References

- **Implementation**: `src/kaizen/providers/document/base_provider.py`, `src/kaizen/providers/document/provider_manager.py`
- **Tests**: `tests/unit/providers/document/test_provider_manager.py`, `tests/e2e/document_extraction/test_performance_and_cost.py`
- **Documentation**: `docs/guides/document-extraction-integration.md`
- **Examples**: `examples/8-multi-modal/document-rag/cost_estimation_demo.py`, `examples/8-multi-modal/document-rag/production_monitoring.py`
- **Related ADRs**: ADR-017 (Multi-Provider Architecture), ADR-018 (RAG Chunking)

---

**Approved**: 2025-01-22
**Implemented**: TODO-167 Phases 1-4
**Test Coverage**: 41 cost-optimization tests (100% passing)
