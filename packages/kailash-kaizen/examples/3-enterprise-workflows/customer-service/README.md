# Customer Service Enterprise Workflow

**Category**: Enterprise Workflows
**Pattern**: Multi-Agent Sequential Pipeline
**Complexity**: Intermediate
**Use Cases**: Automated ticket triage, knowledge base search, response generation, ticket routing, customer support automation

## Overview

This example demonstrates automated customer service using four specialized agents that collaborate through SharedMemoryPool to triage tickets, search knowledge bases, generate responses, and route tickets to appropriate teams.

### Key Features

- **Automated triage** - Classify tickets by priority, category, urgency
- **Knowledge base search** - Find relevant articles and solutions
- **Response generation** - Generate customer-facing responses
- **Ticket routing** - Route to appropriate teams/agents
- **Multi-channel support** - Email, chat, phone ticket processing
- **Priority handling** - Fast-track critical tickets

## Architecture

```
Support Ticket
     |
     v
┌─────────────────────┐
│ TicketTriageAgent   │ - Triages tickets by priority/category
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["triage", "pipeline"]
           │
           v
┌─────────────────────┐
│KnowledgeSearchAgent │ - Searches knowledge base
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["knowledge", "pipeline"]
           │
           v
┌─────────────────────┐
│ResponseGeneratorAgent│ - Generates customer response
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["response", "pipeline"]
           │
           v
┌─────────────────────┐
│ TicketRouterAgent   │ - Routes ticket to team
└──────────┬──────────┘
           │ writes to SharedMemoryPool
           v
    ["routing", "pipeline"]
           │
           v
  Complete Ticket Processing
```

## Agents

### 1. TicketTriageAgent

**Signature**: `TicketTriageSignature`
- **Inputs**: `ticket` (str) - Support ticket data as JSON
- **Outputs**:
  - `priority` (str) - Ticket priority (low, medium, high, critical)
  - `category` (str) - Ticket category
  - `urgency` (str) - Urgency level

**Responsibilities**:
- Analyze ticket content
- Assign priority level
- Categorize ticket type
- Assess urgency
- Write triage results to SharedMemoryPool

**SharedMemory Tags**: `["triage", "pipeline"]`, segment: `"pipeline"`

### 2. KnowledgeSearchAgent

**Signature**: `KnowledgeSearchSignature`
- **Inputs**: `query` (str) - Search query
- **Outputs**:
  - `articles` (str) - Relevant articles as JSON
  - `solutions` (str) - Suggested solutions as JSON

**Responsibilities**:
- Search knowledge base
- Find relevant articles
- Identify solutions
- Limit results to max_articles
- Write search results to SharedMemoryPool

**SharedMemory Tags**: `["knowledge", "pipeline"]`, segment: `"pipeline"`

### 3. ResponseGeneratorAgent

**Signature**: `ResponseGenerationSignature`
- **Inputs**:
  - `ticket` (str) - Support ticket as JSON
  - `knowledge` (str) - Knowledge base results as JSON
- **Outputs**:
  - `response` (str) - Customer response text
  - `tone` (str) - Response tone

**Responsibilities**:
- Generate customer-facing response
- Apply appropriate tone (professional, friendly, formal)
- Incorporate knowledge base solutions
- Write response to SharedMemoryPool

**SharedMemory Tags**: `["response", "pipeline"]`, segment: `"pipeline"`

### 4. TicketRouterAgent

**Signature**: `TicketRoutingSignature`
- **Inputs**: `triage_result` (str) - Triage result as JSON
- **Outputs**:
  - `routing_decision` (str) - Routing decision
  - `assigned_team` (str) - Assigned team/agent

**Responsibilities**:
- Route ticket based on triage
- Assign to appropriate team
- Handle escalations
- Write routing decision to SharedMemoryPool

**SharedMemory Tags**: `["routing", "pipeline"]`, segment: `"pipeline"`

## Quick Start

### 1. Basic Usage

```python
from workflow import customer_service_workflow, CustomerServiceConfig

config = CustomerServiceConfig(llm_provider="mock")

ticket = {
    "ticket_id": "T12345",
    "subject": "Cannot login to my account",
    "description": "I'm getting an error message when trying to log in.",
    "customer_email": "customer@example.com",
    "priority": "high"
}

result = customer_service_workflow(ticket, config)
print(f"Priority: {result['triage']['priority']}")
print(f"Response: {result['response']['response']}")
```

### 2. Custom Configuration

```python
config = CustomerServiceConfig(
    llm_provider="openai",
    model="gpt-4",
    auto_response=True,
    knowledge_base_enabled=True,
    max_articles=5,
    response_tone="professional",  # "professional", "friendly", "formal"
    routing_enabled=True,
    escalation_threshold="high"  # "low", "medium", "high", "critical"
)
```

### 3. Batch Ticket Processing

```python
from workflow import batch_ticket_processing

tickets = [
    {"ticket_id": "T1", "subject": "Login issue", "description": "Cannot login"},
    {"ticket_id": "T2", "subject": "Payment failed", "description": "Card declined"},
    {"ticket_id": "T3", "subject": "Feature request", "description": "Need export feature"}
]

results = batch_ticket_processing(tickets, config)
print(f"Processed {len(results)} tickets")
```

## Configuration

### CustomerServiceConfig Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_provider` | str | "mock" | LLM provider (mock, openai, anthropic) |
| `model` | str | "gpt-3.5-turbo" | Model name |
| `auto_response` | bool | True | Enable automatic response generation |
| `knowledge_base_enabled` | bool | True | Enable knowledge base search |
| `max_articles` | int | 5 | Maximum articles to return |
| `response_tone` | str | "professional" | Response tone: professional, friendly, formal |
| `routing_enabled` | bool | True | Enable ticket routing |
| `escalation_threshold` | str | "high" | Escalation threshold: low, medium, high, critical |

## Use Cases

### 1. Automated Ticket Triage

Automatically classify incoming support tickets by priority, category, and urgency.

```python
ticket = {
    "subject": "URGENT: System down",
    "description": "Critical system outage affecting all users"
}

result = customer_service_workflow(ticket, config)
print(f"Priority: {result['triage']['priority']}")  # "critical"
```

### 2. Knowledge Base Search

Search knowledge base for relevant articles and solutions.

```python
config = CustomerServiceConfig(
    knowledge_base_enabled=True,
    max_articles=5
)

result = customer_service_workflow(ticket, config)
print(f"Articles: {len(result['knowledge']['articles'])}")
```

### 3. Response Generation

Generate customer-facing responses with appropriate tone.

```python
config = CustomerServiceConfig(
    auto_response=True,
    response_tone="friendly"
)

result = customer_service_workflow(ticket, config)
print(f"Response: {result['response']['response']}")
```

### 4. Ticket Routing

Route tickets to appropriate teams based on triage.

```python
config = CustomerServiceConfig(
    routing_enabled=True,
    escalation_threshold="high"
)

result = customer_service_workflow(ticket, config)
print(f"Assigned to: {result['routing']['assigned_team']}")
```

### 5. Batch Processing

Process multiple tickets efficiently.

```python
tickets = [
    {"ticket_id": f"T{i}", "subject": f"Issue {i}"}
    for i in range(100)
]

results = batch_ticket_processing(tickets, config)
print(f"Processed {len(results)} tickets")
```

## Testing

```bash
# Run all tests
pytest tests/unit/examples/test_customer_service.py -v

# Run specific test class
pytest tests/unit/examples/test_customer_service.py::TestCustomerServiceAgents -v
```

**Test Coverage**: 17 tests, 100% passing

## Related Examples

- **document-analysis** - Multi-agent document processing
- **compliance-monitoring** - Compliance checking workflow
- **data-reporting** - Automated report generation

## Implementation Notes

- **Phase**: 5E.2 (Enterprise Workflow Examples)
- **Created**: 2025-10-03
- **Tests**: 17/17 passing
- **TDD**: Tests written first, implementation second
- **Pattern**: Sequential pipeline with SharedMemoryPool

## Author

Kaizen Framework Team
