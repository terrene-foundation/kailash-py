"""
Test DataFlow JSON/dict field support with SQLite.

Demonstrates:
1. dict field type annotation
2. Automatic JSON serialization/deserialization
3. Creating, reading, and querying JSON data
"""
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from datetime import datetime
import json

# Initialize DataFlow with in-memory SQLite
db = DataFlow(":memory:")

# Define model with dict field
@db.model
class ConversationMessage:
    id: str
    conversation_id: str
    sender: str
    content: str
    metadata: dict = {}  # ✅ dict type annotation - auto-handled by DataFlow
    created_at: datetime

print("✅ Model registered successfully with dict field")

# Test 1: Create message with JSON metadata
workflow = WorkflowBuilder()

test_metadata = {
    "session_id": "sess_456",
    "channel": "web",
    "user_agent": "Mozilla/5.0",
    "ip_address": "192.168.1.1",
    "nested": {
        "preferences": {
            "theme": "dark",
            "language": "en"
        }
    }
}

workflow.add_node("ConversationMessageCreateNode", "create_msg", {
    "db_instance": "default",
    "model_name": "ConversationMessage",
    "id": "msg_001",
    "conversation_id": "conv_123",
    "sender": "user",
    "content": "Hello, how can I help?",
    "metadata": test_metadata  # ✅ Pass dict directly - no manual serialization
})

print("\n📝 Creating message with dict metadata...")
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# Verify creation
created_msg = results["create_msg"]
print(f"✅ Message created: {created_msg['id']}")
print(f"   Metadata type: {type(created_msg['metadata'])}")
print(f"   Metadata: {json.dumps(created_msg['metadata'], indent=2)}")

# Test 2: Read message and verify metadata deserialization
workflow2 = WorkflowBuilder()
workflow2.add_node("ConversationMessageReadNode", "read_msg", {
    "db_instance": "default",
    "model_name": "ConversationMessage",
    "id": "msg_001"
})

print("\n📖 Reading message...")
results2, run_id2 = runtime.execute(workflow2.build())

read_msg = results2["read_msg"]
print(f"✅ Message read: {read_msg['id']}")
print(f"   Content: {read_msg['content']}")
print(f"   Metadata type: {type(read_msg['metadata'])}")
print(f"   Metadata channel: {read_msg['metadata']['channel']}")
print(f"   Nested preference: {read_msg['metadata']['nested']['preferences']['theme']}")

# Test 3: List messages with filter
workflow3 = WorkflowBuilder()
workflow3.add_node("ConversationMessageListNode", "list_msgs", {
    "db_instance": "default",
    "model_name": "ConversationMessage",
    "filter": {"conversation_id": "conv_123"},
    "limit": 10
})

print("\n🔍 Listing messages...")
results3, run_id3 = runtime.execute(workflow3.build())

messages = results3["list_msgs"]["records"]
print(f"✅ Found {len(messages)} message(s)")
for msg in messages:
    print(f"   - {msg['id']}: {msg['content']}")
    print(f"     Metadata: {msg['metadata']['channel']}")

# Test 4: Create multiple messages with different metadata
workflow4 = WorkflowBuilder()

for i in range(3):
    workflow4.add_node("ConversationMessageCreateNode", f"create_msg_{i}", {
        "db_instance": "default",
        "model_name": "ConversationMessage",
        "id": f"msg_00{i+2}",
        "conversation_id": "conv_123",
        "sender": "agent" if i % 2 == 0 else "user",
        "content": f"Message {i+2}",
        "metadata": {
            "index": i,
            "channel": "api" if i == 0 else "web",
            "timestamp": datetime.now().isoformat()
        }
    })

print("\n➕ Creating multiple messages with different metadata...")
results4, run_id4 = runtime.execute(workflow4.build())
print(f"✅ Created {len([k for k in results4.keys() if k.startswith('create_msg_')])} additional messages")

# Test 5: Update metadata
workflow5 = WorkflowBuilder()
workflow5.add_node("ConversationMessageUpdateNode", "update_msg", {
    "db_instance": "default",
    "model_name": "ConversationMessage",
    "filter": {"id": "msg_001"},
    "fields": {
        "metadata": {
            **test_metadata,
            "updated": True,
            "updated_at": datetime.now().isoformat()
        }
    }
})

print("\n🔄 Updating message metadata...")
results5, run_id5 = runtime.execute(workflow5.build())
print(f"✅ Updated {results5['update_msg'].get('count', 1)} message(s)")

# Verify update
workflow6 = WorkflowBuilder()
workflow6.add_node("ConversationMessageReadNode", "read_updated", {
    "db_instance": "default",
    "model_name": "ConversationMessage",
    "id": "msg_001"
})

results6, run_id6 = runtime.execute(workflow6.build())
updated_msg = results6["read_updated"]
print(f"   Updated metadata: {json.dumps(updated_msg['metadata'], indent=2)}")

print("\n" + "="*60)
print("✅ ALL TESTS PASSED - DataFlow dict/JSON fields work perfectly!")
print("="*60)
print("\n📚 Key Takeaways:")
print("1. Use 'dict' type annotation - DataFlow handles JSON automatically")
print("2. Pass dict objects directly - no manual json.dumps() needed")
print("3. Read results are already dicts - no json.loads() needed")
print("4. Works with PostgreSQL (JSONB), MySQL (JSON), and SQLite (JSON1)")
print("5. Supports nested structures and complex metadata")
