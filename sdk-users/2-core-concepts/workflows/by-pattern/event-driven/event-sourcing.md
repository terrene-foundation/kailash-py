# Event-Driven Patterns Guide

## Overview

This guide covers production-ready event-driven architectural patterns for building scalable, resilient microservices with Kailash SDK. Each pattern includes comprehensive error handling, scalability considerations, and real-world implementation examples.

## Table of Contents

1. [Event Sourcing Patterns](#event-sourcing-patterns)
2. [Pub/Sub Messaging with Queuing Systems](#pubsub-messaging)
3. [CQRS Patterns](#cqrs-patterns)
4. [Saga Patterns for Distributed Transactions](#saga-patterns)
5. [Event Streaming and Real-Time Processing](#event-streaming)
6. [Domain Event Patterns](#domain-event-patterns)
7. [Production-Ready Event Handling](#production-event-handling)

## Event Sourcing Patterns

### Core Concepts

Event sourcing stores all changes to application state as a sequence of events, providing complete audit trails and enabling temporal queries.

### Basic Event Store Implementation

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.nodes import PythonCodeNode, DataWriterNode, DataReaderNode
from kailash.runtime.local import LocalRuntime
from datetime import datetime
import json
import uuid

# Event Store Writer
event_store_writer = PythonCodeNode(
    name="event_store_writer",
    code="""
import json
import uuid
from datetime import datetime

# Validate event structure
if not all(k in event for k in ['aggregate_id', 'event_type', 'payload']):
    raise ValueError("Invalid event structure")

# Add metadata
enriched_event = {
    'event_id': str(uuid.uuid4()),
    'aggregate_id': event['aggregate_id'],
    'event_type': event['event_type'],
    'payload': event['payload'],
    'timestamp': datetime.utcnow().isoformat(),
    'version': event.get('version', 1),
    'metadata': {
        'source': event.get('source', 'unknown'),
        'correlation_id': event.get('correlation_id', str(uuid.uuid4())),
        'causation_id': event.get('causation_id', None)
    }
}

# Format for storage
result = json.dumps(enriched_event) + '\\n'
""",
    input_types={"event": dict}
)

# Event Store Snapshot Manager
snapshot_manager = PythonCodeNode(
    name="snapshot_manager",
    code="""
import json
from datetime import datetime

# Configuration
SNAPSHOT_FREQUENCY = 10  # Create snapshot every N events

# Check if snapshot needed
event_count = len(events)
needs_snapshot = event_count > 0 and event_count % SNAPSHOT_FREQUENCY == 0

if needs_snapshot:
    # Build aggregate state from events
    state = {}
    for event in events:
        if event['event_type'] == 'Created':
            state = event['payload']
        elif event['event_type'] == 'Updated':
            state.update(event['payload'])
        elif event['event_type'] == 'Deleted':
            state['deleted'] = True
            state['deleted_at'] = event['timestamp']

    # Create snapshot
    snapshot = {
        'aggregate_id': events[0]['aggregate_id'],
        'version': event_count,
        'state': state,
        'timestamp': datetime.utcnow().isoformat(),
        'events_included': event_count
    }

    result = {'snapshot': snapshot, 'created': True}
else:
    result = {'snapshot': None, 'created': False}
""",
    input_types={"events": list}
)

# Event Replay Engine
event_replay = PythonCodeNode(
    name="event_replay",
    code="""

# Initialize state
state = initial_state if initial_state else {}
replayed_events = []
errors = []

# Apply events in order
for event in events:
    try:
        # Filter by time range if specified
        if start_time and event['timestamp'] < start_time:
            continue
        if end_time and event['timestamp'] > end_time:
            break

        # Apply event based on type
        if event['event_type'] == 'Created':
            state = event['payload']
        elif event['event_type'] == 'Updated':
            state.update(event['payload'])
        elif event['event_type'] == 'Deleted':
            state['deleted'] = True
            state['deleted_at'] = event['timestamp']
        else:
            # Custom event handler
            handler_name = f"handle_{event['event_type'].lower()}"
            if handler_name in custom_handlers:
                state = custom_handlers[handler_name](state, event)

        replayed_events.append(event['event_id'])

    except Exception as e:
        errors.append({
            'event_id': event.get('event_id', 'unknown'),
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })

result = {
    'final_state': state,
    'events_replayed': len(replayed_events),
    'errors': errors,
    'success': len(errors) == 0
}
""",
    input_types={
        "events": list,
        "initial_state": dict,
        "start_time": str,
        "end_time": str,
        "custom_handlers": dict
    }
)

# Build Event Sourcing Workflow
es_workflow = WorkflowBuilder()
workflow.es_workflow.add_node(event_store_writer)
es_workflow.add_node(snapshot_manager)
es_workflow.add_node(event_replay)

# Connect for event processing
es_workflow.add_connection("event_store_writer", "snapshot_manager", "result", "events")
es_workflow.add_connection("snapshot_manager", "event_replay", "snapshot", "initial_state")

```

### Advanced Event Projection

```python
# Event Projection Builder
projection_builder = PythonCodeNode(
    name="projection_builder",
    code="""
import json
from collections import defaultdict

# Initialize projections
projections = {
    'by_type': defaultdict(list),
    'by_aggregate': defaultdict(list),
    'by_date': defaultdict(list),
    'statistics': {
        'total_events': 0,
        'event_types': defaultdict(int),
        'aggregates_affected': set(),
        'time_range': {'start': None, 'end': None}
    }
}

# Build projections
for event in events:
    # Type-based projection
    projections['by_type'][event['event_type']].append(event)

    # Aggregate-based projection
    projections['by_aggregate'][event['aggregate_id']].append(event)

    # Date-based projection
    date_key = event['timestamp'][:10]  # YYYY-MM-DD
    projections['by_date'][date_key].append(event)

    # Update statistics
    projections['statistics']['total_events'] += 1
    projections['statistics']['event_types'][event['event_type']] += 1
    projections['statistics']['aggregates_affected'].add(event['aggregate_id'])

    # Update time range
    if not projections['statistics']['time_range']['start']:
        projections['statistics']['time_range']['start'] = event['timestamp']
    projections['statistics']['time_range']['end'] = event['timestamp']

# Convert sets to lists for JSON serialization
projections['statistics']['aggregates_affected'] = list(
    projections['statistics']['aggregates_affected']
)

# Apply custom projections if provided
if custom_projections:
    for name, projection_func in custom_projections.items():
        projections[name] = projection_func(events)

result = projections
""",
    input_types={"events": list, "custom_projections": dict}
)

# Temporal Query Engine
temporal_query = PythonCodeNode(
    name="temporal_query",
    code="""
from datetime import datetime, timedelta

# Parse query parameters
point_in_time = datetime.fromisoformat(query_time) if query_time else datetime.utcnow()
aggregate_ids = query_aggregates if query_aggregates else []

# Filter events up to point in time
relevant_events = [
    e for e in events
    if datetime.fromisoformat(e['timestamp']) <= point_in_time
    and (not aggregate_ids or e['aggregate_id'] in aggregate_ids)
]

# Reconstruct state at point in time
states = {}
for event in relevant_events:
    agg_id = event['aggregate_id']
    if agg_id not in states:
        states[agg_id] = {'history': [], 'current': {}}

    states[agg_id]['history'].append(event)

    # Apply event to current state
    if event['event_type'] == 'Created':
        states[agg_id]['current'] = event['payload']
    elif event['event_type'] == 'Updated':
        states[agg_id]['current'].update(event['payload'])
    elif event['event_type'] == 'Deleted':
        states[agg_id]['current']['deleted'] = True

result = {
    'point_in_time': point_in_time.isoformat(),
    'aggregates': states,
    'total_events_processed': len(relevant_events)
}
""",
    input_types={
        "events": list,
        "query_time": str,
        "query_aggregates": list
    }
)

```

## Pub/Sub Messaging with Queuing Systems

### Message Publisher Pattern

```python
# Reliable Message Publisher
message_publisher = PythonCodeNode(
    name="message_publisher",
    code="""
import json
import uuid
from datetime import datetime

# Message envelope
envelope = {
    'message_id': str(uuid.uuid4()),
    'topic': topic,
    'payload': payload,
    'headers': {
        'content_type': 'application/json',
        'timestamp': datetime.utcnow().isoformat(),
        'source': source_system,
        'correlation_id': correlation_id or str(uuid.uuid4()),
        'priority': priority or 'normal',
        'ttl': ttl or 3600  # Time to live in seconds
    },
    'routing': {
        'key': routing_key or topic,
        'exchange': exchange or 'default',
        'retry_count': 0,
        'max_retries': max_retries or 3
    }
}

# Add partition key for ordered processing
if partition_key:
    envelope['routing']['partition_key'] = partition_key

# Add scheduling information
if scheduled_time:
    envelope['headers']['scheduled_time'] = scheduled_time
    envelope['headers']['delayed'] = True

# Validate message size
message_json = json.dumps(envelope)
if len(message_json) > max_message_size:
    # Store large payload externally
    storage_key = f"large_payloads/{envelope['message_id']}"
    envelope['payload'] = {
        'type': 'reference',
        'storage_key': storage_key,
        'size': len(message_json)
    }
    envelope['headers']['large_payload'] = True

result = {
    'message': envelope,
    'published': True,
    'message_id': envelope['message_id']
}
""",
    input_types={
        "topic": str,
        "payload": dict,
        "source_system": str,
        "correlation_id": str,
        "routing_key": str,
        "partition_key": str,
        "priority": str,
        "ttl": int,
        "exchange": str,
        "scheduled_time": str,
        "max_retries": int,
        "max_message_size": int
    }
)

# Message Consumer with Error Handling
message_consumer = PythonCodeNode(
    name="message_consumer",
    code="""
import json
from datetime import datetime

processed_messages = []
failed_messages = []
dead_letter_messages = []

for message in messages:
    try:
        # Check message TTL
        if 'ttl' in message['headers']:
            message_age = (datetime.utcnow() -
                          datetime.fromisoformat(message['headers']['timestamp'])).total_seconds()
            if message_age > message['headers']['ttl']:
                dead_letter_messages.append({
                    'message': message,
                    'reason': 'TTL expired',
                    'expired_at': datetime.utcnow().isoformat()
                })
                continue

        # Process based on topic
        if message['topic'] in topic_handlers:
            handler = topic_handlers[message['topic']]
            result = handler(message['payload'])

            processed_messages.append({
                'message_id': message['message_id'],
                'result': result,
                'processed_at': datetime.utcnow().isoformat()
            })
        else:
            # Unknown topic - send to dead letter queue
            dead_letter_messages.append({
                'message': message,
                'reason': f"No handler for topic: {message['topic']}",
                'failed_at': datetime.utcnow().isoformat()
            })

    except Exception as e:
        # Increment retry count
        message['routing']['retry_count'] += 1

        if message['routing']['retry_count'] >= message['routing']['max_retries']:
            # Max retries exceeded - send to dead letter queue
            dead_letter_messages.append({
                'message': message,
                'reason': f"Max retries exceeded: {str(e)}",
                'failed_at': datetime.utcnow().isoformat()
            })
        else:
            # Retry later
            failed_messages.append({
                'message': message,
                'error': str(e),
                'retry_count': message['routing']['retry_count'],
                'retry_after': datetime.utcnow().isoformat()
            })

result = {
    'processed': processed_messages,
    'failed': failed_messages,
    'dead_letter': dead_letter_messages,
    'summary': {
        'total': len(messages),
        'processed': len(processed_messages),
        'failed': len(failed_messages),
        'dead_letter': len(dead_letter_messages)
    }
}
""",
    input_types={"messages": list, "topic_handlers": dict}
)

# Message Queue Manager
queue_manager = PythonCodeNode(
    name="queue_manager",
    code="""
from collections import defaultdict
import heapq
from datetime import datetime

# Initialize queues
queues = defaultdict(list)
priority_queues = defaultdict(list)
delayed_messages = []

# Queue metrics
metrics = {
    'messages_enqueued': 0,
    'messages_dequeued': 0,
    'queue_depths': {},
    'processing_times': []
}

# Enqueue messages
for message in messages_to_enqueue:
    queue_name = message['routing']['key']

    # Check if delayed message
    if message['headers'].get('delayed'):
        scheduled_time = datetime.fromisoformat(message['headers']['scheduled_time'])
        heapq.heappush(delayed_messages, (scheduled_time, message))
    else:
        # Check priority
        priority = message['headers'].get('priority', 'normal')
        if priority == 'high':
            heapq.heappush(priority_queues[queue_name], (0, message))
        elif priority == 'low':
            heapq.heappush(priority_queues[queue_name], (2, message))
        else:
            heapq.heappush(priority_queues[queue_name], (1, message))

    metrics['messages_enqueued'] += 1

# Process delayed messages that are ready
current_time = datetime.utcnow()
ready_messages = []
while delayed_messages and delayed_messages[0][0] <= current_time:
    _, message = heapq.heappop(delayed_messages)
    ready_messages.append(message)

# Dequeue messages for processing
dequeued_messages = []
for queue_name, max_batch_size in dequeue_requests.items():
    batch = []

    # Dequeue from priority queue
    while len(batch) < max_batch_size and priority_queues[queue_name]:
        _, message = heapq.heappop(priority_queues[queue_name])
        batch.append(message)
        metrics['messages_dequeued'] += 1

    if batch:
        dequeued_messages.extend(batch)

# Update queue depth metrics
for queue_name in priority_queues:
    metrics['queue_depths'][queue_name] = len(priority_queues[queue_name])

result = {
    'dequeued': dequeued_messages,
    'ready_delayed': ready_messages,
    'metrics': metrics,
    'remaining_delayed': len(delayed_messages)
}
""",
    input_types={
        "messages_to_enqueue": list,
        "dequeue_requests": dict
    }
)

```

## CQRS Patterns

### Command and Query Separation

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Command Handler
command_handler = PythonCodeNode(
    name="command_handler",
    code="""
import json
import uuid
from datetime import datetime

# Command validation
def validate_command(command):
    required_fields = ['command_type', 'aggregate_id', 'payload']
    return all(field in command for field in required_fields)

# Command processors
command_processors = {
    'CreateOrder': lambda cmd: {
        'event_type': 'OrderCreated',
        'aggregate_id': cmd['aggregate_id'],
        'payload': cmd['payload'],
        'timestamp': datetime.utcnow().isoformat()
    },
    'UpdateOrder': lambda cmd: {
        'event_type': 'OrderUpdated',
        'aggregate_id': cmd['aggregate_id'],
        'payload': cmd['payload'],
        'timestamp': datetime.utcnow().isoformat()
    },
    'CancelOrder': lambda cmd: {
        'event_type': 'OrderCancelled',
        'aggregate_id': cmd['aggregate_id'],
        'payload': {'cancelled_at': datetime.utcnow().isoformat()},
        'timestamp': datetime.utcnow().isoformat()
    }
}

# Process commands
events = []
rejected_commands = []

for command in commands:
    try:
        # Validate command
        if not validate_command(command):
            rejected_commands.append({
                'command': command,
                'reason': 'Invalid command structure',
                'rejected_at': datetime.utcnow().isoformat()
            })
            continue

        # Check if processor exists
        if command['command_type'] not in command_processors:
            rejected_commands.append({
                'command': command,
                'reason': f"Unknown command type: {command['command_type']}",
                'rejected_at': datetime.utcnow().isoformat()
            })
            continue

        # Process command
        event = command_processors[command['command_type']](command)
        event['command_id'] = command.get('command_id', str(uuid.uuid4()))
        events.append(event)

    except Exception as e:
        rejected_commands.append({
            'command': command,
            'reason': f"Processing error: {str(e)}",
            'rejected_at': datetime.utcnow().isoformat()
        })

result = {
    'events': events,
    'rejected': rejected_commands,
    'success_rate': len(events) / len(commands) if commands else 0
}
""",
    input_types={"commands": list}
)

# Query Handler with Caching
query_handler = PythonCodeNode(
    name="query_handler",
    code="""
import json
from datetime import datetime, timedelta

# Cache configuration
CACHE_TTL = 300  # 5 minutes
cache = cache if cache else {}

# Query processors
def query_order_by_id(query, read_model):
    order_id = query['parameters']['order_id']
    return read_model.get('orders', {}).get(order_id)

def query_orders_by_customer(query, read_model):
    customer_id = query['parameters']['customer_id']
    all_orders = read_model.get('orders', {})
    return [order for order in all_orders.values()
            if order.get('customer_id') == customer_id]

def query_orders_by_status(query, read_model):
    status = query['parameters']['status']
    all_orders = read_model.get('orders', {})
    return [order for order in all_orders.values()
            if order.get('status') == status]

query_processors = {
    'GetOrderById': query_order_by_id,
    'GetOrdersByCustomer': query_orders_by_customer,
    'GetOrdersByStatus': query_orders_by_status
}

# Process queries
results = []
cache_hits = 0
cache_misses = 0

for query in queries:
    try:
        # Generate cache key
        cache_key = f"{query['query_type']}:{json.dumps(query['parameters'], sort_keys=True)}"

        # Check cache
        if cache_key in cache:
            cached_entry = cache[cache_key]
            if datetime.fromisoformat(cached_entry['expires_at']) > datetime.utcnow():
                results.append({
                    'query_id': query.get('query_id'),
                    'result': cached_entry['data'],
                    'from_cache': True
                })
                cache_hits += 1
                continue

        # Process query
        cache_misses += 1
        processor = query_processors.get(query['query_type'])
        if processor:
            query_result = processor(query, read_model)

            # Cache result
            cache[cache_key] = {
                'data': query_result,
                'expires_at': (datetime.utcnow() + timedelta(seconds=CACHE_TTL)).isoformat()
            }

            results.append({
                'query_id': query.get('query_id'),
                'result': query_result,
                'from_cache': False
            })
        else:
            results.append({
                'query_id': query.get('query_id'),
                'error': f"Unknown query type: {query['query_type']}"
            })

    except Exception as e:
        results.append({
            'query_id': query.get('query_id'),
            'error': str(e)
        })

result = {
    'results': results,
    'cache_stats': {
        'hits': cache_hits,
        'misses': cache_misses,
        'hit_rate': cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0
    },
    'cache': cache  # Return updated cache
}
""",
    input_types={"queries": list, "read_model": dict, "cache": dict}
)

# Read Model Updater
read_model_updater = PythonCodeNode(
    name="read_model_updater",
    code="""
from datetime import datetime

# Initialize read model if needed
if not read_model:
    read_model = {
        'orders': {},
        'customers': {},
        'products': {},
        'statistics': {
            'total_orders': 0,
            'orders_by_status': {},
            'revenue': 0
        }
    }

# Event handlers
def handle_order_created(event, model):
    order_data = event['payload']
    order_id = event['aggregate_id']

    model['orders'][order_id] = {
        'id': order_id,
        'customer_id': order_data['customer_id'],
        'items': order_data['items'],
        'total': order_data['total'],
        'status': 'created',
        'created_at': event['timestamp'],
        'updated_at': event['timestamp']
    }

    # Update statistics
    model['statistics']['total_orders'] += 1
    status_counts = model['statistics']['orders_by_status']
    status_counts['created'] = status_counts.get('created', 0) + 1
    model['statistics']['revenue'] += order_data['total']

def handle_order_updated(event, model):
    order_id = event['aggregate_id']
    if order_id in model['orders']:
        model['orders'][order_id].update(event['payload'])
        model['orders'][order_id]['updated_at'] = event['timestamp']

def handle_order_cancelled(event, model):
    order_id = event['aggregate_id']
    if order_id in model['orders']:
        order = model['orders'][order_id]
        old_status = order['status']
        order['status'] = 'cancelled'
        order['cancelled_at'] = event['timestamp']

        # Update statistics
        status_counts = model['statistics']['orders_by_status']
        status_counts[old_status] = max(0, status_counts.get(old_status, 0) - 1)
        status_counts['cancelled'] = status_counts.get('cancelled', 0) + 1
        model['statistics']['revenue'] -= order['total']

event_handlers = {
    'OrderCreated': handle_order_created,
    'OrderUpdated': handle_order_updated,
    'OrderCancelled': handle_order_cancelled
}

# Apply events to read model
processed_events = 0
errors = []

for event in events:
    try:
        handler = event_handlers.get(event['event_type'])
        if handler:
            handler(event, read_model)
            processed_events += 1
    except Exception as e:
        errors.append({
            'event_id': event.get('event_id'),
            'error': str(e)
        })

result = {
    'read_model': read_model,
    'processed_events': processed_events,
    'errors': errors,
    'model_version': processed_events
}
""",
    input_types={"events": list, "read_model": dict}
)

# Build CQRS Workflow
cqrs_workflow = WorkflowBuilder()
workflow.workflow = WorkflowBuilder()
workflow.add_node(command_handler)
workflow = WorkflowBuilder()
workflow.add_node(read_model_updater)
workflow = WorkflowBuilder()
workflow.add_node(query_handler)

# Connect command flow
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Saga Patterns for Distributed Transactions

### Orchestration-Based Saga

```python
# Saga Orchestrator
saga_orchestrator = PythonCodeNode(
    name="saga_orchestrator",
    code="""
import uuid
from datetime import datetime

# Saga definition
saga_steps = {
    'CreateOrderSaga': [
        {'step': 'reserve_inventory', 'compensate': 'release_inventory'},
        {'step': 'charge_payment', 'compensate': 'refund_payment'},
        {'step': 'create_shipment', 'compensate': 'cancel_shipment'},
        {'step': 'send_confirmation', 'compensate': None}  # No compensation needed
    ]
}

# Initialize saga state
saga_id = str(uuid.uuid4())
saga_state = {
    'id': saga_id,
    'type': saga_type,
    'status': 'started',
    'current_step': 0,
    'steps_completed': [],
    'compensations_needed': [],
    'context': initial_context,
    'started_at': datetime.utcnow().isoformat(),
    'errors': []
}

# Execute saga steps
for i, step_def in enumerate(saga_steps[saga_type]):
    saga_state['current_step'] = i
    step_name = step_def['step']

    try:
        # Execute step
        if step_name in step_handlers:
            step_result = step_handlers[step_name](saga_state['context'])

            # Update context with step results
            saga_state['context'][f'{step_name}_result'] = step_result
            saga_state['steps_completed'].append({
                'step': step_name,
                'completed_at': datetime.utcnow().isoformat(),
                'result': step_result
            })

            # Track compensation if needed
            if step_def['compensate']:
                saga_state['compensations_needed'].insert(0, {
                    'step': step_def['compensate'],
                    'context': step_result
                })
        else:
            raise Exception(f"No handler for step: {step_name}")

    except Exception as e:
        # Step failed - start compensation
        saga_state['status'] = 'compensating'
        saga_state['errors'].append({
            'step': step_name,
            'error': str(e),
            'failed_at': datetime.utcnow().isoformat()
        })

        # Execute compensations
        for compensation in saga_state['compensations_needed']:
            try:
                comp_handler = compensation_handlers.get(compensation['step'])
                if comp_handler:
                    comp_handler(compensation['context'])
            except Exception as comp_error:
                saga_state['errors'].append({
                    'compensation': compensation['step'],
                    'error': str(comp_error)
                })

        saga_state['status'] = 'failed'
        break
else:
    # All steps completed successfully
    saga_state['status'] = 'completed'
    saga_state['completed_at'] = datetime.utcnow().isoformat()

result = saga_state
""",
    input_types={
        "saga_type": str,
        "initial_context": dict,
        "step_handlers": dict,
        "compensation_handlers": dict
    }
)

# Saga State Manager
saga_state_manager = PythonCodeNode(
    name="saga_state_manager",
    code="""
from datetime import datetime, timedelta

# Saga timeout configuration
SAGA_TIMEOUT = 300  # 5 minutes
RETRY_DELAYS = [5, 15, 45]  # Exponential backoff

# Update saga states
active_sagas = []
completed_sagas = []
failed_sagas = []
timed_out_sagas = []

for saga in sagas:
    # Check timeout
    started_at = datetime.fromisoformat(saga['started_at'])
    if datetime.utcnow() - started_at > timedelta(seconds=SAGA_TIMEOUT):
        saga['status'] = 'timed_out'
        saga['timed_out_at'] = datetime.utcnow().isoformat()
        timed_out_sagas.append(saga)
        continue

    # Check status
    if saga['status'] == 'completed':
        completed_sagas.append(saga)
    elif saga['status'] == 'failed':
        # Check retry policy
        retry_count = saga.get('retry_count', 0)
        if retry_count < len(RETRY_DELAYS):
            last_error_time = datetime.fromisoformat(saga['errors'][-1]['failed_at'])
            retry_delay = timedelta(seconds=RETRY_DELAYS[retry_count])

            if datetime.utcnow() - last_error_time >= retry_delay:
                # Mark for retry
                saga['status'] = 'pending_retry'
                saga['retry_count'] = retry_count + 1
                saga['retry_at'] = datetime.utcnow().isoformat()
                active_sagas.append(saga)
            else:
                failed_sagas.append(saga)
        else:
            # Max retries exceeded
            saga['status'] = 'permanently_failed'
            failed_sagas.append(saga)
    else:
        active_sagas.append(saga)

result = {
    'active': active_sagas,
    'completed': completed_sagas,
    'failed': failed_sagas,
    'timed_out': timed_out_sagas,
    'statistics': {
        'total': len(sagas),
        'active': len(active_sagas),
        'completed': len(completed_sagas),
        'failed': len(failed_sagas),
        'timed_out': len(timed_out_sagas)
    }
}
""",
    input_types={"sagas": list}
)

# Choreography-Based Saga Event Handler
choreography_handler = PythonCodeNode(
    name="choreography_handler",
    code="""

# Event to command mapping
event_command_map = {
    'OrderCreated': [
        {'service': 'inventory', 'command': 'ReserveItems'},
        {'service': 'payment', 'command': 'AuthorizePayment'}
    ],
    'InventoryReserved': [
        {'service': 'payment', 'command': 'CapturePayment'}
    ],
    'PaymentCaptured': [
        {'service': 'shipping', 'command': 'CreateShipment'}
    ],
    'ShipmentCreated': [
        {'service': 'notification', 'command': 'SendConfirmation'}
    ],
    # Compensation events
    'InventoryReservationFailed': [
        {'service': 'order', 'command': 'CancelOrder'}
    ],
    'PaymentFailed': [
        {'service': 'inventory', 'command': 'ReleaseReservation'},
        {'service': 'order', 'command': 'CancelOrder'}
    ]
}

# Process events and generate commands
generated_commands = []
saga_updates = []

for event in events:
    # Get saga context
    saga_id = event.get('saga_id')
    if not saga_id:
        # Start new saga
        saga_id = str(uuid.uuid4())
        saga_updates.append({
            'saga_id': saga_id,
            'started_by': event['event_type'],
            'started_at': datetime.utcnow().isoformat()
        })

    # Generate commands based on event
    if event['event_type'] in event_command_map:
        for cmd_spec in event_command_map[event['event_type']]:
            command = {
                'command_id': str(uuid.uuid4()),
                'saga_id': saga_id,
                'service': cmd_spec['service'],
                'command_type': cmd_spec['command'],
                'payload': event['payload'],
                'correlation_id': event.get('correlation_id', saga_id),
                'created_at': datetime.utcnow().isoformat()
            }
            generated_commands.append(command)

    # Track saga progress
    saga_updates.append({
        'saga_id': saga_id,
        'event': event['event_type'],
        'processed_at': datetime.utcnow().isoformat()
    })

result = {
    'commands': generated_commands,
    'saga_updates': saga_updates,
    'events_processed': len(events)
}
""",
    input_types={"events": list}
)

```

## Event Streaming and Real-Time Processing

### Stream Processing Engine

```python
# Event Stream Processor
stream_processor = PythonCodeNode(
    name="stream_processor",
    code="""
from datetime import datetime, timedelta
from collections import defaultdict

# Window configuration
window_size = window_config.get('size', 60)  # seconds
window_type = window_config.get('type', 'tumbling')  # tumbling, sliding, session
slide_interval = window_config.get('slide', 30)  # for sliding windows

# Initialize windows
windows = defaultdict(lambda: {
    'events': [],
    'aggregates': {},
    'start_time': None,
    'end_time': None
})

# Process stream events
processed_events = []
window_results = []

for event in stream_events:
    event_time = datetime.fromisoformat(event['timestamp'])

    # Determine window key
    if window_type == 'tumbling':
        window_start = event_time.replace(second=0, microsecond=0)
        window_key = window_start.isoformat()
    elif window_type == 'sliding':
        # Multiple windows for sliding
        base_time = event_time.replace(second=0, microsecond=0)
        for offset in range(0, window_size, slide_interval):
            window_start = base_time - timedelta(seconds=offset)
            if window_start <= event_time < window_start + timedelta(seconds=window_size):
                window_key = f"{window_start.isoformat()}_{offset}"
                windows[window_key]['events'].append(event)
    elif window_type == 'session':
        # Session windows based on gaps
        session_gap = window_config.get('gap', 30)
        # Logic for session window detection
        pass

    # Add to window
    window = windows[window_key]
    window['events'].append(event)

    # Update window boundaries
    if not window['start_time'] or event_time < datetime.fromisoformat(window['start_time']):
        window['start_time'] = event_time.isoformat()
    if not window['end_time'] or event_time > datetime.fromisoformat(window['end_time']):
        window['end_time'] = event_time.isoformat()

    # Apply aggregation functions
    for agg_name, agg_func in aggregations.items():
        if agg_name not in window['aggregates']:
            window['aggregates'][agg_name] = agg_func(window['events'])
        else:
            # Incremental aggregation
            window['aggregates'][agg_name] = agg_func(window['events'])

    processed_events.append({
        'event_id': event.get('event_id'),
        'window_key': window_key,
        'processed_at': datetime.utcnow().isoformat()
    })

# Check for closed windows
current_time = datetime.utcnow()
for window_key, window in windows.items():
    window_end = datetime.fromisoformat(window['end_time']) if window['end_time'] else current_time
    if current_time - window_end > timedelta(seconds=window_size):
        # Window is closed
        window_results.append({
            'window_key': window_key,
            'start_time': window['start_time'],
            'end_time': window['end_time'],
            'event_count': len(window['events']),
            'aggregates': window['aggregates']
        })

result = {
    'processed_events': processed_events,
    'window_results': window_results,
    'active_windows': len(windows)
}
""",
    input_types={
        "stream_events": list,
        "window_config": dict,
        "aggregations": dict
    }
)

# Complex Event Processing (CEP)
complex_event_processor = PythonCodeNode(
    name="complex_event_processor",
    code="""
import re
from datetime import datetime, timedelta

# Pattern definitions
patterns = {
    'fraud_pattern': {
        'sequence': ['Login', 'HighValueTransaction', 'LocationChange'],
        'time_window': 300,  # 5 minutes
        'conditions': lambda events: (
            events[1]['payload'].get('amount', 0) > 10000 and
            events[2]['payload'].get('distance', 0) > 1000
        )
    },
    'abandon_cart': {
        'sequence': ['AddToCart', 'ViewCart', '!Checkout'],
        'time_window': 1800,  # 30 minutes
        'conditions': lambda events: True
    },
    'system_failure': {
        'sequence': ['ServiceError', 'ServiceError', 'ServiceError'],
        'time_window': 60,  # 1 minute
        'conditions': lambda events: (
            all(e['payload'].get('service') == events[0]['payload'].get('service')
                for e in events)
        )
    }
}

# Detect patterns
detected_patterns = []
partial_matches = []

# Group events by entity (user, session, etc.)
events_by_entity = defaultdict(list)
for event in events:
    entity_id = event.get('entity_id') or event.get('user_id') or event.get('session_id')
    if entity_id:
        events_by_entity[entity_id].append(event)

# Check patterns for each entity
for entity_id, entity_events in events_by_entity.items():
    # Sort events by time
    entity_events.sort(key=lambda e: e['timestamp'])

    for pattern_name, pattern_def in patterns.items():
        sequence = pattern_def['sequence']
        time_window = pattern_def['time_window']
        conditions = pattern_def['conditions']

        # Sliding window pattern detection
        for i in range(len(entity_events)):
            match_events = []
            seq_index = 0
            start_time = datetime.fromisoformat(entity_events[i]['timestamp'])

            for j in range(i, len(entity_events)):
                event = entity_events[j]
                event_time = datetime.fromisoformat(event['timestamp'])

                # Check time window
                if event_time - start_time > timedelta(seconds=time_window):
                    break

                # Check sequence
                expected = sequence[seq_index]
                if expected.startswith('!'):
                    # Negative pattern - should NOT occur
                    if event['event_type'] == expected[1:]:
                        break
                elif event['event_type'] == expected:
                    match_events.append(event)
                    seq_index += 1

                    if seq_index == len(sequence):
                        # Full sequence matched
                        if conditions(match_events):
                            detected_patterns.append({
                                'pattern': pattern_name,
                                'entity_id': entity_id,
                                'events': match_events,
                                'detected_at': datetime.utcnow().isoformat(),
                                'confidence': 1.0
                            })
                        break

            # Track partial matches
            if 0 < seq_index < len(sequence):
                partial_matches.append({
                    'pattern': pattern_name,
                    'entity_id': entity_id,
                    'matched': seq_index,
                    'total': len(sequence),
                    'last_event': match_events[-1] if match_events else None
                })

result = {
    'detected_patterns': detected_patterns,
    'partial_matches': partial_matches,
    'entities_analyzed': len(events_by_entity),
    'total_events': len(events)
}
""",
    input_types={"events": list}
)

# Stream Join Processor
stream_join = PythonCodeNode(
    name="stream_join",
    code="""
from datetime import datetime, timedelta

# Join configuration
join_window = join_config.get('window', 60)  # seconds
join_type = join_config.get('type', 'inner')  # inner, left, right, outer
join_key = join_config.get('key', 'id')

# Time-based stream join
joined_results = []
unmatched_left = []
unmatched_right = []

# Create time-indexed structures
left_by_time = defaultdict(list)
right_by_time = defaultdict(list)

for event in left_stream:
    time_bucket = datetime.fromisoformat(event['timestamp']).replace(second=0, microsecond=0)
    left_by_time[time_bucket].append(event)

for event in right_stream:
    time_bucket = datetime.fromisoformat(event['timestamp']).replace(second=0, microsecond=0)
    right_by_time[time_bucket].append(event)

# Perform time-windowed join
for time_bucket in sorted(set(left_by_time.keys()) | set(right_by_time.keys())):
    # Get events within window
    window_start = time_bucket - timedelta(seconds=join_window)
    window_end = time_bucket + timedelta(seconds=join_window)

    left_events = []
    right_events = []

    # Collect events within window
    for t in [window_start, time_bucket, window_end]:
        if t in left_by_time:
            left_events.extend(left_by_time[t])
        if t in right_by_time:
            right_events.extend(right_by_time[t])

    # Create join key indexes
    left_index = defaultdict(list)
    right_index = defaultdict(list)

    for event in left_events:
        key_value = event.get(join_key)
        if key_value:
            left_index[key_value].append(event)

    for event in right_events:
        key_value = event.get(join_key)
        if key_value:
            right_index[key_value].append(event)

    # Perform join based on type
    all_keys = set(left_index.keys()) | set(right_index.keys())

    for key in all_keys:
        left_matches = left_index.get(key, [])
        right_matches = right_index.get(key, [])

        if left_matches and right_matches:
            # Inner join - cartesian product of matches
            for left_event in left_matches:
                for right_event in right_matches:
                    joined_results.append({
                        'join_key': key,
                        'left': left_event,
                        'right': right_event,
                        'joined_at': datetime.utcnow().isoformat()
                    })
        elif left_matches and not right_matches and join_type in ['left', 'outer']:
            for left_event in left_matches:
                unmatched_left.append(left_event)
        elif right_matches and not left_matches and join_type in ['right', 'outer']:
            for right_event in right_matches:
                unmatched_right.append(right_event)

result = {
    'joined': joined_results,
    'unmatched_left': unmatched_left,
    'unmatched_right': unmatched_right,
    'statistics': {
        'joined_count': len(joined_results),
        'left_unmatched': len(unmatched_left),
        'right_unmatched': len(unmatched_right)
    }
}
""",
    input_types={
        "left_stream": list,
        "right_stream": list,
        "join_config": dict
    }
)

```

## Domain Event Patterns

### Domain Event Design

```python
# Domain Event Factory
domain_event_factory = PythonCodeNode(
    name="domain_event_factory",
    code="""
import uuid
from datetime import datetime

# Domain event specifications
event_specs = {
    'Customer': {
        'Registered': ['customer_id', 'email', 'name'],
        'ProfileUpdated': ['customer_id', 'changes'],
        'Deactivated': ['customer_id', 'reason']
    },
    'Order': {
        'Placed': ['order_id', 'customer_id', 'items', 'total'],
        'Paid': ['order_id', 'payment_method', 'amount'],
        'Shipped': ['order_id', 'tracking_number', 'carrier'],
        'Delivered': ['order_id', 'delivered_at'],
        'Cancelled': ['order_id', 'reason', 'refund_amount']
    },
    'Inventory': {
        'ItemAdded': ['sku', 'quantity', 'location'],
        'ItemRemoved': ['sku', 'quantity', 'reason'],
        'LowStockAlert': ['sku', 'current_quantity', 'threshold']
    }
}

# Create domain events
created_events = []
validation_errors = []

for event_request in event_requests:
    try:
        aggregate_type = event_request['aggregate_type']
        event_type = event_request['event_type']
        event_data = event_request['data']

        # Validate event type
        if aggregate_type not in event_specs:
            raise ValueError(f"Unknown aggregate type: {aggregate_type}")

        if event_type not in event_specs[aggregate_type]:
            raise ValueError(f"Unknown event type: {event_type} for {aggregate_type}")

        # Validate required fields
        required_fields = event_specs[aggregate_type][event_type]
        missing_fields = [field for field in required_fields if field not in event_data]

        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        # Create domain event
        domain_event = {
            'event_id': str(uuid.uuid4()),
            'aggregate_type': aggregate_type,
            'aggregate_id': event_data.get(f"{aggregate_type.lower()}_id"),
            'event_type': f"{aggregate_type}{event_type}",
            'event_version': 1,
            'occurred_at': datetime.utcnow().isoformat(),
            'data': event_data,
            'metadata': {
                'user_id': event_request.get('user_id'),
                'source': event_request.get('source', 'system'),
                'correlation_id': event_request.get('correlation_id', str(uuid.uuid4())),
                'causation_id': event_request.get('causation_id')
            }
        }

        created_events.append(domain_event)

    except Exception as e:
        validation_errors.append({
            'request': event_request,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        })

result = {
    'events': created_events,
    'errors': validation_errors,
    'success_rate': len(created_events) / len(event_requests) if event_requests else 0
}
""",
    input_types={"event_requests": list}
)

# Event Policy Engine
event_policy_engine = PythonCodeNode(
    name="event_policy_engine",
    code="""
from datetime import datetime

# Policy definitions
policies = {
    'OrderPlaced': [
        {
            'name': 'reserve_inventory',
            'condition': lambda e: e['data']['total'] > 0,
            'actions': ['ReserveInventory', 'CheckFraud']
        },
        {
            'name': 'vip_notification',
            'condition': lambda e: e['data'].get('customer_tier') == 'VIP',
            'actions': ['NotifyVIPService']
        }
    ],
    'PaymentFailed': [
        {
            'name': 'retry_payment',
            'condition': lambda e: e['metadata'].get('retry_count', 0) < 3,
            'actions': ['RetryPayment']
        },
        {
            'name': 'cancel_order',
            'condition': lambda e: e['metadata'].get('retry_count', 0) >= 3,
            'actions': ['CancelOrder', 'NotifyCustomer']
        }
    ],
    'LowStockAlert': [
        {
            'name': 'auto_reorder',
            'condition': lambda e: e['data']['current_quantity'] < e['data']['threshold'],
            'actions': ['CreatePurchaseOrder', 'NotifySupplier']
        }
    ]
}

# Process events through policies
triggered_actions = []
policy_violations = []

for event in events:
    event_type = event['event_type']

    if event_type in policies:
        for policy in policies[event_type]:
            try:
                # Evaluate policy condition
                if policy['condition'](event):
                    # Trigger actions
                    for action in policy['actions']:
                        triggered_actions.append({
                            'action': action,
                            'trigger_event': event['event_id'],
                            'policy': policy['name'],
                            'triggered_at': datetime.utcnow().isoformat(),
                            'context': {
                                'event_data': event['data'],
                                'metadata': event['metadata']
                            }
                        })

            except Exception as e:
                policy_violations.append({
                    'event_id': event['event_id'],
                    'policy': policy['name'],
                    'error': str(e),
                    'timestamp': datetime.utcnow().isoformat()
                })

result = {
    'triggered_actions': triggered_actions,
    'policy_violations': policy_violations,
    'events_processed': len(events),
    'actions_triggered': len(triggered_actions)
}
""",
    input_types={"events": list}
)

# Event Choreography Coordinator
event_choreography = PythonCodeNode(
    name="event_choreography",
    code="""
from datetime import datetime
import uuid

# Service event subscriptions
subscriptions = {
    'inventory_service': ['OrderPlaced', 'OrderCancelled'],
    'payment_service': ['OrderPlaced', 'RefundRequested'],
    'shipping_service': ['PaymentCompleted', 'OrderPacked'],
    'notification_service': ['OrderPlaced', 'OrderShipped', 'OrderDelivered'],
    'analytics_service': ['*']  # Subscribe to all events
}

# Event routing
routed_events = defaultdict(list)
routing_metrics = {
    'total_events': 0,
    'events_by_service': defaultdict(int),
    'events_by_type': defaultdict(int)
}

for event in events:
    routing_metrics['total_events'] += 1
    routing_metrics['events_by_type'][event['event_type']] += 1

    # Route to subscribed services
    for service, event_types in subscriptions.items():
        if '*' in event_types or event['event_type'] in event_types:
            # Create service-specific event envelope
            service_event = {
                'envelope_id': str(uuid.uuid4()),
                'service': service,
                'event': event,
                'routed_at': datetime.utcnow().isoformat(),
                'retry_count': 0,
                'acknowledgment_required': True
            }

            routed_events[service].append(service_event)
            routing_metrics['events_by_service'][service] += 1

# Generate service commands based on events
service_commands = []

# Service-specific event handlers
if 'inventory_service' in routed_events:
    for envelope in routed_events['inventory_service']:
        event = envelope['event']
        if event['event_type'] == 'OrderPlaced':
            service_commands.append({
                'service': 'inventory_service',
                'command': 'ReserveItems',
                'payload': {
                    'order_id': event['data']['order_id'],
                    'items': event['data']['items']
                },
                'triggered_by': event['event_id']
            })

if 'payment_service' in routed_events:
    for envelope in routed_events['payment_service']:
        event = envelope['event']
        if event['event_type'] == 'OrderPlaced':
            service_commands.append({
                'service': 'payment_service',
                'command': 'ProcessPayment',
                'payload': {
                    'order_id': event['data']['order_id'],
                    'amount': event['data']['total'],
                    'customer_id': event['data']['customer_id']
                },
                'triggered_by': event['event_id']
            })

result = {
    'routed_events': dict(routed_events),
    'service_commands': service_commands,
    'routing_metrics': dict(routing_metrics)
}
""",
    input_types={"events": list}
)

```

## Production-Ready Event Handling

### Resilient Event Processing

```python
# SDK Setup for example
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = WorkflowBuilder()
# Runtime should be created separately
runtime = LocalRuntime()

# Circuit Breaker Pattern
circuit_breaker = PythonCodeNode(
    name="circuit_breaker",
    code="""
from datetime import datetime, timedelta

# Circuit breaker configuration
FAILURE_THRESHOLD = 5
SUCCESS_THRESHOLD = 3
TIMEOUT = 30  # seconds
HALF_OPEN_REQUESTS = 3

# Initialize or update circuit state
if not circuit_state:
    circuit_state = {
        'status': 'closed',  # closed, open, half_open
        'failure_count': 0,
        'success_count': 0,
        'last_failure_time': None,
        'last_success_time': None,
        'half_open_attempts': 0
    }

# Process requests based on circuit state
processed_requests = []
rejected_requests = []

for request in requests:
    if circuit_state['status'] == 'open':
        # Check if timeout has passed
        if circuit_state['last_failure_time']:
            time_since_failure = (datetime.utcnow() -
                                datetime.fromisoformat(circuit_state['last_failure_time'])).total_seconds()
            if time_since_failure >= TIMEOUT:
                # Move to half-open state
                circuit_state['status'] = 'half_open'
                circuit_state['half_open_attempts'] = 0
            else:
                # Still in timeout, reject request
                rejected_requests.append({
                    'request': request,
                    'reason': 'Circuit breaker is open',
                    'rejected_at': datetime.utcnow().isoformat()
                })
                continue

    if circuit_state['status'] == 'half_open':
        # Limit requests in half-open state
        if circuit_state['half_open_attempts'] >= HALF_OPEN_REQUESTS:
            rejected_requests.append({
                'request': request,
                'reason': 'Half-open request limit reached',
                'rejected_at': datetime.utcnow().isoformat()
            })
            continue
        circuit_state['half_open_attempts'] += 1

    # Process request
    try:
        # Simulate processing with handler
        if request_handler:
            result = request_handler(request)
            processed_requests.append({
                'request': request,
                'result': result,
                'processed_at': datetime.utcnow().isoformat()
            })

            # Update success count
            circuit_state['success_count'] += 1
            circuit_state['last_success_time'] = datetime.utcnow().isoformat()

            # Check state transitions
            if circuit_state['status'] == 'half_open':
                if circuit_state['success_count'] >= SUCCESS_THRESHOLD:
                    circuit_state['status'] = 'closed'
                    circuit_state['failure_count'] = 0
                    circuit_state['success_count'] = 0
        else:
            raise Exception("No request handler provided")

    except Exception as e:
        # Request failed
        circuit_state['failure_count'] += 1
        circuit_state['last_failure_time'] = datetime.utcnow().isoformat()

        # Check failure threshold
        if circuit_state['failure_count'] >= FAILURE_THRESHOLD:
            circuit_state['status'] = 'open'
            circuit_state['success_count'] = 0

        rejected_requests.append({
            'request': request,
            'reason': f"Processing failed: {str(e)}",
            'rejected_at': datetime.utcnow().isoformat()
        })

result = {
    'processed': processed_requests,
    'rejected': rejected_requests,
    'circuit_state': circuit_state,
    'metrics': {
        'total_requests': len(requests),
        'processed': len(processed_requests),
        'rejected': len(rejected_requests),
        'circuit_status': circuit_state['status']
    }
}
""",
    input_types={
        "requests": list,
        "circuit_state": dict,
        "request_handler": dict
    }
)

# Dead Letter Queue Handler
dlq_handler = PythonCodeNode(
    name="dlq_handler",
    code="""

# DLQ configuration
MAX_AGE_DAYS = 7
BATCH_SIZE = 100
RETRY_STRATEGIES = {
    'exponential': lambda attempt: 2 ** attempt,
    'linear': lambda attempt: attempt * 60,
    'fibonacci': lambda attempt: [1, 1, 2, 3, 5, 8, 13, 21][min(attempt, 7)] * 60
}

# Process dead letter messages
processed_messages = []
permanently_failed = []
retry_scheduled = []
expired_messages = []

# Group messages by failure reason
failure_groups = defaultdict(list)
for msg in dead_letter_messages:
    failure_groups[msg.get('failure_reason', 'unknown')].append(msg)

# Process each group
for failure_reason, messages in failure_groups.items():
    for message in messages[:BATCH_SIZE]:  # Process in batches
        # Check message age
        message_time = datetime.fromisoformat(message['failed_at'])
        age_days = (datetime.utcnow() - message_time).days

        if age_days > MAX_AGE_DAYS:
            expired_messages.append({
                'message': message,
                'expired_at': datetime.utcnow().isoformat(),
                'age_days': age_days
            })
            continue

        # Apply retry strategy
        retry_count = message.get('retry_count', 0)
        retry_strategy = message.get('retry_strategy', 'exponential')

        if retry_count < message.get('max_retries', 5):
            # Calculate next retry time
            strategy_func = RETRY_STRATEGIES.get(retry_strategy, RETRY_STRATEGIES['exponential'])
            delay_seconds = strategy_func(retry_count)
            next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)

            retry_scheduled.append({
                'message': message['original_message'],
                'retry_count': retry_count + 1,
                'next_retry': next_retry.isoformat(),
                'strategy': retry_strategy
            })
        else:
            # Max retries exceeded - permanent failure
            permanently_failed.append({
                'message': message,
                'final_status': 'permanently_failed',
                'total_retries': retry_count,
                'failed_at': datetime.utcnow().isoformat()
            })

# Generate alerts for high failure rates
alert_threshold = 0.1  # 10% failure rate
failure_rate = len(permanently_failed) / len(dead_letter_messages) if dead_letter_messages else 0

alerts = []
if failure_rate > alert_threshold:
    alerts.append({
        'type': 'high_failure_rate',
        'rate': failure_rate,
        'threshold': alert_threshold,
        'message_count': len(permanently_failed),
        'alert_time': datetime.utcnow().isoformat()
    })

result = {
    'retry_scheduled': retry_scheduled,
    'permanently_failed': permanently_failed,
    'expired': expired_messages,
    'alerts': alerts,
    'statistics': {
        'total_messages': len(dead_letter_messages),
        'scheduled_for_retry': len(retry_scheduled),
        'permanent_failures': len(permanently_failed),
        'expired': len(expired_messages),
        'failure_rate': failure_rate
    }
}
""",
    input_types={"dead_letter_messages": list}
)

# Event Store Compaction
event_compaction = PythonCodeNode(
    name="event_compaction",
    code="""

# Compaction configuration
SNAPSHOT_INTERVAL = 100  # Create snapshot every N events
RETENTION_DAYS = 90  # Keep detailed events for N days
ARCHIVE_BATCH_SIZE = 1000

# Process events for compaction
compacted_streams = {}
archived_events = []
active_events = []

# Group events by aggregate
events_by_aggregate = defaultdict(list)
for event in events:
    events_by_aggregate[event['aggregate_id']].append(event)

# Compact each aggregate's events
for aggregate_id, aggregate_events in events_by_aggregate.items():
    # Sort by timestamp
    aggregate_events.sort(key=lambda e: e['timestamp'])

    # Find last snapshot
    last_snapshot = None
    last_snapshot_version = 0

    for existing_snapshot in snapshots:
        if (existing_snapshot['aggregate_id'] == aggregate_id and
            existing_snapshot['version'] > last_snapshot_version):
            last_snapshot = existing_snapshot
            last_snapshot_version = existing_snapshot['version']

    # Determine which events to keep
    events_since_snapshot = [
        e for e in aggregate_events
        if not last_snapshot or e['timestamp'] > last_snapshot['timestamp']
    ]

    # Check if new snapshot needed
    if len(events_since_snapshot) >= SNAPSHOT_INTERVAL:
        # Build new snapshot
        state = last_snapshot['state'] if last_snapshot else {}

        for event in events_since_snapshot:
            # Apply event to state
            if event['event_type'].endswith('Created'):
                state = event['data']
            elif event['event_type'].endswith('Updated'):
                state.update(event['data'])
            elif event['event_type'].endswith('Deleted'):
                state['deleted'] = True

        new_snapshot = {
            'aggregate_id': aggregate_id,
            'version': last_snapshot_version + len(events_since_snapshot),
            'state': state,
            'timestamp': events_since_snapshot[-1]['timestamp'],
            'created_at': datetime.utcnow().isoformat()
        }

        compacted_streams[aggregate_id] = {
            'snapshot': new_snapshot,
            'events_compacted': len(events_since_snapshot)
        }

    # Archive old events
    cutoff_date = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    for event in aggregate_events:
        event_time = datetime.fromisoformat(event['timestamp'])
        if event_time < cutoff_date:
            archived_events.append(event)
        else:
            active_events.append(event)

# Batch archive events
archive_batches = []
for i in range(0, len(archived_events), ARCHIVE_BATCH_SIZE):
    batch = archived_events[i:i + ARCHIVE_BATCH_SIZE]
    archive_batches.append({
        'batch_id': f"archive_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{i//ARCHIVE_BATCH_SIZE}",
        'events': batch,
        'event_count': len(batch),
        'date_range': {
            'start': min(e['timestamp'] for e in batch),
            'end': max(e['timestamp'] for e in batch)
        }
    })

result = {
    'compacted_streams': compacted_streams,
    'archive_batches': archive_batches,
    'active_events': active_events,
    'statistics': {
        'total_events': len(events),
        'aggregates_compacted': len(compacted_streams),
        'events_archived': len(archived_events),
        'events_active': len(active_events),
        'archive_batches_created': len(archive_batches)
    }
}
""",
    input_types={"events": list, "snapshots": list}
)

# Build Production Event Handling Workflow
production_workflow = WorkflowBuilder()
workflow.workflow = WorkflowBuilder()
workflow.add_node(circuit_breaker)
workflow = WorkflowBuilder()
workflow.add_node(dlq_handler)
workflow = WorkflowBuilder()
workflow.add_node(event_compaction)

# Connect for resilient processing
workflow = WorkflowBuilder()
# Workflow setup goes here  # Method signature

```

## Best Practices and Guidelines

### 1. Event Design Principles
- Use past tense for event names (OrderPlaced, not PlaceOrder)
- Include all necessary data in events (events should be self-contained)
- Version events for backward compatibility
- Use correlation IDs for tracing across services

### 2. Performance Optimization
- Implement event batching for high-throughput scenarios
- Use partitioning for parallel processing
- Apply backpressure mechanisms to prevent overwhelming consumers
- Implement efficient serialization (consider Protobuf or Avro)

### 3. Error Handling Strategies
- Implement idempotent event handlers
- Use dead letter queues for unprocessable messages
- Apply circuit breakers for failing services
- Implement compensating transactions for saga failures

### 4. Monitoring and Observability
- Track event processing latency
- Monitor queue depths and consumer lag
- Implement distributed tracing with correlation IDs
- Set up alerts for abnormal patterns

### 5. Security Considerations
- Encrypt sensitive data in events
- Implement event authentication and authorization
- Use secure channels for event transmission
- Audit all event operations

### 6. Testing Strategies
- Test event ordering and delivery guarantees
- Simulate failures and recovery scenarios
- Test saga compensation logic
- Verify idempotency of event handlers

## Conclusion

This guide provides comprehensive patterns for building event-driven architectures with Kailash SDK. By following these patterns and best practices, you can build scalable, resilient, and maintainable event-driven systems that handle complex business workflows effectively.

Remember to:
- Start simple and evolve your event model
- Design for failure from the beginning
- Monitor and measure everything
- Keep events immutable and versioned
- Document your event contracts clearly
