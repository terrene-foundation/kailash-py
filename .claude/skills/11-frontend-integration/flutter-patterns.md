---
name: flutter-patterns
description: "Flutter implementation patterns for Kailash SDK integration including Riverpod state management, Nexus/DataFlow/Kaizen clients, responsive design, forms, and testing. Use for 'flutter patterns', 'flutter state management', 'flutter Kailash', 'flutter riverpod', or 'flutter design system'."
---

# Flutter Implementation Patterns

## Material Design 3 Theming

```dart
ThemeData appTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(seedColor: Colors.purple, brightness: Brightness.light),
);
```

## Nexus API Client

```dart
class NexusClient {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:8000',
    connectTimeout: Duration(seconds: 5),
    receiveTimeout: Duration(seconds: 30),
    headers: {'Content-Type': 'application/json'},
  ));

  Future<WorkflowResult> executeWorkflow(String workflowId, Map<String, dynamic> parameters) async {
    try {
      final response = await _dio.post('/workflows/$workflowId/execute', data: parameters);
      return WorkflowResult.fromJson(response.data);
    } on DioException catch (e) {
      throw NexusException('Workflow execution failed: ${e.message}');
    }
  }

  Future<List<WorkflowDefinition>> listWorkflows() async {
    final response = await _dio.get('/workflows');
    return (response.data as List).map((json) => WorkflowDefinition.fromJson(json)).toList();
  }
}
```

## Riverpod State Management

```dart
final nexusClientProvider = Provider<NexusClient>((ref) => NexusClient());

final workflowListProvider = FutureProvider<List<WorkflowDefinition>>((ref) async {
  return ref.watch(nexusClientProvider).listWorkflows();
});

class WorkflowExecutionNotifier extends StateNotifier<AsyncValue<WorkflowResult>> {
  final NexusClient _client;
  WorkflowExecutionNotifier(this._client) : super(const AsyncValue.loading());

  Future<void> executeWorkflow(String id, Map<String, dynamic> params) async {
    state = const AsyncValue.loading();
    try {
      state = AsyncValue.data(await _client.executeWorkflow(id, params));
    } catch (error, stackTrace) {
      state = AsyncValue.error(error, stackTrace);
    }
  }
}
```

## DataFlow List UI Pattern

```dart
class DataFlowModelsList extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref.watch(dataFlowModelsProvider).when(
      data: (models) => RefreshIndicator(
        onRefresh: () => ref.refresh(dataFlowModelsProvider.future),
        child: ListView.builder(
          itemCount: models.length,
          itemBuilder: (context, index) => ModelCard(model: models[index]),
        ),
      ),
      loading: () => Center(child: CircularProgressIndicator()),
      error: (error, stack) => ErrorView(error: error.toString(), onRetry: () => ref.refresh(dataFlowModelsProvider)),
    );
  }
}
```

## Kaizen AI Chat Interface

```dart
class KaizenChatScreen extends ConsumerStatefulWidget {
  @override
  ConsumerState<KaizenChatScreen> createState() => _KaizenChatScreenState();
}

class _KaizenChatScreenState extends ConsumerState<KaizenChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final List<ChatMessage> _messages = [];

  void _sendMessage() {
    final text = _controller.text.trim();
    if (text.isEmpty) return;
    setState(() { _messages.add(ChatMessage(text: text, isUser: true, timestamp: DateTime.now())); });
    _controller.clear();
    ref.read(kaizenChatProvider.notifier).sendMessage(text).then((response) {
      setState(() { _messages.add(ChatMessage(text: response, isUser: false, timestamp: DateTime.now())); });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Kaizen AI Chat')),
      body: Column(children: [
        Expanded(child: ListView.builder(
          itemCount: _messages.length,
          itemBuilder: (context, index) => ChatBubble(message: _messages[index]),
        )),
        ChatInput(controller: _controller, onSend: _sendMessage),
      ]),
    );
  }
}
```

## Platform-Specific Features

```dart
class NativeFeatures {
  static const platform = MethodChannel('com.kailash.studio/native');

  Future<String> getDeviceInfo() async {
    try {
      return await platform.invokeMethod('getDeviceInfo');
    } on PlatformException catch (e) {
      return 'Failed: ${e.message}';
    }
  }

  Future<void> shareWorkflow(WorkflowDefinition workflow) async {
    await platform.invokeMethod('shareWorkflow', {'id': workflow.id, 'name': workflow.name});
  }
}
```

## Mobile Workflow Editor

```dart
class MobileWorkflowEditor extends ConsumerWidget {
  final String workflowId;
  const MobileWorkflowEditor({required this.workflowId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workflowAsync = ref.watch(workflowProvider(workflowId));
    return Scaffold(
      appBar: AppBar(title: Text('Edit Workflow'), actions: [
        IconButton(icon: Icon(Icons.play_arrow), onPressed: () {
          ref.read(workflowExecutionProvider.notifier).executeWorkflow(workflowId, {});
        }),
      ]),
      body: workflowAsync.when(
        data: (workflow) => SingleChildScrollView(
          child: Column(children: [...workflow.nodes.map((node) => NodeCard(node: node))]),
        ),
        loading: () => Center(child: CircularProgressIndicator()),
        error: (error, stack) => ErrorView(error: error.toString()),
      ),
      floatingActionButton: FloatingActionButton(
        child: Icon(Icons.add),
        onPressed: () => showModalBottomSheet(context: context, builder: (_) => NodePalette()),
      ),
    );
  }
}
```

## Feature-Based Structure

```
lib/
├── main.dart
├── core/
│   ├── providers/          # Global Riverpod providers
│   ├── models/             # Shared data models
│   ├── services/           # API clients (Nexus, DataFlow, Kaizen)
│   └── utils/
├── features/
│   ├── workflows/
│   │   ├── presentation/   # screens/ + widgets/
│   │   ├── providers/
│   │   └── models/
│   ├── dataflow/
│   └── kaizen/
└── shared/
    ├── widgets/
    └── theme/
```

## Responsive Widget Pattern

```dart
class Responsive {
  static bool isMobile(BuildContext context) => MediaQuery.of(context).size.width < 600;
  static bool isTablet(BuildContext context) =>
      MediaQuery.of(context).size.width >= 600 && MediaQuery.of(context).size.width < 1200;
  static bool isDesktop(BuildContext context) => MediaQuery.of(context).size.width >= 1200;
}
```

## AsyncBuilder Pattern

```dart
class AsyncBuilder<T> extends StatelessWidget {
  final AsyncValue<T> asyncValue;
  final Widget Function(T data) builder;
  final Widget? loading;
  final Widget Function(Object error, StackTrace stack)? error;

  const AsyncBuilder({required this.asyncValue, required this.builder, this.loading, this.error});

  @override
  Widget build(BuildContext context) {
    return asyncValue.when(
      data: builder,
      loading: () => loading ?? Center(child: CircularProgressIndicator()),
      error: (err, stack) => error?.call(err, stack) ?? ErrorView(error: err.toString()),
    );
  }
}
```

## Performance

```dart
// const constructors prevent unnecessary rebuilds
const Card(child: Padding(padding: EdgeInsets.all(16.0), child: Text('Static')));

// ListView.builder for large lists (only builds visible items)
ListView.builder(itemCount: items.length, itemBuilder: (ctx, i) => ItemCard(item: items[i]));

// RepaintBoundary for expensive widgets
RepaintBoundary(child: ComplexCustomPaintWidget());

// Cached network images
CachedNetworkImage(imageUrl: url, placeholder: (_, __) => CircularProgressIndicator());
```

## Form Validation

```dart
class WorkflowFormNotifier extends StateNotifier<WorkflowFormState> {
  WorkflowFormNotifier() : super(WorkflowFormState.initial());
  void updateName(String name) => state = state.copyWith(name: name);
  String? validateName() {
    if (state.name.isEmpty) return 'Name is required';
    if (state.name.length < 3) return 'Name must be at least 3 characters';
    return null;
  }
  bool isValid() => validateName() == null;
}
```

## Go Router Navigation

```dart
final goRouter = GoRouter(routes: [
  GoRoute(path: '/', builder: (context, state) => HomeScreen()),
  GoRoute(path: '/workflows', builder: (context, state) => WorkflowListScreen()),
  GoRoute(path: '/workflows/:id', builder: (context, state) =>
      WorkflowDetailScreen(id: state.pathParameters['id']!)),
]);

context.go('/workflows/123');
context.push('/kaizen/chat');
```

## Error Handling

```dart
class ErrorHandler {
  void handle(Object error, StackTrace stack, {String? context}) {
    if (error is DioException) {
      if (error.type == DioExceptionType.connectionTimeout) _showError('Connection timeout.');
      else if (error.response?.statusCode == 401) _showError('Unauthorized. Please log in again.');
      else if (error.response?.statusCode == 500) _showError('Server error.');
    }
  }
}
```

## Testing

```dart
// Unit test with Riverpod
test('workflow execution updates state', () async {
  final container = ProviderContainer();
  await container.read(workflowExecutionProvider.notifier).executeWorkflow('test', {});
  expect(container.read(workflowExecutionProvider), isA<AsyncData<WorkflowResult>>());
});

// Widget test
testWidgets('WorkflowCard displays info', (tester) async {
  await tester.pumpWidget(ProviderScope(child: MaterialApp(
    home: WorkflowCard(workflow: WorkflowDefinition(id: 'test', name: 'Test', description: 'Desc')),
  )));
  expect(find.text('Test'), findsOneWidget);
});
```

## Design System Tokens

```dart
import 'package:[app]/core/design/design_system.dart';

AppColors.primary / .secondary / .success / .warning / .error
AppTypography.h1 / h2 / h3 / h4 / bodyLarge / bodyMedium / bodySmall
AppSpacing.xs(4) / sm(8) / md(16) / lg(24) / xl(32)
AppSpacing.allMd / gapMd  // EdgeInsets.all(16) / SizedBox(height: 16)
```
