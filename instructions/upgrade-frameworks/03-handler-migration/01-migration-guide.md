# Handler Migration Guide: From WorkflowBuilder to @app.handler()

**Version**: Nexus 1.2.0+
**Date**: 2026-02-09
**Audience**: Codegen Agents, Production Teams

## Executive Summary

This guide provides authoritative patterns for migrating Nexus workflows from the legacy `WorkflowBuilder` + `PythonCodeNode` pattern to the new `@app.handler()` decorator pattern introduced in Nexus v1.2.0.

**Key Benefits of Migration**:

- **80% code reduction** (~40 lines -> ~10 lines per workflow)
- **No sandbox restrictions** (full Python access)
- **Direct function testing** (no workflow execution needed)
- **Type safety** (IDE autocomplete, linting)
- **Automatic multi-channel deployment** (API + CLI + MCP)

---

## Pattern 1: Simple CRUD Workflow

### Before: Legacy Pattern (~40 lines)

```python
# File: workflows/conversation.py
from kailash.workflow.builder import WorkflowBuilder

def create_conversation_workflow():
    """Create a new conversation for a user."""
    workflow = WorkflowBuilder()

    # Input validation node
    workflow.add_node("PythonCodeNode", "validate_input", {
        "code": """
title = parameters.get('title', 'Untitled')
user_id = parameters.get('user_id')

if not user_id:
    raise ValueError("user_id is required")

result = {'validated_title': title, 'validated_user_id': user_id}
"""
    })

    # Creation node (simulated - real would use DataFlow)
    workflow.add_node("PythonCodeNode", "create", {
        "code": """
import json
from datetime import datetime

validated_title = parameters.get('validated_title', 'Untitled')
validated_user_id = parameters.get('validated_user_id')

# Simulated DB insert
conversation = {
    'id': f'conv_{hash(validated_title) % 10000}',
    'title': validated_title,
    'user_id': validated_user_id,
    'created_at': datetime.now().isoformat()
}

result = {'conversation': conversation}
"""
    })

    workflow.add_connection("validate_input", "validated_title", "create", "validated_title")
    workflow.add_connection("validate_input", "validated_user_id", "create", "validated_user_id")

    return workflow


# File: api/app.py
from nexus import Nexus
from workflows.conversation import create_conversation_workflow

app = Nexus(api_port=8000)
app.register("create_conversation", create_conversation_workflow().build())
```

### After: Handler Pattern (~10 lines)

```python
# File: api/app.py
from nexus import Nexus
from datetime import datetime

app = Nexus(api_port=8000)

@app.handler("create_conversation", description="Create a new conversation")
async def create_conversation(title: str = "Untitled", user_id: str = None) -> dict:
    """Create a new conversation for a user."""
    if not user_id:
        raise ValueError("user_id is required")

    # Full Python access - no sandbox restrictions
    conversation = {
        'id': f'conv_{hash(title) % 10000}',
        'title': title,
        'user_id': user_id,
        'created_at': datetime.now().isoformat()
    }

    return {"conversation": conversation}
```

**Code Reduction**: ~40 lines -> ~15 lines (62% reduction)

---

## Pattern 2: Multi-Step Workflow with Validation

### Before: Legacy Pattern (~60 lines)

```python
# File: workflows/order.py
from kailash.workflow.builder import WorkflowBuilder

def create_order_workflow():
    workflow = WorkflowBuilder()

    # Step 1: Validate order data
    workflow.add_node("PythonCodeNode", "validate", {
        "code": """
import json

items = parameters.get('items', [])
customer_id = parameters.get('customer_id')

if not customer_id:
    raise ValueError("customer_id is required")
if not items or len(items) == 0:
    raise ValueError("Order must have at least one item")

# Validate each item
validated_items = []
for item in items:
    if 'product_id' not in item:
        raise ValueError("Each item must have product_id")
    if 'quantity' not in item or item['quantity'] < 1:
        raise ValueError("Each item must have quantity >= 1")
    validated_items.append({
        'product_id': item['product_id'],
        'quantity': int(item['quantity']),
        'price': float(item.get('price', 0))
    })

result = {'validated_items': validated_items, 'customer_id': customer_id}
"""
    })

    # Step 2: Calculate totals
    workflow.add_node("PythonCodeNode", "calculate", {
        "code": """
validated_items = parameters.get('validated_items', [])

subtotal = sum(item['quantity'] * item['price'] for item in validated_items)
tax = subtotal * 0.08  # 8% tax
total = subtotal + tax

result = {
    'subtotal': round(subtotal, 2),
    'tax': round(tax, 2),
    'total': round(total, 2),
    'item_count': len(validated_items)
}
"""
    })

    # Step 3: Create order record
    workflow.add_node("PythonCodeNode", "create_order", {
        "code": """
from datetime import datetime

customer_id = parameters.get('customer_id')
subtotal = parameters.get('subtotal')
tax = parameters.get('tax')
total = parameters.get('total')
item_count = parameters.get('item_count')

order = {
    'order_id': f'ORD-{datetime.now().strftime("%Y%m%d%H%M%S")}',
    'customer_id': customer_id,
    'subtotal': subtotal,
    'tax': tax,
    'total': total,
    'item_count': item_count,
    'status': 'pending',
    'created_at': datetime.now().isoformat()
}

result = {'order': order}
"""
    })

    workflow.add_connection("validate", "validated_items", "calculate", "validated_items")
    workflow.add_connection("validate", "customer_id", "create_order", "customer_id")
    workflow.add_connection("calculate", "subtotal", "create_order", "subtotal")
    workflow.add_connection("calculate", "tax", "create_order", "tax")
    workflow.add_connection("calculate", "total", "create_order", "total")
    workflow.add_connection("calculate", "item_count", "create_order", "item_count")

    return workflow
```

### After: Handler Pattern (~25 lines)

```python
# File: api/app.py
from nexus import Nexus
from datetime import datetime
from typing import List, Optional

app = Nexus(api_port=8000)

@app.handler("create_order", description="Create an order with validation and tax calculation")
async def create_order(customer_id: str, items: List[dict]) -> dict:
    """Create a new order with automatic tax calculation."""
    if not customer_id:
        raise ValueError("customer_id is required")
    if not items or len(items) == 0:
        raise ValueError("Order must have at least one item")

    # Validate items
    validated_items = []
    for item in items:
        if 'product_id' not in item:
            raise ValueError("Each item must have product_id")
        if 'quantity' not in item or item['quantity'] < 1:
            raise ValueError("Each item must have quantity >= 1")
        validated_items.append({
            'product_id': item['product_id'],
            'quantity': int(item['quantity']),
            'price': float(item.get('price', 0))
        })

    # Calculate totals
    subtotal = sum(item['quantity'] * item['price'] for item in validated_items)
    tax = subtotal * 0.08
    total = subtotal + tax

    # Create order
    order = {
        'order_id': f'ORD-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'customer_id': customer_id,
        'items': validated_items,
        'subtotal': round(subtotal, 2),
        'tax': round(tax, 2),
        'total': round(total, 2),
        'status': 'pending',
        'created_at': datetime.now().isoformat()
    }

    return {"order": order}
```

**Code Reduction**: ~70 lines -> ~35 lines (50% reduction)

---

## Pattern 3: Workflow with DataFlow Operations

### Before: Legacy Pattern with Service Workaround

The legacy pattern cannot directly use DataFlow because `PythonCodeNode` blocks asyncio imports.

```python
# File: workflows/contacts.py
# BROKEN at runtime - PythonCodeNode sandbox blocks service imports
def create_search_contacts_workflow():
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "search", {
        "code": """
# This FAILS at runtime:
# SecurityError: Import of 'asyncio' is not allowed
# SecurityError: Import of 'my_app.services' is not allowed
from my_app.services import ContactService

search_text = parameters.get('search_text', '')
page = parameters.get('page', 1)
page_size = parameters.get('page_size', 20)

service = ContactService()
results = await service.search(search_text, page, page_size)  # FAILS
result = {'contacts': results}
"""
    })

    return workflow
```

### After: Handler Pattern with Full DataFlow Access

```python
# File: api/app.py
from nexus import Nexus
from dataflow import DataFlow
from typing import Optional

app = Nexus(api_port=8000, auto_discovery=False)

# Initialize DataFlow with Nexus-compatible settings
db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,  # Prevents blocking
    auto_migrate=False,
    skip_migration=True
)

@db.model
class Contact:
    id: int
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None

@app.handler("search_contacts", description="Search contacts by text")
async def search_contacts(
    search_text: str = "",
    page: int = 1,
    page_size: int = 20
) -> dict:
    """Search contacts with pagination."""
    # Full DataFlow access - no sandbox restrictions
    offset = (page - 1) * page_size

    results = await db.execute_async(
        db.Contact.LIST,
        filter={
            "$or": [
                {"name": {"$contains": search_text}},
                {"email": {"$contains": search_text}},
                {"company": {"$contains": search_text}}
            ]
        },
        limit=page_size,
        offset=offset
    )

    total = await db.execute_async(db.Contact.COUNT, filter={})

    return {
        "contacts": results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }
```

---

## Pattern 4: Workflow with AI/Kaizen Agent Calls

### Before: Legacy Pattern (Impossible with Sandbox)

```python
# BROKEN - PythonCodeNode cannot import kaizen or make async AI calls
def create_ai_analysis_workflow():
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "analyze", {
        "code": """
# This FAILS at runtime:
# SecurityError: Import of 'kaizen' is not allowed
from kaizen.api import Agent

text = parameters.get('text', '')
agent = Agent(model="gpt-4")
analysis = await agent.run(f"Analyze this text: {text}")  # FAILS
result = {'analysis': analysis}
"""
    })

    return workflow
```

### After: Handler Pattern with Full Kaizen Access

```python
# File: api/app.py
from nexus import Nexus
from kaizen.api import Agent
from typing import Optional

app = Nexus(api_port=8000)

# Initialize Kaizen agent
analyst = Agent(
    model="gpt-4",
    execution_mode="autonomous",
    system_prompt="You are a text analysis expert."
)

@app.handler("analyze_text", description="Analyze text using AI")
async def analyze_text(
    text: str,
    analysis_type: str = "sentiment",
    include_summary: bool = True
) -> dict:
    """Analyze text using Kaizen AI agent."""
    # Full Kaizen access - no sandbox restrictions
    prompt = f"""
    Analyze the following text for {analysis_type}:

    {text}

    {"Include a brief summary." if include_summary else ""}
    """

    result = await analyst.run(prompt)

    return {
        "analysis": result,
        "analysis_type": analysis_type,
        "text_length": len(text)
    }

@app.handler("summarize_document", description="Summarize a document")
async def summarize_document(
    document: str,
    max_length: int = 200,
    style: str = "professional"
) -> dict:
    """Generate document summary using AI."""
    prompt = f"""
    Summarize the following document in {style} style.
    Maximum {max_length} words.

    Document:
    {document}
    """

    summary = await analyst.run(prompt)

    return {
        "summary": summary,
        "original_length": len(document.split()),
        "style": style
    }
```

---

## Pattern 5: Workflow with SSE Streaming Response

### Before: Legacy Pattern (Not Possible)

SSE streaming is not possible with `PythonCodeNode` as it requires access to FastAPI's `StreamingResponse` and async generators.

### After: Handler Pattern with Streaming

```python
# File: api/app.py
from nexus import Nexus
from kaizen.api import Agent
from typing import AsyncGenerator
import json

app = Nexus(api_port=8000)

# For streaming, register a custom endpoint alongside the handler
# The handler provides multi-channel access, the endpoint provides streaming

@app.handler("chat", description="Chat with AI (non-streaming)")
async def chat(message: str, conversation_id: str = None) -> dict:
    """Chat with AI - returns complete response."""
    agent = Agent(model="gpt-4")
    response = await agent.run(message)
    return {"response": response, "conversation_id": conversation_id}

# For streaming, use @app.endpoint() which is API-only
@app.endpoint("/api/chat/stream", methods=["POST"])
async def chat_stream(request):
    """Stream chat responses via SSE."""
    from fastapi.responses import StreamingResponse

    data = await request.json()
    message = data.get("message", "")

    async def generate():
        agent = Agent(model="gpt-4", streaming=True)
        async for chunk in agent.stream(message):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )
```

---

## Migration Checklist

### Phase 1: Audit Existing Workflows

- [ ] List all `app.register()` calls in the codebase
- [ ] Categorize each workflow:
  - **Simple**: Single-node, pure data transformation -> Migrate to `@app.handler()`
  - **Complex**: Multi-node with dependencies -> Keep as `app.register()` OR refactor to handler
  - **Blocked**: Uses imports blocked by sandbox -> MUST migrate to `@app.handler()`

### Phase 2: Migrate Simple Workflows

- [ ] For each simple workflow:
  - [ ] Extract the logic from `PythonCodeNode` code strings
  - [ ] Convert to async function with proper type hints
  - [ ] Register with `@app.handler()` decorator
  - [ ] Remove old workflow file

### Phase 3: Migrate Complex Workflows

- [ ] For each complex workflow:
  - [ ] Determine if multi-node structure is necessary
  - [ ] If not: Combine into single handler function
  - [ ] If yes: Keep as `app.register()` but consider `@app.handler()` for sub-functions

### Phase 4: Handle Service Dependencies

- [ ] For workflows using services/DataFlow:
  - [ ] Move service initialization to module level
  - [ ] Use dependency injection pattern in handlers
  - [ ] Ensure async initialization is handled properly

### Phase 5: Update Tests

- [ ] Convert workflow execution tests to direct handler tests
- [ ] Test handler functions independently (no workflow needed)
- [ ] Add integration tests for multi-channel access
- [ ] Verify API, CLI, and MCP channels all work

### Phase 6: Cleanup

- [ ] Remove duplicate FastAPI endpoint registrations (handlers auto-expose)
- [ ] Delete orphaned workflow files
- [ ] Update documentation

---

## When NOT to Migrate

Keep using `app.register()` with `WorkflowBuilder` when:

1. **Complex Multi-Node Workflows with Branching**

   ```python
   # Keep as WorkflowBuilder if you need:
   # - Conditional execution between nodes
   # - Parallel node execution
   # - Node-level monitoring/logging
   workflow.add_connection("validate", "is_valid", "process", "input")
   workflow.add_connection("validate", "is_invalid", "reject", "reason")
   ```

2. **Workflows Using Cycle Patterns**

   ```python
   # Cyclic workflows need WorkflowBuilder
   workflow.add_connection("process", "needs_retry", "process", "input")
   ```

3. **Workflows Requiring Fine-Grained Node Monitoring**

   ```python
   # If you need per-node metrics, keep WorkflowBuilder
   # Handlers execute as a single unit
   ```

4. **Workflows Composed from Reusable Node Libraries**
   ```python
   # If you have shared node definitions across workflows
   # WorkflowBuilder allows node reuse
   ```

---

## Quick Reference: API Comparison

| Feature        | Legacy (`app.register()`)            | Handler (`@app.handler()`)   |
| -------------- | ------------------------------------ | ---------------------------- |
| Lines of code  | ~40-60 per workflow                  | ~10-20 per workflow          |
| Sandbox        | Restricted (no asyncio, no services) | Unrestricted (full Python)   |
| Type hints     | Not supported                        | Full support                 |
| IDE support    | None (code strings)                  | Full (autocomplete, linting) |
| Direct testing | Requires workflow execution          | Test function directly       |
| Multi-channel  | Automatic                            | Automatic                    |
| Use when       | Complex multi-node flows             | Simple-to-moderate logic     |

---

## File Locations

- Handler implementation: `src/kailash/nodes/handler.py`
- Nexus handler API: `apps/kailash-nexus/src/nexus/core.py` (lines 790-880)
- Test examples: `apps/kailash-nexus/tests/integration/test_handler_execution.py`
- E2E examples: `apps/kailash-nexus/tests/e2e/test_handler_e2e.py`
