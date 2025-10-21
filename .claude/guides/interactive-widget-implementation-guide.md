# Interactive Widget Response System - Implementation Guide (Part 3)

**Version**: 1.0
**Created**: 2025-10-18
**Status**: Developer Implementation Guide
**Prerequisite Reading**: [Widget Response Technical Spec](./widget-response-technical-spec.md), [Enterprise AI Hub UI/UX Design](./enterprise-ai-hub-uiux-design.md)

---

## Table of Contents
1. [Quick Start](#quick-start)
2. [Backend Implementation Walkthrough](#backend-implementation-walkthrough)
3. [Frontend Implementation Walkthrough](#frontend-implementation-walkthrough)
4. [Advanced Widget Patterns](#advanced-widget-patterns)
5. [State Management Deep Dive](#state-management-deep-dive)
6. [Performance Best Practices](#performance-best-practices)
7. [Testing Cookbook](#testing-cookbook)
8. [Deployment Checklist](#deployment-checklist)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Real-World Examples](#real-world-examples)

---

## Quick Start

### 5-Minute Widget Hello World

**Goal**: Render your first interactive widget in an AI response.

#### Backend (Python + Kailash)

```python
# backend/agents/simple_widget_agent.py
from kaizen.agents import BaseAgent, Signature
from kaizen.signatures import InputField, OutputField
from typing import Dict, Any
import uuid
from datetime import datetime

class SimpleWidgetSignature(Signature):
    query: str = InputField(description="User query")
    widget_descriptor: Dict[str, Any] = OutputField(description="Widget descriptor")

class SimpleWidgetAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            signature=SimpleWidgetSignature,
            instructions="""Generate a simple card widget."""
        )

    async def generate_hello_widget(self) -> Dict[str, Any]:
        """Generate a hello world card widget"""
        return {
            "type": "widget",
            "widget_id": str(uuid.uuid4()),
            "widget_type": "card",
            "data": {
                "title": "Hello from AI!",
                "description": "This is your first interactive widget.",
                "icon": "celebration",
            },
            "config": {
                "interactive": True,
            },
            "actions": [
                {
                    "action_id": str(uuid.uuid4()),
                    "label": "Click Me",
                    "type": "api_call",
                    "params": {
                        "endpoint": "/api/widget/hello",
                        "method": "POST"
                    },
                    "permissions": []
                }
            ],
            "metadata": {
                "sources": [],
                "generated_at": datetime.utcnow().isoformat()
            }
        }

# backend/api/endpoints.py
from nexus import Nexus
from kailash.runtime import AsyncLocalRuntime
import json

nexus = Nexus()

@nexus.stream_endpoint("/ai/chat")
async def chat_stream(message: str):
    """Simple streaming endpoint"""
    agent = SimpleWidgetAgent()

    # Stream text
    yield json.dumps({
        "type": "text",
        "content": "Here's an interactive widget for you:"
    }) + "\n"

    # Stream widget
    widget = await agent.generate_hello_widget()
    yield json.dumps({
        "type": "widget",
        "content": widget
    }) + "\n"

@nexus.endpoint("/api/widget/hello", methods=["POST"])
async def handle_hello_action():
    """Handle widget button click"""
    return {"message": "Hello from backend!"}
```

#### Frontend (Flutter)

```dart
// lib/features/chat/widgets/hello_widget.dart
import 'package:flutter/material.dart';
import 'package:aihub/core/design/design_system.dart';

class HelloCardWidget extends StatelessWidget {
  final Map<String, dynamic> data;
  final List<WidgetAction> actions;

  const HelloCardWidget({
    required this.data,
    required this.actions,
  });

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Icon + Title
          Row(
            children: [
              Icon(Icons.celebration, color: AppColors.primary, size: 32),
              AppSpacing.gapSm,
              Text(data['title'], style: AppTypography.h3),
            ],
          ),
          AppSpacing.gapSm,

          // Description
          Text(data['description'], style: AppTypography.bodyMedium),

          AppSpacing.gapMd,

          // Action button
          if (actions.isNotEmpty)
            AppButton.primary(
              label: actions[0].label,
              onPressed: () => _handleAction(context, actions[0]),
            ),
        ],
      ),
    );
  }

  Future<void> _handleAction(BuildContext context, WidgetAction action) async {
    // Call backend
    final response = await context.read<ApiClient>().post(
      action.params['endpoint'],
      {},
    );

    // Show result
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(response['message'])),
    );
  }
}
```

**Run it**:
```bash
# Backend
cd backend && python -m nexus run

# Frontend
cd frontend && flutter run -d chrome
```

---

## Backend Implementation Walkthrough

### Step 1: Create Widget Generator Agent

**Purpose**: AI agent that determines WHEN and WHAT widget to generate.

```python
# backend/agents/widget_generator.py
from kaizen.agents import BaseAgent, Signature
from kaizen.signatures import InputField, OutputField
from dataflow import DataFlow
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime
from enum import Enum

class QueryIntent(str, Enum):
    """Types of queries that need visualization"""
    DATA_ANALYSIS = "data_analysis"        # "Show Q2 sales"
    COMPARISON = "comparison"              # "Compare regions"
    TREND_ANALYSIS = "trend_analysis"      # "Sales over time"
    SEARCH_FILTER = "search_filter"        # "Find customers in NY"
    FORM_INPUT = "form_input"              # "Add new record"
    NAVIGATION = "navigation"              # "Go to dashboard"
    TEXT_ONLY = "text_only"                # "What is our policy?"

class WidgetGeneratorSignature(Signature):
    query: str = InputField(description="User's natural language query")
    intent: str = OutputField(description="Query intent classification")
    needs_widget: bool = OutputField(description="True if widget is needed")
    widget_type: Optional[str] = OutputField(description="Suggested widget type")
    reasoning: str = OutputField(description="Why this widget type")

class WidgetGeneratorAgent(BaseAgent):
    """
    Master agent for widget generation.

    Responsibilities:
    1. Analyze query intent
    2. Determine if widget is needed
    3. Select appropriate widget type
    4. Generate widget descriptor
    5. Apply RBAC to actions
    """

    def __init__(self, db: DataFlow):
        super().__init__(
            signature=WidgetGeneratorSignature,
            instructions="""
            You are an expert at analyzing user queries for data visualization needs.

            Classification Rules:
            - DATA_ANALYSIS: Query asks for metrics, totals, breakdowns
            - COMPARISON: Query compares entities (regions, products, time periods)
            - TREND_ANALYSIS: Query asks about changes over time
            - SEARCH_FILTER: Query filters/searches large datasets
            - FORM_INPUT: Query implies data entry or updates
            - NAVIGATION: Query asks to go to different page/section
            - TEXT_ONLY: Query is conceptual/explanatory

            Widget Selection:
            - DATA_ANALYSIS → card (metrics) or chart (breakdown)
            - COMPARISON → chart (bar/grouped bar)
            - TREND_ANALYSIS → chart (line/area)
            - SEARCH_FILTER → form (filters) + table (results)
            - FORM_INPUT → form
            - NAVIGATION → navigation_card
            - TEXT_ONLY → no widget

            Be conservative: Only suggest widgets when they CLEARLY add value.
            """,
        )
        self.db = db

    async def analyze_query(
        self,
        query: str,
        conversation_history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Analyze user query to determine visualization needs.

        Args:
            query: User's query
            conversation_history: Previous turns for context

        Returns:
            {
                'intent': QueryIntent,
                'needs_widget': bool,
                'widget_type': str | None,
                'reasoning': str
            }
        """
        # Run LLM analysis
        response = await self.run(query=query)

        return {
            'intent': QueryIntent(response.intent),
            'needs_widget': response.needs_widget,
            'widget_type': response.widget_type,
            'reasoning': response.reasoning
        }

    async def generate_widget(
        self,
        query: str,
        data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate complete widget descriptor.

        Args:
            query: User's query
            data: Fetched data from sources
            user_context: User permissions, preferences, active sources

        Returns:
            Widget descriptor dict or None
        """
        # Analyze query
        analysis = await self.analyze_query(query)

        if not analysis['needs_widget']:
            return None

        # Route to specific widget generator
        widget_type = analysis['widget_type']

        if widget_type == 'chart':
            return await self._generate_chart_widget(query, data, user_context)
        elif widget_type == 'table':
            return await self._generate_table_widget(query, data, user_context)
        elif widget_type == 'form':
            return await self._generate_form_widget(query, data, user_context)
        elif widget_type == 'card':
            return await self._generate_card_widget(query, data, user_context)
        elif widget_type == 'navigation_card':
            return await self._generate_navigation_widget(query, data, user_context)
        else:
            return None

    async def _generate_chart_widget(
        self,
        query: str,
        data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Generate chart widget (bar, line, pie)"""

        # Determine chart type from data shape
        chart_type = self._infer_chart_type(data)

        # Extract chart data
        series_data = self._extract_series_data(data)

        # Build actions based on permissions
        actions = []
        user_permissions = user_context.get('permissions', [])

        # Drill-down action (managers only)
        if 'manager' in user_permissions or 'analyst' in user_permissions:
            actions.append({
                "action_id": str(uuid.uuid4()),
                "label": "View Details",
                "type": "api_call",
                "params": {
                    "endpoint": "/api/data/drilldown",
                    "method": "POST",
                    "data_key": data.get('data_key')  # Reference to data
                },
                "permissions": ["manager", "analyst"]
            })

        # Export action (exporters only)
        if 'data_exporter' in user_permissions:
            actions.append({
                "action_id": str(uuid.uuid4()),
                "label": "Export CSV",
                "type": "download",
                "params": {
                    "format": "csv",
                    "filename": f"{query[:30].replace(' ', '_')}.csv",
                    "data_key": data.get('data_key')
                },
                "permissions": ["data_exporter"]
            })

        # Build widget descriptor
        return {
            "type": "widget",
            "widget_id": str(uuid.uuid4()),
            "widget_type": "chart",
            "data": {
                "chart_type": chart_type,
                "series": series_data,
                "x_axis_label": data.get('x_label', 'Category'),
                "y_axis_label": data.get('y_label', 'Value'),
                "title": data.get('title', query),
            },
            "config": {
                "interactive": True,
                "responsive": True,
                "exportable": 'data_exporter' in user_permissions,
                "drill_down_enabled": 'manager' in user_permissions or 'analyst' in user_permissions
            },
            "actions": actions,
            "metadata": self._build_metadata(data, user_context)
        }

    def _infer_chart_type(self, data: Dict[str, Any]) -> str:
        """Infer best chart type from data shape"""
        # Simple heuristic (can be enhanced with LLM)
        records = data.get('records', [])

        if len(records) <= 5:
            return 'bar'  # Few categories → bar
        elif len(records) > 20:
            return 'line'  # Many points → line
        else:
            return 'bar'  # Default

    def _extract_series_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract chart series from data"""
        records = data.get('records', [])

        # Assume records have 'label' and 'value' keys
        # (Adjust based on actual data structure)
        return [{
            "name": data.get('metric_name', 'Value'),
            "values": [r.get('value', 0) for r in records],
            "labels": [r.get('label', '') for r in records],
        }]

    def _build_metadata(
        self,
        data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build widget metadata with sources"""
        sources = []

        # Extract sources from data
        for source in data.get('sources', []):
            sources.append({
                "source_id": source.get('id', str(uuid.uuid4())),
                "source_name": source.get('name', 'Unknown'),
                "confidence": source.get('confidence', 0.0),
                "location": source.get('location', None)
            })

        return {
            "sources": sources,
            "generated_at": datetime.utcnow().isoformat(),
            "query": data.get('original_query'),
            "user_id": user_context.get('user_id')
        }

    async def _generate_table_widget(self, query, data, user_context):
        """Generate table widget - implementation similar to chart"""
        # TODO: Implement table generation
        pass

    async def _generate_form_widget(self, query, data, user_context):
        """Generate form widget - implementation similar to chart"""
        # TODO: Implement form generation
        pass

    async def _generate_card_widget(self, query, data, user_context):
        """Generate card widget - implementation similar to chart"""
        # TODO: Implement card generation
        pass

    async def _generate_navigation_widget(self, query, data, user_context):
        """Generate navigation card widget"""
        # TODO: Implement navigation generation
        pass
```

### Step 2: Integrate with Nexus Streaming API

**Purpose**: Stream text + widgets to Flutter frontend via WebSocket.

```python
# backend/api/chat_endpoint.py
from nexus import Nexus
from kailash.runtime import AsyncLocalRuntime
from dataflow import DataFlow
from agents.widget_generator import WidgetGeneratorAgent
from typing import Dict, Any, AsyncGenerator
import json

nexus = Nexus()
db = DataFlow()  # Initialize DataFlow

@nexus.stream_endpoint("/ai/chat")
async def chat_stream(
    session_id: str,
    message: str,
    user_context: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    Main chat streaming endpoint.

    Flow:
    1. Analyze query → determine if widget needed
    2. Fetch data from DataFlow sources
    3. Stream text response
    4. Stream widget descriptor (if needed)
    5. Stream citations

    Args:
        session_id: Unique conversation session ID
        message: User's message
        user_context: {
            'user_id': str,
            'permissions': List[str],
            'active_sources': List[str],
            'preferences': Dict[str, Any]
        }

    Yields:
        JSON chunks: {"type": "text"|"widget"|"citations", "content": ...}
    """

    # Initialize agents
    widget_agent = WidgetGeneratorAgent(db)

    # Step 1: Analyze query intent
    analysis = await widget_agent.analyze_query(message)

    # Step 2: Generate text response (streaming)
    yield json.dumps({
        "type": "status",
        "content": "Analyzing query..."
    }) + "\n"

    # Stream text response
    async for text_chunk in _generate_text_response(message, user_context):
        yield json.dumps({
            "type": "text",
            "content": text_chunk
        }) + "\n"

    # Step 3: If widget needed, fetch data and generate widget
    if analysis['needs_widget']:
        yield json.dumps({
            "type": "status",
            "content": "Generating visualization..."
        }) + "\n"

        # Fetch data
        data = await _fetch_data(
            query=message,
            sources=user_context['active_sources'],
            permissions=user_context['permissions']
        )

        # Generate widget
        widget_descriptor = await widget_agent.generate_widget(
            query=message,
            data=data,
            user_context=user_context
        )

        if widget_descriptor:
            yield json.dumps({
                "type": "widget",
                "content": widget_descriptor
            }) + "\n"

    # Step 4: Stream citations
    citations = await _generate_citations(message, user_context)
    yield json.dumps({
        "type": "citations",
        "content": citations
    }) + "\n"

    # Step 5: Done
    yield json.dumps({
        "type": "done"
    }) + "\n"


async def _generate_text_response(
    message: str,
    user_context: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """Generate streaming text response using LLM"""
    # Integrate with your LLM (OpenAI, Anthropic, etc.)
    # This is a placeholder

    text = f"Based on your query '{message}', here are the insights:"

    # Stream word by word for real-time effect
    for word in text.split():
        yield word + " "
        await asyncio.sleep(0.05)  # Simulate streaming


async def _fetch_data(
    query: str,
    sources: List[str],
    permissions: List[str]
) -> Dict[str, Any]:
    """
    Fetch data from DataFlow sources.

    Args:
        query: User's query
        sources: Active data source IDs
        permissions: User's RBAC permissions

    Returns:
        {
            'records': List[Dict],
            'sources': List[Dict],
            'title': str,
            'x_label': str,
            'y_label': str,
            'data_key': str  # For future drill-down
        }
    """
    # This is where you'd integrate with DataFlow
    # Example: Query sales data

    # Placeholder data
    return {
        'records': [
            {'label': 'Q1', 'value': 45000},
            {'label': 'Q2', 'value': 52000},
            {'label': 'Q3', 'value': 48000},
            {'label': 'Q4', 'value': 61000},
        ],
        'sources': [
            {
                'id': 'source-1',
                'name': 'Q2_Sales_Report.xlsx',
                'confidence': 0.95,
                'location': 'Sheet: Summary'
            }
        ],
        'title': 'Quarterly Sales',
        'x_label': 'Quarter',
        'y_label': 'Revenue ($)',
        'data_key': 'sales_quarterly_2024',
        'metric_name': 'Revenue'
    }


async def _generate_citations(
    message: str,
    user_context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate citations for response"""
    # Placeholder
    return [
        {
            'source_id': 'source-1',
            'source_name': 'Q2_Sales_Report.xlsx',
            'snippet': 'Q2 revenue was $52,000...',
            'confidence': 0.95,
            'page': 3
        }
    ]
```

### Step 3: Implement Action Handlers

**Purpose**: Handle user interactions with widgets (clicks, form submits, etc.).

```python
# backend/api/widget_actions.py
from nexus import Nexus
from kailash.rbac import check_permissions
from typing import Dict, Any
import uuid

nexus = Nexus()

@nexus.endpoint("/api/widget/action", methods=["POST"])
async def handle_widget_action(
    widget_id: str,
    action_id: str,
    params: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Universal widget action handler.

    Handles:
    - API calls (drill-down, fetch more data)
    - Downloads (CSV, PDF exports)
    - Form submissions
    - Navigation triggers

    Args:
        widget_id: UUID of widget
        action_id: UUID of action
        params: Action-specific parameters
        user_context: User ID, permissions, session

    Returns:
        Action result (data, file, redirect)
    """

    # Retrieve widget from cache/DB (for validation)
    widget = await get_widget_by_id(widget_id)

    if not widget:
        raise ValueError(f"Widget {widget_id} not found")

    # Find action
    action = next(
        (a for a in widget['actions'] if a['action_id'] == action_id),
        None
    )

    if not action:
        raise ValueError(f"Action {action_id} not found")

    # Validate RBAC
    user_permissions = user_context.get('permissions', [])
    required_permissions = action.get('permissions', [])

    if not check_permissions(user_permissions, required_permissions):
        raise PermissionError(
            f"User lacks required permissions: {required_permissions}"
        )

    # Route to action type handler
    action_type = action['type']

    if action_type == 'api_call':
        return await _handle_api_call(action, params, user_context)
    elif action_type == 'download':
        return await _handle_download(action, params, user_context)
    elif action_type == 'navigate':
        return await _handle_navigation(action, params, user_context)
    elif action_type == 'submit':
        return await _handle_form_submit(action, params, user_context)
    else:
        raise NotImplementedError(f"Action type {action_type} not supported")


async def _handle_api_call(
    action: Dict[str, Any],
    params: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle API call actions (drill-down, fetch more)"""
    endpoint = action['params']['endpoint']

    if endpoint == '/api/data/drilldown':
        # Fetch detailed data
        data_key = action['params']['data_key']
        detailed_data = await fetch_drilldown_data(data_key, params)

        # Return new widget or data
        return {
            "type": "new_widget",
            "widget": {
                "widget_type": "table",
                "data": detailed_data,
                # ... full widget descriptor
            }
        }

    else:
        raise NotImplementedError(f"Endpoint {endpoint} not supported")


async def _handle_download(
    action: Dict[str, Any],
    params: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle download actions (CSV, PDF exports)"""
    format = action['params']['format']
    filename = action['params']['filename']
    data_key = action['params']['data_key']

    # Fetch data
    data = await fetch_data_by_key(data_key)

    # Generate file
    if format == 'csv':
        file_content = generate_csv(data)
        content_type = 'text/csv'
    elif format == 'pdf':
        file_content = generate_pdf(data)
        content_type = 'application/pdf'
    else:
        raise ValueError(f"Unsupported format: {format}")

    # Return file URL (upload to S3 or return base64)
    file_url = await upload_file(file_content, filename)

    return {
        "type": "download",
        "url": file_url,
        "filename": filename,
        "content_type": content_type
    }


async def _handle_navigation(action, params, user_context):
    """Handle navigation actions"""
    route = action['params']['route']
    return {
        "type": "navigate",
        "route": route
    }


async def _handle_form_submit(action, params, user_context):
    """Handle form submissions"""
    form_data = params.get('form_data', {})

    # Validate and save
    # ... implementation depends on form type

    return {
        "type": "success",
        "message": "Form submitted successfully"
    }


# Helper functions
async def get_widget_by_id(widget_id: str) -> Dict[str, Any]:
    """Retrieve widget from cache or DB"""
    # TODO: Implement widget storage/retrieval
    pass

async def fetch_drilldown_data(data_key: str, params: Dict) -> Dict:
    """Fetch detailed drill-down data"""
    # TODO: Implement
    pass

async def fetch_data_by_key(data_key: str) -> List[Dict]:
    """Fetch data by key for export"""
    # TODO: Implement
    pass

def generate_csv(data: List[Dict]) -> bytes:
    """Generate CSV file from data"""
    import csv
    import io

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    return output.getvalue().encode('utf-8')

def generate_pdf(data: List[Dict]) -> bytes:
    """Generate PDF file from data"""
    # TODO: Implement with reportlab or similar
    pass

async def upload_file(content: bytes, filename: str) -> str:
    """Upload file to S3 and return URL"""
    # TODO: Implement S3 upload
    pass
```

---

## Frontend Implementation Walkthrough

### Step 1: WebSocket Connection Manager

**Purpose**: Manage persistent WebSocket connection to Nexus API.

```dart
// lib/core/services/chat_websocket_service.dart
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:convert';
import 'dart:async';
import 'package:flutter/foundation.dart';

class ChatWebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  final String _baseUrl;
  final StreamController<ChatMessage> _messageController =
      StreamController<ChatMessage>.broadcast();

  bool _isConnected = false;
  Timer? _reconnectTimer;
  int _reconnectAttempts = 0;

  ChatWebSocketService({required String baseUrl}) : _baseUrl = baseUrl;

  /// Stream of incoming messages
  Stream<ChatMessage> get messageStream => _messageController.stream;

  /// Connection status
  bool get isConnected => _isConnected;

  /// Connect to WebSocket
  Future<void> connect({
    required String sessionId,
    required Map<String, dynamic> userContext,
  }) async {
    try {
      final uri = Uri.parse('$_baseUrl/ai/chat?session_id=$sessionId');

      _channel = WebSocketChannel.connect(uri);

      // Send authentication
      _channel!.sink.add(json.encode({
        'type': 'auth',
        'user_context': userContext,
      }));

      // Listen to incoming messages
      _channel!.stream.listen(
        _handleIncomingMessage,
        onError: _handleError,
        onDone: _handleDisconnect,
      );

      _isConnected = true;
      _reconnectAttempts = 0;
      notifyListeners();

      debugPrint('✅ WebSocket connected');
    } catch (e) {
      debugPrint('❌ WebSocket connection failed: $e');
      _scheduleReconnect();
    }
  }

  /// Send message to backend
  void sendMessage(String message, {Map<String, dynamic>? metadata}) {
    if (!_isConnected || _channel == null) {
      throw StateError('WebSocket not connected');
    }

    _channel!.sink.add(json.encode({
      'type': 'message',
      'content': message,
      'metadata': metadata,
      'timestamp': DateTime.now().toIso8601String(),
    }));
  }

  /// Handle incoming messages
  void _handleIncomingMessage(dynamic data) {
    try {
      final jsonData = json.decode(data as String) as Map<String, dynamic>;
      final type = jsonData['type'] as String;

      ChatMessage message;

      switch (type) {
        case 'text':
          message = TextMessage(
            id: _generateMessageId(),
            content: jsonData['content'] as String,
            timestamp: DateTime.now(),
          );
          break;

        case 'widget':
          final widgetDesc = WidgetDescriptor.fromJson(
            jsonData['content'] as Map<String, dynamic>
          );
          message = WidgetMessage(
            id: _generateMessageId(),
            descriptor: widgetDesc,
            timestamp: DateTime.now(),
          );
          break;

        case 'citations':
          message = CitationsMessage(
            id: _generateMessageId(),
            citations: (jsonData['content'] as List)
                .map((c) => Citation.fromJson(c))
                .toList(),
            timestamp: DateTime.now(),
          );
          break;

        case 'status':
          message = StatusMessage(
            id: _generateMessageId(),
            status: jsonData['content'] as String,
            timestamp: DateTime.now(),
          );
          break;

        case 'done':
          message = DoneMessage(
            id: _generateMessageId(),
            timestamp: DateTime.now(),
          );
          break;

        default:
          debugPrint('⚠️ Unknown message type: $type');
          return;
      }

      _messageController.add(message);
    } catch (e) {
      debugPrint('❌ Error parsing message: $e');
    }
  }

  /// Handle errors
  void _handleError(error) {
    debugPrint('❌ WebSocket error: $error');
    _isConnected = false;
    notifyListeners();
    _scheduleReconnect();
  }

  /// Handle disconnection
  void _handleDisconnect() {
    debugPrint('⚠️ WebSocket disconnected');
    _isConnected = false;
    notifyListeners();
    _scheduleReconnect();
  }

  /// Schedule reconnection with exponential backoff
  void _scheduleReconnect() {
    if (_reconnectTimer != null && _reconnectTimer!.isActive) {
      return;
    }

    _reconnectAttempts++;
    final delay = Duration(
      seconds: (2 * _reconnectAttempts).clamp(1, 30), // Max 30s
    );

    debugPrint('🔄 Reconnecting in ${delay.inSeconds}s (attempt $_reconnectAttempts)');

    _reconnectTimer = Timer(delay, () {
      if (_reconnectAttempts < 10) {  // Max 10 attempts
        // Re-use last session ID and context
        // (Store these in the service or pass from caller)
        // connect(sessionId: _lastSessionId, userContext: _lastContext);
      } else {
        debugPrint('❌ Max reconnect attempts reached');
      }
    });
  }

  /// Disconnect
  void disconnect() {
    _channel?.sink.close();
    _reconnectTimer?.cancel();
    _isConnected = false;
    notifyListeners();
  }

  /// Generate unique message ID
  String _generateMessageId() {
    return 'msg_${DateTime.now().millisecondsSinceEpoch}';
  }

  @override
  void dispose() {
    disconnect();
    _messageController.close();
    super.dispose();
  }
}

// Message types
abstract class ChatMessage {
  final String id;
  final DateTime timestamp;

  ChatMessage({required this.id, required this.timestamp});
}

class TextMessage extends ChatMessage {
  final String content;

  TextMessage({
    required String id,
    required this.content,
    required DateTime timestamp,
  }) : super(id: id, timestamp: timestamp);
}

class WidgetMessage extends ChatMessage {
  final WidgetDescriptor descriptor;

  WidgetMessage({
    required String id,
    required this.descriptor,
    required DateTime timestamp,
  }) : super(id: id, timestamp: timestamp);
}

class CitationsMessage extends ChatMessage {
  final List<Citation> citations;

  CitationsMessage({
    required String id,
    required this.citations,
    required DateTime timestamp,
  }) : super(id: id, timestamp: timestamp);
}

class StatusMessage extends ChatMessage {
  final String status;

  StatusMessage({
    required String id,
    required this.status,
    required DateTime timestamp,
  }) : super(id: id, timestamp: timestamp);
}

class DoneMessage extends ChatMessage {
  DoneMessage({
    required String id,
    required DateTime timestamp,
  }) : super(id: id, timestamp: timestamp);
}
```

### Step 2: Widget Descriptor Models

```dart
// lib/core/models/widget_descriptor.dart
import 'package:uuid/uuid.dart';

enum WidgetType {
  chart,
  table,
  form,
  card,
  navigation,
  custom;

  static WidgetType fromString(String value) {
    return WidgetType.values.firstWhere(
      (e) => e.name == value,
      orElse: () => WidgetType.custom,
    );
  }
}

enum ActionType {
  navigate,
  apiCall,
  dialog,
  download,
  submit;

  static ActionType fromString(String value) {
    // Map snake_case from backend to camelCase
    final normalized = value.replaceAll('_', '');
    return ActionType.values.firstWhere(
      (e) => e.name.toLowerCase() == normalized.toLowerCase(),
      orElse: () => throw ArgumentError('Invalid action type: $value'),
    );
  }
}

class WidgetDescriptor {
  final String type;
  final String widgetId;
  final WidgetType widgetType;
  final Map<String, dynamic> data;
  final Map<String, dynamic> config;
  final List<WidgetAction> actions;
  final WidgetMetadata? metadata;

  WidgetDescriptor({
    this.type = 'widget',
    required this.widgetId,
    required this.widgetType,
    required this.data,
    this.config = const {},
    this.actions = const [],
    this.metadata,
  }) {
    // Validate UUID
    if (!Uuid.isValidUUID(fromString: widgetId)) {
      throw ArgumentError('widgetId must be a valid UUID v4');
    }

    // Validate type
    if (type != 'widget') {
      throw ArgumentError('type must be "widget"');
    }
  }

  factory WidgetDescriptor.fromJson(Map<String, dynamic> json) {
    return WidgetDescriptor(
      type: json['type'] as String,
      widgetId: json['widget_id'] as String,
      widgetType: WidgetType.fromString(json['widget_type'] as String),
      data: json['data'] as Map<String, dynamic>,
      config: json['config'] as Map<String, dynamic>? ?? {},
      actions: (json['actions'] as List?)
          ?.map((a) => WidgetAction.fromJson(a as Map<String, dynamic>))
          .toList() ?? [],
      metadata: json['metadata'] != null
          ? WidgetMetadata.fromJson(json['metadata'] as Map<String, dynamic>)
          : null,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'type': type,
      'widget_id': widgetId,
      'widget_type': widgetType.name,
      'data': data,
      'config': config,
      'actions': actions.map((a) => a.toJson()).toList(),
      'metadata': metadata?.toJson(),
    };
  }
}

class WidgetAction {
  final String actionId;
  final String label;
  final ActionType type;
  final Map<String, dynamic> params;
  final List<String> permissions;

  WidgetAction({
    required this.actionId,
    required this.label,
    required this.type,
    this.params = const {},
    this.permissions = const [],
  });

  factory WidgetAction.fromJson(Map<String, dynamic> json) {
    return WidgetAction(
      actionId: json['action_id'] as String,
      label: json['label'] as String,
      type: ActionType.fromString(json['type'] as String),
      params: json['params'] as Map<String, dynamic>? ?? {},
      permissions: (json['permissions'] as List?)
          ?.map((p) => p as String)
          .toList() ?? [],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'action_id': actionId,
      'label': label,
      'type': type.name,
      'params': params,
      'permissions': permissions,
    };
  }
}

class DataSource {
  final String sourceId;
  final String sourceName;
  final double confidence;
  final String? location;

  DataSource({
    required this.sourceId,
    required this.sourceName,
    required this.confidence,
    this.location,
  });

  factory DataSource.fromJson(Map<String, dynamic> json) {
    return DataSource(
      sourceId: json['source_id'] as String,
      sourceName: json['source_name'] as String,
      confidence: (json['confidence'] as num).toDouble(),
      location: json['location'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'source_id': sourceId,
      'source_name': sourceName,
      'confidence': confidence,
      'location': location,
    };
  }
}

class WidgetMetadata {
  final List<DataSource> sources;
  final String generatedAt;
  final String? expiresAt;

  WidgetMetadata({
    required this.sources,
    required this.generatedAt,
    this.expiresAt,
  });

  factory WidgetMetadata.fromJson(Map<String, dynamic> json) {
    return WidgetMetadata(
      sources: (json['sources'] as List?)
          ?.map((s) => DataSource.fromJson(s as Map<String, dynamic>))
          .toList() ?? [],
      generatedAt: json['generated_at'] as String,
      expiresAt: json['expires_at'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'sources': sources.map((s) => s.toJson()).toList(),
      'generated_at': generatedAt,
      'expires_at': expiresAt,
    };
  }
}

class Citation {
  final String sourceId;
  final String sourceName;
  final String snippet;
  final double confidence;
  final int? page;

  Citation({
    required this.sourceId,
    required this.sourceName,
    required this.snippet,
    required this.confidence,
    this.page,
  });

  factory Citation.fromJson(Map<String, dynamic> json) {
    return Citation(
      sourceId: json['source_id'] as String,
      sourceName: json['source_name'] as String,
      snippet: json['snippet'] as String,
      confidence: (json['confidence'] as num).toDouble(),
      page: json['page'] as int?,
    );
  }
}
```

### Step 3: Widget Renderer

```dart
// lib/features/chat/widgets/widget_renderer.dart
import 'package:flutter/material.dart';
import 'package:aihub/core/models/widget_descriptor.dart';
import 'package:aihub/core/design/design_system.dart';
import 'chart_widget.dart';
import 'table_widget.dart';
import 'form_widget.dart';
import 'card_widget.dart';
import 'navigation_widget.dart';

class WidgetRenderer extends StatelessWidget {
  final WidgetDescriptor descriptor;

  const WidgetRenderer({
    Key? key,
    required this.descriptor,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    // Route to specific widget implementation
    switch (descriptor.widgetType) {
      case WidgetType.chart:
        return ChartWidget(descriptor: descriptor);

      case WidgetType.table:
        return TableWidget(descriptor: descriptor);

      case WidgetType.form:
        return FormWidget(descriptor: descriptor);

      case WidgetType.card:
        return CardWidget(descriptor: descriptor);

      case WidgetType.navigation:
        return NavigationWidget(descriptor: descriptor);

      case WidgetType.custom:
        return CustomWidget(descriptor: descriptor);

      default:
        return _ErrorWidget(
          message: 'Unsupported widget type: ${descriptor.widgetType}',
        );
    }
  }
}

class _ErrorWidget extends StatelessWidget {
  final String message;

  const _ErrorWidget({required this.message});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Row(
        children: [
          Icon(Icons.error_outline, color: AppColors.error),
          AppSpacing.gapSm,
          Expanded(
            child: Text(
              message,
              style: AppTypography.bodyMedium.copyWith(color: AppColors.error),
            ),
          ),
        ],
      ),
    );
  }
}
```

---

## Advanced Widget Patterns

### Pattern 1: Drill-Down Chart

**Use Case**: User clicks on a bar chart → Show detailed table.

**Backend**:
```python
# Add drill-down action to chart widget
actions.append({
    "action_id": str(uuid.uuid4()),
    "label": "View Details",
    "type": "api_call",
    "params": {
        "endpoint": "/api/data/drilldown",
        "method": "POST",
        "data_key": "sales_q2_2024_regional"
    },
    "permissions": ["analyst", "manager"]
})

# Handle drill-down
@nexus.endpoint("/api/data/drilldown", methods=["POST"])
async def drilldown(
    data_key: str,
    selected_item: str,  # e.g., "North Region"
    user_context: Dict[str, Any]
):
    # Fetch detailed data
    detailed_data = await db.query_sales_details(
        region=selected_item,
        time_period="Q2 2024"
    )

    # Generate table widget
    agent = WidgetGeneratorAgent(db)
    table_widget = await agent.generate_table_widget(
        query=f"Details for {selected_item}",
        data={'records': detailed_data},
        user_context=user_context
    )

    return {
        "type": "new_widget",
        "widget": table_widget
    }
```

**Frontend**:
```dart
// Handle bar tap in ChartWidget
void _handleBarTap(int index) {
  final labels = descriptor.data['series'][0]['labels'] as List;
  final selectedLabel = labels[index] as String;

  // Find drill-down action
  final drillDownAction = descriptor.actions.firstWhere(
    (a) => a.label == 'View Details',
    orElse: () => throw StateError('No drill-down action'),
  );

  // Call backend
  context.read<ApiClient>().post(
    drillDownAction.params['endpoint'],
    {
      'data_key': drillDownAction.params['data_key'],
      'selected_item': selectedLabel,
    },
  ).then((response) {
    if (response['type'] == 'new_widget') {
      // Add new widget to conversation
      context.read<ConversationProvider>().addWidget(
        WidgetDescriptor.fromJson(response['widget']),
      );
    }
  });
}
```

### Pattern 2: Form → Chart Pipeline

**Use Case**: User submits filter form → AI generates filtered chart.

**Backend**:
```python
@nexus.stream_endpoint("/ai/chat/filter")
async def filter_and_visualize(
    form_data: Dict[str, Any],
    user_context: Dict[str, Any]
):
    # Extract filters
    start_date = form_data['start_date']
    end_date = form_data['end_date']
    regions = form_data['regions']  # List

    # Fetch filtered data
    data = await db.query_sales(
        start_date=start_date,
        end_date=end_date,
        regions=regions
    )

    # Generate chart
    agent = WidgetGeneratorAgent(db)
    chart_widget = await agent.generate_chart_widget(
        query=f"Sales from {start_date} to {end_date} for {', '.join(regions)}",
        data=data,
        user_context=user_context
    )

    # Stream results
    yield json.dumps({
        "type": "text",
        "content": f"Here's the data for your filters:"
    }) + "\n"

    yield json.dumps({
        "type": "widget",
        "content": chart_widget
    }) + "\n"
```

**Frontend**:
```dart
// FormWidget handles submission
Future<void> _handleSubmit() async {
  if (!_formKey.currentState!.validate()) return;

  // Collect form data
  final formData = {
    'start_date': _startDateController.text,
    'end_date': _endDateController.text,
    'regions': _selectedRegions,
  };

  // Send via WebSocket
  context.read<ChatWebSocketService>().sendMessage(
    'Filter and visualize sales data',
    metadata: {
      'form_data': formData,
      'form_id': descriptor.data['form_id'],
    },
  );

  // Clear form (optional)
  _formKey.currentState!.reset();
}
```

### Pattern 3: Navigation Cards with Deep Links

**Use Case**: AI suggests related pages/reports with clickable cards.

**Backend**:
```python
navigation_widget = {
    "widget_type": "navigation",
    "data": {
        "cards": [
            {
                "title": "Sales Dashboard",
                "description": "View comprehensive sales metrics",
                "icon": "dashboard",
                "badge": "Updated 2h ago",
                "badge_color": "success",
                "route": "/dashboard/sales",
                "params": {"period": "Q2", "region": "North"}
            },
            {
                "title": "Customer Insights",
                "description": "Analyze customer behavior patterns",
                "icon": "people",
                "route": "/analytics/customers"
            }
        ]
    }
}
```

**Frontend**:
```dart
// NavigationWidget
class NavigationWidget extends StatelessWidget {
  final WidgetDescriptor descriptor;

  @override
  Widget build(BuildContext context) {
    final cards = descriptor.data['cards'] as List;

    return Wrap(
      spacing: AppSpacing.md,
      runSpacing: AppSpacing.md,
      children: [
        for (var card in cards)
          _NavigationCard(
            title: card['title'],
            description: card['description'],
            icon: _getIcon(card['icon']),
            badge: card['badge'],
            badgeColor: _getBadgeColor(card['badge_color']),
            onTap: () => _navigate(context, card),
          ),
      ],
    );
  }

  void _navigate(BuildContext context, Map<String, dynamic> card) {
    final route = card['route'] as String;
    final params = card['params'] as Map<String, dynamic>?;

    Navigator.pushNamed(
      context,
      route,
      arguments: params,
    );
  }
}
```

---

## State Management Deep Dive

### Three-Tier State Architecture

**Tier 1: Widget-Local State (Ephemeral)**
- User interactions within widget (hover, focus, selection)
- Does NOT persist across widget rebuilds
- Use `StatefulWidget` + `setState`

**Tier 2: Conversation State (Session-Scoped)**
- Active data sources
- Uploaded documents
- Widget states that affect other widgets
- Use `Provider` or `Riverpod`

**Tier 3: Backend-Synced State (Persistent)**
- Form submissions
- User preferences
- Action triggers that need server validation
- Use WebSocket messages + backend storage

### Example: Multi-Widget State Coordination

**Scenario**: Filter form affects multiple charts in the same conversation.

```dart
// lib/core/providers/conversation_provider.dart
import 'package:flutter/foundation.dart';
import 'package:aihub/core/models/widget_descriptor.dart';

class ConversationProvider extends ChangeNotifier {
  // Active widgets in conversation
  final Map<String, WidgetDescriptor> _widgets = {};

  // Shared conversation state
  Map<String, dynamic> _conversationState = {
    'active_filters': {},
    'selected_date_range': null,
    'active_data_sources': [],
  };

  /// Add widget to conversation
  void addWidget(WidgetDescriptor descriptor) {
    _widgets[descriptor.widgetId] = descriptor;
    notifyListeners();
  }

  /// Update widget state
  void updateWidgetState(String widgetId, dynamic state) {
    // Store widget-specific state
    _conversationState['widget_$widgetId'] = state;
    notifyListeners();
  }

  /// Update global filter (affects all charts)
  void updateGlobalFilter(String key, dynamic value) {
    final filters = _conversationState['active_filters'] as Map;
    filters[key] = value;
    notifyListeners();

    // Notify backend
    _syncToBackend('filter_update', {'key': key, 'value': value});
  }

  /// Get widget state
  dynamic getWidgetState(String widgetId) {
    return _conversationState['widget_$widgetId'];
  }

  /// Check if filters are active
  bool hasActiveFilters() {
    final filters = _conversationState['active_filters'] as Map;
    return filters.isNotEmpty;
  }

  void _syncToBackend(String event, Map<String, dynamic> data) {
    // Use WebSocket service to sync
    // (Inject ChatWebSocketService via constructor or service locator)
  }
}
```

**Usage in Widgets**:
```dart
// FormWidget updates global filters
class _FormWidgetState extends State<FormWidget> {
  void _handleFilterChange(String key, dynamic value) {
    // Update local state
    setState(() {
      _formData[key] = value;
    });

    // Update conversation-level filter (affects other widgets)
    context.read<ConversationProvider>().updateGlobalFilter(key, value);
  }
}

// ChartWidget reacts to filter changes
class _ChartWidgetState extends State<ChartWidget> {
  @override
  Widget build(BuildContext context) {
    return Consumer<ConversationProvider>(
      builder: (context, conversationProvider, child) {
        final hasFilters = conversationProvider.hasActiveFilters();

        return Column(
          children: [
            // Show filter indicator
            if (hasFilters)
              _FilterIndicator(
                onClear: () {
                  conversationProvider.updateGlobalFilter('all', null);
                },
              ),

            // Chart
            _buildChart(),
          ],
        );
      },
    );
  }
}
```

---

## Performance Best Practices

### 1. Lazy Widget Rendering

**Problem**: Scrolling through long conversations with many widgets is laggy.

**Solution**: Use `ListView.builder` + visibility detection.

```dart
import 'package:visibility_detector/visibility_detector.dart';

class ConversationStream extends StatelessWidget {
  final List<ChatMessage> messages;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final message = messages[index];

        if (message is WidgetMessage) {
          return VisibilityDetector(
            key: Key('widget-${message.descriptor.widgetId}'),
            onVisibilityChanged: (info) {
              if (info.visibleFraction > 0.5) {
                // Widget is visible → render it
                context.read<ConversationProvider>()
                    .markWidgetAsVisible(message.descriptor.widgetId);
              } else {
                // Widget scrolled out → unload it (optional)
                context.read<ConversationProvider>()
                    .markWidgetAsHidden(message.descriptor.widgetId);
              }
            },
            child: _ConversationWidgetItem(message: message),
          );
        } else {
          return _ConversationTextItem(message: message);
        }
      },
    );
  }
}

class _ConversationWidgetItem extends StatelessWidget {
  final WidgetMessage message;

  @override
  Widget build(BuildContext context) {
    // Check if widget should be rendered
    final isVisible = context.select<ConversationProvider, bool>(
      (provider) => provider.isWidgetVisible(message.descriptor.widgetId)
    );

    if (!isVisible) {
      // Placeholder while not visible
      return Container(
        height: 400,  // Estimated widget height
        color: AppColors.surfaceLight,
        child: Center(child: CircularProgressIndicator()),
      );
    }

    // Render actual widget
    return WidgetRenderer(descriptor: message.descriptor);
  }
}
```

### 2. Widget Caching

**Problem**: Re-rendering expensive widgets (complex charts) on every rebuild.

**Solution**: Cache rendered widgets by `widget_id`.

```dart
class WidgetCache {
  final Map<String, Widget> _cache = {};

  Widget getOrBuild(WidgetDescriptor descriptor) {
    // Check cache
    if (_cache.containsKey(descriptor.widgetId)) {
      return _cache[descriptor.widgetId]!;
    }

    // Build and cache
    final widget = WidgetRenderer(descriptor: descriptor);
    _cache[descriptor.widgetId] = widget;

    return widget;
  }

  void invalidate(String widgetId) {
    _cache.remove(widgetId);
  }

  void clear() {
    _cache.clear();
  }
}

// Usage in ConversationProvider
class ConversationProvider extends ChangeNotifier {
  final WidgetCache _widgetCache = WidgetCache();

  Widget getCachedWidget(WidgetDescriptor descriptor) {
    return _widgetCache.getOrBuild(descriptor);
  }

  void invalidateWidget(String widgetId) {
    _widgetCache.invalidate(widgetId);
    notifyListeners();
  }
}
```

### 3. Isolate for Heavy Computation

**Problem**: Processing large datasets for charts blocks UI thread.

**Solution**: Offload to background isolate.

```dart
import 'dart:isolate';
import 'package:flutter/foundation.dart';

class ChartDataProcessor {
  /// Process chart data in background isolate
  static Future<List<BarChartGroupData>> processBarChartData(
    List<dynamic> rawData
  ) async {
    if (kIsWeb) {
      // Web doesn't support isolates yet → compute
      return await compute(_processBarChartDataSync, rawData);
    } else {
      // Mobile/desktop → isolate
      return await Isolate.run(() => _processBarChartDataSync(rawData));
    }
  }

  static List<BarChartGroupData> _processBarChartDataSync(List<dynamic> rawData) {
    // Heavy computation here
    return rawData.asMap().entries.map((entry) {
      final index = entry.key;
      final value = entry.value as num;

      return BarChartGroupData(
        x: index,
        barRods: [
          BarChartRodData(
            toY: value.toDouble(),
            color: AppColors.primary,
            width: 40,
            borderRadius: BorderRadius.circular(4),
          ),
        ],
      );
    }).toList();
  }
}

// Usage in ChartWidget
class _ChartWidgetState extends State<ChartWidget> {
  List<BarChartGroupData>? _chartData;
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadChartData();
  }

  Future<void> _loadChartData() async {
    final rawData = descriptor.data['series'][0]['values'] as List;

    setState(() => _isLoading = true);

    // Process in background
    final processedData = await ChartDataProcessor.processBarChartData(rawData);

    setState(() {
      _chartData = processedData;
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return Center(child: CircularProgressIndicator());
    }

    return BarChart(BarChartData(barGroups: _chartData!));
  }
}
```

### 4. Image/Asset Precaching

**Problem**: Widget icons/images load slowly.

**Solution**: Precache common assets.

```dart
class WidgetAssetCache {
  static Future<void> precacheWidgetAssets(BuildContext context) async {
    final assets = [
      'assets/icons/chart.png',
      'assets/icons/table.png',
      'assets/icons/form.png',
      'assets/icons/card.png',
      // ... more assets
    ];

    for (final asset in assets) {
      await precacheImage(AssetImage(asset), context);
    }
  }
}

// Call in app initialization
class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: WidgetAssetCache.precacheWidgetAssets(context),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return SplashScreen();
        }

        return MaterialApp(home: HomePage());
      },
    );
  }
}
```

---

## Testing Cookbook

### Backend Tests

#### Test 1: Widget Generation

```python
# tests/test_widget_generator.py
import pytest
from agents.widget_generator import WidgetGeneratorAgent, QueryIntent
from dataflow import DataFlow

@pytest.mark.asyncio
async def test_chart_widget_generation():
    """Test that chart widget is correctly generated"""
    db = DataFlow()
    agent = WidgetGeneratorAgent(db)

    data = {
        'records': [
            {'label': 'Q1', 'value': 45000},
            {'label': 'Q2', 'value': 52000},
        ],
        'sources': [
            {'id': 's1', 'name': 'report.xlsx', 'confidence': 0.95}
        ],
        'title': 'Quarterly Sales',
        'data_key': 'sales_q_2024'
    }

    widget = await agent.generate_widget(
        query="Show quarterly sales",
        data=data,
        user_context={'permissions': ['viewer']}
    )

    # Assertions
    assert widget is not None
    assert widget['widget_type'] == 'chart'
    assert widget['data']['chart_type'] in ['bar', 'line']
    assert len(widget['data']['series']) > 0
    assert widget['config']['interactive'] is True
    assert len(widget['actions']) >= 0  # May be empty for viewer
    assert len(widget['metadata']['sources']) == 1

@pytest.mark.asyncio
async def test_rbac_action_filtering():
    """Test that actions are filtered by user permissions"""
    db = DataFlow()
    agent = WidgetGeneratorAgent(db)

    data = {...}  # Same as above

    # Viewer (no export permission)
    widget_viewer = await agent.generate_widget(
        query="Show sales",
        data=data,
        user_context={'permissions': ['viewer']}
    )

    assert not any(a['type'] == 'download' for a in widget_viewer['actions'])

    # Exporter (has export permission)
    widget_exporter = await agent.generate_widget(
        query="Show sales",
        data=data,
        user_context={'permissions': ['viewer', 'data_exporter']}
    )

    assert any(a['type'] == 'download' for a in widget_exporter['actions'])
```

#### Test 2: Action Handler

```python
# tests/test_action_handler.py
import pytest
from api.widget_actions import handle_widget_action

@pytest.mark.asyncio
async def test_download_action():
    """Test CSV download action"""
    response = await handle_widget_action(
        widget_id="test-widget-1",
        action_id="test-action-1",
        params={},
        user_context={'permissions': ['data_exporter'], 'user_id': 'user1'}
    )

    assert response['type'] == 'download'
    assert response['url'].endswith('.csv')
    assert response['content_type'] == 'text/csv'

@pytest.mark.asyncio
async def test_rbac_violation():
    """Test that unauthorized action raises PermissionError"""
    with pytest.raises(PermissionError):
        await handle_widget_action(
            widget_id="test-widget-1",
            action_id="test-action-1",  # Requires 'manager'
            params={},
            user_context={'permissions': ['viewer'], 'user_id': 'user1'}
        )
```

### Frontend Tests

#### Test 1: Widget Rendering

```dart
// test/features/chat/widgets/chart_widget_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:aihub/core/models/widget_descriptor.dart';
import 'package:aihub/features/chat/widgets/chart_widget.dart';

void main() {
  group('ChartWidget', () {
    testWidgets('renders bar chart from descriptor', (tester) async {
      final descriptor = WidgetDescriptor(
        widgetId: 'test-widget-1',
        widgetType: WidgetType.chart,
        data: {
          'chart_type': 'bar',
          'series': [
            {
              'name': 'Q2 Sales',
              'values': [450, 380, 290],
              'labels': ['North', 'South', 'East'],
            }
          ],
          'title': 'Q2 Sales by Region',
        },
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ChartWidget(descriptor: descriptor),
          ),
        ),
      );

      // Verify title
      expect(find.text('Q2 Sales by Region'), findsOneWidget);

      // Verify chart is rendered
      expect(find.byType(BarChart), findsOneWidget);
    });

    testWidgets('handles bar tap interaction', (tester) async {
      final descriptor = WidgetDescriptor(...);

      await tester.pumpWidget(...);

      // Tap on first bar
      final barChart = find.byType(BarChart);
      await tester.tap(barChart);
      await tester.pumpAndSettle();

      // Verify drill-down modal appears
      expect(find.text('North'), findsOneWidget);
      expect(find.text('View Details'), findsOneWidget);
    });
  });
}
```

#### Test 2: WebSocket Integration

```dart
// test/core/services/chat_websocket_service_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mockito/mockito.dart';
import 'package:aihub/core/services/chat_websocket_service.dart';

void main() {
  group('ChatWebSocketService', () {
    test('receives and parses widget message', () async {
      final service = ChatWebSocketService(baseUrl: 'ws://test.com');

      // Listen to message stream
      final messages = <ChatMessage>[];
      service.messageStream.listen((msg) => messages.add(msg));

      // Simulate incoming widget message
      final widgetJson = json.encode({
        'type': 'widget',
        'content': {
          'widget_id': 'w1',
          'widget_type': 'chart',
          'data': {...},
        },
      });

      service._handleIncomingMessage(widgetJson);  // Expose for testing

      // Verify
      expect(messages.length, 1);
      expect(messages[0], isA<WidgetMessage>());
      final widgetMsg = messages[0] as WidgetMessage;
      expect(widgetMsg.descriptor.widgetType, WidgetType.chart);
    });
  });
}
```

---

## Deployment Checklist

### Backend Deployment

- [ ] **Environment Variables**
  - [ ] `NEXUS_API_URL`
  - [ ] `DATAFLOW_DATABASE_URL`
  - [ ] `LLM_API_KEY` (OpenAI, Anthropic, etc.)
  - [ ] `AWS_S3_BUCKET` (for file downloads)

- [ ] **Database Setup**
  - [ ] DataFlow migrations applied
  - [ ] Widget cache table created
  - [ ] RBAC tables populated

- [ ] **API Endpoints**
  - [ ] `/ai/chat` streaming endpoint tested
  - [ ] `/api/widget/action` handler tested
  - [ ] WebSocket connection stable (reconnection logic)

- [ ] **Performance**
  - [ ] Widget generation < 2s
  - [ ] Streaming latency < 500ms
  - [ ] Action handler response < 1s

- [ ] **Security**
  - [ ] RBAC enforcement on all actions
  - [ ] Input validation on widget descriptors
  - [ ] Rate limiting enabled
  - [ ] CORS configured for Flutter frontend

### Frontend Deployment

- [ ] **Dependencies**
  - [ ] `fl_chart` for charts
  - [ ] `web_socket_channel` for WebSocket
  - [ ] `provider` or `riverpod` for state management
  - [ ] `visibility_detector` for lazy rendering

- [ ] **Configuration**
  - [ ] API base URL configured
  - [ ] WebSocket URL configured
  - [ ] Authentication tokens handled

- [ ] **Widget Library**
  - [ ] All widget types implemented (chart, table, form, card, navigation)
  - [ ] Action handlers implemented
  - [ ] Error states handled
  - [ ] Loading states handled

- [ ] **Performance**
  - [ ] Lazy rendering enabled
  - [ ] Widget caching enabled
  - [ ] Isolate processing for heavy data
  - [ ] Assets precached

- [ ] **Testing**
  - [ ] Widget tests pass
  - [ ] Integration tests pass
  - [ ] E2E tests pass (with real backend)

---

## Troubleshooting Guide

### Problem: Widgets not rendering

**Symptoms**: Widget descriptors arrive but nothing shows in UI.

**Checks**:
1. Verify `widget_type` is supported in `WidgetRenderer.build()`
2. Check console for parsing errors in `WidgetDescriptor.fromJson()`
3. Verify `widget_id` is valid UUID v4
4. Check if widget is marked as visible (if using lazy rendering)

**Fix**:
```dart
// Add debug logging in WidgetRenderer
@override
Widget build(BuildContext context) {
  debugPrint('Rendering widget: ${descriptor.widgetType} (${descriptor.widgetId})');

  switch (descriptor.widgetType) {
    // ...
  }
}
```

### Problem: Actions not triggering

**Symptoms**: User clicks button but nothing happens.

**Checks**:
1. Verify action has correct `endpoint` in params
2. Check RBAC permissions (user may lack permission)
3. Check network console for API call errors
4. Verify `action_id` exists in widget descriptor

**Fix**:
```dart
Future<void> _handleAction(WidgetAction action) async {
  debugPrint('Triggering action: ${action.label} (${action.actionId})');

  try {
    final response = await context.read<ApiClient>().post(
      action.params['endpoint'],
      {'widget_id': descriptor.widgetId, 'action_id': action.actionId},
    );
    debugPrint('Action response: $response');
  } catch (e) {
    debugPrint('Action failed: $e');
    // Show error to user
  }
}
```

### Problem: WebSocket keeps disconnecting

**Symptoms**: Frequent disconnects, reconnection loops.

**Checks**:
1. Verify WebSocket URL is correct (`wss://` not `ws://` for SSL)
2. Check backend logs for connection errors
3. Verify authentication payload is correct
4. Check network stability (mobile data vs WiFi)

**Fix**:
```dart
// Add more robust reconnection logic
void _scheduleReconnect() {
  _reconnectAttempts++;

  if (_reconnectAttempts >= 10) {
    debugPrint('Max reconnect attempts reached. Manual reconnect required.');
    _messageController.add(ErrorMessage(
      message: 'Connection lost. Please refresh.',
    ));
    return;
  }

  final delay = Duration(seconds: (2 * _reconnectAttempts).clamp(1, 30));
  _reconnectTimer = Timer(delay, () => connect(...));
}
```

### Problem: Widgets render slowly

**Symptoms**: Lag when scrolling through conversation.

**Checks**:
1. Verify lazy rendering is enabled
2. Check if widget caching is working
3. Profile with Flutter DevTools (CPU, memory)
4. Check if heavy computation is on UI thread

**Fix**:
```dart
// Use Isolate.run for heavy processing
Future<void> _processChartData() async {
  final processed = await Isolate.run(() {
    // Heavy computation here
    return _computeChartData(rawData);
  });

  setState(() {
    _chartData = processed;
  });
}
```

---

## Real-World Examples

### Example 1: Sales Dashboard Widget

**User Query**: "Show me Q2 sales by region with drill-down"

**Backend Response**:
```python
{
    "type": "widget",
    "widget_id": "w-12345",
    "widget_type": "chart",
    "data": {
        "chart_type": "bar",
        "series": [{
            "name": "Q2 Sales",
            "values": [450000, 380000, 290000, 520000],
            "labels": ["North", "South", "East", "West"]
        }],
        "x_axis_label": "Region",
        "y_axis_label": "Revenue ($)",
        "title": "Q2 2024 Sales by Region"
    },
    "config": {
        "interactive": true,
        "responsive": true,
        "exportable": true,
        "drill_down_enabled": true
    },
    "actions": [
        {
            "action_id": "a-1",
            "label": "View Details",
            "type": "api_call",
            "params": {
                "endpoint": "/api/data/drilldown",
                "method": "POST",
                "data_key": "sales_q2_2024_regional"
            },
            "permissions": ["manager"]
        },
        {
            "action_id": "a-2",
            "label": "Export CSV",
            "type": "download",
            "params": {
                "format": "csv",
                "filename": "q2_sales_by_region.csv",
                "data_key": "sales_q2_2024_regional"
            },
            "permissions": ["data_exporter"]
        }
    ],
    "metadata": {
        "sources": [
            {
                "source_id": "s-1",
                "source_name": "Q2_Sales_Report.xlsx",
                "confidence": 0.95,
                "location": "Sheet: Regional Summary"
            }
        ],
        "generated_at": "2025-10-18T10:30:00Z"
    }
}
```

**Flutter Widget** (simplified):
```dart
AppCard(
  child: Column(
    children: [
      Text("Q2 2024 Sales by Region", style: AppTypography.h4),

      SizedBox(
        height: 300,
        child: BarChart(
          BarChartData(
            barGroups: [/* bars */],
            barTouchData: BarTouchData(
              touchCallback: (event, response) {
                if (event is FlTapUpEvent) {
                  _handleBarTap(response.spot.touchedBarGroupIndex);
                }
              },
            ),
          ),
        ),
      ),

      Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          AppButton.text(label: "View Details", onPressed: () {}),
          AppButton.text(label: "Export CSV", onPressed: () {}),
        ],
      ),
    ],
  ),
)
```

### Example 2: Customer Search Form

**User Query**: "Help me find customers in New York"

**Backend Response**:
```python
{
    "type": "widget",
    "widget_id": "w-67890",
    "widget_type": "form",
    "data": {
        "form_id": "customer_search",
        "fields": [
            {
                "field_id": "name",
                "type": "text",
                "label": "Customer Name",
                "placeholder": "Enter name...",
                "required": false
            },
            {
                "field_id": "city",
                "type": "text",
                "label": "City",
                "placeholder": "e.g., New York",
                "required": false,
                "default_value": "New York"
            },
            {
                "field_id": "state",
                "type": "select",
                "label": "State",
                "options": ["NY", "CA", "TX", "FL"],
                "default_value": "NY"
            },
            {
                "field_id": "revenue_min",
                "type": "number",
                "label": "Min Revenue ($)",
                "placeholder": "0",
                "required": false
            }
        ],
        "submit_button_label": "Search"
    },
    "actions": [
        {
            "action_id": "a-1",
            "label": "Search",
            "type": "submit",
            "params": {
                "endpoint": "/api/customers/search",
                "method": "POST"
            },
            "permissions": []
        }
    ]
}
```

**Flutter Widget** (simplified):
```dart
Form(
  key: _formKey,
  child: Column(
    children: [
      AppTextField(label: "Customer Name", controller: _nameController),
      AppTextField(label: "City", controller: _cityController, initialValue: "New York"),
      AppDropdown(label: "State", options: ["NY", "CA", "TX", "FL"], value: "NY"),
      AppTextField(label: "Min Revenue", controller: _revenueController, keyboardType: number),

      AppButton.primary(
        label: "Search",
        onPressed: _handleSubmit,
      ),
    ],
  ),
)
```

### Example 3: Navigation Cards

**User Query**: "What can I do with sales data?"

**Backend Response**:
```python
{
    "type": "widget",
    "widget_id": "w-nav-1",
    "widget_type": "navigation",
    "data": {
        "cards": [
            {
                "title": "Sales Dashboard",
                "description": "View comprehensive sales metrics and trends",
                "icon": "dashboard",
                "badge": "Updated 2h ago",
                "badge_color": "success",
                "route": "/dashboard/sales"
            },
            {
                "title": "Customer Insights",
                "description": "Analyze customer behavior and patterns",
                "icon": "people",
                "route": "/analytics/customers"
            },
            {
                "title": "Export Reports",
                "description": "Download sales reports in various formats",
                "icon": "download",
                "route": "/reports/export"
            }
        ]
    }
}
```

**Flutter Widget** (simplified):
```dart
Wrap(
  spacing: 16,
  runSpacing: 16,
  children: [
    for (var card in cards)
      AppCard(
        onTap: () => Navigator.pushNamed(context, card['route']),
        child: Column(
          children: [
            Icon(getIcon(card['icon']), size: 48),
            Text(card['title'], style: AppTypography.h4),
            Text(card['description'], style: AppTypography.bodySmall),
            if (card['badge'] != null)
              AppBadge(label: card['badge'], color: AppColors.success),
          ],
        ),
      ),
  ],
)
```

---

## Next Steps

1. **Prototype Phase** (Week 1-2)
   - Implement hello world widget (card)
   - Test end-to-end flow (backend → Flutter)
   - Validate WebSocket streaming

2. **Core Widgets** (Week 3-4)
   - Implement chart widget (bar, line, pie)
   - Implement table widget (sortable, filterable)
   - Implement form widget (text, select, date)

3. **Advanced Features** (Week 5-6)
   - Drill-down actions
   - Export actions (CSV, PDF)
   - Navigation cards

4. **Polish & Testing** (Week 7-8)
   - Performance optimization (lazy rendering, caching)
   - Comprehensive testing (unit, integration, E2E)
   - User testing with 5-10 enterprise users

5. **Production Rollout** (Week 9+)
   - Deploy to staging
   - Monitor performance metrics
   - Gather user feedback
   - Iterate based on feedback

---

**Document Version**: 1.0
**Created**: 2025-10-18
**Next Review**: After prototype completion
**Maintainer**: Technical Architecture Team
