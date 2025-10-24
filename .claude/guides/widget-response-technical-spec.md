# Interactive Widget Response System - Technical Specification

**Version**: 1.0
**Created**: 2025-10-18
**Status**: Technical Design Document
**Target**: Backend (Python/Kailash) + Frontend (Flutter) Engineers

---

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Widget Descriptor Protocol](#widget-descriptor-protocol)
4. [Backend Implementation (Python/Kailash)](#backend-implementation-pythonkailash)
5. [Frontend Implementation (Flutter)](#frontend-implementation-flutter)
6. [Widget Types Reference](#widget-types-reference)
7. [State Management](#state-management)
8. [Performance Optimization](#performance-optimization)
9. [Testing Strategy](#testing-strategy)
10. [Security Considerations](#security-considerations)

---

## Overview

### Problem Statement
Current AI assistants are limited to:
- Static text responses (markdown)
- Pre-rendered charts (images)
- External links (context switching)

**Our Solution**: Embed interactive Flutter widgets directly in AI conversation stream with:
- Real-time interactivity (tap, drag, input)
- Navigation capabilities
- State management
- Backend action triggers

### Inspiration: Google's AI Playground
Google's AI playground embeds Flutter widgets in responses by:
1. Backend generates widget specifications (JSON)
2. Streaming API sends widget specs to frontend
3. Flutter dynamically renders widgets from specs
4. Widget actions trigger backend API calls

**Our approach builds on this with**:
- Kailash SDK for widget generation (AI-powered)
- Nexus API for streaming widget specs
- Design system components for consistency
- RBAC integration for action permissions

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│ USER QUERY                                                  │
│ "Show me Q2 sales breakdown by region"                     │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ FLUTTER FRONTEND                                            │
│ - Sends query via WebSocket/SSE                             │
│ - User context (session_id, permissions, active_sources)    │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ NEXUS API (Streaming Endpoint)                              │
│ - Receives query                                            │
│ - Routes to appropriate AI agent                            │
│ - Streams response chunks to frontend                       │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ KAILASH AI AGENT (Kaizen Framework)                         │
│ - Analyzes query intent                                     │
│ - Fetches data from sources (DataFlow)                      │
│ - Generates widget descriptor (JSON)                        │
│ - Streams text + widget descriptor                          │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ STREAMING RESPONSE                                          │
│ {                                                            │
│   "type": "text",                                            │
│   "content": "Here's the Q2 sales breakdown:"               │
│ }                                                            │
│ {                                                            │
│   "type": "widget",                                          │
│   "content": {                                               │
│     "widget_type": "chart",                                  │
│     "data": {...},                                           │
│     "config": {...},                                         │
│     "actions": [...]                                         │
│   }                                                          │
│ }                                                            │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ FLUTTER WIDGET RENDERER                                     │
│ - Receives streamed chunks                                  │
│ - Parses widget descriptor                                  │
│ - Dynamically builds Flutter widget                         │
│ - Renders in conversation stream                            │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ USER INTERACTS WITH WIDGET                                  │
│ - Taps bar in chart → Drill down                           │
│ - Clicks "Export CSV" → Downloads data                      │
│ - Submits form → Sends data to backend                     │
└───────────────┬─────────────────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND ACTION HANDLER (Nexus API)                          │
│ - Receives action request                                   │
│ - Validates permissions (RBAC)                              │
│ - Executes action (query DB, generate file, etc.)          │
│ - Returns response or new widget                            │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

**Backend**:
- **Kailash SDK Core**: Workflow orchestration
- **Kaizen Framework**: AI agent development
- **DataFlow**: Database operations (sales data, user context)
- **Nexus API**: Multi-channel API gateway (WebSocket/SSE streaming)

**Frontend**:
- **Flutter**: Cross-platform UI (Web + iOS/Android)
- **Design System**: `lib/core/design/` components
- **State Management**: Provider + Riverpod for reactive state
- **WebSocket**: `web_socket_channel` package for real-time streaming

**Communication Protocol**:
- **WebSocket** (primary): Bidirectional, low-latency
- **Server-Sent Events (SSE)**: Fallback for unidirectional streaming
- **JSON**: Widget descriptor format

---

## Widget Descriptor Protocol

### Base Schema

```json
{
  "type": "widget",
  "widget_id": "uuid-v4",
  "widget_type": "chart|table|form|card|navigation|custom",
  "data": {
    // Widget-specific data structure
  },
  "config": {
    // Widget configuration options
    "interactive": true,
    "responsive": true,
    "exportable": true
  },
  "actions": [
    {
      "action_id": "uuid-v4",
      "label": "Action Label",
      "type": "navigate|api_call|dialog|download|submit",
      "params": {
        // Action-specific parameters
      },
      "permissions": ["role1", "role2"] // RBAC
    }
  ],
  "metadata": {
    "sources": [
      {
        "source_id": "uuid-v4",
        "source_name": "Q2_Sales_Report.xlsx",
        "confidence": 0.95,
        "location": "Page 3, Cell B12"
      }
    ],
    "generated_at": "2025-10-18T10:30:00Z",
    "expires_at": "2025-10-18T11:30:00Z" // Optional: widget expiry
  }
}
```

### Validation Rules

**Required Fields**:
- `type` (must be "widget")
- `widget_id` (must be valid UUID v4)
- `widget_type` (must be supported type)
- `data` (structure depends on widget_type)

**Optional Fields**:
- `config` (defaults to `{}`)
- `actions` (defaults to `[]`)
- `metadata` (defaults to `{}`)

**Backend Validator** (Python):
```python
from pydantic import BaseModel, Field, validator
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid

class WidgetType(str, Enum):
    CHART = "chart"
    TABLE = "table"
    FORM = "form"
    CARD = "card"
    NAVIGATION = "navigation"
    CUSTOM = "custom"

class ActionType(str, Enum):
    NAVIGATE = "navigate"
    API_CALL = "api_call"
    DIALOG = "dialog"
    DOWNLOAD = "download"
    SUBMIT = "submit"

class WidgetAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str
    type: ActionType
    params: Dict[str, Any] = {}
    permissions: List[str] = []

class DataSource(BaseModel):
    source_id: str
    source_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    location: Optional[str] = None

class WidgetMetadata(BaseModel):
    sources: List[DataSource] = []
    generated_at: str
    expires_at: Optional[str] = None

class WidgetDescriptor(BaseModel):
    type: str = "widget"
    widget_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    widget_type: WidgetType
    data: Dict[str, Any]
    config: Dict[str, Any] = {}
    actions: List[WidgetAction] = []
    metadata: WidgetMetadata

    @validator('widget_id')
    def validate_uuid(cls, v):
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError('widget_id must be a valid UUID v4')
        return v

    @validator('type')
    def validate_type(cls, v):
        if v != "widget":
            raise ValueError('type must be "widget"')
        return v
```

**Frontend Validator** (Dart):
```dart
import 'package:uuid/uuid.dart';

enum WidgetType { chart, table, form, card, navigation, custom }
enum ActionType { navigate, apiCall, dialog, download, submit }

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
      widgetType: WidgetType.values.byName(json['widget_type'] as String),
      data: json['data'] as Map<String, dynamic>,
      config: json['config'] as Map<String, dynamic>? ?? {},
      actions: (json['actions'] as List?)
          ?.map((a) => WidgetAction.fromJson(a))
          .toList() ?? [],
      metadata: json['metadata'] != null
          ? WidgetMetadata.fromJson(json['metadata'])
          : null,
    );
  }
}
```

---

## Backend Implementation (Python/Kailash)

### Widget Generator Agent

**Purpose**: AI agent that generates widget descriptors based on user query and data.

**Implementation**:
```python
from kaizen.agents import BaseAgent, Signature
from kaizen.signatures import InputField, OutputField
from dataflow import DataFlow
from typing import Dict, Any, List
import json

class WidgetGeneratorSignature(Signature):
    """Signature for widget generation"""
    query: str = InputField(description="User's natural language query")
    data: Dict[str, Any] = InputField(description="Fetched data from sources")
    user_context: Dict[str, Any] = InputField(description="User permissions, preferences")

    widget_descriptor: Dict[str, Any] = OutputField(description="Generated widget descriptor")
    explanation: str = OutputField(description="Explanation of widget choice")

class WidgetGeneratorAgent(BaseAgent):
    """
    AI agent that generates interactive widget descriptors.

    Capabilities:
    - Analyzes user query to determine best widget type
    - Fetches data from DataFlow sources
    - Generates widget descriptor (JSON)
    - Applies RBAC to actions
    """

    def __init__(self, db: DataFlow):
        super().__init__(
            signature=WidgetGeneratorSignature,
            instructions="""
            You are an expert at generating interactive data visualizations.

            Given a user query and data, determine the best widget type:
            - Use 'chart' for trends, comparisons, distributions
            - Use 'table' for detailed data, sorting, filtering
            - Use 'form' for data input, searches, filters
            - Use 'card' for metrics, KPIs, summaries
            - Use 'navigation' for workflows, related pages

            Generate a complete widget descriptor following the schema.
            """,
        )
        self.db = db

    async def generate_chart_widget(
        self,
        query: str,
        data: List[Dict[str, Any]],
        user_permissions: List[str]
    ) -> WidgetDescriptor:
        """
        Generate a chart widget descriptor.

        Args:
            query: User's query (e.g., "Show Q2 sales by region")
            data: List of data points (e.g., [{'region': 'North', 'sales': 450000}, ...])
            user_permissions: User's RBAC roles (e.g., ['sales_viewer', 'manager'])

        Returns:
            WidgetDescriptor with chart configuration
        """

        # Extract chart parameters from query using LLM
        response = await self.run(
            query=query,
            data=data,
            user_context={'permissions': user_permissions}
        )

        # Parse LLM response into widget descriptor
        widget_desc = response.widget_descriptor

        # Add actions based on permissions
        actions = []

        if 'sales_manager' in user_permissions:
            # Managers can drill down
            actions.append(WidgetAction(
                label="View Details",
                type=ActionType.API_CALL,
                params={
                    "endpoint": "/api/sales/drilldown",
                    "method": "POST"
                },
                permissions=["sales_manager"]
            ))

        if 'data_exporter' in user_permissions:
            # Exporters can download data
            actions.append(WidgetAction(
                label="Export CSV",
                type=ActionType.DOWNLOAD,
                params={
                    "format": "csv",
                    "filename": "q2_sales_by_region.csv"
                },
                permissions=["data_exporter"]
            ))

        # Build final descriptor
        descriptor = WidgetDescriptor(
            widget_type=WidgetType.CHART,
            data={
                "chart_type": "bar",
                "series": [
                    {
                        "name": "Q2 Sales",
                        "values": [d['sales'] for d in data],
                        "labels": [d['region'] for d in data]
                    }
                ],
                "x_axis_label": "Region",
                "y_axis_label": "Sales ($)",
                "title": "Q2 Sales by Region"
            },
            config={
                "interactive": True,
                "responsive": True,
                "exportable": 'data_exporter' in user_permissions
            },
            actions=actions,
            metadata=WidgetMetadata(
                sources=[
                    DataSource(
                        source_id=str(uuid.uuid4()),
                        source_name="Q2_Sales_Report.xlsx",
                        confidence=0.95,
                        location="Sheet: Regional Sales"
                    )
                ],
                generated_at=datetime.utcnow().isoformat()
            )
        )

        return descriptor
```

### Nexus Streaming Endpoint

**Purpose**: Stream AI responses + widget descriptors to Flutter frontend.

**Implementation**:
```python
from nexus import Nexus
from kailash.runtime import AsyncLocalRuntime
from typing import AsyncGenerator
import json

nexus = Nexus()
runtime = AsyncLocalRuntime()

@nexus.stream_endpoint("/ai/chat")
async def chat_stream(
    session_id: str,
    message: str,
    user_context: Dict[str, Any]
) -> AsyncGenerator[str, None]:
    """
    Streaming chat endpoint that returns text + widgets.

    Args:
        session_id: Unique session ID for conversation
        message: User's message
        user_context: User permissions, active sources, etc.

    Yields:
        JSON chunks: {"type": "text"|"widget", "content": ...}
    """

    # Initialize widget generator agent
    db = DataFlow()
    agent = WidgetGeneratorAgent(db)

    # Analyze query to determine if widget is needed
    query_analysis = await agent.analyze_query(message)

    # Stream text response
    async for text_chunk in agent.stream_text_response(message):
        yield json.dumps({
            "type": "text",
            "content": text_chunk
        }) + "\n"

    # If query needs visualization, generate widget
    if query_analysis['needs_visualization']:
        # Fetch data
        data = await agent.fetch_data(
            query=message,
            sources=user_context['active_sources']
        )

        # Generate widget descriptor
        widget_descriptor = await agent.generate_chart_widget(
            query=message,
            data=data,
            user_permissions=user_context['permissions']
        )

        # Stream widget descriptor
        yield json.dumps({
            "type": "widget",
            "content": widget_descriptor.dict()
        }) + "\n"

    # Stream citation data
    citations = await agent.get_citations(message)
    yield json.dumps({
        "type": "citations",
        "content": citations
    }) + "\n"
```

### Action Handler

**Purpose**: Handle widget action triggers (API calls, downloads, etc.).

**Implementation**:
```python
from nexus import Nexus
from kailash.rbac import check_permissions
from typing import Dict, Any

nexus = Nexus()

@nexus.endpoint("/api/widget/action", methods=["POST"])
async def handle_widget_action(
    widget_id: str,
    action_id: str,
    params: Dict[str, Any],
    user_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle widget action triggers.

    Args:
        widget_id: UUID of widget
        action_id: UUID of action
        params: Action parameters
        user_context: User permissions, session, etc.

    Returns:
        Action result (new widget, file download, etc.)
    """

    # Retrieve widget descriptor from cache/DB
    widget = await get_widget_by_id(widget_id)

    # Find action in widget
    action = next(
        (a for a in widget.actions if a.action_id == action_id),
        None
    )

    if not action:
        raise ValueError(f"Action {action_id} not found in widget {widget_id}")

    # Check RBAC permissions
    if not check_permissions(user_context['permissions'], action.permissions):
        raise PermissionError(
            f"User lacks permissions: {action.permissions}"
        )

    # Execute action based on type
    if action.type == ActionType.API_CALL:
        return await execute_api_call(action.params)

    elif action.type == ActionType.DOWNLOAD:
        return await generate_download(action.params)

    elif action.type == ActionType.NAVIGATE:
        return {"redirect_url": action.params['route']}

    elif action.type == ActionType.SUBMIT:
        return await handle_form_submission(action.params)

    else:
        raise NotImplementedError(f"Action type {action.type} not implemented")
```

---

## Frontend Implementation (Flutter)

### WebSocket Connection Manager

**Purpose**: Manage WebSocket connection to Nexus streaming API.

**Implementation**:
```dart
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:convert';
import 'dart:async';

class ChatWebSocketManager {
  WebSocketChannel? _channel;
  final String _baseUrl = 'wss://api.aihub.example.com/ai/chat';
  final StreamController<ChatMessage> _messageController =
      StreamController<ChatMessage>.broadcast();

  Stream<ChatMessage> get messageStream => _messageController.stream;

  Future<void> connect(String sessionId, Map<String, dynamic> userContext) async {
    final url = Uri.parse('$_baseUrl?session_id=$sessionId');

    _channel = WebSocketChannel.connect(url);

    // Send user context on connect
    _channel!.sink.add(json.encode({
      'type': 'auth',
      'user_context': userContext,
    }));

    // Listen to incoming messages
    _channel!.stream.listen(
      (data) => _handleIncomingMessage(data),
      onError: (error) => _handleError(error),
      onDone: () => _handleDisconnect(),
    );
  }

  void sendMessage(String message) {
    if (_channel == null) {
      throw StateError('WebSocket not connected');
    }

    _channel!.sink.add(json.encode({
      'type': 'message',
      'content': message,
    }));
  }

  void _handleIncomingMessage(dynamic data) {
    final json = jsonDecode(data as String);
    final type = json['type'] as String;

    switch (type) {
      case 'text':
        _messageController.add(TextMessage(content: json['content']));
        break;

      case 'widget':
        final widgetDesc = WidgetDescriptor.fromJson(json['content']);
        _messageController.add(WidgetMessage(descriptor: widgetDesc));
        break;

      case 'citations':
        _messageController.add(CitationsMessage(citations: json['content']));
        break;

      default:
        print('Unknown message type: $type');
    }
  }

  void _handleError(error) {
    print('WebSocket error: $error');
    // Implement reconnection logic
  }

  void _handleDisconnect() {
    print('WebSocket disconnected');
    // Implement reconnection logic
  }

  void dispose() {
    _channel?.sink.close();
    _messageController.close();
  }
}
```

### Widget Renderer

**Purpose**: Dynamically render widgets from descriptors.

**Implementation**:
```dart
import 'package:flutter/material.dart';
import 'package:aihub/core/design/design_system.dart';

class WidgetRenderer extends StatelessWidget {
  final WidgetDescriptor descriptor;

  const WidgetRenderer({required this.descriptor});

  @override
  Widget build(BuildContext context) {
    switch (descriptor.widgetType) {
      case WidgetType.chart:
        return ChartWidget(descriptor: descriptor as ChartWidgetDescriptor);

      case WidgetType.table:
        return TableWidget(descriptor: descriptor as TableWidgetDescriptor);

      case WidgetType.form:
        return FormWidget(descriptor: descriptor as FormWidgetDescriptor);

      case WidgetType.card:
        return CardWidget(descriptor: descriptor as CardWidgetDescriptor);

      case WidgetType.navigation:
        return NavigationWidget(descriptor: descriptor as NavigationWidgetDescriptor);

      case WidgetType.custom:
        return CustomWidget(descriptor: descriptor);

      default:
        return ErrorWidget(
          message: 'Unsupported widget type: ${descriptor.widgetType}',
        );
    }
  }
}

class ErrorWidget extends StatelessWidget {
  final String message;

  const ErrorWidget({required this.message});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Row(
        children: [
          Icon(Icons.error_outline, color: AppColors.error),
          AppSpacing.gapSm,
          Text(message, style: AppTypography.bodyMedium),
        ],
      ),
    );
  }
}
```

### Chart Widget Implementation

**Purpose**: Render interactive charts from descriptor.

**Implementation**:
```dart
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:aihub/core/design/design_system.dart';

class ChartWidget extends StatefulWidget {
  final ChartWidgetDescriptor descriptor;

  const ChartWidget({required this.descriptor});

  @override
  State<ChartWidget> createState() => _ChartWidgetState();
}

class _ChartWidgetState extends State<ChartWidget> {
  int? _selectedBarIndex;

  @override
  Widget build(BuildContext context) {
    final chartData = widget.descriptor.data;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Title
          Text(chartData['title'] as String, style: AppTypography.h4),
          AppSpacing.gapMd,

          // Chart
          SizedBox(
            height: 300,
            child: _buildChart(chartData),
          ),

          AppSpacing.gapMd,

          // Actions
          if (widget.descriptor.actions.isNotEmpty)
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                for (var action in widget.descriptor.actions)
                  Padding(
                    padding: EdgeInsets.only(left: AppSpacing.sm),
                    child: AppButton.text(
                      label: action.label,
                      onPressed: () => _handleAction(action),
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _buildChart(Map<String, dynamic> chartData) {
    final chartType = chartData['chart_type'] as String;

    switch (chartType) {
      case 'bar':
        return _buildBarChart(chartData);
      case 'line':
        return _buildLineChart(chartData);
      case 'pie':
        return _buildPieChart(chartData);
      default:
        return Text('Unsupported chart type: $chartType');
    }
  }

  Widget _buildBarChart(Map<String, dynamic> chartData) {
    final series = chartData['series'] as List;
    final values = series[0]['values'] as List<dynamic>;
    final labels = series[0]['labels'] as List<dynamic>;

    return BarChart(
      BarChartData(
        barGroups: values.asMap().entries.map((entry) {
          final index = entry.key;
          final value = entry.value as num;

          return BarChartGroupData(
            x: index,
            barRods: [
              BarChartRodData(
                toY: value.toDouble(),
                color: _selectedBarIndex == index
                    ? AppColors.primary
                    : AppColors.primaryLight,
                width: 40,
                borderRadius: BorderRadius.circular(4),
              ),
            ],
          );
        }).toList(),
        titlesData: FlTitlesData(
          show: true,
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                final index = value.toInt();
                if (index >= 0 && index < labels.length) {
                  return Text(
                    labels[index] as String,
                    style: AppTypography.caption,
                  );
                }
                return const SizedBox();
              },
            ),
          ),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 40,
            ),
          ),
          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        borderData: FlBorderData(show: false),
        barTouchData: BarTouchData(
          touchCallback: (event, response) {
            if (event is FlTapUpEvent && response != null) {
              final touchedIndex = response.spot?.touchedBarGroupIndex;
              setState(() {
                _selectedBarIndex = touchedIndex;
              });

              if (touchedIndex != null) {
                _handleBarTap(touchedIndex);
              }
            }
          },
        ),
      ),
    );
  }

  void _handleBarTap(int index) {
    // Show drill-down modal or trigger action
    final labels = widget.descriptor.data['series'][0]['labels'] as List;
    final values = widget.descriptor.data['series'][0]['values'] as List;

    showModalBottomSheet(
      context: context,
      builder: (context) => Padding(
        padding: AppSpacing.allLg,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              labels[index] as String,
              style: AppTypography.h3,
            ),
            AppSpacing.gapSm,
            Text(
              'Sales: \$${(values[index] as num).toStringAsFixed(0)}',
              style: AppTypography.h4,
            ),
            AppSpacing.gapLg,
            AppButton.primary(
              label: 'View Details',
              onPressed: () {
                // Trigger drill-down action
                Navigator.pop(context);
              },
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _handleAction(WidgetAction action) async {
    switch (action.type) {
      case ActionType.download:
        await _handleDownload(action);
        break;

      case ActionType.apiCall:
        await _handleApiCall(action);
        break;

      case ActionType.navigate:
        _handleNavigation(action);
        break;

      default:
        print('Unsupported action type: ${action.type}');
    }
  }

  Future<void> _handleDownload(WidgetAction action) async {
    // Trigger download (CSV, PNG, etc.)
    final format = action.params['format'] as String;
    final filename = action.params['filename'] as String;

    // Implementation depends on platform (web vs mobile)
    // Use file_saver package or platform-specific code
    print('Downloading $filename as $format...');
  }

  Future<void> _handleApiCall(WidgetAction action) async {
    // Call backend API
    final endpoint = action.params['endpoint'] as String;
    final method = action.params['method'] as String;

    // Use Dio or http package
    print('Calling $method $endpoint...');
  }

  void _handleNavigation(WidgetAction action) {
    // Navigate to route
    final route = action.params['route'] as String;
    Navigator.pushNamed(context, route);
  }
}
```

---

## Widget Types Reference

### 1. Chart Widget

**Use Cases**:
- Sales trends over time
- Regional comparisons
- Product performance
- KPI visualizations

**Descriptor Schema**:
```json
{
  "widget_type": "chart",
  "data": {
    "chart_type": "bar|line|pie|scatter|combo",
    "series": [
      {
        "name": "Series 1",
        "values": [100, 200, 150],
        "labels": ["Jan", "Feb", "Mar"],
        "color": "#3B82F6" // Optional
      }
    ],
    "x_axis_label": "Month",
    "y_axis_label": "Sales ($)",
    "title": "Monthly Sales Trend",
    "legend_position": "bottom|top|left|right" // Optional
  },
  "config": {
    "interactive": true,
    "responsive": true,
    "exportable": true,
    "drill_down_enabled": true
  }
}
```

### 2. Table Widget

**Use Cases**:
- Customer lists
- Product catalogs
- Transaction history
- Search results

**Descriptor Schema**:
```json
{
  "widget_type": "table",
  "data": {
    "columns": [
      {
        "key": "name",
        "label": "Name",
        "sortable": true,
        "filterable": true,
        "format": "text|currency|percentage|date"
      }
    ],
    "rows": [
      {"name": "Alice", "revenue": 123000, "growth": 0.23}
    ],
    "pagination": {
      "page": 1,
      "per_page": 20,
      "total": 250
    }
  },
  "config": {
    "selectable_rows": true,
    "exportable": true,
    "filterable": true
  }
}
```

### 3. Form Widget

**Use Cases**:
- Search forms
- Filter panels
- Data input
- Settings

**Descriptor Schema**:
```json
{
  "widget_type": "form",
  "data": {
    "form_id": "customer_search",
    "fields": [
      {
        "field_id": "name",
        "type": "text|email|password|date|select|multiselect|number",
        "label": "Customer Name",
        "placeholder": "Enter name...",
        "required": true,
        "default_value": "",
        "validation": {
          "min_length": 3,
          "max_length": 100,
          "pattern": "regex_pattern"
        }
      }
    ],
    "submit_button_label": "Search"
  },
  "config": {
    "auto_submit": false,
    "preserve_state": true
  }
}
```

### 4. Navigation Card Widget

**Use Cases**:
- Related pages
- Quick actions
- Workflow steps
- Suggested resources

**Descriptor Schema**:
```json
{
  "widget_type": "navigation_card",
  "data": {
    "cards": [
      {
        "title": "Sales Dashboard",
        "description": "View sales metrics",
        "icon": "dashboard|people|analytics|...",
        "badge": "New Data",
        "badge_color": "success|warning|error|info"
      }
    ]
  }
}
```

---

## State Management

### Widget State Hierarchy

**Level 1: Widget-Local State** (Transient)
- Selected bar in chart
- Expanded row in table
- Form input values (before submission)

**Implementation**: StatefulWidget + setState

**Level 2: Conversation State** (Persistent)
- Active data sources
- Uploaded documents
- User preferences

**Implementation**: Provider/Riverpod

**Level 3: Backend Sync** (Important changes)
- Form submission
- Filter changes that affect AI responses
- Action triggers

**Implementation**: WebSocket messages to backend

### Example: Form Widget State

```dart
// Level 1: Local state
class FormWidget extends StatefulWidget {
  final FormWidgetDescriptor descriptor;

  @override
  State<FormWidget> createState() => _FormWidgetState();
}

class _FormWidgetState extends State<FormWidget> {
  final _formKey = GlobalKey<FormState>();
  Map<String, dynamic> _formData = {};

  void _handleInputChange(String fieldId, dynamic value) {
    setState(() {
      _formData[fieldId] = value;
    });
  }

  Future<void> _handleSubmit() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    // Level 3: Sync to backend
    await context.read<ChatService>().sendMessage(
      'Form submitted: ${json.encode(_formData)}',
      metadata: {
        'widget_id': widget.descriptor.widgetId,
        'form_data': _formData,
      },
    );

    // Level 2: Update conversation state
    context.read<ConversationProvider>().updateWidgetState(
      widget.descriptor.widgetId,
      _formData,
    );
  }
}

// Level 2: Conversation-level state
class ConversationProvider extends ChangeNotifier {
  Map<String, dynamic> _widgetStates = {};

  void updateWidgetState(String widgetId, dynamic state) {
    _widgetStates[widgetId] = state;
    notifyListeners();
  }

  dynamic getWidgetState(String widgetId) {
    return _widgetStates[widgetId];
  }
}
```

---

## Performance Optimization

### 1. Lazy Widget Rendering

**Problem**: Long conversations with many widgets can slow down rendering.

**Solution**: Only render widgets when visible.

```dart
import 'package:visibility_detector/visibility_detector.dart';

class ConversationStream extends StatelessWidget {
  final List<Message> messages;

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final message = messages[index];

        return VisibilityDetector(
          key: Key('message-${message.id}'),
          onVisibilityChanged: (info) {
            if (info.visibleFraction > 0.5) {
              // Trigger widget rendering
              context.read<ConversationProvider>()
                  .markWidgetAsVisible(message.id);
            }
          },
          child: ConversationMessage(message: message),
        );
      },
    );
  }
}
```

### 2. Widget Caching

**Problem**: Re-rendering complex widgets on scroll is expensive.

**Solution**: Cache rendered widgets keyed by widget_id.

```dart
class WidgetCache {
  final Map<String, Widget> _cache = {};

  Widget getOrRender(WidgetDescriptor descriptor) {
    if (_cache.containsKey(descriptor.widgetId)) {
      return _cache[descriptor.widgetId]!;
    }

    final widget = WidgetRenderer(descriptor: descriptor);
    _cache[descriptor.widgetId] = widget;
    return widget;
  }

  void clear() {
    _cache.clear();
  }
}
```

### 3. Isolate for Heavy Computation

**Problem**: Chart data processing blocks UI thread.

**Solution**: Offload to background isolate.

```dart
import 'dart:isolate';

Future<List<BarChartGroupData>> _processChartData(
  List<dynamic> rawData
) async {
  return await Isolate.run(() {
    // Heavy computation in background
    return rawData.asMap().entries.map((entry) {
      return BarChartGroupData(
        x: entry.key,
        barRods: [
          BarChartRodData(
            toY: (entry.value as num).toDouble(),
            // ... more processing
          ),
        ],
      );
    }).toList();
  });
}
```

---

## Testing Strategy

### Backend Tests (Python)

**Unit Tests**:
```python
import pytest
from widget_generator import WidgetGeneratorAgent

@pytest.mark.asyncio
async def test_chart_widget_generation():
    """Test chart widget descriptor generation"""
    agent = WidgetGeneratorAgent(db=MockDataFlow())

    descriptor = await agent.generate_chart_widget(
        query="Show Q2 sales by region",
        data=[
            {'region': 'North', 'sales': 450000},
            {'region': 'South', 'sales': 380000},
        ],
        user_permissions=['sales_viewer']
    )

    assert descriptor.widget_type == WidgetType.CHART
    assert descriptor.data['chart_type'] == 'bar'
    assert len(descriptor.data['series'][0]['values']) == 2
    assert descriptor.config['interactive'] is True

@pytest.mark.asyncio
async def test_rbac_action_filtering():
    """Test that actions are filtered based on user permissions"""
    agent = WidgetGeneratorAgent(db=MockDataFlow())

    # User WITHOUT export permissions
    descriptor = await agent.generate_chart_widget(
        query="Show sales",
        data=[...],
        user_permissions=['sales_viewer']  # No 'data_exporter'
    )

    assert not any(a.type == ActionType.DOWNLOAD for a in descriptor.actions)

    # User WITH export permissions
    descriptor = await agent.generate_chart_widget(
        query="Show sales",
        data=[...],
        user_permissions=['sales_viewer', 'data_exporter']
    )

    assert any(a.type == ActionType.DOWNLOAD for a in descriptor.actions)
```

**Integration Tests**:
```python
@pytest.mark.asyncio
async def test_end_to_end_widget_streaming():
    """Test full widget generation and streaming"""
    from nexus_test_client import NexusTestClient

    client = NexusTestClient()

    # Send query
    response = client.stream_chat(
        session_id="test_session",
        message="Show Q2 sales by region",
        user_context={'permissions': ['sales_viewer']}
    )

    # Collect streamed chunks
    chunks = [chunk async for chunk in response]

    # Verify text chunk
    assert any(c['type'] == 'text' for c in chunks)

    # Verify widget chunk
    widget_chunks = [c for c in chunks if c['type'] == 'widget']
    assert len(widget_chunks) == 1

    widget = widget_chunks[0]['content']
    assert widget['widget_type'] == 'chart'
```

### Frontend Tests (Dart)

**Widget Tests**:
```dart
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ChartWidget', () {
    testWidgets('renders bar chart from descriptor', (tester) async {
      final descriptor = ChartWidgetDescriptor(
        widgetId: 'test-widget-1',
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
      final descriptor = ChartWidgetDescriptor(...);

      await tester.pumpWidget(...);

      // Tap on first bar
      await tester.tap(find.byType(BarChart));
      await tester.pumpAndSettle();

      // Verify drill-down modal appears
      expect(find.text('North'), findsOneWidget);
      expect(find.text('Sales: \$450'), findsOneWidget);
    });
  });
}
```

**Integration Tests**:
```dart
void main() {
  group('Widget Streaming Integration', () {
    testWidgets('receives and renders streamed widget', (tester) async {
      final mockWebSocket = MockWebSocketChannel();

      await tester.pumpWidget(
        MaterialApp(
          home: ConversationPage(webSocket: mockWebSocket),
        ),
      );

      // Simulate streamed widget
      mockWebSocket.simulateIncoming(json.encode({
        'type': 'widget',
        'content': {
          'widget_type': 'chart',
          'data': {...},
        },
      }));

      await tester.pumpAndSettle();

      // Verify widget is rendered
      expect(find.byType(ChartWidget), findsOneWidget);
    });
  });
}
```

---

## Security Considerations

### 1. RBAC Enforcement

**Backend**:
- All widget actions MUST check user permissions before execution
- Widget descriptors MUST only include actions user is authorized for

**Frontend**:
- Display only actions user has permissions for (UI-level filtering)
- Backend validates again (never trust frontend)

### 2. Input Validation

**Backend**:
- Validate all widget descriptors against schema
- Sanitize user inputs in forms
- Prevent XSS/injection attacks

**Frontend**:
- Validate form inputs before submission
- Sanitize rendered content (especially custom widgets)

### 3. Rate Limiting

**Backend**:
- Limit widget generation requests per user
- Limit action triggers per widget
- Prevent DoS attacks

### 4. Data Exposure

**Backend**:
- Only include data user has access to (RBAC-filtered)
- Mask sensitive data in widget descriptors
- Audit all widget generations

**Frontend**:
- Never cache sensitive data in local storage
- Clear widget cache on logout

---

## Next Steps

1. **Implement Phase 2** (Interactive Widgets) from main UI/UX design doc
2. **Create prototype** with 1-2 widget types (chart + table)
3. **User testing** with 5-10 enterprise users
4. **Iterate** based on feedback
5. **Scale to all widget types**

---

**Document Version**: 1.0
**Created**: 2025-10-18
**Next Review**: After Phase 2 completion
**Maintainer**: Technical Architecture Team
