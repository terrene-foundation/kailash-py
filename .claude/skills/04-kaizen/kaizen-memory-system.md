# Kaizen Memory & Learning System

**Available in**: v0.5.0+ | **Storage**: FileStorage, SQLiteStorage

## Quick Reference

```python
from kaizen.memory.storage import FileStorage, SQLiteStorage
from kaizen.memory import ShortTermMemory, LongTermMemory, SemanticMemory
from kaizen.memory import PatternRecognizer, PreferenceLearner, MemoryPromoter, ErrorCorrectionLearner

storage = FileStorage("memory.jsonl")  # or SQLiteStorage("memory.db")
short_term = ShortTermMemory(storage, ttl_seconds=3600)
long_term = LongTermMemory(storage)
semantic = SemanticMemory(storage)
```

## Storage Backends

```python
# FileStorage: JSONL, dev/prototyping
storage = FileStorage("memory.jsonl")
entry_id = storage.create(content="...", metadata={"user_id": "alice"}, importance=0.8, tags=["pref"])
entry = storage.read(entry_id)
results = storage.search(query="preferences", filters={"user_id": "alice"}, limit=10)

# SQLiteStorage: Production single-instance, FTS5 + vector similarity
storage = SQLiteStorage("memory.db")
similar = storage.similarity_search(embedding=[0.1, 0.2, ...], top_k=5)
```

## Memory Types

### ShortTermMemory -- Session-scoped, TTL-based

```python
short_term = ShortTermMemory(storage, ttl_seconds=3600, session_id="session_456")
short_term.store(content="User asked about decorators", metadata={"topic": "python"}, importance=0.6)
recent = short_term.retrieve(query="python questions", top_k=5, filters={"topic": "python"})
short_term.cleanup_expired()  # Automatic TTL cleanup
```

### LongTermMemory -- Persistent cross-session

```python
long_term = LongTermMemory(storage)
long_term.store(content="User is a senior Python dev", metadata={"user_id": "alice"}, importance=0.9, tags=["profile"])
important = long_term.retrieve_by_importance(min_importance=0.8, limit=10)
long_term.consolidate(similarity_threshold=0.9, merge_strategy="keep_highest_importance")
long_term.archive(age_threshold_days=90, min_importance=0.5)
```

### SemanticMemory -- Concept extraction and similarity search

```python
semantic = SemanticMemory(storage)
semantic.store(content="Python decorators modify functions", metadata={}, importance=0.7)
# Auto-extracts concepts: ["python", "decorators", "functions"]

similar = semantic.search_similar(query="function modifiers", top_k=5, similarity_threshold=0.7)
concepts = semantic.extract_concepts(text="async/await in Python")
relationships = semantic.get_concept_relationships(concept="python", max_depth=2)
```

## Learning Mechanisms

### PatternRecognizer -- FAQ detection

```python
recognizer = PatternRecognizer(memory=long_term)
faqs = recognizer.detect_faqs(min_frequency=5, similarity_threshold=0.85, time_window_days=30)
# Returns: [{"question": "...", "frequency": N, "best_answer": "...", "confidence": 0.9}]

patterns = recognizer.detect_patterns(pattern_type="sequential", min_occurrences=3)
recommendations = recognizer.recommend_based_on_patterns(current_context="...", top_k=3)
```

### PreferenceLearner -- User preferences

```python
learner = PreferenceLearner(memory=long_term)
preferences = learner.learn_preferences(user_id="alice", min_occurrences=3, time_window_days=90)
format_pref = learner.get_preference(user_id="alice", category="output_format")
learner.update_preference(user_id="alice", category="verbosity", value="concise", importance=0.8)
```

### MemoryPromoter -- Short-term to long-term

```python
promoter = MemoryPromoter(short_term_memory=short_term, long_term_memory=long_term)
result = promoter.auto_promote(min_importance=0.7, min_access_count=3, age_threshold_seconds=3600)
# Returns: {"promoted": N, "skipped": N, "failed": N}
```

### ErrorCorrectionLearner -- Learn from mistakes

```python
learner = ErrorCorrectionLearner(memory=long_term)
learner.record_error(error_type="type_error", context="String passed instead of int", correction="Added validation", success=True)
correction = learner.get_correction(error_type="type_error", context="Invalid input", top_k=1)
errors = learner.analyze_errors(min_frequency=2, time_window_seconds=604800, similarity_threshold=0.8)
```

## BaseAgent Integration

```python
class MemoryEnabledAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=MySignature())
        storage = SQLiteStorage("agent_memory.db")
        self.long_term = LongTermMemory(storage)
        self.semantic = SemanticMemory(storage)

    def process_with_memory(self, user_input: str, user_id: str):
        relevant = self.semantic.search_similar(query=user_input, top_k=5, similarity_threshold=0.7)
        memory_context = "\n".join([m.content for m in relevant])
        result = self.run(input=f"{memory_context}\n\nUser: {user_input}")
        self.long_term.store(content=f"Q: {user_input}\nA: {result['output']}", metadata={"user_id": user_id}, importance=0.7)
        return result
```

## Performance

| Operation         | Latency (p95) | Notes             |
| ----------------- | ------------- | ----------------- |
| Store (File)      | <5ms          | JSONL append      |
| Store (SQLite)    | <20ms         | SQL insert        |
| Retrieve (SQLite) | <10ms         | B-tree index      |
| Semantic search   | <50ms         | Cosine similarity |
| Pattern detection | <500ms        | Clustering        |

Tested with 10,000 entries per agent.

## Importance Score Guide

| Score | Use Case                       |
| ----- | ------------------------------ |
| 0.9   | Critical user preferences      |
| 0.7   | Important conversation context |
| 0.5   | General interaction history    |
| 0.3   | Temporary session data         |

## Troubleshooting

| Problem                  | Fix                                                                              |
| ------------------------ | -------------------------------------------------------------------------------- |
| Slow retrieval (>100ms)  | Switch to SQLiteStorage, add indexes, reduce top_k, archive old memories         |
| Memory growing unbounded | Consolidate (0.9 threshold), archive (90 days), set TTL, delete importance < 0.3 |
| Poor semantic search     | Increase similarity_threshold (0.8+), add metadata filters, use keyword fallback |
