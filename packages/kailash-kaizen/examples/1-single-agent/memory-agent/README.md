# Memory-Augmented Agent with Conversational State

## Overview
Demonstrates persistent memory management for conversational agents. This agent maintains context across multiple interactions, learns from conversation history, and adapts responses based on accumulated knowledge about users and topics.

## Use Case
- Personal assistant applications
- Customer support with conversation history
- Educational tutoring with learning progression
- Long-term relationship building in chatbots

## Agent Specification

### Core Functionality
- **Input**: Messages with conversation context
- **Processing**: Context-aware response generation with memory integration
- **Output**: Responses that reference and build upon conversation history
- **Memory**: Persistent conversation state, user preferences, topic knowledge

### Signature Pattern
```python
class MemoryAgentSignature(dspy.Signature):
    """Generate contextually aware responses using conversation memory."""
    current_message: str = dspy.InputField(desc="Current user message")
    conversation_id: str = dspy.InputField(desc="Unique conversation identifier")
    user_id: str = dspy.InputField(desc="User identifier for personalization")

    response: str = dspy.OutputField(desc="Contextually appropriate response")
    memory_updates: str = dspy.OutputField(desc="Information to store in memory")
    relevance_score: float = dspy.OutputField(desc="Relevance of memory to response")
    emotional_tone: str = dspy.OutputField(desc="Detected emotional context")
    next_topic_suggestions: str = dspy.OutputField(desc="Suggested conversation directions")
```

## Expected Execution Flow

### Phase 1: Memory Retrieval (0-100ms)
```
[00:00:000] Conversation ID and user ID extracted
[00:00:020] Recent conversation history retrieved (last 10 messages)
[00:00:045] User preference profile loaded
[00:00:070] Topic-specific memory searched
[00:00:095] Context ranking and relevance scoring completed
```

### Phase 2: Context Integration (100-300ms)
```
[00:00:100] Current message analyzed for intent and entities
[00:00:130] Relevant memories integrated into prompt context
[00:00:160] User personalization factors applied
[00:00:190] Emotional context and conversation tone assessed
[00:00:220] Response generation strategy determined
[00:00:280] Contextual prompt constructed
```

### Phase 3: Response Generation (300-1800ms)
```
[00:00:300] LLM called with enriched context
[00:01:200] Response generated with memory awareness
[00:01:350] Memory extraction performed on conversation
[00:01:480] New information categorized and prioritized
[00:01:620] User model updated with new insights
[00:01:750] Response validated for consistency with history
[00:01:800] Final response prepared
```

### Phase 4: Memory Update (1800-2000ms)
```
[00:01:800] New memories stored in conversation database
[00:01:850] User preference updates applied
[00:01:900] Topic knowledge graph updated
[00:01:950] Conversation metadata indexed
[00:02:000] Memory consolidation completed
```

## Technical Requirements

### Dependencies
```python
# Core Kailash SDK
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.llm_agent import LLMAgentNode
from kailash.nodes.database import DatabaseNode
from kailash.nodes.vector_search import VectorSearchNode

# Memory management
import dspy
from typing import List, Dict, Optional, Tuple
import json
import sqlite3
import numpy as np
from datetime import datetime, timedelta
```

### Configuration
```yaml
memory_config:
  max_conversation_length: 50
  memory_retention_days: 365
  relevance_threshold: 0.6
  max_retrievals: 10

database_config:
  type: "sqlite"
  path: "conversation_memory.db"
  vector_dimension: 384
  similarity_threshold: 0.7

llm_config:
  provider: "openai"
  model: "gpt-4"
  temperature: 0.7
  max_tokens: 500

personalization:
  learning_rate: 0.1
  preference_decay: 0.95
  emotional_memory_weight: 1.2
```

### Memory Requirements
- **Runtime Memory**: ~200MB (includes vector embeddings)
- **Database Storage**: ~10MB per 1000 conversations
- **Vector Index**: ~5MB per 10K memory entries
- **Cache**: ~50MB for active conversations

## Architecture Overview

### Agent Coordination Pattern
```
User Message → Memory Retrieval → Context Integration → Response Generation
     ↑                                                           ↓
Conversation DB ← Memory Update ← Response Analysis ← Generated Response
```

### Data Flow
1. **Message Reception**: Parse and extract conversation metadata
2. **Memory Retrieval**: Fetch relevant conversation history and user data
3. **Context Assembly**: Integrate memories into coherent context
4. **Response Generation**: Create contextually aware response
5. **Memory Extraction**: Identify new information to remember
6. **Memory Storage**: Update conversation database with new insights

### Memory Schema
```sql
-- Conversation messages
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    timestamp DATETIME,
    message TEXT,
    response TEXT,
    emotion TEXT,
    topics TEXT
);

-- User preferences and characteristics
CREATE TABLE user_profiles (
    user_id TEXT PRIMARY KEY,
    preferences JSON,
    communication_style TEXT,
    interests JSON,
    last_updated DATETIME
);

-- Semantic memory for topics and concepts
CREATE TABLE semantic_memory (
    id TEXT PRIMARY KEY,
    content TEXT,
    embedding BLOB,
    topic_tags TEXT,
    importance_score REAL,
    last_accessed DATETIME
);
```

## Success Criteria

### Functional Requirements
- ✅ Maintains consistent personality across conversations
- ✅ References appropriate conversation history
- ✅ Learns and adapts to user preferences
- ✅ Handles memory gaps gracefully

### Memory Accuracy
- ✅ Conversation history recall accuracy >90%
- ✅ User preference learning accuracy >85%
- ✅ Temporal consistency in responses >95%
- ✅ Memory relevance scoring precision >80%

### Performance Requirements
- ✅ Memory retrieval latency <100ms
- ✅ Response generation with memory <3 seconds
- ✅ Memory update operations <200ms
- ✅ Concurrent conversation handling >50 users

## Enterprise Considerations

### Privacy and Security
- End-to-end encryption for sensitive conversations
- User consent management for memory retention
- GDPR compliance with right to deletion
- Access control and audit logging

### Scalability
- Distributed memory storage across multiple databases
- Efficient vector similarity search with indexing
- Memory compression and archival strategies
- Load balancing for concurrent memory operations

### Data Management
- Automatic memory cleanup and retention policies
- Memory importance scoring and prioritization
- Cross-conversation learning while maintaining privacy
- Backup and disaster recovery for conversation data

## Error Scenarios

### Memory Retrieval Failure
```python
# Response when memory system is unavailable
{
  "response": "I'll help you, though I may not have access to our previous conversations right now.",
  "memory_status": "UNAVAILABLE",
  "fallback_mode": "STATELESS_OPERATION",
  "suggested_action": "Please provide context if needed"
}
```

### Memory Inconsistency Detected
```python
# Handling contradictory information in memory
{
  "response": "I notice some conflicting information in our conversation history. Let me clarify...",
  "conflict_detected": true,
  "resolution_strategy": "CLARIFICATION_REQUEST",
  "confidence_adjustment": -0.2
}
```

### Storage Capacity Exceeded
```python
# Memory management when storage limits reached
{
  "response": "Generated response with available context",
  "memory_action": "OLDEST_CONVERSATIONS_ARCHIVED",
  "retention_policy": "PRIORITY_BASED_CLEANUP",
  "capacity_status": "OPTIMIZED"
}
```

## Testing Strategy

### Unit Tests
- Memory storage and retrieval operations
- Context integration and ranking algorithms
- User preference learning and adaptation
- Memory cleanup and archival processes

### Integration Tests
- End-to-end conversation flow with memory
- Cross-conversation learning validation
- Performance testing with large memory datasets
- Database consistency and integrity checks

### Behavioral Tests
- Long-term conversation consistency
- Personalization effectiveness measurement
- Memory relevance and accuracy assessment
- Privacy compliance validation

### Performance Tests
- Memory retrieval latency under load
- Concurrent conversation handling capacity
- Database query optimization validation
- Memory usage profiling and optimization

## Implementation Details

### Key Components
1. **Memory Manager**: Handles storage, retrieval, and indexing of conversation data
2. **Context Assembler**: Integrates relevant memories into coherent context
3. **Personalization Engine**: Learns and applies user-specific preferences
4. **Relevance Scorer**: Ranks memory importance for context selection
5. **Privacy Controller**: Manages data retention and user consent

### Algorithms
- **Semantic Similarity**: Vector embeddings for topic-based memory retrieval
- **Temporal Decay**: Time-based importance weighting for memory relevance
- **Preference Learning**: Reinforcement learning for user personalization
- **Memory Consolidation**: Periodic compression and importance re-ranking
- **Context Window Management**: Sliding window with relevance-based selection
