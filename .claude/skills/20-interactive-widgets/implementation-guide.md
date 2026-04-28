# Interactive Widget Response System - Implementation Guide

## Quick Start: Hello World Widget

### Backend (Python + Kailash)

```python
from kaizen.agents import BaseAgent, Signature
from kaizen.signatures import InputField, OutputField
from nexus import Nexus
import uuid, json
from datetime import datetime
from typing import Dict, Any

class SimpleWidgetAgent(BaseAgent):
    async def generate_hello_widget(self) -> Dict[str, Any]:
        return {
            "type": "widget",
            "widget_id": str(uuid.uuid4()),
            "widget_type": "card",
            "data": {"title": "Hello from AI!", "description": "First interactive widget.", "icon": "celebration"},
            "config": {"interactive": True},
            "actions": [{
                "action_id": str(uuid.uuid4()),
                "label": "Click Me",
                "type": "api_call",
                "params": {"endpoint": "/api/widget/hello", "method": "POST"},
                "permissions": []
            }],
            "metadata": {"sources": [], "generated_at": datetime.utcnow().isoformat()}
        }

nexus = Nexus()

@nexus.stream_endpoint("/ai/chat")
async def chat_stream(message: str):
    agent = SimpleWidgetAgent()
    yield json.dumps({"type": "text", "content": "Here's an interactive widget:"}) + "\n"
    widget = await agent.generate_hello_widget()
    yield json.dumps({"type": "widget", "content": widget}) + "\n"
```

### Frontend (Flutter)

```dart
class HelloCardWidget extends StatelessWidget {
  final Map<String, dynamic> data;
  final List<WidgetAction> actions;

  const HelloCardWidget({required this.data, required this.actions});

  @override
  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(Icons.celebration, color: AppColors.primary, size: 32),
            AppSpacing.gapSm,
            Text(data['title'], style: AppTypography.h3),
          ]),
          AppSpacing.gapSm,
          Text(data['description'], style: AppTypography.bodyMedium),
          AppSpacing.gapMd,
          if (actions.isNotEmpty)
            AppButton.primary(
              label: actions[0].label,
              onPressed: () => _handleAction(context, actions[0]),
            ),
        ],
      ),
    );
  }
}
```

## Backend: Widget Generator Agent

```python
from kaizen.agents import BaseAgent, Signature
from kaizen.signatures import InputField, OutputField
from dataflow import DataFlow
from enum import Enum

class QueryIntent(str, Enum):
    DATA_ANALYSIS = "data_analysis"
    COMPARISON = "comparison"
    TREND_ANALYSIS = "trend_analysis"
    SEARCH_FILTER = "search_filter"
    FORM_INPUT = "form_input"
    NAVIGATION = "navigation"
    TEXT_ONLY = "text_only"

# Intent -> Widget mapping:
# DATA_ANALYSIS -> card (metrics) or chart (breakdown)
# COMPARISON -> chart (bar/grouped bar)
# TREND_ANALYSIS -> chart (line/area)
# SEARCH_FILTER -> form (filters) + table (results)
# FORM_INPUT -> form
# NAVIGATION -> navigation_card
# TEXT_ONLY -> no widget

class WidgetGeneratorAgent(BaseAgent):
    def __init__(self, db: DataFlow):
        super().__init__(
            signature=WidgetGeneratorSignature,
            instructions="Analyze query intent, determine widget type. Be conservative.",
        )
        self.db = db

    async def analyze_query(self, query: str) -> Dict[str, Any]:
        response = await self.run(query=query)
        return {
            'intent': QueryIntent(response.intent),
            'needs_widget': response.needs_widget,
            'widget_type': response.widget_type,
        }

    async def generate_widget(self, query, data, user_context):
        analysis = await self.analyze_query(query)
        if not analysis['needs_widget']:
            return None
        # Route to: _generate_chart_widget, _generate_table_widget,
        # _generate_form_widget, _generate_card_widget, _generate_navigation_widget
```

## Backend: Streaming Chat Endpoint

```python
@nexus.stream_endpoint("/ai/chat")
async def chat_stream(session_id: str, message: str, user_context: Dict[str, Any]):
    """Yields JSON chunks: {"type": "text"|"widget"|"citations"|"status"|"done", "content": ...}"""
    widget_agent = WidgetGeneratorAgent(db)
    analysis = await widget_agent.analyze_query(message)

    yield json.dumps({"type": "status", "content": "Analyzing query..."}) + "\n"

    async for text_chunk in _generate_text_response(message, user_context):
        yield json.dumps({"type": "text", "content": text_chunk}) + "\n"

    if analysis['needs_widget']:
        data = await _fetch_data(query=message, sources=user_context['active_sources'],
                                  permissions=user_context['permissions'])
        widget_descriptor = await widget_agent.generate_widget(query=message, data=data,
                                                                user_context=user_context)
        if widget_descriptor:
            yield json.dumps({"type": "widget", "content": widget_descriptor}) + "\n"

    citations = await _generate_citations(message, user_context)
    yield json.dumps({"type": "citations", "content": citations}) + "\n"
    yield json.dumps({"type": "done"}) + "\n"
```

## Backend: Action Handler

```python
@nexus.endpoint("/api/widget/action", methods=["POST"])
async def handle_widget_action(widget_id: str, action_id: str, params: Dict, user_context: Dict):
    widget = await get_widget_by_id(widget_id)
    action = next((a for a in widget['actions'] if a['action_id'] == action_id), None)
    if not action:
        raise ValueError(f"Action {action_id} not found")

    # RBAC check
    if not check_permissions(user_context.get('permissions', []), action.get('permissions', [])):
        raise PermissionError(f"User lacks permissions: {action['permissions']}")

    # Route by type
    action_type = action['type']
    if action_type == 'api_call':
        return await _handle_api_call(action, params, user_context)
    elif action_type == 'download':
        return await _handle_download(action, params, user_context)
    elif action_type == 'navigate':
        return {"type": "navigate", "route": action['params']['route']}
    elif action_type == 'submit':
        return await _handle_form_submit(action, params, user_context)
```

## Frontend: WebSocket Service

```dart
class ChatWebSocketService extends ChangeNotifier {
  WebSocketChannel? _channel;
  final StreamController<ChatMessage> _messageController =
      StreamController<ChatMessage>.broadcast();
  bool _isConnected = false;
  int _reconnectAttempts = 0;

  Stream<ChatMessage> get messageStream => _messageController.stream;

  Future<void> connect({required String sessionId, required Map<String, dynamic> userContext}) async {
    _channel = WebSocketChannel.connect(Uri.parse('$_baseUrl/ai/chat?session_id=$sessionId'));
    _channel!.sink.add(json.encode({'type': 'auth', 'user_context': userContext}));
    _channel!.stream.listen(_handleIncomingMessage, onError: _handleError, onDone: _handleDisconnect);
    _isConnected = true;
    _reconnectAttempts = 0;
  }

  void _handleIncomingMessage(dynamic data) {
    final jsonData = json.decode(data as String);
    switch (jsonData['type']) {
      case 'text':    _messageController.add(TextMessage(content: jsonData['content']));
      case 'widget':  _messageController.add(WidgetMessage(descriptor: WidgetDescriptor.fromJson(jsonData['content'])));
      case 'citations': _messageController.add(CitationsMessage(citations: jsonData['content']));
      case 'status':  _messageController.add(StatusMessage(status: jsonData['content']));
      case 'done':    _messageController.add(DoneMessage());
    }
  }

  // Reconnect with exponential backoff: delay = (2 * attempts).clamp(1, 30) seconds, max 10 attempts
}
```

## Frontend: Widget Renderer

```dart
class WidgetRenderer extends StatelessWidget {
  final WidgetDescriptor descriptor;
  const WidgetRenderer({required this.descriptor});

  @override
  Widget build(BuildContext context) {
    switch (descriptor.widgetType) {
      case WidgetType.chart:      return ChartWidget(descriptor: descriptor);
      case WidgetType.table:      return TableWidget(descriptor: descriptor);
      case WidgetType.form:       return FormWidget(descriptor: descriptor);
      case WidgetType.card:       return CardWidget(descriptor: descriptor);
      case WidgetType.navigation: return NavigationWidget(descriptor: descriptor);
      case WidgetType.custom:     return CustomWidget(descriptor: descriptor);
      default: return _ErrorWidget(message: 'Unsupported: ${descriptor.widgetType}');
    }
  }
}
```

## Advanced Patterns

### Pattern 1: Drill-Down Chart (Chart -> Table)

```python
# Backend: bar tap triggers drill-down endpoint
@nexus.endpoint("/api/data/drilldown", methods=["POST"])
async def drilldown(data_key: str, selected_item: str, user_context: Dict):
    detailed_data = await db.query_sales_details(region=selected_item)
    table_widget = await agent.generate_table_widget(query=f"Details for {selected_item}",
                                                      data={'records': detailed_data},
                                                      user_context=user_context)
    return {"type": "new_widget", "widget": table_widget}
```

```dart
// Frontend: handle bar tap -> call drill-down -> add new widget to conversation
void _handleBarTap(int index) {
  final selectedLabel = descriptor.data['series'][0]['labels'][index];
  context.read<ApiClient>().post(drillDownAction.params['endpoint'],
    {'data_key': drillDownAction.params['data_key'], 'selected_item': selectedLabel},
  ).then((response) {
    if (response['type'] == 'new_widget') {
      context.read<ConversationProvider>().addWidget(WidgetDescriptor.fromJson(response['widget']));
    }
  });
}
```

### Pattern 2: Form -> Chart Pipeline

```python
# Backend: form submission triggers filtered chart generation
@nexus.stream_endpoint("/ai/chat/filter")
async def filter_and_visualize(form_data: Dict, user_context: Dict):
    data = await db.query_sales(start_date=form_data['start_date'],
                                 end_date=form_data['end_date'], regions=form_data['regions'])
    chart_widget = await agent.generate_chart_widget(query=f"Sales filtered", data=data,
                                                      user_context=user_context)
    yield json.dumps({"type": "widget", "content": chart_widget}) + "\n"
```

### Pattern 3: Navigation Cards with Deep Links

```python
navigation_widget = {
    "widget_type": "navigation",
    "data": {
        "cards": [
            {"title": "Sales Dashboard", "description": "View sales metrics",
             "icon": "dashboard", "badge": "Updated 2h ago", "route": "/dashboard/sales"},
            {"title": "Customer Insights", "description": "Analyze behavior",
             "icon": "people", "route": "/analytics/customers"}
        ]
    }
}
```

## State Management (3 Tiers)

| Tier | Scope          | Persistence | Tool                          | Example                       |
| ---- | -------------- | ----------- | ----------------------------- | ----------------------------- |
| 1    | Widget-local   | Ephemeral   | `StatefulWidget` + `setState` | Hover, focus, selection       |
| 2    | Conversation   | Session     | `Provider`/`Riverpod`         | Active sources, filter state  |
| 3    | Backend-synced | Persistent  | WebSocket + backend storage   | Form submissions, preferences |

```dart
// Tier 2: ConversationProvider coordinates multi-widget state
class ConversationProvider extends ChangeNotifier {
  final Map<String, WidgetDescriptor> _widgets = {};
  Map<String, dynamic> _conversationState = {'active_filters': {}, 'active_data_sources': []};

  void addWidget(WidgetDescriptor d) { _widgets[d.widgetId] = d; notifyListeners(); }
  void updateGlobalFilter(String key, dynamic value) {
    (_conversationState['active_filters'] as Map)[key] = value;
    notifyListeners();
  }
}
```

## Performance

### Lazy Widget Rendering

Use `ListView.builder` + `VisibilityDetector` -- render only visible widgets, show placeholder for offscreen.

### Widget Caching

Cache rendered widgets by `widget_id` in a `Map<String, Widget>`. Invalidate on data change.

### Background Isolate

Offload heavy chart data processing to `Isolate.run()` (mobile/desktop) or `compute()` (web).

### Asset Precaching

Precache widget icons/images at app init:

```dart
class WidgetAssetCache {
  static Future<void> precacheWidgetAssets(BuildContext context) async {
    for (final asset in ['assets/icons/chart.png', 'assets/icons/table.png',
                         'assets/icons/form.png', 'assets/icons/card.png']) {
      await precacheImage(AssetImage(asset), context);
    }
  }
}

// App root: wrap with FutureBuilder
FutureBuilder(
  future: WidgetAssetCache.precacheWidgetAssets(context),
  builder: (ctx, snap) => snap.connectionState == ConnectionState.done
      ? MaterialApp(home: HomePage()) : SplashScreen(),
);
```

## Testing

### Backend

```python
@pytest.mark.asyncio
async def test_chart_widget_generation():
    agent = WidgetGeneratorAgent(db)
    widget = await agent.generate_widget(query="Show quarterly sales", data=data,
                                          user_context={'permissions': ['viewer']})
    assert widget['widget_type'] == 'chart'
    assert widget['config']['interactive'] is True

@pytest.mark.asyncio
async def test_rbac_action_filtering():
    widget_viewer = await agent.generate_widget(query="Show sales", data=data,
                                                 user_context={'permissions': ['viewer']})
    assert not any(a['type'] == 'download' for a in widget_viewer['actions'])
```

```python
@pytest.mark.asyncio
async def test_download_action():
    response = await handle_widget_action(widget_id="w1", action_id="a1", params={},
                                           user_context={'permissions': ['data_exporter'], 'user_id': 'u1'})
    assert response['type'] == 'download'
    assert response['url'].endswith('.csv')

@pytest.mark.asyncio
async def test_rbac_violation():
    with pytest.raises(PermissionError):
        await handle_widget_action(widget_id="w1", action_id="a1", params={},
                                    user_context={'permissions': ['viewer'], 'user_id': 'u1'})
```

### Frontend

```dart
testWidgets('renders bar chart from descriptor', (tester) async {
  final descriptor = WidgetDescriptor(widgetId: 'test-1', widgetType: WidgetType.chart,
    data: {'chart_type': 'bar', 'series': [{'name': 'Q2', 'values': [450, 380], 'labels': ['N', 'S']}],
           'title': 'Sales'});
  await tester.pumpWidget(MaterialApp(home: Scaffold(body: ChartWidget(descriptor: descriptor))));
  expect(find.text('Sales'), findsOneWidget);
  expect(find.byType(BarChart), findsOneWidget);
});

testWidgets('handles bar tap interaction', (tester) async {
  await tester.pumpWidget(/* ChartWidget with descriptor */);
  await tester.tap(find.byType(BarChart));
  await tester.pumpAndSettle();
  expect(find.text('View Details'), findsOneWidget); // Drill-down modal
});

test('WebSocket reconnects on disconnect', () async {
  final service = ChatWebSocketService(url: 'ws://test');
  await service.connect();
  service.simulateDisconnect();
  await Future.delayed(Duration(seconds: 2)); // Exponential backoff
  expect(service.isConnected, isTrue);
});
```

## Deployment Checklist

### Backend

- [ ] Env vars: `NEXUS_API_URL`, `DATAFLOW_DATABASE_URL`, `LLM_API_KEY`, `AWS_S3_BUCKET`
- [ ] DataFlow migrations + RBAC tables
- [ ] `/ai/chat` streaming + `/api/widget/action` tested
- [ ] Widget generation <2s, streaming latency <500ms, action response <1s
- [ ] RBAC on all actions, input validation, rate limiting, CORS

### Frontend

- [ ] Dependencies: `fl_chart`, `web_socket_channel`, `provider`/`riverpod`, `visibility_detector`
- [ ] All widget types implemented with error/loading states
- [ ] Lazy rendering + caching + isolate processing enabled

## Troubleshooting

| Problem                 | Check                                                           |
| ----------------------- | --------------------------------------------------------------- |
| Widgets not rendering   | `widget_type` supported? Valid UUID? Parsing errors in console? |
| Actions not triggering  | Correct `endpoint`? RBAC permissions? `action_id` exists?       |
| WebSocket disconnecting | `wss://` not `ws://`? Auth payload correct? Backend logs?       |
| Widgets render slowly   | Lazy rendering on? Caching working? Heavy compute on UI thread? |
