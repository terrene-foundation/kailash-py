# Testing Patterns

Agent testing, fixtures, standardized tests from conftest.py.

## 3-Tier Testing Strategy

1. **Tier 1 (Unit)**: Fast, mocked LLM providers
2. **Tier 2 (Integration)**: Real Ollama inference (local, free)
3. **Tier 3 (E2E)**: Real OpenAI inference (paid API)

**CRITICAL**: NO MOCKING in Tiers 2-3

## Standard Fixtures

```python
def test_qa_agent(simple_qa_example, assert_async_strategy, test_queries):
    QAConfig = simple_qa_example.config_classes["QAConfig"]
    QAAgent = simple_qa_example.agent_classes["SimpleQAAgent"]

    agent = QAAgent(config=QAConfig())
    assert_async_strategy(agent)

    result = agent.ask(test_queries["simple"])
    assert isinstance(result, dict)
```

## Available Fixtures

**Example Loading**: `load_example()`, `simple_qa_example`, `code_generation_example`
**Assertions**: `assert_async_strategy()`, `assert_agent_result()`, `assert_shared_memory()`
**Test Data**: `test_queries`, `test_documents`, `test_code_snippets`

## References
- **Source**: `apps/kailash-kaizen/tests/conftest.py`
- **Specialist**: `.claude/agents/frameworks/kaizen-specialist.md` lines 382-404
