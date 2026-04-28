# Interactive Widget Response System - Technical Specification

## Architecture

```
User Query -> Flutter Frontend (WebSocket) -> Nexus API (streaming)
  -> Kaizen AI Agent (analyze intent, fetch data, generate widget descriptor)
  -> Streaming Response: {"type": "text"|"widget", "content": ...}
  -> Flutter Widget Renderer (dynamic build from descriptor)
  -> User Interaction -> Backend Action Handler (RBAC validated)
```

**Stack**: Kailash SDK + Kaizen (agents) + DataFlow (DB) + Nexus (API) | Flutter + fl_chart + Provider/Riverpod

## Widget Descriptor Protocol

### Base Schema

```json
{
  "type": "widget",
  "widget_id": "uuid-v4",
  "widget_type": "chart|table|form|card|navigation|custom",
  "data": {},
  "config": { "interactive": true, "responsive": true, "exportable": true },
  "actions": [
    {
      "action_id": "uuid-v4",
      "label": "Action Label",
      "type": "navigate|api_call|dialog|download|submit",
      "params": {},
      "permissions": ["role1"]
    }
  ],
  "metadata": {
    "sources": [
      {
        "source_id": "uuid",
        "source_name": "file.xlsx",
        "confidence": 0.95,
        "location": "Page 3"
      }
    ],
    "generated_at": "2025-10-18T10:30:00Z",
    "expires_at": null
  }
}
```

**Required**: `type` ("widget"), `widget_id` (UUID v4), `widget_type`, `data`. Optional: `config`, `actions`, `metadata`.

### Backend Validator (Python)

```python
from pydantic import BaseModel, Field, validator
from enum import Enum
import uuid

class WidgetType(str, Enum):
    CHART = "chart"; TABLE = "table"; FORM = "form"
    CARD = "card"; NAVIGATION = "navigation"; CUSTOM = "custom"

class ActionType(str, Enum):
    NAVIGATE = "navigate"; API_CALL = "api_call"; DIALOG = "dialog"
    DOWNLOAD = "download"; SUBMIT = "submit"

class WidgetAction(BaseModel):
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str
    type: ActionType
    params: Dict[str, Any] = {}
    permissions: List[str] = []

class WidgetDescriptor(BaseModel):
    type: str = "widget"
    widget_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    widget_type: WidgetType
    data: Dict[str, Any]
    config: Dict[str, Any] = {}
    actions: List[WidgetAction] = []
    metadata: WidgetMetadata
```

### Frontend Validator (Dart)

```dart
class WidgetDescriptor {
  final String type, widgetId;
  final WidgetType widgetType;
  final Map<String, dynamic> data, config;
  final List<WidgetAction> actions;
  final WidgetMetadata? metadata;

  factory WidgetDescriptor.fromJson(Map<String, dynamic> json) {
    return WidgetDescriptor(
      type: json['type'], widgetId: json['widget_id'],
      widgetType: WidgetType.values.byName(json['widget_type']),
      data: json['data'], config: json['config'] ?? {},
      actions: (json['actions'] as List?)?.map((a) => WidgetAction.fromJson(a)).toList() ?? [],
      metadata: json['metadata'] != null ? WidgetMetadata.fromJson(json['metadata']) : null,
    );
  }
}
```

## Widget Types Reference

### Chart Widget

```json
{
  "widget_type": "chart",
  "data": {
    "chart_type": "bar|line|pie|scatter|combo",
    "series": [
      {
        "name": "Q2 Sales",
        "values": [450, 380],
        "labels": ["North", "South"],
        "color": "#3B82F6"
      }
    ],
    "x_axis_label": "Region",
    "y_axis_label": "Sales ($)",
    "title": "Q2 Sales",
    "legend_position": "bottom|top|left|right"
  },
  "config": {
    "interactive": true,
    "responsive": true,
    "exportable": true,
    "drill_down_enabled": true
  }
}
```

### Table Widget

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
    "rows": [{ "name": "Product A", "revenue": 123000, "growth": 0.23 }],
    "pagination": { "page": 1, "per_page": 20, "total": 250 }
  },
  "config": { "selectable_rows": true, "exportable": true, "filterable": true }
}
```

### Form Widget

```json
{
  "widget_type": "form",
  "data": {
    "form_id": "customer_search",
    "fields": [
      {
        "field_id": "name",
        "type": "text|email|date|select|multiselect|number",
        "label": "Customer Name",
        "placeholder": "Enter name...",
        "required": true,
        "validation": { "min_length": 3, "max_length": 100, "pattern": "regex" }
      }
    ],
    "submit_button_label": "Search"
  },
  "config": { "auto_submit": false, "preserve_state": true }
}
```

### Navigation Card Widget

```json
{
  "widget_type": "navigation_card",
  "data": {
    "cards": [
      {
        "title": "Sales Dashboard",
        "description": "View sales metrics",
        "icon": "dashboard|people|analytics",
        "badge": "New Data",
        "badge_color": "success|warning|error"
      }
    ]
  }
}
```

## Backend: Widget Generator Agent

```python
class WidgetGeneratorAgent(BaseAgent):
    def __init__(self, db: DataFlow):
        super().__init__(signature=WidgetGeneratorSignature,
            instructions="Determine best widget type: chart (trends/comparisons), "
                         "table (detailed data), form (input/search), card (KPIs), navigation (workflows)")
        self.db = db

    async def generate_chart_widget(self, query, data, user_permissions) -> WidgetDescriptor:
        response = await self.run(query=query, data=data, user_context={'permissions': user_permissions})
        actions = []
        if 'sales_manager' in user_permissions:
            actions.append(WidgetAction(label="View Details", type=ActionType.API_CALL,
                params={"endpoint": "/api/sales/drilldown", "method": "POST"},
                permissions=["sales_manager"]))
        if 'data_exporter' in user_permissions:
            actions.append(WidgetAction(label="Export CSV", type=ActionType.DOWNLOAD,
                params={"format": "csv", "filename": "export.csv"}, permissions=["data_exporter"]))
        return WidgetDescriptor(widget_type=WidgetType.CHART, data={...}, actions=actions, ...)
```

## Backend: Nexus Streaming + Action Handler

```python
@nexus.stream_endpoint("/ai/chat")
async def chat_stream(session_id: str, message: str, user_context: Dict):
    """Yields: {"type": "text"|"widget"|"citations", "content": ...}"""
    agent = WidgetGeneratorAgent(db)
    query_analysis = await agent.analyze_query(message)

    async for text_chunk in agent.stream_text_response(message):
        yield json.dumps({"type": "text", "content": text_chunk}) + "\n"

    if query_analysis['needs_visualization']:
        data = await agent.fetch_data(query=message, sources=user_context['active_sources'])
        widget = await agent.generate_chart_widget(query=message, data=data,
                                                    user_permissions=user_context['permissions'])
        yield json.dumps({"type": "widget", "content": widget.dict()}) + "\n"

@nexus.endpoint("/api/widget/action", methods=["POST"])
async def handle_widget_action(widget_id, action_id, params, user_context):
    widget = await get_widget_by_id(widget_id)
    action = next((a for a in widget.actions if a.action_id == action_id), None)
    if not check_permissions(user_context['permissions'], action.permissions):
        raise PermissionError(f"User lacks permissions: {action.permissions}")
    # Route: API_CALL -> execute_api_call, DOWNLOAD -> generate_download,
    #        NAVIGATE -> redirect, SUBMIT -> handle_form_submission
```

## Frontend: WebSocket + Widget Renderer

```dart
// WebSocket manager: connect, send messages, parse incoming by type (text/widget/citations)
class ChatWebSocketManager {
  Stream<ChatMessage> get messageStream => _messageController.stream;
  void _handleIncomingMessage(dynamic data) {
    final json = jsonDecode(data);
    switch (json['type']) {
      case 'text':   _messageController.add(TextMessage(content: json['content']));
      case 'widget': _messageController.add(WidgetMessage(descriptor: WidgetDescriptor.fromJson(json['content'])));
      case 'citations': _messageController.add(CitationsMessage(citations: json['content']));
    }
  }
}

// Widget renderer: route by widgetType to ChartWidget, TableWidget, FormWidget, etc.
class WidgetRenderer extends StatelessWidget {
  final WidgetDescriptor descriptor;
  Widget build(BuildContext context) {
    switch (descriptor.widgetType) {
      case WidgetType.chart: return ChartWidget(descriptor: descriptor);
      case WidgetType.table: return TableWidget(descriptor: descriptor);
      // ... form, card, navigation, custom
    }
  }
}
```

## Frontend: Chart Widget (fl_chart)

```dart
class _ChartWidgetState extends State<ChartWidget> {
  int? _selectedBarIndex;

  Widget build(BuildContext context) {
    return AppCard(child: Column(children: [
      Text(chartData['title'], style: AppTypography.h4),
      SizedBox(height: 300, child: BarChart(BarChartData(
        barGroups: _buildBarGroups(),
        barTouchData: BarTouchData(touchCallback: (event, response) {
          if (event is FlTapUpEvent && response != null) {
            setState(() => _selectedBarIndex = response.spot?.touchedBarGroupIndex);
            _handleBarTap(_selectedBarIndex!);
          }
        }),
      ))),
      // Action buttons row
      for (var action in descriptor.actions)
        AppButton.text(label: action.label, onPressed: () => _handleAction(action)),
    ]));
  }

  // _handleAction routes by ActionType: download, apiCall, navigate
}
```

## State Management (3 Levels)

| Level        | Scope      | Tool                  | Example                         |
| ------------ | ---------- | --------------------- | ------------------------------- |
| Widget-local | Transient  | `StatefulWidget`      | Selected bar, form input        |
| Conversation | Session    | `Provider`/`Riverpod` | Active sources, widget states   |
| Backend sync | Persistent | WebSocket messages    | Form submission, filter changes |

## Performance

| Technique          | Solution                                      |
| ------------------ | --------------------------------------------- |
| Lazy rendering     | `ListView.builder` + `VisibilityDetector`     |
| Widget caching     | Cache by `widget_id` in `Map<String, Widget>` |
| Background compute | `Isolate.run()` for chart data processing     |

## Security

- **RBAC**: All actions MUST check permissions backend-side. Frontend filters UI-only (never trust frontend).
- **Validation**: Validate all widget descriptors against schema. Sanitize form inputs.
- **Rate limiting**: Limit widget generation and action triggers per user.
- **Data exposure**: Only include RBAC-filtered data. Mask sensitive data. Clear cache on logout.

## Testing

```python
# Backend: verify widget generation and RBAC filtering
@pytest.mark.asyncio
async def test_chart_widget_generation():
    descriptor = await agent.generate_chart_widget(query="Show Q2 sales", data=[...],
                                                    user_permissions=['sales_viewer'])
    assert descriptor.widget_type == WidgetType.CHART
    assert descriptor.config['interactive'] is True

@pytest.mark.asyncio
async def test_rbac_action_filtering():
    desc = await agent.generate_chart_widget(query="Show sales", data=[...],
                                              user_permissions=['sales_viewer'])
    assert not any(a.type == ActionType.DOWNLOAD for a in desc.actions)
```

```dart
// Frontend: verify rendering and interaction
testWidgets('renders bar chart', (tester) async {
  await tester.pumpWidget(MaterialApp(home: ChartWidget(descriptor: chartDescriptor)));
  expect(find.text('Q2 Sales by Region'), findsOneWidget);
  expect(find.byType(BarChart), findsOneWidget);
});
```
