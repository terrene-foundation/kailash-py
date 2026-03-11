# Customer Support Agent - Persistent Conversation Memory

## Overview

Production-ready customer support agent with persistent conversation memory that survives application restarts. The agent automatically loads conversation history, learns user preferences, and provides personalized responses based on past interactions across multiple sessions.

**Key Features:**
- **Cross-Session Persistence**: Conversations survive restarts
- **User Preference Learning**: Detects communication style and topics
- **Automatic Context Loading**: Seamless conversation continuity
- **Auto-Persist**: Saves every 5 messages automatically
- **JSONL Compression**: 60%+ size reduction for efficient storage
- **Budget Tracking**: $0.00 cost with Ollama (FREE local inference)

## Prerequisites

- **Python 3.8+**
- **Ollama** with llama3.1:8b-instruct-q8_0 model (FREE - local inference)
- **kailash-kaizen** (`pip install kailash-kaizen`)
- **kailash-dataflow** (`pip install kailash-dataflow`)

## Installation

```bash
# 1. Install Ollama
# macOS:
brew install ollama

# Linux:
curl -fsSL https://ollama.ai/install.sh | sh

# Windows: Download from https://ollama.ai

# 2. Start Ollama service
ollama serve

# 3. Pull model (first time only)
ollama pull llama3.1:8b-instruct-q8_0

# 4. Install dependencies
pip install kailash-kaizen kailash-dataflow
```

## Usage

```bash
python customer_support_agent.py
```

The agent will simulate a multi-session customer support conversation demonstrating:
- Session 1: Initial support inquiry (new customer)
- Session 2: Follow-up question (remembers context from Session 1)
- Session 3: Related issue (learns preferences from Sessions 1-2)
- Cross-session persistence and context continuity

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│               CUSTOMER SUPPORT AGENT                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         PERSISTENT BUFFER MEMORY                         │ │
│  ├──────────────────────────────────────────────────────────┤ │
│  │                                                          │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │  IN-MEMORY BUFFER (Hot Cache)                   │   │ │
│  │  │  - Size: Last 50 turns                           │   │ │
│  │  │  - TTL: 30 minutes                               │   │ │
│  │  │  - Access: < 1ms                                 │   │ │
│  │  │  - Use: Active conversation context              │   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  │                       ↑ auto-load                        │ │
│  │                       ↓ auto-persist (every 5 messages)  │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │  DATABASE STORAGE (Persistent)                  │   │ │
│  │  │  - Backend: DataFlowBackend                      │   │ │
│  │  │  - Storage: SQLite/PostgreSQL                    │   │ │
│  │  │  - Compression: JSONL (60%+ reduction)           │   │ │
│  │  │  - Capacity: Unlimited                           │   │ │
│  │  │  - Use: Full conversation archive                │   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  │                                                          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         BaseAgent (Support Logic)                        │ │
│  │  - Load conversation history                             │ │
│  │  - Extract user preferences                              │ │
│  │  - Generate personalized responses                       │ │
│  │  - Auto-persist every 5 messages                         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │         ConversationAnalyticsHook                        │ │
│  │  - Track conversation turns                              │ │
│  │  - Calculate resolution rates                            │ │
│  │  - Monitor response quality (confidence scores)          │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

## Persistent Memory Flow

```
SESSION 1 (Day 1):
┌─────────────────────────────────────────────────────────┐
│ User: "I can't login"                                   │
│ Agent: "Let me help. What error message?"              │
│ ────────────────────────────────────────────────────── │
│ ✅ Saved to memory buffer                              │
│ ✅ Auto-persisted to database                          │
└─────────────────────────────────────────────────────────┘

[Application Restart - All state lost in vanilla systems]

SESSION 2 (Day 2 - NEW PROCESS):
┌─────────────────────────────────────────────────────────┐
│ 🔄 Agent restarted - Loading history...                │
│ ✅ Loaded 2 turns from database (Session 1)            │
│                                                         │
│ User: "Did you send the reset email?"                  │
│ Agent: "Yes, I sent it yesterday after your login      │
│         issue. Let me resend it."                      │
│ ────────────────────────────────────────────────────── │
│ ✅ Context preserved! Agent remembers Session 1        │
│ ✅ Saved to memory buffer                              │
│ ✅ Auto-persisted to database                          │
└─────────────────────────────────────────────────────────┘

[Application Restart Again]

SESSION 3 (Day 3 - NEW PROCESS):
┌─────────────────────────────────────────────────────────┐
│ 🔄 Agent restarted - Loading history...                │
│ ✅ Loaded 4 turns from database (Sessions 1-2)         │
│ ✅ Learned user preferences:                           │
│    - Communication style: Formal                        │
│    - Common topics: login, billing                      │
│                                                         │
│ User: "How do I update billing info?"                  │
│ Agent: "I'd be happy to assist with your billing.      │
│         [Formal tone detected from history]            │
│ ────────────────────────────────────────────────────── │
│ ✅ Personalized response based on learned preferences  │
│ ✅ All 5 turns preserved across 3 sessions             │
└─────────────────────────────────────────────────────────┘
```

## Expected Output

```
================================================================================
CUSTOMER SUPPORT - MULTI-SESSION CONVERSATION
================================================================================

--------------------------------------------------------------------------------
SESSION 1 (Day 1) - Initial Support Inquiry
--------------------------------------------------------------------------------

👤 User: Hi, I can't login to my account. It says 'invalid password'.
🤖 Agent: I'm sorry to hear you're having trouble logging in. Let me help you reset your password.
   [Confidence: 0.85, Resolved: False]

👤 User: I tried resetting my password but didn't receive the email.
🤖 Agent: I'll check our email logs and resend the password reset link to your email address.
   [Confidence: 0.78, Resolved: False]

👤 User: My email is alice@example.com. Can you check?
🤖 Agent: Thank you. I've verified your email and sent a new password reset link to alice@example.com.
   [Confidence: 0.92, Resolved: True]

📊 SESSION 1 STATS:
   Turns: 3
   Total history: 3 turns
   Budget: $0.00 (FREE with Ollama)

--------------------------------------------------------------------------------
SESSION 2 (Day 2) - Follow-up Question (NEW SESSION)
--------------------------------------------------------------------------------

👤 User: Did you send the password reset email?
🤖 Agent: Yes, I sent the password reset link to alice@example.com yesterday after you reported the login issue.
   [Confidence: 0.88, Resolved: False, History: 4 turns]

👤 User: I still haven't received it. Can you resend?
🤖 Agent: I'll resend the password reset link immediately. Please check your spam folder as well.
   [Confidence: 0.82, Resolved: True, History: 5 turns]

📊 SESSION 2 STATS:
   Current session turns: 2
   Total history: 5 turns (includes Session 1)
   ✅ Context preserved across sessions! (5 total turns from 2 sessions)

--------------------------------------------------------------------------------
SESSION 3 (Day 3) - Related Issue (NEW SESSION)
--------------------------------------------------------------------------------

👤 User: Great! I received the email and reset my password. Thanks!
🤖 Agent: Wonderful! I'm glad the password reset worked. Is there anything else I can help you with?
   [Confidence: 0.90, Resolved: True, Style: formal]

👤 User: Now I have another question - how do I update my billing information?
🤖 Agent: I'd be happy to assist with your billing information. You can update it in Account Settings > Billing.
   [Confidence: 0.87, Resolved: True, Style: formal]

📊 SESSION 3 STATS:
   Current session turns: 2
   Total history: 7 turns (all 3 sessions)
   User preferences learned:
     - Communication style: formal
     - Response length: medium
     - Common topics: login, billing

📈 CONVERSATION ANALYTICS:
   Total turns: 7
   Resolved conversations: 4
   Resolution rate: 57.1%
   Average confidence: 0.86

================================================================================
✅ Multi-session conversation completed successfully!
✅ Memory database: .kaizen/support_memory.db
✅ All 7 turns persisted across 3 sessions
================================================================================
```

## User Preference Learning

The agent automatically learns user preferences from conversation history:

### Communication Style Detection

**Formal Style** (detected keywords):
- "please", "thank you", "appreciate", "kindly"
- Agent responds with formal language

**Casual Style** (detected keywords):
- "hey", "thanks", "cool", "awesome"
- Agent responds with casual, friendly language

**Example:**
```python
# Formal user (3 uses of "please"):
User: "Could you please help me? I'd appreciate it."
Agent: "I'd be happy to assist you with that." [Formal tone]

# Casual user (2 uses of "thanks"):
User: "Hey, thanks for the help! That's awesome."
Agent: "No problem! Glad I could help!" [Casual tone]
```

### Response Length Preference

**Brief** (user messages < 50 characters):
- Agent provides concise, direct answers

**Detailed** (user messages > 150 characters):
- Agent provides comprehensive, explanatory responses

**Example:**
```python
# Brief preference:
User: "How do I reset?" [18 chars]
Agent: "Click 'Forgot Password' on login page." [Brief]

# Detailed preference:
User: "I'm having trouble resetting my password. I tried clicking..." [150+ chars]
Agent: "Let me walk you through the password reset process step by step..." [Detailed]
```

### Common Topics Tracking

Agent identifies frequently discussed topics:
- **Login**: password, authentication, sign in
- **Billing**: payment, invoice, subscription, charge
- **Technical**: error, bug, crash, not working
- **Account**: profile, settings

**Example:**
```python
# After 3 conversations about login issues:
preferences["common_topics"] = ["login", "account"]

# Agent proactively addresses login in future:
User: "I need help"
Agent: "Are you experiencing login issues again?" [Anticipates need]
```

## Configuration Options

### Memory Buffer Size

```python
memory = PersistentBufferMemory(
    backend=backend,
    max_turns=50,              # Last 50 turns in memory (default)
    cache_ttl_seconds=1800     # 30 minutes TTL (default)
)
```

**Recommendations:**
- **Small sessions** (< 10 turns): `max_turns=20`
- **Medium sessions** (10-50 turns): `max_turns=50` (default)
- **Large sessions** (50+ turns): `max_turns=100`

### Auto-Persist Frequency

The agent automatically persists every turn to the database. For high-frequency scenarios, you can batch writes:

```python
# Persist every N messages (reduce DB writes)
if self.session_turns % 5 == 0:
    self.memory.save_turn(customer_id, turn)
```

### Database Backend

**SQLite (Development/Small Scale)**:
```python
db = DataFlow(
    database_type="sqlite",
    database_config={"database": "./support_memory.db"}
)
```

**PostgreSQL (Production/Large Scale)**:
```python
db = DataFlow(
    database_type="postgresql",
    database_config={
        "host": "localhost",
        "port": 5432,
        "database": "support_db",
        "user": "support_user",
        "password": "secure_password"
    }
)
```

## Production Deployment

### Multi-Tenancy Isolation

```python
# Tenant A backend (isolated)
backend_a = DataFlowBackend(db, tenant_id="tenant_a")
agent_a = CustomerSupportAgent(config, db=db, customer_id="customer_alice")

# Tenant B backend (isolated, cannot see tenant_a data)
backend_b = DataFlowBackend(db, tenant_id="tenant_b")
agent_b = CustomerSupportAgent(config, db=db, customer_id="customer_bob")
```

### Scaling to Thousands of Customers

```python
# Each customer gets isolated memory
for customer_id in customer_ids:
    agent = CustomerSupportAgent(
        config=config,
        db=db,
        customer_id=customer_id
    )
    response = agent.respond(user_message)
```

**Performance:**
- SQLite: 1,000-10,000 customers
- PostgreSQL: 100,000+ customers (horizontal scaling)

### Conversation Analytics

```python
# Get analytics across all customers
analytics = agent.analytics_hook.get_summary()

print(f"Total turns: {analytics['total_turns']}")
print(f"Resolution rate: {analytics['resolution_rate']}%")
print(f"Average confidence: {analytics['average_confidence']}")
```

## Troubleshooting

### Issue: Context not loading across sessions

**Cause**: Database file path incorrect or permissions issue

**Solution:**
```bash
# Check database file exists
ls -la .kaizen/support_memory.db

# Ensure write permissions
chmod 644 .kaizen/support_memory.db
```

### Issue: Memory buffer too small, context truncated

**Cause**: `max_turns` too low for long conversations

**Solution:**
```python
# Increase buffer size
memory = PersistentBufferMemory(
    backend=backend,
    max_turns=100,  # Increase from default 50
    cache_ttl_seconds=3600  # 1 hour
)
```

### Issue: User preferences not detected

**Cause**: Not enough conversation history (< 3 turns)

**Solution:**
- Wait for at least 3 turns before expecting preference detection
- Lower detection thresholds in `_extract_user_preferences()`

### Issue: Database file too large

**Cause**: Many customers with long conversation histories

**Solution:**
```python
# Enable JSONL compression (60%+ reduction)
# Already enabled by default in DataFlowBackend

# Or prune old conversations
backend.clear_session(customer_id)  # Remove old data
```

## Performance Metrics

| Operation | Target | Typical | Notes |
|-----------|--------|---------|-------|
| **Load history** | < 50ms | 20-35ms | First load from DB |
| **Save turn** | < 10ms | 5-8ms | Write to DB |
| **Cache hit** | < 1ms | 0.3-0.7ms | Memory read |
| **Preference extraction** | < 5ms | 2-4ms | Keyword analysis |

## Cost Analysis

**With Ollama (Recommended)**:
- LLM Inference: $0.00 (FREE - local inference)
- Database: $0.00 (SQLite local file)
- Total: **$0.00 per conversation**

**With OpenAI (Alternative)**:
- LLM Inference: ~$0.02 per 10 turns (gpt-3.5-turbo)
- Database: $0.00 (SQLite local file)
- Total: **~$0.002 per turn**

## Best Practices

1. **Set Appropriate Buffer Size**: 50 turns for typical support conversations
2. **Enable Auto-Persist**: Save every turn to prevent data loss
3. **Monitor Analytics**: Track resolution rates and confidence scores
4. **Use PostgreSQL for Production**: Better performance with thousands of customers
5. **Implement Tenant Isolation**: Separate customer data for compliance
6. **Archive Old Conversations**: Prune conversations older than 90 days

## Integration with Other Systems

### With Ticketing Systems

```python
# Create ticket when conversation starts
ticket_id = create_ticket(customer_id, first_message)

# Link conversation to ticket
agent.respond(user_message, metadata={"ticket_id": ticket_id})
```

### With CRM Systems

```python
# Load customer profile from CRM
customer_profile = crm.get_profile(customer_id)

# Inject profile into conversation context
agent.respond(user_message, customer_profile=customer_profile)
```

### With Analytics Platforms

```python
# Export conversation analytics
analytics = agent.analytics_hook.get_summary()
analytics_platform.log_metrics(analytics)
```

## References

- **Memory System Guide**: [docs/guides/memory-and-learning-system.md](../../../../docs/guides/memory-and-learning-system.md)
- **PersistentBufferMemory API**: [src/kaizen/memory/persistent_buffer.py](../../../../src/kaizen/memory/persistent_buffer.py)
- **DataFlow Integration**: [src/kaizen/memory/backends/dataflow_backend.py](../../../../src/kaizen/memory/backends/dataflow_backend.py)
- **BaseAgent Architecture**: [docs/guides/baseagent-architecture.md](../../../../docs/guides/baseagent-architecture.md)

## License

MIT License - see LICENSE file for details
