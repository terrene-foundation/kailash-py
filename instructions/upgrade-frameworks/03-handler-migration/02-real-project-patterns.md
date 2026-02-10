# Real Project Migration Patterns

**Version**: Nexus 1.2.0+
**Date**: 2026-02-09
**Audience**: Codegen Agents, Production Teams

## Overview

This document provides concrete migration examples based on patterns observed in three production projects:

- **example-backend**: Chat/conversation management (30+ workflows, ~5,400 LOC)
- **example-project**: Investment tracking and CRM (~380 workflows, ~13,700 LOC)
- **enterprise-app**: Multi-agent orchestration (20+ workflows, ~1,700 LOC)

All three projects currently use the legacy pattern and can benefit significantly from handler migration.

---

## example-backend Patterns

### Pattern 1: Create Conversation Workflow

**Before: Legacy Pattern (example-app style)**

```python
# File: example-app/workflows/conversation.py
from kailash.workflow.builder import WorkflowBuilder

def create_conversation_workflow():
    """Create a new conversation with system message."""
    workflow = WorkflowBuilder()

    # Step 1: Validate and prepare input
    workflow.add_node("PythonCodeNode", "prepare", {
        "code": """
import json
from datetime import datetime

title = parameters.get('title', 'New Conversation')
user_id = parameters.get('user_id')
model = parameters.get('model', 'gpt-4')
system_prompt = parameters.get('system_prompt', 'You are a helpful assistant.')

if not user_id:
    raise ValueError("user_id is required")

conversation_data = {
    'title': title,
    'user_id': user_id,
    'model': model,
    'system_prompt': system_prompt,
    'created_at': datetime.now().isoformat()
}

result = {'conversation_data': conversation_data}
"""
    })

    # Step 2: Create conversation record (simulated)
    workflow.add_node("PythonCodeNode", "create_record", {
        "code": """
import json
import uuid

conversation_data = parameters.get('conversation_data', {})

# Generate conversation ID
conv_id = str(uuid.uuid4())

# Create full record
conversation = {
    'id': conv_id,
    **conversation_data,
    'messages': [{
        'role': 'system',
        'content': conversation_data.get('system_prompt', ''),
        'timestamp': conversation_data.get('created_at')
    }],
    'message_count': 1
}

result = {'conversation': conversation}
"""
    })

    workflow.add_connection("prepare", "conversation_data", "create_record", "conversation_data")
    return workflow


# File: example-app/api/app.py
from nexus import Nexus
from example-app.workflows.conversation import create_conversation_workflow

app = Nexus(api_port=8000)
app.register("create_conversation", create_conversation_workflow().build())

# Separate FastAPI endpoint often added
from fastapi import APIRouter, Request
router = APIRouter()

@router.post("/api/conversations")
async def create_conversation_endpoint(request: Request):
    """Custom endpoint wrapping the workflow."""
    data = await request.json()
    results, _ = await runtime.execute_workflow_async(
        app._workflows["create_conversation"],
        inputs=data
    )
    return results.get("create_record", {}).get("conversation", {})

app._gateway.app.include_router(router)
```

**After: Handler Pattern**

```python
# File: example-app/api/app.py
from nexus import Nexus
from datetime import datetime
from typing import Optional
import uuid

app = Nexus(api_port=8000)

@app.handler("create_conversation", description="Create a new conversation with system message")
async def create_conversation(
    user_id: str,
    title: str = "New Conversation",
    model: str = "gpt-4",
    system_prompt: str = "You are a helpful assistant."
) -> dict:
    """Create a new conversation for a user."""
    conv_id = str(uuid.uuid4())
    created_at = datetime.now().isoformat()

    conversation = {
        'id': conv_id,
        'title': title,
        'user_id': user_id,
        'model': model,
        'system_prompt': system_prompt,
        'created_at': created_at,
        'messages': [{
            'role': 'system',
            'content': system_prompt,
            'timestamp': created_at
        }],
        'message_count': 1
    }

    return {"conversation": conversation}

# No need for separate FastAPI endpoint - handler auto-exposes at:
# POST /workflows/create_conversation/execute
```

**Reduction**: ~55 lines -> ~25 lines (55% reduction)

---

### Pattern 2: List Conversations Workflow

**Before: Legacy Pattern**

```python
# File: example-app/workflows/conversation.py
def list_conversations_workflow():
    """List conversations for a user with pagination."""
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "list", {
        "code": """
import json

user_id = parameters.get('user_id')
page = int(parameters.get('page', 1))
page_size = int(parameters.get('page_size', 20))
sort_by = parameters.get('sort_by', 'created_at')
sort_order = parameters.get('sort_order', 'desc')

if not user_id:
    raise ValueError("user_id is required")

# Simulated database query
# In production: would query ConversationService
offset = (page - 1) * page_size

# Mock data for demo
conversations = [
    {
        'id': f'conv_{i}',
        'title': f'Conversation {i}',
        'user_id': user_id,
        'message_count': i * 5,
        'created_at': '2025-01-15T10:00:00Z'
    }
    for i in range(offset, min(offset + page_size, 100))
]

result = {
    'conversations': conversations,
    'pagination': {
        'page': page,
        'page_size': page_size,
        'total': 100,
        'total_pages': 5
    }
}
"""
    })

    return workflow

# Registration
app.register("list_conversations", list_conversations_workflow().build())
```

**After: Handler Pattern with DataFlow**

```python
# File: example-app/api/app.py
from nexus import Nexus
from dataflow import DataFlow
from typing import Optional

app = Nexus(api_port=8000, auto_discovery=False)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False
)

@db.model
class Conversation:
    id: str
    title: str
    user_id: str
    model: str = "gpt-4"
    system_prompt: str = "You are a helpful assistant."
    message_count: int = 0
    created_at: str = None

@app.handler("list_conversations", description="List conversations with pagination")
async def list_conversations(
    user_id: str,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "created_at",
    sort_order: str = "desc"
) -> dict:
    """List conversations for a user with pagination."""
    offset = (page - 1) * page_size

    conversations = await db.execute_async(
        db.Conversation.LIST,
        filter={"user_id": user_id},
        limit=page_size,
        offset=offset,
        order_by=[(sort_by, sort_order)]
    )

    total = await db.execute_async(
        db.Conversation.COUNT,
        filter={"user_id": user_id}
    )

    return {
        "conversations": conversations,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    }
```

**Reduction**: ~45 lines -> ~30 lines (33% reduction) + Real database access

---

### Pattern 3: Add Message Workflow (with AI)

**Before: Legacy Pattern (BROKEN - sandbox blocks AI)**

```python
# File: example-app/workflows/message.py
def add_message_workflow():
    """Add a message and get AI response."""
    workflow = WorkflowBuilder()

    # This FAILS at runtime due to sandbox restrictions
    workflow.add_node("PythonCodeNode", "process_message", {
        "code": """
# BROKEN: SecurityError - Import of 'openai' is not allowed
# BROKEN: SecurityError - Import of 'asyncio' is not allowed
import asyncio
from openai import AsyncOpenAI

conversation_id = parameters.get('conversation_id')
user_message = parameters.get('message')
model = parameters.get('model', 'gpt-4')

client = AsyncOpenAI()

# This async call FAILS in sandbox
response = await client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": user_message}]
)

result = {'response': response.choices[0].message.content}
"""
    })

    return workflow
```

**After: Handler Pattern with Full AI Access**

```python
# File: example-app/api/app.py
from nexus import Nexus
from kaizen.api import Agent
from dataflow import DataFlow
from datetime import datetime
from typing import Optional
import uuid

app = Nexus(api_port=8000, auto_discovery=False)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False
)

@db.model
class Message:
    id: str
    conversation_id: str
    role: str  # 'user', 'assistant', 'system'
    content: str
    created_at: str = None

@app.handler("add_message", description="Add a message and get AI response")
async def add_message(
    conversation_id: str,
    message: str,
    model: str = "gpt-4"
) -> dict:
    """Add user message and generate AI response."""
    now = datetime.now().isoformat()

    # Save user message
    user_msg = await db.execute_async(
        db.Message.CREATE,
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="user",
        content=message,
        created_at=now
    )

    # Get conversation history
    history = await db.execute_async(
        db.Message.LIST,
        filter={"conversation_id": conversation_id},
        order_by=[("created_at", "asc")]
    )

    # Generate AI response using Kaizen
    agent = Agent(model=model)
    ai_response = await agent.run(
        message,
        context={"conversation_history": history}
    )

    # Save AI response
    assistant_msg = await db.execute_async(
        db.Message.CREATE,
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        role="assistant",
        content=ai_response,
        created_at=datetime.now().isoformat()
    )

    return {
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "response": ai_response
    }
```

---

## example-project Patterns

### Pattern 1: Contact CRUD Gateway

**Before: Legacy Gateway Wrapper Pattern (example-project style)**

```python
# File: example_project/gateways/nexus/contact_gateway.py
from kailash.workflow.builder import WorkflowBuilder

class ContactGateway:
    """Gateway for contact operations - 400+ lines of boilerplate."""

    def __init__(self, nexus_app):
        self.app = nexus_app
        self._register_workflows()

    def _register_workflows(self):
        self.app.register("contact_create", self._create_contact_workflow().build())
        self.app.register("contact_read", self._read_contact_workflow().build())
        self.app.register("contact_update", self._update_contact_workflow().build())
        self.app.register("contact_delete", self._delete_contact_workflow().build())
        self.app.register("contact_list", self._list_contacts_workflow().build())
        self.app.register("contact_search", self._search_contacts_workflow().build())

    def _create_contact_workflow(self):
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "validate", {
            "code": """
name = parameters.get('name')
email = parameters.get('email')
phone = parameters.get('phone')
company = parameters.get('company')

if not name or not name.strip():
    raise ValueError("Name is required")
if not email or '@' not in email:
    raise ValueError("Valid email is required")

result = {
    'validated_data': {
        'name': name.strip(),
        'email': email.strip().lower(),
        'phone': phone.strip() if phone else None,
        'company': company.strip() if company else None
    }
}
"""
        })

        workflow.add_node("PythonCodeNode", "create", {
            "code": """
# BROKEN: Cannot import ContactService - sandbox restriction
# from example_project.services import ContactService
# service = ContactService()
# contact = await service.create(**validated_data)

# Workaround: Simulate database insert
import uuid
from datetime import datetime

validated_data = parameters.get('validated_data', {})
contact = {
    'id': str(uuid.uuid4()),
    **validated_data,
    'created_at': datetime.now().isoformat()
}
result = {'contact': contact}
"""
        })

        workflow.add_connection("validate", "validated_data", "create", "validated_data")
        return workflow

    # ... 300+ more lines for other CRUD operations
```

**After: Handler Pattern with DataFlow**

```python
# File: example_project/api/contacts.py
from nexus import Nexus
from dataflow import DataFlow
from datetime import datetime
from typing import Optional, List
import uuid

app = Nexus(api_port=8000, auto_discovery=False)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False
)

@db.model
class Contact:
    id: str
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    created_at: str = None
    updated_at: str = None

# All 6 workflows in ~100 lines instead of 400+

@app.handler("contact_create", description="Create a new contact")
async def contact_create(
    name: str,
    email: str,
    phone: str = None,
    company: str = None
) -> dict:
    """Create a new contact."""
    if not name or not name.strip():
        raise ValueError("Name is required")
    if not email or '@' not in email:
        raise ValueError("Valid email is required")

    now = datetime.now().isoformat()
    contact = await db.execute_async(
        db.Contact.CREATE,
        id=str(uuid.uuid4()),
        name=name.strip(),
        email=email.strip().lower(),
        phone=phone.strip() if phone else None,
        company=company.strip() if company else None,
        created_at=now,
        updated_at=now
    )
    return {"contact": contact}

@app.handler("contact_read", description="Get contact by ID")
async def contact_read(contact_id: str) -> dict:
    """Retrieve a contact by ID."""
    contact = await db.execute_async(
        db.Contact.READ,
        filter={"id": contact_id}
    )
    if not contact:
        raise ValueError(f"Contact not found: {contact_id}")
    return {"contact": contact}

@app.handler("contact_update", description="Update a contact")
async def contact_update(
    contact_id: str,
    name: str = None,
    email: str = None,
    phone: str = None,
    company: str = None
) -> dict:
    """Update contact fields."""
    fields = {}
    if name is not None:
        fields["name"] = name.strip()
    if email is not None:
        fields["email"] = email.strip().lower()
    if phone is not None:
        fields["phone"] = phone.strip() or None
    if company is not None:
        fields["company"] = company.strip() or None

    if fields:
        fields["updated_at"] = datetime.now().isoformat()

    contact = await db.execute_async(
        db.Contact.UPDATE,
        filter={"id": contact_id},
        fields=fields
    )
    return {"contact": contact}

@app.handler("contact_delete", description="Delete a contact")
async def contact_delete(contact_id: str) -> dict:
    """Delete a contact by ID."""
    await db.execute_async(
        db.Contact.DELETE,
        filter={"id": contact_id}
    )
    return {"deleted": True, "contact_id": contact_id}

@app.handler("contact_list", description="List contacts with pagination")
async def contact_list(
    page: int = 1,
    page_size: int = 20,
    company: str = None
) -> dict:
    """List contacts with optional company filter."""
    filter_params = {}
    if company:
        filter_params["company"] = company

    offset = (page - 1) * page_size
    contacts = await db.execute_async(
        db.Contact.LIST,
        filter=filter_params,
        limit=page_size,
        offset=offset
    )
    total = await db.execute_async(
        db.Contact.COUNT,
        filter=filter_params
    )
    return {
        "contacts": contacts,
        "pagination": {"page": page, "page_size": page_size, "total": total}
    }

@app.handler("contact_search", description="Search contacts")
async def contact_search(
    query: str,
    page: int = 1,
    page_size: int = 20
) -> dict:
    """Search contacts by name, email, or company."""
    offset = (page - 1) * page_size
    contacts = await db.execute_async(
        db.Contact.LIST,
        filter={
            "$or": [
                {"name": {"$contains": query}},
                {"email": {"$contains": query}},
                {"company": {"$contains": query}}
            ]
        },
        limit=page_size,
        offset=offset
    )
    return {"contacts": contacts, "query": query}
```

**Reduction**: ~400 lines -> ~100 lines (75% reduction)

---

### Pattern 2: Investment Tracking Gateway

**Before: Legacy Pattern**

```python
# File: example_project/gateways/nexus/investment_gateway.py
# Similar 400+ line pattern for investments
class InvestmentGateway:
    def _create_investment_workflow(self):
        workflow = WorkflowBuilder()
        # BROKEN: Cannot access InvestmentService
        workflow.add_node("PythonCodeNode", "create", {
            "code": """
# SecurityError: Import of 'example_project.services' is not allowed
from example_project.services import InvestmentService
# ... blocked by sandbox
"""
        })
        return workflow
```

**After: Handler Pattern**

```python
# File: example_project/api/investments.py
from nexus import Nexus
from dataflow import DataFlow
from datetime import datetime
from typing import Optional
from decimal import Decimal
import uuid

app = Nexus(api_port=8000, auto_discovery=False)
db = DataFlow(database_url=os.environ["DATABASE_URL"], enable_model_persistence=False)

@db.model
class Investment:
    id: str
    contact_id: str
    fund_id: str
    amount: float
    currency: str = "USD"
    status: str = "pending"  # pending, confirmed, completed
    invested_at: str = None
    created_at: str = None

@app.handler("investment_create", description="Create a new investment")
async def investment_create(
    contact_id: str,
    fund_id: str,
    amount: float,
    currency: str = "USD"
) -> dict:
    """Create a new investment record."""
    if amount <= 0:
        raise ValueError("Amount must be positive")

    now = datetime.now().isoformat()
    investment = await db.execute_async(
        db.Investment.CREATE,
        id=str(uuid.uuid4()),
        contact_id=contact_id,
        fund_id=fund_id,
        amount=float(amount),
        currency=currency,
        status="pending",
        invested_at=now,
        created_at=now
    )
    return {"investment": investment}

@app.handler("investment_confirm", description="Confirm an investment")
async def investment_confirm(investment_id: str) -> dict:
    """Confirm a pending investment."""
    investment = await db.execute_async(
        db.Investment.UPDATE,
        filter={"id": investment_id},
        fields={"status": "confirmed"}
    )
    return {"investment": investment}

@app.handler("investment_by_contact", description="List investments for a contact")
async def investment_by_contact(contact_id: str) -> dict:
    """Get all investments for a contact."""
    investments = await db.execute_async(
        db.Investment.LIST,
        filter={"contact_id": contact_id}
    )
    total = sum(inv.get("amount", 0) for inv in investments)
    return {"investments": investments, "total_invested": total}
```

---

### Pattern 3: AI Analytics Gateway

**Before: Legacy Pattern (BROKEN)**

```python
# File: example_project/gateways/nexus/analytics_gateway.py
def create_ai_analysis_workflow():
    workflow = WorkflowBuilder()

    # BROKEN: Cannot use AI libraries in sandbox
    workflow.add_node("PythonCodeNode", "analyze", {
        "code": """
# SecurityError: Import of 'kaizen' is not allowed
from kaizen.api import Agent

data = parameters.get('data', {})
analysis_type = parameters.get('analysis_type', 'summary')

agent = Agent(model='gpt-4')
result = await agent.run(f"Analyze: {data}")  # FAILS
"""
    })
    return workflow
```

**After: Handler Pattern**

```python
# File: example_project/api/analytics.py
from nexus import Nexus
from kaizen.api import Agent
from dataflow import DataFlow
from typing import Optional, List

app = Nexus(api_port=8000, auto_discovery=False)
db = DataFlow(database_url=os.environ["DATABASE_URL"], enable_model_persistence=False)

# Initialize analyst agent
analyst = Agent(
    model="gpt-4",
    system_prompt="You are a financial analytics expert."
)

@app.handler("analyze_portfolio", description="AI analysis of investment portfolio")
async def analyze_portfolio(
    contact_id: str,
    include_recommendations: bool = True
) -> dict:
    """Generate AI analysis of a contact's portfolio."""
    # Get investments
    investments = await db.execute_async(
        db.Investment.LIST,
        filter={"contact_id": contact_id}
    )

    prompt = f"""
    Analyze this investment portfolio:
    {investments}

    Provide:
    1. Portfolio summary
    2. Risk assessment
    3. Diversification analysis
    {"4. Recommendations for optimization" if include_recommendations else ""}
    """

    analysis = await analyst.run(prompt)

    return {
        "contact_id": contact_id,
        "investment_count": len(investments),
        "analysis": analysis
    }

@app.handler("generate_report", description="Generate AI-powered investment report")
async def generate_report(
    fund_id: str,
    report_type: str = "quarterly"
) -> dict:
    """Generate fund performance report."""
    investments = await db.execute_async(
        db.Investment.LIST,
        filter={"fund_id": fund_id, "status": "completed"}
    )

    total_invested = sum(inv.get("amount", 0) for inv in investments)
    investor_count = len(set(inv.get("contact_id") for inv in investments))

    prompt = f"""
    Generate a {report_type} report for this fund:
    - Total invested: ${total_invested:,.2f}
    - Number of investors: {investor_count}
    - Individual investments: {len(investments)}

    Include executive summary, performance metrics, and outlook.
    """

    report = await analyst.run(prompt)

    return {
        "fund_id": fund_id,
        "report_type": report_type,
        "metrics": {
            "total_invested": total_invested,
            "investor_count": investor_count
        },
        "report": report
    }
```

---

## enterprise-app Patterns

### Pattern 1: Session Management

**Before: Legacy Pattern**

```python
# File: enterprise_app/api/routes.py
from kailash.workflow.builder import WorkflowBuilder

def create_session_workflow():
    workflow = WorkflowBuilder()

    workflow.add_node("PythonCodeNode", "create_session", {
        "code": """
import uuid
from datetime import datetime

user_id = parameters.get('user_id')
agent_id = parameters.get('agent_id')
context = parameters.get('context', {})

session = {
    'session_id': str(uuid.uuid4()),
    'user_id': user_id,
    'agent_id': agent_id,
    'context': context,
    'status': 'active',
    'created_at': datetime.now().isoformat(),
    'messages': []
}

result = {'session': session}
"""
    })
    return workflow

nexus.register("create_session", create_session_workflow().build())
nexus.register("get_session", get_session_workflow().build())
nexus.register("update_session", update_session_workflow().build())
nexus.register("close_session", close_session_workflow().build())
```

**After: Handler Pattern**

```python
# File: enterprise_app/api/sessions.py
from nexus import Nexus
from datetime import datetime
from typing import Optional, Dict, Any
import uuid

app = Nexus(api_port=8000)

# In-memory session store (use Redis/DataFlow in production)
_sessions: Dict[str, dict] = {}

@app.handler("create_session", description="Create a new agent session")
async def create_session(
    user_id: str,
    agent_id: str,
    context: dict = None
) -> dict:
    """Create a new session for user-agent interaction."""
    session_id = str(uuid.uuid4())
    session = {
        'session_id': session_id,
        'user_id': user_id,
        'agent_id': agent_id,
        'context': context or {},
        'status': 'active',
        'created_at': datetime.now().isoformat(),
        'messages': []
    }
    _sessions[session_id] = session
    return {"session": session}

@app.handler("get_session", description="Retrieve session by ID")
async def get_session(session_id: str) -> dict:
    """Get session details."""
    session = _sessions.get(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")
    return {"session": session}

@app.handler("update_session", description="Update session context")
async def update_session(
    session_id: str,
    context: dict = None,
    add_message: dict = None
) -> dict:
    """Update session context or add message."""
    session = _sessions.get(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    if context:
        session['context'].update(context)
    if add_message:
        add_message['timestamp'] = datetime.now().isoformat()
        session['messages'].append(add_message)

    return {"session": session}

@app.handler("close_session", description="Close an active session")
async def close_session(session_id: str) -> dict:
    """Close a session."""
    session = _sessions.get(session_id)
    if not session:
        raise ValueError(f"Session not found: {session_id}")

    session['status'] = 'closed'
    session['closed_at'] = datetime.now().isoformat()
    return {"session": session}
```

---

### Pattern 2: Agent Pool Management

**Before: Legacy Pattern (BROKEN - cannot manage agents)**

```python
# File: enterprise_app/api/routes.py
def create_agent_pool_workflow():
    workflow = WorkflowBuilder()

    # BROKEN: Cannot import kaizen in sandbox
    workflow.add_node("PythonCodeNode", "spawn_agent", {
        "code": """
# SecurityError: Import of 'kaizen' is not allowed
from kaizen.api import Agent
from kaizen.core.registry import AgentRegistry

agent_config = parameters.get('config', {})
agent = Agent(**agent_config)
# ... FAILS
"""
    })
    return workflow
```

**After: Handler Pattern with Full Kaizen Access**

```python
# File: enterprise_app/api/agents.py
from nexus import Nexus
from kaizen.api import Agent
from kaizen.core.registry import AgentRegistry
from typing import Optional, Dict, Any
import uuid

app = Nexus(api_port=8000)

# Agent registry for pool management
registry = AgentRegistry()

@app.handler("spawn_agent", description="Spawn a new agent in the pool")
async def spawn_agent(
    model: str = "gpt-4",
    execution_mode: str = "autonomous",
    system_prompt: str = None,
    tools: list = None
) -> dict:
    """Spawn a new agent and add to pool."""
    agent_id = f"agent_{uuid.uuid4().hex[:8]}"

    agent = Agent(
        model=model,
        execution_mode=execution_mode,
        system_prompt=system_prompt or "You are a helpful assistant.",
        tool_access="constrained" if tools else "none"
    )

    registry.register(agent_id, agent)

    return {
        "agent_id": agent_id,
        "model": model,
        "execution_mode": execution_mode,
        "status": "active"
    }

@app.handler("execute_agent_task", description="Execute a task with a pooled agent")
async def execute_agent_task(
    agent_id: str,
    task: str,
    context: dict = None
) -> dict:
    """Execute a task using a specific agent from the pool."""
    agent = registry.get(agent_id)
    if not agent:
        raise ValueError(f"Agent not found: {agent_id}")

    result = await agent.run(task, context=context or {})

    return {
        "agent_id": agent_id,
        "task": task,
        "result": result
    }

@app.handler("list_agents", description="List all agents in the pool")
async def list_agents() -> dict:
    """List all registered agents."""
    agents = registry.list_all()
    return {
        "agents": [
            {"agent_id": aid, "status": "active"}
            for aid in agents
        ],
        "total": len(agents)
    }

@app.handler("terminate_agent", description="Remove agent from pool")
async def terminate_agent(agent_id: str) -> dict:
    """Terminate and remove an agent from the pool."""
    if not registry.get(agent_id):
        raise ValueError(f"Agent not found: {agent_id}")

    registry.unregister(agent_id)
    return {"agent_id": agent_id, "status": "terminated"}
```

---

## Estimated Impact Summary

### example-backend

| Metric                      | Before | After                            |
| --------------------------- | ------ | -------------------------------- |
| Workflow files              | 30+    | ~10 (handlers grouped by domain) |
| Lines of code               | ~5,400 | ~1,500                           |
| Broken workflows (sandbox)  | 15+    | 0                                |
| Duplicate FastAPI endpoints | 20+    | 0                                |

### example-project

| Metric                     | Before     | After             |
| -------------------------- | ---------- | ----------------- |
| Gateway classes            | 25+        | 0 (handlers only) |
| Lines of code              | ~13,700    | ~3,500            |
| Broken workflows (sandbox) | 226+       | 0                 |
| CRUD boilerplate per model | ~400 lines | ~100 lines        |

### enterprise-app

| Metric                    | Before         | After |
| ------------------------- | -------------- | ----- |
| Workflow files            | 20+            | ~5    |
| Lines of code             | ~1,700         | ~500  |
| AI-capable workflows      | 0 (all broken) | 20+   |
| Agent management possible | No             | Yes   |

---

## Handler + Auth Integration

All handlers automatically integrate with Nexus authentication when enabled:

```python
# File: api/app.py
from nexus import Nexus
from nexus.trust.middleware import require_role, get_current_tenant
from fastapi import Request

app = Nexus(api_port=8000, enable_auth=True)

@app.handler("list_users", description="List users in tenant (admin only)")
async def list_users(request: Request) -> dict:
    """List users - requires admin role."""
    # Auth enforcement
    user = require_role(request, "admin")
    tenant = get_current_tenant()

    # DataFlow auto-scoped to tenant
    users = await db.execute_async(
        db.User.LIST,
        filter={"org_id": tenant.id}
    )

    return {
        "users": users,
        "requested_by": user.id,
        "tenant": tenant.id
    }

@app.handler("get_profile", description="Get current user profile")
async def get_profile(request: Request) -> dict:
    """Get authenticated user's profile."""
    # Any authenticated user can access
    user = require_role(request, "user")

    profile = await db.execute_async(
        db.User.READ,
        filter={"id": user.id}
    )

    return {"profile": profile}
```

---

## File Locations

### Implementation Files

- `src/kailash/nodes/handler.py` - HandlerNode and make_handler_workflow()
- `apps/kailash-nexus/src/nexus/core.py` (lines 790-880) - @app.handler() and register_handler()

### Test Files

- `apps/kailash-nexus/tests/unit/test_handler_registration.py` - 16 unit tests
- `apps/kailash-nexus/tests/integration/test_handler_execution.py` - 7 integration tests
- `apps/kailash-nexus/tests/e2e/test_handler_e2e.py` - 3 E2E tests

### Documentation

- `apps/kailash-nexus/instructions/01-analysis/nexus-pythoncodenode-challenges.md` - Original problem analysis
- `apps/kailash-nexus/todos/completed/TODO-200A-core-handler-node.md` - Implementation details
- `apps/kailash-nexus/todos/completed/TODO-200B-nexus-handler-api.md` - API details
