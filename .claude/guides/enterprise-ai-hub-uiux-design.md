# Enterprise AI Hub - UI/UX Design Principles & Specifications

**Version**: 1.0
**Created**: 2025-10-18
**Status**: Production Design Standard
**Applies To**: All Enterprise AI Hub UI/UX development

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Core Design Challenges](#core-design-challenges)
3. [Design Principles for AI Interfaces](#design-principles-for-ai-interfaces)
4. [Interactive Widget Response System](#interactive-widget-response-system)
5. [Multi-Conversation Workflow](#multi-conversation-workflow)
6. [Response Verification & Citations](#response-verification--citations)
7. [Data Source Selection UI](#data-source-selection-ui)
8. [Document Upload & Management](#document-upload--management)
9. [Visual Response Components](#visual-response-components)
10. [Information Architecture](#information-architecture)
11. [Cognitive Load Management](#cognitive-load-management)
12. [Implementation Roadmap](#implementation-roadmap)

---

## Executive Summary

### Primary Goals
1. **Reduce cognitive overload** while maintaining enterprise-grade transparency
2. **Enable interactive widget responses** embedded in AI conversation stream
3. **Support multi-conversation workflows** with context sharing
4. **Provide verifiable responses** with clear data source attribution
5. **Create intuitive data source selection** with RBAC integration

### Success Metrics
- Users can verify AI responses in < 5 seconds
- Users can complete multi-conversation workflows without confusion
- Interactive widgets render seamlessly in conversation stream
- Data source selection requires < 3 clicks
- Cognitive load score < 4/10 (via NASA TLX evaluation)

---

## Core Design Challenges

### Challenge 1: Interactive Widget Responses (PRIORITY)
**Problem**: Current AI assistants are limited to text, markdown, and static charts. Users need interactive Flutter widgets embedded in responses with navigation capabilities.

**User Story**:
> "As an enterprise user, I want to interact with data visualizations, forms, and navigation elements directly within AI responses, rather than being limited to static content or external links."

**Complexity**: Medium-High
- Widget serialization/deserialization from backend to Flutter
- State management for interactive widgets in conversation stream
- Performance optimization for complex widgets
- Deep linking and navigation from widgets

### Challenge 2: Multi-Conversation Workflows
**Problem**: Enterprise users need to work across multiple conversations simultaneously and reference context from different conversations.

**User Story**:
> "As a research analyst, I want to branch from specific conversation turns, maintain multiple parallel conversations, and ask the AI to combine insights from different conversations."

**Complexity**: High
- Conversation tree visualization
- Context sharing between conversations
- Turn-level branching UI
- Session management

### Challenge 3: Response Verification
**Problem**: Enterprise users must verify AI responses for compliance, accuracy, and auditability.

**User Story**:
> "As a compliance officer, I need to see exactly which documents, pages, and snippets were used to generate each AI response, with the ability to verify by confidence level or anomaly detection."

**Complexity**: Medium
- Citation UI that doesn't overwhelm
- Confidence scoring visualization
- Inline document preview
- Anomaly highlighting

### Challenge 4: Data Source Selection
**Problem**: Users need granular control over which data sources the AI uses, respecting RBAC.

**User Story**:
> "As a department head, I want to select only certain data sources (e.g., my department's SharePoint + internal docs) for AI to use, excluding web search or other departments' data."

**Complexity**: Medium
- RBAC-aware UI
- Multi-select with categorization
- Persistent source preferences
- Visual feedback on active sources

### Challenge 5: Document Upload & Management
**Problem**: Users upload documents for AI to reference, but need visibility into which documents are being used.

**User Story**:
> "As a project manager, I want to upload project documents and see which documents the AI referenced when answering my questions, with the ability to remove documents from the active context."

**Complexity**: Low-Medium
- File upload UI with progress
- Active document list visualization
- Document relevance scoring
- Context window management

---

## Design Principles for AI Interfaces

### Principle 1: Progressive Disclosure of Complexity
**Definition**: Show essential information by default, reveal details on demand.

**Application**:
```
DEFAULT VIEW (Clean):
┌────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased │
│ by 23% compared to Q1.                              │
│ [3 sources ▼]                                       │
└────────────────────────────────────────────────────┘

EXPANDED VIEW (On click):
┌────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased │
│ by 23% compared to Q1.                              │
│                                                     │
│ ┌─ Data Sources (3) ─────────────────────────────┐ │
│ │ ✓ Q2_Sales_Report.xlsx (Page 3, Cell B12)      │ │
│ │   Confidence: 95% | "Q2 Revenue: $1.23M"       │ │
│ │                                                 │ │
│ │ ✓ Finance_Dashboard.pdf (Page 1)               │ │
│ │   Confidence: 87% | Chart showing growth trend │ │
│ │                                                 │ │
│ │ ✓ Internal DB: sales_quarterly                 │ │
│ │   Confidence: 98% | Query: SELECT SUM(revenue) │ │
│ └─────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

**Benefits**:
- Reduces cognitive overload
- Allows verification without forcing it
- Maintains clean conversation flow

### Principle 2: Inline Verification Without Context Switching
**Definition**: Users can verify responses without leaving the conversation context.

**Application**:
- Inline document preview in slide-over (not new tab)
- Snippet highlighting with context (before/after text)
- Hover tooltips for quick confidence scores
- Embedded page viewers for documents

**Benefits**:
- Reduces interruption
- Faster verification workflow
- Maintains conversation momentum

### Principle 3: Visual Hierarchy for AI Responses
**Definition**: Different response types have distinct visual treatments.

**Visual Hierarchy**:
```
┌────────────────────────────────────────────────────┐
│ ┌─ DIRECT ANSWER (High Confidence) ──────────────┐ │
│ │ Revenue increased by 23% in Q2.                │ │
│ │ [Sources: 3 ✓] [Confidence: 95%]               │ │
│ └────────────────────────────────────────────────┘ │
│                                                     │
│ ┌─ ANALYSIS (Medium Confidence) ─────────────────┐ │
│ │ This growth appears driven by new customer     │ │
│ │ acquisition (based on limited data).           │ │
│ │ [Sources: 2 ⚠] [Confidence: 72%]               │ │
│ └────────────────────────────────────────────────┘ │
│                                                     │
│ ┌─ SUGGESTION (Action Item) ─────────────────────┐ │
│ │ Consider analyzing customer segmentation.      │ │
│ │ [Action: Run Report ▶]                          │ │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

**Color Coding**:
- **High Confidence (≥90%)**: Green accent, ✓ icon
- **Medium Confidence (70-89%)**: Yellow accent, ⚠ icon
- **Low Confidence (<70%)**: Orange accent, ⓘ icon
- **Action Items**: Blue accent, ▶ icon

### Principle 4: Contextual Widget Integration
**Definition**: Interactive widgets are seamlessly integrated into the conversation flow, not isolated.

**Layout Pattern**:
```
┌────────────────────────────────────────────────────┐
│ User: Show me Q2 sales breakdown by region        │
└────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────┐
│ AI: Here's the regional breakdown:                 │
│                                                     │
│ ┌─ INTERACTIVE CHART WIDGET ────────────────────┐ │
│ │ [Bar Chart: Sales by Region]                  │ │
│ │ North: $450K  [Details ▶]                     │ │
│ │ South: $380K  [Details ▶]                     │ │
│ │ East:  $290K  [Details ▶]                     │ │
│ │ West:  $110K  [Details ▶]                     │ │
│ │                                               │ │
│ │ [Export CSV] [View in Dashboard] [Filter ▼]  │ │
│ └───────────────────────────────────────────────┘ │
│                                                     │
│ North region shows highest growth (+34% vs Q1).    │
│ [3 sources ▼]                                       │
└────────────────────────────────────────────────────┘
```

**Benefits**:
- Natural conversation flow maintained
- Immediate actionability
- No context switching required
- Progressive disclosure of details

### Principle 5: Conversation Branching as First-Class Citizen
**Definition**: Multi-conversation workflows are core functionality, not an afterthought.

**UI Treatment**:
- Visual conversation tree
- Turn-level branching indicators
- Cross-conversation references
- Session timeline view

---

## Interactive Widget Response System

### Architecture Overview

#### Backend → Frontend Widget Specification

**Widget Descriptor Format** (JSON):
```json
{
  "type": "widget",
  "widget_type": "chart|table|form|card|navigation|custom",
  "widget_id": "uuid-v4",
  "data": {
    // Widget-specific data
  },
  "config": {
    // Widget configuration
  },
  "actions": [
    {
      "action_id": "uuid-v4",
      "label": "View Details",
      "type": "navigate|api_call|dialog|download",
      "params": {}
    }
  ],
  "metadata": {
    "sources": [...],
    "confidence": 0.95,
    "generated_at": "2025-10-18T10:30:00Z"
  }
}
```

#### Widget Type Specifications

##### 1. Chart Widget
```json
{
  "widget_type": "chart",
  "data": {
    "chart_type": "bar|line|pie|scatter|combo",
    "series": [
      {
        "name": "Q2 Sales",
        "values": [450, 380, 290, 110],
        "labels": ["North", "South", "East", "West"]
      }
    ],
    "x_axis_label": "Region",
    "y_axis_label": "Revenue (K)",
    "title": "Q2 Sales by Region"
  },
  "config": {
    "interactive": true,
    "export_formats": ["csv", "png", "pdf"],
    "drill_down_enabled": true,
    "responsive": true
  },
  "actions": [
    {
      "action_id": "drill_down_north",
      "label": "North Details",
      "type": "api_call",
      "params": {
        "endpoint": "/api/sales/region/north",
        "method": "GET"
      }
    }
  ]
}
```

**Flutter Implementation**:
```dart
class ChartWidget extends StatelessWidget {
  final ChartWidgetDescriptor descriptor;

  Widget build(BuildContext context) {
    return AppCard(
      child: Column(
        children: [
          // Title
          Text(descriptor.data.title, style: AppTypography.h4),
          AppSpacing.gapMd,

          // Interactive Chart (using fl_chart package)
          SizedBox(
            height: 300,
            child: BarChart(
              BarChartData(
                barGroups: _buildBarGroups(),
                titlesData: _buildTitles(),
                borderData: FlBorderData(show: false),
              ),
            ),
          ),
          AppSpacing.gapMd,

          // Actions
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              for (var action in descriptor.actions)
                AppButton.text(
                  label: action.label,
                  onPressed: () => _handleAction(action),
                ),
            ],
          ),
        ],
      ),
    );
  }
}
```

##### 2. Data Table Widget
```json
{
  "widget_type": "table",
  "data": {
    "columns": [
      {"key": "name", "label": "Name", "sortable": true},
      {"key": "revenue", "label": "Revenue", "sortable": true, "format": "currency"},
      {"key": "growth", "label": "Growth", "sortable": true, "format": "percentage"}
    ],
    "rows": [
      {"name": "Product A", "revenue": 123000, "growth": 0.23},
      {"name": "Product B", "revenue": 98000, "growth": 0.15}
    ],
    "pagination": {
      "page": 1,
      "per_page": 10,
      "total": 45
    }
  },
  "config": {
    "selectable_rows": true,
    "exportable": true,
    "filterable": true
  },
  "actions": [
    {
      "action_id": "export_table",
      "label": "Export CSV",
      "type": "download",
      "params": {"format": "csv"}
    }
  ]
}
```

##### 3. Form Widget
```json
{
  "widget_type": "form",
  "data": {
    "form_id": "customer_search_form",
    "fields": [
      {
        "field_id": "customer_name",
        "type": "text",
        "label": "Customer Name",
        "placeholder": "Enter name...",
        "required": true,
        "validation": {
          "min_length": 3,
          "max_length": 100
        }
      },
      {
        "field_id": "date_range",
        "type": "date_range",
        "label": "Date Range",
        "default": {"start": "2025-01-01", "end": "2025-03-31"}
      },
      {
        "field_id": "region",
        "type": "select",
        "label": "Region",
        "options": [
          {"value": "north", "label": "North"},
          {"value": "south", "label": "South"}
        ],
        "multi_select": true
      }
    ],
    "submit_button_label": "Search"
  },
  "config": {
    "auto_submit": false,
    "preserve_state": true
  },
  "actions": [
    {
      "action_id": "submit_form",
      "type": "api_call",
      "params": {
        "endpoint": "/api/customers/search",
        "method": "POST"
      }
    }
  ]
}
```

##### 4. Navigation Card Widget
```json
{
  "widget_type": "navigation_card",
  "data": {
    "cards": [
      {
        "title": "Sales Dashboard",
        "description": "View detailed sales metrics and trends",
        "icon": "dashboard",
        "badge": "New Data",
        "badge_color": "success"
      },
      {
        "title": "Customer Analysis",
        "description": "Analyze customer behavior and segments",
        "icon": "people",
        "badge": null
      }
    ]
  },
  "actions": [
    {
      "action_id": "nav_sales",
      "type": "navigate",
      "params": {
        "route": "/dashboard/sales",
        "preserve_conversation": true
      }
    },
    {
      "action_id": "nav_customers",
      "type": "navigate",
      "params": {
        "route": "/dashboard/customers",
        "preserve_conversation": true
      }
    }
  ]
}
```

#### Widget Rendering Pipeline

**Step 1: Backend generates widget descriptor**
```python
# Kailash SDK - AI Agent generates widget spec
from kaizen.agents import BaseAgent

class DashboardAgent(BaseAgent):
    async def generate_chart_response(self, user_query: str):
        # Analyze query, fetch data
        sales_data = await self._fetch_sales_data()

        # Generate widget descriptor
        widget_descriptor = {
            "type": "widget",
            "widget_type": "chart",
            "widget_id": str(uuid.uuid4()),
            "data": {
                "chart_type": "bar",
                "series": [sales_data],
                # ...
            },
            # ...
        }

        return {
            "text": "Here's the Q2 sales breakdown:",
            "widgets": [widget_descriptor]
        }
```

**Step 2: Stream to Flutter via WebSocket/SSE**
```python
# Nexus API streaming
from nexus import Nexus

nexus = Nexus()

@nexus.stream_endpoint("/ai/chat")
async def chat_stream(session_id: str, message: str):
    agent = DashboardAgent()

    # Stream text chunks
    async for chunk in agent.stream_response(message):
        yield {"type": "text", "content": chunk}

    # Stream widget descriptor
    widget = await agent.generate_chart_response(message)
    yield {"type": "widget", "content": widget}
```

**Step 3: Flutter receives and renders**
```dart
class ConversationMessage extends StatelessWidget {
  final Message message;

  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Text content (markdown)
        if (message.text != null)
          MarkdownBody(data: message.text!),

        AppSpacing.gapMd,

        // Widgets
        if (message.widgets != null)
          for (var widgetDesc in message.widgets!)
            _buildWidget(widgetDesc),
      ],
    );
  }

  Widget _buildWidget(WidgetDescriptor descriptor) {
    switch (descriptor.widgetType) {
      case 'chart':
        return ChartWidget(descriptor: descriptor as ChartWidgetDescriptor);
      case 'table':
        return DataTableWidget(descriptor: descriptor as TableWidgetDescriptor);
      case 'form':
        return FormWidget(descriptor: descriptor as FormWidgetDescriptor);
      case 'navigation_card':
        return NavigationCardWidget(descriptor: descriptor as NavCardWidgetDescriptor);
      default:
        return Text('Unsupported widget type: ${descriptor.widgetType}');
    }
  }
}
```

#### Widget State Management

**Problem**: Interactive widgets in conversation stream need state management without polluting conversation history.

**Solution**: Hybrid state management
```dart
// 1. Widget-local state for transient interactions
class ChartWidget extends StatefulWidget {
  final ChartWidgetDescriptor descriptor;

  State<ChartWidget> createState() => _ChartWidgetState();
}

class _ChartWidgetState extends State<ChartWidget> {
  String? selectedRegion; // Local state

  Widget build(BuildContext context) {
    return InteractiveBarChart(
      data: widget.descriptor.data,
      onBarTap: (region) {
        setState(() {
          selectedRegion = region;
        });
        _showDrillDown(region); // Local action
      },
    );
  }
}

// 2. Conversation-level state for persistent changes
class ConversationProvider extends ChangeNotifier {
  Map<String, dynamic> widgetStates = {};

  void updateWidgetState(String widgetId, dynamic state) {
    widgetStates[widgetId] = state;
    notifyListeners();
  }

  dynamic getWidgetState(String widgetId) {
    return widgetStates[widgetId];
  }
}

// 3. Backend sync for important state changes
class FormWidget extends StatefulWidget {
  // When form is submitted, send to backend
  void _handleSubmit() async {
    final formData = _collectFormData();

    // Send to conversation context
    await conversationService.addUserMessage(
      "Form submitted: ${formData.toString()}",
      metadata: {
        "widget_id": widget.descriptor.widgetId,
        "form_data": formData
      }
    );
  }
}
```

#### Performance Optimization

**Challenge**: Complex widgets in long conversations can impact performance.

**Solutions**:
1. **Lazy rendering**: Render only visible widgets
2. **Widget caching**: Cache rendered widgets keyed by widget_id
3. **Virtualization**: Use ListView.builder for conversation stream
4. **Offload to isolates**: Heavy computations in background isolates

```dart
class ConversationStream extends StatelessWidget {
  final List<Message> messages;

  Widget build(BuildContext context) {
    return ListView.builder(
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final message = messages[index];

        // Lazy render widgets
        return VisibilityDetector(
          key: Key('message-${message.id}'),
          onVisibilityChanged: (info) {
            if (info.visibleFraction > 0.5) {
              // Trigger widget rendering only when visible
              _renderWidgetsForMessage(message);
            }
          },
          child: ConversationMessage(message: message),
        );
      },
    );
  }
}
```

---

## Multi-Conversation Workflow

### Conceptual Model

**Mental Model**: Think of conversations as Git branches
- Main conversation thread = main branch
- Turn-level branching = feature branches
- Context merging = git merge
- Conversation history = git log

### UI Components

#### 1. Conversation Sidebar (Primary Navigation)

**Layout**:
```
┌─ CONVERSATIONS ───────────────┐
│ [+ New Chat]                  │
│                               │
│ ┌─ Active (3) ──────────────┐ │
│ │ ● Q2 Sales Analysis        │ │
│ │   └─ Regional Breakdown    │ │ ← Branch indicator
│ │   └─ Customer Segments     │ │
│ │                            │ │
│ │ ○ HR Policy Questions      │ │
│ │                            │ │
│ │ ○ Product Roadmap Review   │ │
│ └────────────────────────────┘ │
│                               │
│ ┌─ Recent (5) ──────────────┐ │
│ │ Oct 17 - Budget Planning   │ │
│ │ Oct 16 - Vendor Analysis   │ │
│ │ ...                        │ │
│ └────────────────────────────┘ │
│                               │
│ ┌─ Starred (2) ─────────────┐ │
│ │ ★ Template: Weekly Report  │ │
│ │ ★ Knowledge Base Setup     │ │
│ └────────────────────────────┘ │
└───────────────────────────────┘
```

**Features**:
- Visual hierarchy: Active (bold, colored dot) > Recent > Starred
- Nested branches shown with indentation
- Badge count for unread/updated conversations
- Drag-drop to organize/star
- Quick actions on hover (rename, delete, share, star)

#### 2. Turn-Level Branching UI

**Inline Branch Creation**:
```
┌─────────────────────────────────────────────────────┐
│ User: Show me Q2 sales breakdown                    │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ AI: Here's the Q2 breakdown: [Chart Widget]         │
│ Revenue grew 23% compared to Q1.                    │
│                                                      │
│ [Branch from here ⑂]  [Copy] [Regenerate]          │ ← Hover actions
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ User: What drove the growth in North region?        │
└─────────────────────────────────────────────────────┘
```

**When user clicks "Branch from here"**:
```
┌─────────────────────────────────────────────────────┐
│ ┌─ Create Branch ──────────────────────────────────┐ │
│ │ Branch Name: [Regional Deep Dive_________]       │ │
│ │                                                  │ │
│ │ Starting from:                                   │ │
│ │ "AI: Here's the Q2 breakdown..."                 │ │
│ │                                                  │ │
│ │ [ ] Copy conversation context to new branch      │ │
│ │ [ ] Share data sources with new branch           │ │
│ │                                                  │ │
│ │ [Cancel]  [Create Branch →]                      │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**After branching**:
```
MAIN CONVERSATION          BRANCH CONVERSATION
┌─────────────────┐       ┌─────────────────────────┐
│ [Original msgs] │       │ [Copied context]        │
│ ...             │       │ ...                     │
│                 │  ⑂→   │ AI: Q2 breakdown        │
│ ⑂ Branch point  │       │ [Chart Widget]          │
│                 │       │                         │
│ User: Continue  │       │ User: [New question]    │
│ in main...      │       │ ...                     │
└─────────────────┘       └─────────────────────────┘
```

#### 3. Conversation Tree Visualization

**Accessed via**: Sidebar icon or keyboard shortcut (Cmd+Shift+T)

**Layout**:
```
┌─ Conversation Tree: Q2 Sales Analysis ─────────────────┐
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │ ● Q2 Sales Analysis (Main)                        │ │
│  │   ├─ Turn 1: User asks for sales data             │ │
│  │   ├─ Turn 2: AI shows chart                       │ │
│  │   │   ├─⑂ Regional Deep Dive (Branch 1)          │ │
│  │   │   │   ├─ Turn 3: North region analysis        │ │
│  │   │   │   └─ Turn 4: Customer segments in North   │ │
│  │   │   │                                            │ │
│  │   │   └─⑂ Customer Segments (Branch 2)           │ │
│  │   │       ├─ Turn 3: Overall segments             │ │
│  │   │       └─ Turn 4: Segment profitability        │ │
│  │   │                                                │ │
│  │   └─ Turn 5: Continue main analysis               │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  [Export Tree] [Collapse All] [Expand All]             │
└─────────────────────────────────────────────────────────┘
```

**Interactions**:
- Click node → Jump to that turn in conversation
- Right-click → Context menu (branch, delete, merge)
- Hover → Show turn preview tooltip
- Drag node → Reorder (if supported)

#### 4. Cross-Conversation References

**User Input Pattern**:
```
User: In conversation "Q2 Sales Analysis", you showed me revenue
growth by region. Can you combine that with the customer churn
data from "HR Analytics" conversation to identify at-risk regions?
```

**AI Detection & Linking**:
```dart
class ConversationReferenceDetector {
  Future<List<ConversationReference>> detectReferences(String userMessage) async {
    // NLP/regex to detect:
    // - "In conversation X"
    // - "From our chat about Y"
    // - "@ConversationName"

    return [
      ConversationReference(
        conversationId: 'uuid-sales',
        conversationName: 'Q2 Sales Analysis',
        referencedTurns: [2, 3], // Turn numbers
      ),
      ConversationReference(
        conversationId: 'uuid-hr',
        conversationName: 'HR Analytics',
        referencedTurns: [5],
      ),
    ];
  }
}
```

**Visual Indicator in Message**:
```
┌─────────────────────────────────────────────────────┐
│ User: In conversation [Q2 Sales ▸] you showed me    │
│ revenue growth. Combine with [HR Analytics ▸] churn │
│ data to identify at-risk regions.                   │
└─────────────────────────────────────────────────────┘
        ↑ Clickable links to referenced conversations

┌─────────────────────────────────────────────────────┐
│ AI: I've analyzed data from both conversations:     │
│                                                      │
│ ┌─ Context Used ────────────────────────────────┐  │
│ │ [Q2 Sales ▸] Turn 2: Regional revenue chart   │  │
│ │ [HR Analytics ▸] Turn 5: Churn by department  │  │
│ └───────────────────────────────────────────────┘  │
│                                                      │
│ At-risk regions (high revenue, high churn):         │
│ [Combined Chart Widget]                             │
│ ...                                                  │
└─────────────────────────────────────────────────────┘
```

#### 5. Multi-Conversation Dashboard

**Accessed via**: Conversations menu → "Dashboard View"

**Layout**:
```
┌─ Active Conversations Dashboard ─────────────────────────────┐
│                                                               │
│ ┌─ Q2 Sales Analysis ────────┐ ┌─ HR Analytics ───────────┐ │
│ │ Last update: 2m ago        │ │ Last update: 15m ago     │ │
│ │ 8 turns                    │ │ 12 turns                 │ │
│ │ 2 branches                 │ │ 1 branch                 │ │
│ │                            │ │                          │ │
│ │ Latest: AI showed chart... │ │ Latest: Churn analysis..│ │
│ │                            │ │                          │ │
│ │ [Continue →]               │ │ [Continue →]             │ │
│ └────────────────────────────┘ └──────────────────────────┘ │
│                                                               │
│ ┌─ Product Roadmap ──────────┐                               │
│ │ Last update: 1h ago        │                               │
│ │ 5 turns                    │                               │
│ │ 0 branches                 │                               │
│ │                            │                               │
│ │ Latest: Feature priorities │                               │
│ │                            │                               │
│ │ [Continue →]               │                               │
│ └────────────────────────────┘                               │
│                                                               │
│ [+ New Conversation]                                          │
└───────────────────────────────────────────────────────────────┘
```

**Benefits**:
- See all active conversations at a glance
- Quick resume from dashboard
- Visual indicators of conversation health (active, stale, needs attention)

---

## Response Verification & Citations

### Cognitive Load Challenge

**Problem**: Enterprise users need to verify AI responses, but traditional citation UIs are overwhelming:
- Long lists of sources break flow
- Academic-style footnotes [1][2][3] require scrolling
- External links force context switching
- Lack of confidence scoring makes triage difficult

**Solution**: Progressive, inline verification with visual hierarchy

### Citation UI Patterns

#### Pattern 1: Collapsed Citation Bar (Default State)

**Visual Design**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased  │
│ by 23% compared to Q1, driven primarily by new      │
│ customer acquisition in the North region.           │
│                                                      │
│ ┌─ Sources ─────────────────────────────────────┐   │
│ │ 3 documents ✓ | Avg confidence: 92% | ⓘ Info  │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
     ↑ Collapsed by default - clean, minimal
```

**Interaction**: Click to expand

#### Pattern 2: Expanded Citation Panel

**Visual Design**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased  │
│ by 23% compared to Q1, driven primarily by new      │
│ customer acquisition in the North region.           │
│                                                      │
│ ┌─ Sources (3) ─────────────────────────────────┐   │
│ │                                               │   │
│ │ ┌─ Q2_Sales_Report.xlsx ──────────── [95%] ─┐ │   │
│ │ │ Page 3, Cell B12                          │ │   │
│ │ │ "Q2 Revenue: $1.23M (+23% vs Q1)"         │ │   │
│ │ │ [View snippet ▸] [Open doc ▸]             │ │   │
│ │ └───────────────────────────────────────────┘ │   │
│ │                                               │   │
│ │ ┌─ Finance_Dashboard.pdf ──────────── [87%] ─┐ │   │
│ │ │ Page 1, Chart 2                           │ │   │
│ │ │ [Growth trend chart showing 23% increase] │ │   │
│ │ │ [View snippet ▸] [Open doc ▸]             │ │   │
│ │ └───────────────────────────────────────────┘ │   │
│ │                                               │   │
│ │ ┌─ DB: sales_quarterly ───────────── [98%] ─┐ │   │
│ │ │ Query: SELECT SUM(revenue) FROM sales...  │ │   │
│ │ │ Result: Q2=$1,230,000 | Q1=$1,000,000     │ │   │
│ │ │ [View query ▸] [Run query ▸]              │ │   │
│ │ └───────────────────────────────────────────┘ │   │
│ │                                               │   │
│ │ [Sort by: Confidence ▼] [Filter ▼]           │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Confidence badges** (color-coded):
   - Green (≥90%): High confidence
   - Yellow (70-89%): Medium confidence
   - Orange (<70%): Low confidence
2. **Snippet preview**: Show relevant excerpt inline
3. **Action buttons**: View full context or open source
4. **Sorting/filtering**: Triage by confidence or source type

#### Pattern 3: Inline Citation Highlighting

**For precise attribution within AI response**:

```
┌─────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased  │
│ by 23%[1] compared to Q1, driven primarily by new   │
│ customer acquisition[2] in the North region[3].     │
│                                                      │
│ ┌─ Citations ───────────────────────────────────┐   │
│ │ [1] Q2_Sales_Report.xlsx (95%) - Page 3       │   │
│ │ [2] Finance_Dashboard.pdf (87%) - Chart 2     │   │
│ │ [3] DB: sales_quarterly (98%) - North region  │   │
│ └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Interaction**:
- Hover over `[1]` → Tooltip shows snippet
- Click `[1]` → Scroll to full citation in panel
- Ctrl+Click `[1]` → Open source document

#### Pattern 4: Snippet Preview Slide-Over

**When user clicks "View snippet"**:

```
┌─ Main Chat ──────────────────┐┌─ Snippet Preview ──────────┐
│ AI: Based on your Q2 sales   ││ Q2_Sales_Report.xlsx       │
│ data, revenue increased...   ││ Page 3 | Confidence: 95%   │
│                              ││                            │
│ [3 sources ▼]                ││ ...context before...       │
│                              ││                            │
│                              ││ ┌────────────────────────┐ │
│                              ││ │ Q2 Revenue: $1.23M     │ │
│                              ││ │ Q1 Revenue: $1.00M     │ │
│                              ││ │ Growth: +23%           │ │
│                              ││ └────────────────────────┘ │
│                              ││      ↑ Highlighted         │
│                              ││                            │
│                              ││ ...context after...        │
│                              ││                            │
│                              ││ [← Back] [Open full doc ▸] │
└──────────────────────────────┘└────────────────────────────┘
                                    ↑ 400px slide-over
```

**Benefits**:
- No context switching (no new tab)
- Shows context around cited snippet
- Highlighting makes relevant info obvious
- Quick close without losing conversation

#### Pattern 5: Confidence Score Visualization

**Visual Treatment**:
```
Confidence Score Bar:
┌─────────────────────────────────────────┐
│ 98% ████████████████████████░ [98%]    │ ← High (Green)
│ 87% ████████████████░░░░░░░░ [87%]    │ ← Medium (Yellow)
│ 72% ████████████░░░░░░░░░░░░ [72%]    │ ← Medium-Low (Orange)
│ 45% ████░░░░░░░░░░░░░░░░░░░░ [45%]    │ ← Low (Red)
└─────────────────────────────────────────┘

Badge Treatment:
[95%] → Green circle badge
[87%] → Yellow circle badge
[72%] → Orange circle badge
[45%] → Red circle badge with ⚠ icon
```

**Sorting by Confidence**:
```
┌─ Sources (5) ─────────────────────────────────┐
│ Sort by: [Confidence (high→low) ▼]           │
│                                               │
│ [98%] DB: sales_quarterly                     │
│ [95%] Q2_Sales_Report.xlsx                    │
│ [87%] Finance_Dashboard.pdf                   │
│ [72%] Email from CFO (March 15)              │
│ [45%] Vendor_Analysis.doc (partial match)    │ ← Warning
│                                               │
│ ⚠ 1 source below 70% confidence threshold    │
└───────────────────────────────────────────────┘
```

#### Pattern 6: Anomaly Detection & Highlighting

**Anomaly Types**:
1. **Conflicting sources**: Two sources contradict each other
2. **Outdated data**: Source is >6 months old
3. **Low confidence**: Source confidence <70%
4. **Unverified claim**: AI statement has no backing source
5. **Partial match**: Source only partially supports claim

**Visual Treatment**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Based on your Q2 sales data, revenue increased  │
│ by 23% compared to Q1, driven primarily by new      │
│ customer acquisition in the North region.           │
│                                                      │
│ ┌─ ⚠ Anomalies Detected (2) ──────────────────┐    │
│ │                                              │    │
│ │ ⚠ Conflicting data:                          │    │
│ │   - Source 1: Revenue +23% [95%]             │    │
│ │   - Source 2: Revenue +19% [78%] ← Differs   │    │
│ │   [View details ▸]                           │    │
│ │                                              │    │
│ │ ⓘ Outdated source:                           │    │
│ │   - Finance_Dashboard.pdf (Last updated:     │    │
│ │     Oct 2024, 12 months ago)                 │    │
│ │   [View details ▸]                           │    │
│ └──────────────────────────────────────────────┘    │
│                                                      │
│ ┌─ Sources (3) ─────────────────────────────┐       │
│ │ [95%] Q2_Sales_Report.xlsx                 │       │
│ │ [78%] ⚠ Q1_Projections.pdf (conflict)      │       │
│ │ [87%] ⓘ Finance_Dashboard (outdated)       │       │
│ └────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────┘
```

**Anomaly Detail View**:
```
┌─ Anomaly Detail: Conflicting Data ──────────────────┐
│                                                      │
│ Claim: "Revenue increased by 23%"                   │
│                                                      │
│ ┌─ Source 1 (Higher confidence) ──── [95%] ─────┐  │
│ │ Q2_Sales_Report.xlsx                           │  │
│ │ Page 3, Cell B12                               │  │
│ │ "Q2 Revenue: $1.23M (+23% vs Q1: $1.00M)"      │  │
│ │ Last updated: Oct 15, 2025 (3 days ago)       │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ Source 2 (Conflicting) ────────── [78%] ─────┐  │
│ │ Q1_Projections.pdf                             │  │
│ │ Page 5, Table 1                                │  │
│ │ "Projected Q2: $1.19M (+19% vs Q1)"            │  │
│ │ Last updated: Jan 10, 2025 (9 months ago)     │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ Recommendation: Source 1 is more recent and has     │
│ higher confidence. The 23% figure is more reliable. │
│                                                      │
│ [Trust Source 1] [Trust Source 2] [Dismiss]         │
└─────────────────────────────────────────────────────┘
```

### Flutter Implementation

```dart
class CitationPanel extends StatefulWidget {
  final List<Citation> citations;
  final bool isExpanded;

  State<CitationPanel> createState() => _CitationPanelState();
}

class _CitationPanelState extends State<CitationPanel> {
  bool _isExpanded = false;
  String _sortBy = 'confidence';

  Widget build(BuildContext context) {
    final avgConfidence = _calculateAvgConfidence(widget.citations);

    return AppCard(
      child: Column(
        children: [
          // Collapsed header
          GestureDetector(
            onTap: () => setState(() => _isExpanded = !_isExpanded),
            child: Row(
              children: [
                Text('Sources', style: AppTypography.labelMedium),
                AppSpacing.gapSm,
                Text('${widget.citations.length} documents ✓'),
                AppSpacing.gapSm,
                Text('Avg confidence: ${avgConfidence.toStringAsFixed(0)}%'),
                Spacer(),
                Icon(_isExpanded ? Icons.expand_less : Icons.expand_more),
              ],
            ),
          ),

          // Expanded content
          if (_isExpanded) ...[
            AppSpacing.gapMd,
            _buildSortControls(),
            AppSpacing.gapMd,

            for (var citation in _sortedCitations())
              _buildCitationCard(citation),
          ],
        ],
      ),
    );
  }

  Widget _buildCitationCard(Citation citation) {
    return AppCard(
      margin: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(citation.sourceName, style: AppTypography.bodyMedium),
              Spacer(),
              _buildConfidenceBadge(citation.confidence),
            ],
          ),
          AppSpacing.gapXs,
          Text(
            citation.location, // "Page 3, Cell B12"
            style: AppTypography.caption.copyWith(color: AppColors.textSecondary),
          ),
          AppSpacing.gapSm,
          AppCard.info(
            message: citation.snippet,
            type: InfoCardType.neutral,
          ),
          AppSpacing.gapSm,
          Row(
            children: [
              AppButton.text(
                label: 'View snippet',
                onPressed: () => _showSnippetSlideOver(citation),
              ),
              AppButton.text(
                label: 'Open doc',
                onPressed: () => _openDocument(citation),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildConfidenceBadge(double confidence) {
    Color color;
    if (confidence >= 0.9) {
      color = AppColors.success;
    } else if (confidence >= 0.7) {
      color = AppColors.warning;
    } else {
      color = AppColors.error;
    }

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color),
      ),
      child: Text(
        '${(confidence * 100).toStringAsFixed(0)}%',
        style: AppTypography.caption.copyWith(
          color: color,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  void _showSnippetSlideOver(Citation citation) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => SnippetPreviewSlideOver(citation: citation),
    );
  }
}
```

---

## Data Source Selection UI

### Conceptual Model

**User Mental Model**: Think of data sources as "search scopes" or "knowledge boundaries"
- **Default**: All sources user has access to (RBAC-filtered)
- **Focused**: User selects specific sources for precision
- **Persistent**: Preferences saved per conversation

### UI Components

#### 1. Data Source Selector (Primary UI)

**Access Points**:
1. Conversation input area (persistent icon)
2. Settings menu → Data Sources
3. Keyboard shortcut: Cmd+Shift+D

**Layout - Collapsed State**:
```
┌─ Chat Input ────────────────────────────────────────┐
│ [📊 4 sources ▼]  Type your message...     [Send →] │
└─────────────────────────────────────────────────────┘
     ↑ Shows active source count
```

**Layout - Expanded State**:
```
┌─ Data Sources ──────────────────────────────────────┐
│ Search sources: [_______________] 🔍                │
│                                                      │
│ ☑ All Sources (12 available)                        │
│                                                      │
│ ┌─ Internal Data ────────────────────────────────┐  │
│ │ ☑ SharePoint (3 sites)                         │  │
│ │   ☑ Marketing Team                             │  │
│ │   ☑ Sales Team                                 │  │
│ │   ☐ HR Team (no access) 🔒                     │  │
│ │                                                 │  │
│ │ ☑ Email (Outlook)                              │  │
│ │ ☑ Calendar                                     │  │
│ │ ☑ Internal Database (CRM)                      │  │
│ └─────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ Uploaded Documents ───────────────────────────┐  │
│ │ ☑ Q2_Sales_Report.xlsx (uploaded 2h ago)       │  │
│ │ ☑ Customer_Feedback.pdf (uploaded 1d ago)      │  │
│ │ [+ Upload more]                                │  │
│ └─────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ External Sources ─────────────────────────────┐  │
│ │ ☐ Web Search (Bing)                            │  │
│ │ ☐ Industry Reports (Gartner)                   │  │
│ └─────────────────────────────────────────────────┘  │
│                                                      │
│ ┌─ Custom Agents ────────────────────────────────┐  │
│ │ ☑ Sales Analytics Agent                        │  │
│ │ ☐ HR Policy Agent (no access) 🔒              │  │
│ └─────────────────────────────────────────────────┘  │
│                                                      │
│ [Reset to Default] [Save Preferences] [Apply]       │
└─────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Hierarchical categories**: Internal/Uploaded/External/Agents
2. **RBAC integration**: Grayed-out sources user can't access with 🔒 icon
3. **Search/filter**: Find sources by name
4. **Nested checkboxes**: Select all SharePoint sites or individual sites
5. **Persistent preferences**: Save as default for this conversation
6. **Visual feedback**: Source count badge updates in real-time

#### 2. Active Sources Indicator

**In conversation UI**:
```
┌─ Active Sources (4) ────────────────────────────────┐
│ • SharePoint: Marketing Team                        │
│ • SharePoint: Sales Team                            │
│ • Q2_Sales_Report.xlsx                              │
│ • Sales Analytics Agent                             │
│                                                      │
│ [Modify sources ▼]                                   │
└─────────────────────────────────────────────────────┘
```

**Compact version (mobile)**:
```
[4 sources active ▼] → Expands to show list
```

#### 3. Source-Specific Permissions UI

**When user hovers over locked source**:
```
┌─ HR Team (SharePoint) 🔒 ───────────────────────────┐
│ You don't have access to this source.               │
│                                                      │
│ Required role: HR Manager or above                  │
│                                                      │
│ [Request Access]                                     │
└─────────────────────────────────────────────────────┘
```

**Request access flow**:
1. User clicks "Request Access"
2. Modal opens with request form (reason, urgency)
3. Request sent to admin/manager
4. User receives notification when approved/denied

#### 4. Smart Source Recommendations

**AI suggests relevant sources based on query**:

```
User types: "What was our customer churn rate in Q2?"

┌─ Suggested Sources ─────────────────────────────────┐
│ Based on your question, you might want to add:      │
│                                                      │
│ • ☐ Internal Database: customer_retention           │
│ • ☐ CRM Analytics Agent                             │
│ • ☐ Email: Support Team (churn feedback)            │
│                                                      │
│ [Add all] [Dismiss]                                  │
└─────────────────────────────────────────────────────┘
```

**Backend implementation** (Python + Kailash SDK):
```python
from kaizen.agents import BaseAgent

class SourceRecommendationAgent(BaseAgent):
    async def recommend_sources(self, user_query: str, available_sources: List[DataSource]):
        # Use NLP to extract intent
        intent = await self._extract_intent(user_query)

        # Match intent to source capabilities
        recommended = []
        for source in available_sources:
            if self._matches_intent(source, intent):
                recommended.append(source)

        return sorted(recommended, key=lambda s: s.relevance_score, reverse=True)[:3]
```

---

## Document Upload & Management

### Upload UI

#### 1. Primary Upload Methods

**Method A: Drag & Drop**
```
┌─ Chat Input Area ───────────────────────────────────┐
│                                                      │
│ ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐ │
│   Drop files here to upload                         │
│   Supported: PDF, XLSX, DOCX, TXT, CSV              │
│ └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘ │
│                                                      │
│ [📎 Attach] Type your message...          [Send →] │
└─────────────────────────────────────────────────────┘
```

**Method B: Click to Upload**
```
User clicks [📎 Attach] button:

┌─ Upload Documents ──────────────────────────────────┐
│                                                      │
│ ┌─ Upload Area ────────────────────────────────┐   │
│ │                                              │   │
│ │           [📄 Click to Browse]               │   │
│ │      or drag and drop files here             │   │
│ │                                              │   │
│ │   Supported formats: PDF, XLSX, DOCX, etc.   │   │
│ │   Max size: 50MB per file                    │   │
│ └──────────────────────────────────────────────┘   │
│                                                      │
│ [Cancel]                                             │
└─────────────────────────────────────────────────────┘
```

#### 2. Upload Progress

**Single file upload**:
```
┌─ Uploading: Q2_Sales_Report.xlsx ───────────────────┐
│ ████████████████░░░░ 72% (3.6 MB / 5.0 MB)          │
│ Estimated time remaining: 4 seconds                 │
│ [Cancel Upload]                                      │
└─────────────────────────────────────────────────────┘
```

**Multiple file upload**:
```
┌─ Uploading 3 files ──────────────────────────────────┐
│ ✓ Q2_Sales_Report.xlsx (5.0 MB) - Complete          │
│ ⏳ Customer_Feedback.pdf (2.1 MB / 3.2 MB) - 65%     │
│ ⏳ Budget_2025.xlsx (queued)                          │
│                                                       │
│ Overall progress: ████████░░░░░░░░ 55%               │
│ [Cancel All]                                          │
└──────────────────────────────────────────────────────┘
```

#### 3. Processing Status

**After upload, AI processes documents for embedding/indexing**:
```
┌─ Processing Documents ───────────────────────────────┐
│ ✓ Q2_Sales_Report.xlsx - Indexed (3 sheets, 450 rows)│
│ ⏳ Customer_Feedback.pdf - Extracting text (Page 12/25)│
│ ⏳ Budget_2025.xlsx - Queued for processing           │
│                                                       │
│ Documents will be available for AI queries once      │
│ processing is complete (~30 seconds remaining).      │
└──────────────────────────────────────────────────────┘
```

### Active Documents UI

#### 1. Document List (Sidebar Panel)

**Access**: Click "📎 Uploaded Docs" in conversation header

**Layout**:
```
┌─ Uploaded Documents (3) ─────────────────────────────┐
│ Search: [_______________] 🔍                          │
│                                                       │
│ ┌─ Q2_Sales_Report.xlsx ──────────── [Active ✓] ───┐ │
│ │ Uploaded: 2 hours ago                            │ │
│ │ Size: 5.0 MB | 3 sheets                          │ │
│ │ Used in: 5 responses                             │ │
│ │ Relevance: ████████░░ 85%                        │ │
│ │ [Preview] [Download] [Remove]                    │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ Customer_Feedback.pdf ─────────── [Active ✓] ───┐ │
│ │ Uploaded: 1 day ago                              │ │
│ │ Size: 3.2 MB | 25 pages                          │ │
│ │ Used in: 2 responses                             │ │
│ │ Relevance: ██████░░░░ 62%                        │ │
│ │ [Preview] [Download] [Remove]                    │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ ┌─ Budget_2025.xlsx ──────────────── [Inactive] ────┐ │
│ │ Uploaded: 3 days ago                             │ │
│ │ Size: 1.8 MB | 2 sheets                          │ │
│ │ Used in: 0 responses                             │ │
│ │ Relevance: ░░░░░░░░░░ 0%                         │ │
│ │ [Activate] [Download] [Remove]                   │ │
│ └──────────────────────────────────────────────────┘ │
│                                                       │
│ [+ Upload More]                                       │
└──────────────────────────────────────────────────────┘
```

**Key Features**:
1. **Active/Inactive toggle**: Control which docs AI can access
2. **Relevance score**: How relevant to current conversation (AI-scored)
3. **Usage tracking**: How many times AI referenced this doc
4. **Quick actions**: Preview, download, remove

#### 2. Document Referenced Indicator

**In AI response**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Based on your uploaded Q2 Sales Report, revenue │
│ increased by 23% compared to Q1.                    │
│                                                      │
│ ┌─ Documents Used ─────────────────────────────┐   │
│ │ 📄 Q2_Sales_Report.xlsx (Page 3, Cell B12)   │   │
│ │ [View in document ▸]                          │   │
│ └───────────────────────────────────────────────┘   │
│                                                      │
│ [3 sources total ▼]                                  │
└─────────────────────────────────────────────────────┘
```

#### 3. Context Window Management

**Problem**: Too many uploaded docs can exceed AI context window.

**Solution**: AI auto-prioritizes relevant docs + user can manually manage.

**UI**:
```
┌─ Context Window ────────────────────────────────────┐
│ ████████████████████░░░░░░ 75% of 128K token limit  │
│                                                      │
│ ┌─ Active Documents (by token usage) ─────────────┐ │
│ │ 📄 Q2_Sales_Report.xlsx → 35K tokens (44%)      │ │
│ │ 📄 Customer_Feedback.pdf → 18K tokens (23%)     │ │
│ │ 💬 Conversation history → 8K tokens (10%)       │ │
│ │ 📊 System prompt → 2K tokens (3%)               │ │
│ │                                                  │ │
│ │ Available: 65K tokens (remaining)                │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ⚠ Warning: Adding Budget_2025.xlsx (45K tokens)     │
│ will exceed context window. Consider removing a doc. │
│                                                      │
│ [Smart prioritize] [Manual select]                   │
└─────────────────────────────────────────────────────┘
```

**Smart Prioritization**:
- AI analyzes user query → Scores documents by relevance
- Top 3-5 most relevant docs included automatically
- Rest excluded from context (but still available if user manually adds)

---

## Visual Response Components

### Component Types

#### 1. Charts (Interactive)

**Supported Chart Types**:
- Bar charts (grouped, stacked, horizontal)
- Line charts (single/multi-series, area)
- Pie/donut charts
- Scatter plots
- Combo charts (bar + line)
- Heatmaps
- Gantt charts (for timelines)

**Example - Interactive Bar Chart**:
```dart
class InteractiveBarChart extends StatefulWidget {
  final ChartWidgetDescriptor descriptor;

  Widget build(BuildContext context) {
    return GestureDetector(
      onTapDown: (details) {
        // Detect which bar was tapped
        final barIndex = _getBarIndexFromPosition(details.localPosition);
        _showDrillDown(barIndex);
      },
      child: CustomPaint(
        painter: BarChartPainter(descriptor.data),
        size: Size(double.infinity, 300),
      ),
    );
  }

  void _showDrillDown(int barIndex) {
    // Show detailed data for this bar
    showModalBottomSheet(
      context: context,
      builder: (context) => DrillDownPanel(
        region: descriptor.data.labels[barIndex],
        value: descriptor.data.values[barIndex],
      ),
    );
  }
}
```

#### 2. Tables (Sortable, Filterable)

**Features**:
- Column sorting (ascending/descending)
- Row filtering
- Column toggling (show/hide)
- Row selection (single/multi)
- Pagination
- Export (CSV, XLSX)

**Example - Data Table**:
```dart
class InteractiveDataTable extends StatefulWidget {
  final TableWidgetDescriptor descriptor;

  State createState() => _InteractiveDataTableState();
}

class _InteractiveDataTableState extends State<InteractiveDataTable> {
  String _sortColumn = 'name';
  bool _sortAsc = true;
  Set<int> _selectedRows = {};

  Widget build(BuildContext context) {
    return Column(
      children: [
        // Toolbar
        Row(
          children: [
            Text('${_selectedRows.length} selected'),
            Spacer(),
            AppButton.text(
              label: 'Export CSV',
              onPressed: _exportCSV,
            ),
          ],
        ),

        // Table
        AppDataTable(
          columns: widget.descriptor.data.columns.map((col) {
            return DataColumn(
              label: Text(col.label),
              onSort: col.sortable ? (colIndex, asc) {
                setState(() {
                  _sortColumn = col.key;
                  _sortAsc = asc;
                });
              } : null,
            );
          }).toList(),
          rows: _getSortedRows(),
          sortColumnIndex: _getSortColumnIndex(),
          sortAscending: _sortAsc,
        ),
      ],
    );
  }
}
```

#### 3. Collapsible Sections

**Use case**: Hide long content by default, expand on demand.

**Example**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Here's a detailed analysis of your sales data.  │
│                                                      │
│ ▸ Executive Summary (click to expand)               │
│                                                      │
│ ▾ Regional Breakdown (expanded)                     │
│   North: $450K (+34% vs Q1)                         │
│   South: $380K (+18% vs Q1)                         │
│   East: $290K (+12% vs Q1)                          │
│   West: $110K (-5% vs Q1)                           │
│                                                      │
│ ▸ Customer Segmentation (click to expand)           │
│                                                      │
│ ▸ Product Performance (click to expand)             │
└─────────────────────────────────────────────────────┘
```

**Flutter Implementation**:
```dart
class CollapsibleSection extends StatefulWidget {
  final String title;
  final Widget content;
  final bool initiallyExpanded;

  State createState() => _CollapsibleSectionState();
}

class _CollapsibleSectionState extends State<CollapsibleSection> {
  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();
    _isExpanded = widget.initiallyExpanded;
  }

  Widget build(BuildContext context) {
    return Column(
      children: [
        GestureDetector(
          onTap: () => setState(() => _isExpanded = !_isExpanded),
          child: Row(
            children: [
              Icon(_isExpanded ? Icons.expand_more : Icons.chevron_right),
              AppSpacing.gapSm,
              Text(widget.title, style: AppTypography.h4),
            ],
          ),
        ),

        if (_isExpanded) ...[
          AppSpacing.gapMd,
          widget.content,
        ],
      ],
    );
  }
}
```

#### 4. Tooltips for Technical Terms

**Use case**: Explain jargon without cluttering the response.

**Example**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Your CAGR[ⓘ] for Q2 was 23%, indicating strong  │
│ growth momentum. The NPS[ⓘ] score increased to 72.  │
└─────────────────────────────────────────────────────┘

Hover over [ⓘ]:
┌─ CAGR ──────────────────────────┐
│ Compound Annual Growth Rate     │
│ Measures the mean annual growth │
│ rate over a specified period.   │
└─────────────────────────────────┘
```

**Flutter Implementation**:
```dart
class TermWithTooltip extends StatelessWidget {
  final String term;
  final String definition;

  Widget build(BuildContext context) {
    return Tooltip(
      message: definition,
      preferBelow: false,
      padding: AppSpacing.allMd,
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(8),
        boxShadow: [AppShadows.elevated],
      ),
      textStyle: AppTypography.bodySmall,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(term, style: AppTypography.bodyMedium),
          SizedBox(width: 4),
          Icon(Icons.info_outline, size: 16, color: AppColors.primary),
        ],
      ),
    );
  }
}
```

#### 5. Images & Videos

**Use case**: AI references images/videos from documents or generates diagrams.

**Example - Image Embed**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Here's the process flow diagram from page 5:    │
│                                                      │
│ ┌─ Process_Flow_Diagram.png ──────────────────────┐ │
│ │ [Image: 800x600px diagram showing 5-step flow]  │ │
│ │ Source: Q2_Roadmap.pdf (Page 5)                  │ │
│ │ [View full size ▸] [Download ▸]                  │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**Example - Video Embed**:
```
┌─────────────────────────────────────────────────────┐
│ AI: Here's the product demo video:                  │
│                                                      │
│ ┌─ Product_Demo_Q2.mp4 ────────────────────────────┐ │
│ │ [▶ Play] [🔊] [⚙ Settings] Duration: 3:24       │ │
│ │ Source: SharePoint > Marketing > Videos          │ │
│ └──────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

---

## Information Architecture

### Site Map

```
Enterprise AI Hub
├─ Login (SSO)
├─ Dashboard (Home)
│  ├─ Active Conversations (cards)
│  ├─ Recent Activity (timeline)
│  ├─ Quick Actions (+ New Chat, Upload Docs, etc.)
│  └─ Insights (usage stats, trending topics)
│
├─ Conversations (Main App)
│  ├─ Sidebar Navigation
│  │  ├─ Active Conversations
│  │  ├─ Recent Conversations
│  │  ├─ Starred Conversations
│  │  └─ [+ New Conversation]
│  │
│  ├─ Conversation View (Center)
│  │  ├─ Header (title, branch indicator, settings)
│  │  ├─ Message Stream (scrollable)
│  │  │  ├─ User messages
│  │  │  ├─ AI responses (text + widgets)
│  │  │  ├─ Citations
│  │  │  └─ Turn-level actions (branch, copy, regenerate)
│  │  └─ Input Area
│  │     ├─ Data source selector
│  │     ├─ Uploaded docs indicator
│  │     ├─ Text input (with mention/commands)
│  │     └─ Send button
│  │
│  └─ Right Panel (Contextual)
│     ├─ Active Data Sources
│     ├─ Uploaded Documents
│     ├─ Conversation Tree (when branched)
│     └─ Settings
│
├─ Data Sources (Settings)
│  ├─ Available Sources (list)
│  ├─ Configure Sources (API keys, permissions)
│  └─ Usage Analytics (which sources used most)
│
├─ Uploaded Documents (Library)
│  ├─ All Uploaded Docs (table view)
│  ├─ Search & Filter
│  ├─ Bulk Actions (delete, export)
│  └─ Storage Usage
│
├─ Admin Panel (Admin only)
│  ├─ User Management
│  │  ├─ Users List
│  │  ├─ Roles & Permissions (RBAC)
│  │  └─ Access Logs (audit trail)
│  │
│  ├─ Data Source Management
│  │  ├─ Configure Available Sources
│  │  ├─ Set RBAC Policies per Source
│  │  └─ Source Health Monitoring
│  │
│  ├─ AI Agent Management
│  │  ├─ Available Agents List
│  │  ├─ Agent Permissions (RBAC)
│  │  ├─ Agent Performance Metrics
│  │  └─ Agent Configuration
│  │
│  ├─ Governance & Compliance
│  │  ├─ Data Governance Policies
│  │  ├─ AI Model Explainability Dashboard
│  │  ├─ Audit Logs (all AI interactions)
│  │  └─ Compliance Reports (ISO 42001, GDPR)
│  │
│  └─ Analytics
│     ├─ Usage Statistics (conversations, queries, sources)
│     ├─ Performance Metrics (response time, accuracy)
│     └─ Cost Analysis (token usage, API calls)
│
└─ Settings (User Profile)
   ├─ Profile Information
   ├─ Preferences (theme, notifications, defaults)
   ├─ API Keys (personal integrations)
   └─ Privacy Settings
```

### Screen-Level Information Architecture

#### Dashboard (Home)

**Priority Hierarchy** (top to bottom):
```
┌────────────────────────────────────────────────────┐
│ HEADER: Logo, Search, Profile                     │ ← Global nav
├────────────────────────────────────────────────────┤
│ HERO: Quick Actions                               │ ← Primary CTA
│ [+ New Conversation] [Upload Document] [Search]   │
├────────────────────────────────────────────────────┤
│ SECTION 1: Active Conversations (3-4 cards)       │ ← Most important
│ [Card 1] [Card 2] [Card 3] [+ View All →]         │
├────────────────────────────────────────────────────┤
│ SECTION 2: Insights (metrics, trends)             │ ← Secondary
│ [Total Queries: 234] [Avg Response Time: 1.2s]    │
├────────────────────────────────────────────────────┤
│ SECTION 3: Recent Activity (timeline)             │ ← Tertiary
│ [Timeline of recent interactions]                 │
└────────────────────────────────────────────────────┘
```

**Responsive Behavior**:
- **Desktop**: 3-column grid for conversation cards
- **Tablet**: 2-column grid
- **Mobile**: Single column, stacked sections

#### Conversation View (Main App)

**Layout Proportions** (Desktop):
```
┌─────────────────────────────────────────────────────────────┐
│ APP BAR (60px height)                                       │
├───────┬───────────────────────────────────┬─────────────────┤
│       │                                   │                 │
│ SIDE  │ CONVERSATION VIEW (60%)           │ RIGHT PANEL     │
│ BAR   │ - Message stream                  │ (25%)           │
│ (15%) │ - Input area                      │ - Active sources│
│       │                                   │ - Uploaded docs │
│ 240px │ Flexible width (grows/shrinks)    │ - Tree view     │
│       │                                   │ 300px           │
│       │                                   │ (collapsible)   │
└───────┴───────────────────────────────────┴─────────────────┘
```

**Responsive Behavior**:
- **Tablet**: Right panel becomes bottom sheet (slide up from bottom)
- **Mobile**: Sidebar becomes hamburger menu, right panel = bottom sheet

---

## Cognitive Load Management

### Strategies to Reduce Overload

#### Strategy 1: Progressive Disclosure (Already Discussed)
- Start with minimal UI, expand on demand
- Don't show all sources/citations by default

#### Strategy 2: Visual Grouping (Gestalt Principles)
**Group related elements using proximity, color, borders**

Example:
```
GOOD:
┌─ AI Response ──────────────────────────────────────┐
│ Revenue increased by 23%...                        │
│                                                     │
│ ┌─ Evidence ────────────────────────────────────┐  │
│ │ [3 sources ▼] [Confidence: 95%] [✓ Verified]  │  │
│ └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
   ↑ Grouped evidence UI reduces visual clutter

BAD:
┌─────────────────────────────────────────────────────┐
│ Revenue increased by 23%...                         │
│ [Source 1] [Source 2] [Source 3]                    │ ← Scattered
│ Confidence: 95% | Verified: Yes | Date: Oct 18      │
└─────────────────────────────────────────────────────┘
```

#### Strategy 3: Defer Non-Essential Information
**Show only what user needs NOW, defer the rest**

Example:
```
IMMEDIATE NEED:
┌─────────────────────────────────────────────────────┐
│ AI: Revenue increased by 23%.                       │
│ [3 sources ▼]                                        │
└─────────────────────────────────────────────────────┘

DEFERRED (click to see):
┌─────────────────────────────────────────────────────┐
│ AI: Revenue increased by 23%.                       │
│                                                      │
│ ┌─ Sources (3) ───────────────────────────────────┐ │
│ │ [Full citation details]                         │ │
│ └─────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ Methodology ───────────────────────────────────┐ │
│ │ How AI calculated this...                       │ │
│ └─────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ Related Insights ──────────────────────────────┐ │
│ │ Other findings...                               │ │
│ └─────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

#### Strategy 4: Use Visual Hierarchy (Size, Color, Position)
**Make important elements visually dominant**

```
HIGH IMPORTANCE (Large, Bold, Top):
┌─────────────────────────────────────────────────────┐
│ Revenue increased by 23%  ← H3, 20px, bold         │
│                                                      │
│ Supporting detail text...  ← Body, 14px, regular    │
│                                                      │
│ [View details ▸]  ← Small, 12px, text button        │
└─────────────────────────────────────────────────────┘
```

#### Strategy 5: Limit Choices (Hick's Law)
**More options = slower decisions = higher cognitive load**

**Bad**: 15 filter options visible at once
**Good**: 3-5 most common filters visible + "Advanced filters" button

Example:
```
GOOD:
┌─ Filters ──────────────────────────────────────────┐
│ Date: [Last 30 days ▼]                             │
│ Source: [All ▼]                                     │
│ Confidence: [All ▼]                                 │
│ [+ Advanced filters]  ← Hides 10 more options      │
└─────────────────────────────────────────────────────┘

BAD:
┌─ Filters ──────────────────────────────────────────┐
│ Date: [___]                                         │
│ Source: [___]                                       │
│ Confidence: [___]                                   │
│ Region: [___]                                       │
│ Department: [___]                                   │
│ Agent: [___]                                        │
│ ... (9 more filters)                                │ ← Overwhelming
└─────────────────────────────────────────────────────┘
```

#### Strategy 6: Smart Defaults
**Pre-select the most common options**

Examples:
- Data sources → Default to "All sources (RBAC-filtered)"
- Confidence filter → Default to "All" (don't force filtering)
- Date range → Default to "Last 30 days" (not "All time")

#### Strategy 7: Inline Help & Contextual Guidance
**Provide help exactly when/where needed**

Example:
```
┌─ Upload Documents ──────────────────────────────────┐
│ [Drag & Drop Area]                                  │
│                                                      │
│ ⓘ Tip: PDFs and Excel files are usually the most    │
│ useful for AI analysis. Scanned documents need OCR. │
│                                                      │
│ [Browse Files]                                       │
└─────────────────────────────────────────────────────┘
```

### NASA TLX Evaluation (Target Scores)

**NASA Task Load Index** - Standard cognitive load measurement:
1. **Mental Demand**: 4/10 (moderate)
2. **Physical Demand**: 2/10 (very low - mostly clicking)
3. **Temporal Demand**: 3/10 (not time-pressured)
4. **Performance**: 8/10 (high success rate)
5. **Effort**: 4/10 (moderate effort)
6. **Frustration**: 2/10 (very low)

**Overall Target**: < 4/10 (low cognitive load)

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
**Goal**: Basic conversation UI with text responses

**Deliverables**:
- [ ] Dashboard (home page with active conversations)
- [ ] Conversation sidebar (list of conversations)
- [ ] Conversation view (message stream + input)
- [ ] Basic AI responses (text + markdown)
- [ ] Data source selector (basic version)
- [ ] Document upload UI (basic)

**Dependencies**:
- Backend: Kailash SDK + Nexus API for streaming
- Frontend: Flutter design system components
- Database: DataFlow models for conversations, messages, sources

**Acceptance Criteria**:
- User can create new conversation
- User can send message and receive AI response (text)
- User can select data sources before querying
- User can upload documents

---

### Phase 2: Interactive Widgets (Weeks 3-4)
**Goal**: Embed interactive widgets in AI responses

**Deliverables**:
- [ ] Widget descriptor format (JSON spec)
- [ ] Backend: Widget generator (Python)
- [ ] Frontend: Widget renderer (Flutter)
- [ ] Chart widget (bar, line, pie)
- [ ] Table widget (sortable, filterable)
- [ ] Form widget (with validation)
- [ ] Navigation card widget

**Dependencies**:
- Phase 1 complete
- fl_chart package (Flutter)
- Kailash SDK: AI agents for widget generation

**Acceptance Criteria**:
- AI can generate chart widgets from data
- User can interact with charts (tap, drill down)
- User can sort/filter tables
- User can submit forms embedded in responses

---

### Phase 3: Citations & Verification (Weeks 5-6)
**Goal**: Full response verification with citations

**Deliverables**:
- [ ] Citation panel (collapsed/expanded states)
- [ ] Confidence score visualization
- [ ] Snippet preview slide-over
- [ ] Inline citation highlighting
- [ ] Anomaly detection UI
- [ ] Source conflict resolution

**Dependencies**:
- Phase 1 complete
- Backend: Citation extraction (Kailash agents)
- Backend: Confidence scoring (ML model)

**Acceptance Criteria**:
- Every AI response shows source count + avg confidence
- User can expand to see full citation details
- User can preview snippets without leaving conversation
- User is warned of conflicting sources or low confidence

---

### Phase 4: Multi-Conversation Workflow (Weeks 7-8)
**Goal**: Support conversation branching and cross-referencing

**Deliverables**:
- [ ] Turn-level branching UI
- [ ] Conversation tree visualization
- [ ] Cross-conversation reference detection
- [ ] Conversation dashboard (multi-view)
- [ ] Context sharing between conversations

**Dependencies**:
- Phase 1 complete
- Backend: Conversation graph structure (DataFlow)
- Backend: Context merging logic (Kailash agents)

**Acceptance Criteria**:
- User can branch from any conversation turn
- User can view conversation tree
- AI can detect and link cross-conversation references
- User can work on multiple conversations simultaneously

---

### Phase 5: Advanced Features (Weeks 9-10)
**Goal**: Polish and advanced capabilities

**Deliverables**:
- [ ] Smart source recommendations
- [ ] Context window management UI
- [ ] Collapsible sections
- [ ] Tooltips for technical terms
- [ ] Image/video embed support
- [ ] Keyboard shortcuts
- [ ] Command palette (Cmd+K)

**Dependencies**:
- Phases 1-4 complete

**Acceptance Criteria**:
- AI suggests relevant sources based on query
- User is warned when approaching context limit
- User can collapse long sections
- User can hover terms for definitions
- User can use keyboard shortcuts for common actions

---

### Phase 6: Admin & Governance (Weeks 11-12)
**Goal**: Admin panel and compliance features

**Deliverables**:
- [ ] User management (RBAC)
- [ ] Data source management (admin)
- [ ] AI agent management (admin)
- [ ] Audit logs (all interactions)
- [ ] Compliance dashboard (ISO 42001, GDPR)
- [ ] Usage analytics

**Dependencies**:
- All previous phases complete
- Backend: Admin API (Nexus)
- Backend: Audit trail (DataFlow)

**Acceptance Criteria**:
- Admin can manage users and roles
- Admin can configure data sources and permissions
- Admin can view audit logs
- Compliance reports can be generated

---

## Next Steps

1. **Review this document** with stakeholders (product, engineering, compliance)
2. **Create detailed mockups** for each phase (Figma/Adobe XD)
3. **Validate with users** (usability testing on mockups)
4. **Refine specifications** based on feedback
5. **Begin Phase 1 implementation** with flutter-specialist and dataflow-specialist

---

**Document Version**: 1.0
**Created**: 2025-10-18
**Next Review**: After Phase 1 completion
**Maintainer**: UI/UX Designer Agent
