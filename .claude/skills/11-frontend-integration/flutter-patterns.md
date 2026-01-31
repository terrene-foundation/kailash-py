---
name: flutter-patterns
description: "Flutter implementation patterns for Kailash SDK integration including Riverpod state management, Nexus/DataFlow/Kaizen clients, responsive design, forms, and testing. Use for 'flutter patterns', 'flutter state management', 'flutter Kailash', 'flutter riverpod', or 'flutter design system'."
---

# Flutter Implementation Patterns

> **Skill Metadata**
> Category: `frontend`
> Priority: `MEDIUM`
> SDK Version: `0.9.25+`
> Flutter Version: `3.27+`

## Material Design 3 Theming

```dart
// Material 3 theming
ThemeData appTheme = ThemeData(
  useMaterial3: true,
  colorScheme: ColorScheme.fromSeed(
    seedColor: Colors.purple,
    brightness: Brightness.light,
  ),
);

// Responsive scaffold
class ResponsiveScaffold extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 600) {
          return MobileLayout();
        } else if (constraints.maxWidth < 1200) {
          return TabletLayout();
        } else {
          return DesktopLayout();
        }
      },
    );
  }
}
```

## Kailash SDK Integration

### Nexus API Client

```dart
// Nexus API client with Dio
class NexusClient {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:8000',
    connectTimeout: Duration(seconds: 5),
    receiveTimeout: Duration(seconds: 30),
    headers: {'Content-Type': 'application/json'},
  ));

  Future<WorkflowResult> executeWorkflow(
    String workflowId,
    Map<String, dynamic> parameters,
  ) async {
    try {
      final response = await _dio.post(
        '/workflows/$workflowId/execute',
        data: parameters,
      );
      return WorkflowResult.fromJson(response.data);
    } on DioException catch (e) {
      throw NexusException('Workflow execution failed: ${e.message}');
    }
  }

  Future<List<WorkflowDefinition>> listWorkflows() async {
    final response = await _dio.get('/workflows');
    return (response.data as List)
        .map((json) => WorkflowDefinition.fromJson(json))
        .toList();
  }
}
```

### Riverpod State Management

```dart
// Riverpod provider for Nexus client
final nexusClientProvider = Provider<NexusClient>((ref) {
  return NexusClient();
});

// Workflow list provider with auto-refresh
final workflowListProvider = FutureProvider<List<WorkflowDefinition>>((ref) async {
  final client = ref.watch(nexusClientProvider);
  return client.listWorkflows();
});

// Workflow execution state provider
final workflowExecutionProvider = StateNotifierProvider<WorkflowExecutionNotifier, AsyncValue<WorkflowResult>>((ref) {
  final client = ref.watch(nexusClientProvider);
  return WorkflowExecutionNotifier(client);
});

class WorkflowExecutionNotifier extends StateNotifier<AsyncValue<WorkflowResult>> {
  final NexusClient _client;

  WorkflowExecutionNotifier(this._client) : super(const AsyncValue.loading());

  Future<void> executeWorkflow(String id, Map<String, dynamic> params) async {
    state = const AsyncValue.loading();

    try {
      final result = await _client.executeWorkflow(id, params);
      state = AsyncValue.data(result);
    } catch (error, stackTrace) {
      state = AsyncValue.error(error, stackTrace);
    }
  }
}
```

### DataFlow List UI Pattern

```dart
// DataFlow models list with pull-to-refresh
class DataFlowModelsList extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final modelsAsync = ref.watch(dataFlowModelsProvider);

    return modelsAsync.when(
      data: (models) => RefreshIndicator(
        onRefresh: () => ref.refresh(dataFlowModelsProvider.future),
        child: ListView.builder(
          itemCount: models.length,
          itemBuilder: (context, index) {
            final model = models[index];
            return ModelCard(model: model);
          },
        ),
      ),
      loading: () => Center(child: CircularProgressIndicator()),
      error: (error, stack) => ErrorView(
        error: error.toString(),
        onRetry: () => ref.refresh(dataFlowModelsProvider),
      ),
    );
  }
}
```

### Kaizen AI Chat Interface

```dart
// Kaizen streaming chat with optimistic updates
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

    // Optimistic update
    setState(() {
      _messages.add(ChatMessage(
        text: text,
        isUser: true,
        timestamp: DateTime.now(),
      ));
    });

    _controller.clear();

    // Call Kaizen agent
    ref.read(kaizenChatProvider.notifier).sendMessage(text).then((response) {
      setState(() {
        _messages.add(ChatMessage(
          text: response,
          isUser: false,
          timestamp: DateTime.now(),
        ));
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Kaizen AI Chat')),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                return ChatBubble(message: _messages[index]);
              },
            ),
          ),
          ChatInput(
            controller: _controller,
            onSend: _sendMessage,
          ),
        ],
      ),
    );
  }
}
```

## Architecture Patterns

### Feature-Based Structure

```
lib/
├── main.dart                    # App entry point
├── core/
│   ├── providers/               # Global Riverpod providers
│   ├── models/                  # Shared data models
│   ├── services/                # API clients (Nexus, DataFlow, Kaizen)
│   └── utils/                   # Helper functions
├── features/
│   ├── workflows/
│   │   ├── presentation/        # UI widgets
│   │   │   ├── screens/         # Full screens
│   │   │   └── widgets/         # Reusable widgets
│   │   ├── providers/           # Feature-specific providers
│   │   └── models/              # Feature-specific models
│   ├── dataflow/
│   └── kaizen/
└── shared/
    ├── widgets/                 # Reusable UI components
    └── theme/                   # App theming
```

### Responsive Widget Pattern

```dart
// Responsive helper
class Responsive {
  static bool isMobile(BuildContext context) =>
      MediaQuery.of(context).size.width < 600;

  static bool isTablet(BuildContext context) =>
      MediaQuery.of(context).size.width >= 600 &&
      MediaQuery.of(context).size.width < 1200;

  static bool isDesktop(BuildContext context) =>
      MediaQuery.of(context).size.width >= 1200;
}

// Adaptive layout
class WorkflowCanvas extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    if (Responsive.isMobile(context)) {
      return MobileWorkflowCanvas();
    } else if (Responsive.isTablet(context)) {
      return TabletWorkflowCanvas();
    } else {
      return DesktopWorkflowCanvas();
    }
  }
}
```

### Loading States Pattern

```dart
// Consistent loading/error/empty states
class AsyncBuilder<T> extends StatelessWidget {
  final AsyncValue<T> asyncValue;
  final Widget Function(T data) builder;
  final Widget? loading;
  final Widget Function(Object error, StackTrace stack)? error;
  final Widget? empty;

  const AsyncBuilder({
    required this.asyncValue,
    required this.builder,
    this.loading,
    this.error,
    this.empty,
  });

  @override
  Widget build(BuildContext context) {
    return asyncValue.when(
      data: (data) {
        if (data is List && data.isEmpty && empty != null) {
          return empty!;
        }
        return builder(data);
      },
      loading: () => loading ?? Center(child: CircularProgressIndicator()),
      error: (err, stack) => error?.call(err, stack) ?? ErrorView(error: err.toString()),
    );
  }
}
```

## Performance Optimization

### Efficient Widget Rebuilds

```dart
// Use const constructors wherever possible
class MyWidget extends StatelessWidget {
  const MyWidget({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return const Card(  // const prevents unnecessary rebuilds
      child: Padding(
        padding: EdgeInsets.all(16.0),
        child: Text('Static content'),
      ),
    );
  }
}

// ListView.builder for large lists
ListView.builder(
  itemCount: items.length,
  itemBuilder: (context, index) {
    return ItemCard(item: items[index]);  // Only builds visible items
  },
)

// RepaintBoundary for expensive widgets
RepaintBoundary(
  child: ComplexCustomPaintWidget(),
)
```

### Image Optimization

```dart
// Cached network images
CachedNetworkImage(
  imageUrl: workflow.thumbnailUrl,
  placeholder: (context, url) => CircularProgressIndicator(),
  errorWidget: (context, url, error) => Icon(Icons.error),
  fit: BoxFit.cover,
)

// Optimized asset images
Image.asset(
  'assets/images/logo.png',
  cacheWidth: 200,  // Decode at smaller size
  cacheHeight: 200,
)
```

## Form Validation Pattern

```dart
// Form state provider
final workflowFormProvider = StateNotifierProvider<WorkflowFormNotifier, WorkflowFormState>((ref) {
  return WorkflowFormNotifier();
});

class WorkflowFormNotifier extends StateNotifier<WorkflowFormState> {
  WorkflowFormNotifier() : super(WorkflowFormState.initial());

  void updateName(String name) {
    state = state.copyWith(name: name);
  }

  String? validateName() {
    if (state.name.isEmpty) return 'Name is required';
    if (state.name.length < 3) return 'Name must be at least 3 characters';
    return null;
  }

  bool isValid() {
    return validateName() == null;
  }
}

// Form widget
class WorkflowForm extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final formState = ref.watch(workflowFormProvider);
    final formNotifier = ref.read(workflowFormProvider.notifier);

    return Column(
      children: [
        TextFormField(
          decoration: InputDecoration(labelText: 'Workflow Name'),
          onChanged: formNotifier.updateName,
          validator: (_) => formNotifier.validateName(),
        ),
        SizedBox(height: 16),
        ElevatedButton(
          onPressed: formNotifier.isValid()
              ? () { /* Save workflow */ }
              : null,
          child: Text('Save'),
        ),
      ],
    );
  }
}
```

## Navigation Patterns

### Go Router (Recommended)

```dart
// Define routes
final goRouter = GoRouter(
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => HomeScreen(),
    ),
    GoRoute(
      path: '/workflows',
      builder: (context, state) => WorkflowListScreen(),
    ),
    GoRoute(
      path: '/workflows/:id',
      builder: (context, state) {
        final id = state.pathParameters['id']!;
        return WorkflowDetailScreen(id: id);
      },
    ),
    GoRoute(
      path: '/kaizen/chat',
      builder: (context, state) => KaizenChatScreen(),
    ),
  ],
);

// Navigate
context.go('/workflows/123');
context.push('/kaizen/chat');
```

## Error Handling

```dart
// Error handler provider
final errorHandlerProvider = Provider<ErrorHandler>((ref) {
  return ErrorHandler();
});

class ErrorHandler {
  void handle(Object error, StackTrace stack, {String? context}) {
    debugPrint('Error in $context: $error\n$stack');

    if (error is DioException) {
      _handleNetworkError(error);
    } else if (error is NexusException) {
      _handleNexusError(error);
    } else {
      _showGenericError(error);
    }
  }

  void _handleNetworkError(DioException error) {
    String message = 'Network error occurred';

    if (error.type == DioExceptionType.connectionTimeout) {
      message = 'Connection timeout. Please check your internet connection.';
    } else if (error.type == DioExceptionType.connectionError) {
      message = 'Unable to connect to server.';
    } else if (error.response?.statusCode == 401) {
      message = 'Unauthorized. Please log in again.';
    } else if (error.response?.statusCode == 500) {
      message = 'Server error. Please try again later.';
    }

    _showError(message);
  }
}
```

## Testing Patterns

### Unit Tests with Riverpod

```dart
void main() {
  test('workflow execution provider updates state correctly', () async {
    final container = ProviderContainer();

    expect(
      container.read(workflowExecutionProvider),
      isA<AsyncLoading>(),
    );

    await container.read(workflowExecutionProvider.notifier)
        .executeWorkflow('test-workflow', {});

    expect(
      container.read(workflowExecutionProvider),
      isA<AsyncData<WorkflowResult>>(),
    );
  });
}
```

### Widget Tests

```dart
void main() {
  testWidgets('WorkflowCard displays workflow info', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        child: MaterialApp(
          home: WorkflowCard(
            workflow: WorkflowDefinition(
              id: 'test',
              name: 'Test Workflow',
              description: 'Test description',
            ),
          ),
        ),
      ),
    );

    expect(find.text('Test Workflow'), findsOneWidget);
    expect(find.text('Test description'), findsOneWidget);
  });
}
```

## Platform-Specific Features

```dart
// Platform channel for native features
class NativeFeatures {
  static const platform = MethodChannel('com.kailash.studio/native');

  Future<String> getDeviceInfo() async {
    try {
      final String result = await platform.invokeMethod('getDeviceInfo');
      return result;
    } on PlatformException catch (e) {
      return 'Failed to get device info: ${e.message}';
    }
  }

  Future<void> shareWorkflow(WorkflowDefinition workflow) async {
    try {
      await platform.invokeMethod('shareWorkflow', {
        'id': workflow.id,
        'name': workflow.name,
      });
    } on PlatformException catch (e) {
      throw Exception('Failed to share: ${e.message}');
    }
  }
}
```

## Mobile Workflow Editor

```dart
// Simplified workflow editor for mobile
class MobileWorkflowEditor extends ConsumerWidget {
  final String workflowId;

  const MobileWorkflowEditor({required this.workflowId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workflowAsync = ref.watch(workflowProvider(workflowId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Edit Workflow'),
        actions: [
          IconButton(
            icon: Icon(Icons.play_arrow),
            onPressed: () {
              ref.read(workflowExecutionProvider.notifier)
                  .executeWorkflow(workflowId, {});
            },
          ),
        ],
      ),
      body: workflowAsync.when(
        data: (workflow) => SingleChildScrollView(
          child: Column(
            children: [
              ...workflow.nodes.map((node) => NodeCard(node: node)),
            ],
          ),
        ),
        loading: () => Center(child: CircularProgressIndicator()),
        error: (error, stack) => ErrorView(error: error.toString()),
      ),
      floatingActionButton: FloatingActionButton(
        child: Icon(Icons.add),
        onPressed: () {
          showModalBottomSheet(
            context: context,
            builder: (context) => NodePalette(),
          );
        },
      ),
    );
  }
}
```

## Design System Usage

```dart
import 'package:[app]/core/design/design_system.dart';

// Colors
AppColors.primary          // Professional Blue (#1976D2)
AppColors.secondary        // Teal (#26A69A)
AppColors.success         // Green
AppColorsDark.textPrimary     // Dark mode text (high contrast)

// Typography
AppTypography.h1 / h2 / h3 / h4    // Headings
AppTypography.bodyLarge / bodyMedium / bodySmall  // Body text

// Spacing
AppSpacing.xs / sm / md / lg / xl  // 4px → 64px
AppSpacing.allMd         // EdgeInsets.all(16)
AppSpacing.gapMd         // SizedBox(height: 16)

// Example usage
class ContactForm extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return AppCard(
      header: Padding(
        padding: AppSpacing.allMd,
        child: Text('New Contact', style: AppTypography.h4),
      ),
      child: Column(
        children: [
          AppInput(label: 'Name', isRequired: true),
          AppSpacing.gapMd,
          AppInput.email(label: 'Email', isRequired: true),
          AppSpacing.gapMd,
          AppButton.primary(
            label: 'Save Contact',
            isFullWidth: true,
            onPressed: _handleSubmit,
          ),
        ],
      ),
    );
  }
}
```

<!-- Trigger Keywords: flutter patterns, flutter state management, flutter kailash, flutter riverpod, flutter nexus, flutter dataflow, flutter kaizen, flutter design system, flutter responsive, flutter forms, flutter testing -->
