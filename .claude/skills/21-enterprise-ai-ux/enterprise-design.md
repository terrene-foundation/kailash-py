# Enterprise AI Hub - UI/UX Design Specifications

## Design Principles

### 1. Progressive Disclosure

Show essentials by default, reveal details on demand.

```
DEFAULT: "AI: Revenue increased 23%. [3 sources v]"
EXPANDED: Full citation panel with confidence scores, snippets, source links
```

### 2. Inline Verification

Verify without leaving conversation -- slide-over previews, hover tooltips, embedded page viewers.

### 3. Visual Hierarchy for Responses

| Response Type  | Confidence | Visual                      |
| -------------- | ---------- | --------------------------- |
| Direct answer  | >=90%      | Green accent, checkmark     |
| Analysis       | 70-89%     | Yellow accent, warning icon |
| Low confidence | <70%       | Orange accent, info icon    |
| Action item    | N/A        | Blue accent, play icon      |

### 4. Contextual Widget Integration

Widgets render inline in conversation flow with action buttons. No context switching.

### 5. Conversation Branching as First-Class

Git-style branching: visual tree, turn-level fork indicators, cross-conversation references.

## Interactive Widget Response System

### Widget Descriptor Format

```json
{
  "type": "widget",
  "widget_type": "chart|table|form|card|navigation|custom",
  "widget_id": "uuid-v4",
  "data": {},
  "config": {},
  "actions": [{"action_id": "uuid", "label": "View Details", "type": "navigate|api_call|dialog|download", "params": {}}],
  "metadata": {"sources": [...], "confidence": 0.95, "generated_at": "ISO-8601"}
}
```

### Widget Types

**Chart**: `chart_type` (bar|line|pie|scatter|combo), `series` [{name, values, labels}], axis labels, title. Config: interactive, export_formats, drill_down_enabled.

**Table**: `columns` [{key, label, sortable, filterable, format}], `rows`, `pagination` {page, per_page, total}. Config: selectable_rows, exportable, filterable.

**Form**: `form_id`, `fields` [{field_id, type, label, placeholder, required, validation}], submit_button_label. Config: auto_submit, preserve_state.

**Navigation Card**: `cards` [{title, description, icon, badge, badge_color}] with navigate actions.

### Rendering Pipeline

```python
# 1. Backend: AI agent generates widget descriptor
class DashboardAgent(BaseAgent):
    async def generate_chart_response(self, user_query: str):
        sales_data = await self._fetch_sales_data()
        return {"type": "widget", "widget_type": "chart", "data": {"chart_type": "bar", "series": [sales_data]}}

# 2. Stream via Nexus WebSocket/SSE
@nexus.stream_endpoint("/ai/chat")
async def chat_stream(session_id: str, message: str):
    async for chunk in agent.stream_response(message):
        yield {"type": "text", "content": chunk}
    widget = await agent.generate_chart_response(message)
    yield {"type": "widget", "content": widget}
```

```dart
// 3. Flutter renders from descriptor
Widget _buildWidget(WidgetDescriptor descriptor) {
  switch (descriptor.widgetType) {
    case 'chart': return ChartWidget(descriptor: descriptor);
    case 'table': return DataTableWidget(descriptor: descriptor);
    case 'form':  return FormWidget(descriptor: descriptor);
    case 'navigation_card': return NavigationCardWidget(descriptor: descriptor);
  }
}
```

### Widget State Management (3 tiers)

| Tier           | Scope      | Tool                  | Example                   |
| -------------- | ---------- | --------------------- | ------------------------- |
| Widget-local   | Transient  | `StatefulWidget`      | Selected bar, hover state |
| Conversation   | Session    | `Provider`/`Riverpod` | Active sources, filters   |
| Backend-synced | Persistent | WebSocket + backend   | Form submissions          |

### Performance

- **Lazy rendering**: `ListView.builder` + `VisibilityDetector`
- **Widget caching**: Cache by `widget_id`
- **Isolate offload**: Background compute for heavy chart data

## Multi-Conversation Workflow

### Sidebar Layout

```
CONVERSATIONS
[+ New Chat]
Active (3):
  * Q2 Sales Analysis
    |- Regional Breakdown (branch)
    |- Customer Segments (branch)
  o HR Policy Questions
  o Product Roadmap Review
Recent (5): collapsible
Starred (2): collapsible
```

Visual hierarchy: Active (bold, colored dot) > Recent > Starred. Branches indented with fork icon.

### Turn-Level Branching

Hover message -> [Branch from here] -> Name branch, choose context inheritance -> Creates independent branch conversation. Main conversation unchanged.

### Conversation Tree

Git-style graph: click node to jump, hover for preview, right-click for context menu (branch, merge, delete). Collapse/expand controls. Focus mode shows current lineage only.

### Cross-Conversation References

User types "In conversation X, you showed..." -> AI detects references via NLP -> Clickable links in message -> AI fetches context from referenced turns -> Combined analysis with source attribution.

## Response Verification & Citations

### Citation Patterns

**Collapsed bar** (default): `"3 documents | Avg confidence: 92%"` -- click to expand.

**Expanded panel**: Each source shows name, confidence badge (green/yellow/orange), location, snippet preview, action buttons (View snippet, Open doc).

**Inline highlighting**: `"revenue increased by 23%[1]"` -- hover for tooltip, click to scroll to citation.

**Snippet slide-over**: 400px panel shows source context around cited text with highlighting. No tab switching.

### Confidence Visualization

| Score  | Color      | Icon      |
| ------ | ---------- | --------- |
| >=90%  | Green      | Checkmark |
| 70-89% | Yellow     | Warning   |
| <70%   | Orange/Red | Alert     |

### Anomaly Detection

Types: conflicting sources, outdated data (>6 months), low confidence (<70%), unverified claims, partial matches. Visual: warning panel with comparison view and AI recommendation on which source to trust.

```dart
class CitationPanel extends StatefulWidget {
  // Collapsed: source count + avg confidence
  // Expanded: sorted citation cards with confidence badges, snippets, action buttons
  Widget _buildConfidenceBadge(double confidence) {
    Color color = confidence >= 0.9 ? AppColors.success
                : confidence >= 0.7 ? AppColors.warning : AppColors.error;
    // Badge with percentage text
  }
}
```

## Data Source Selection

### Selector UI

Collapsed: `"[4 sources v] Type your message... [Send]"` in chat input area.

Expanded: hierarchical checkboxes by category:

- **Internal Data**: SharePoint (nested sites), Email, Calendar, CRM
- **Uploaded Documents**: with upload timestamps
- **External Sources**: Web Search, Industry Reports
- **Custom Agents**: RBAC-filtered with lock icons

Key features: RBAC integration (locked sources with request access), nested checkboxes, persistent preferences per conversation, search/filter, real-time badge count.

### Smart Source Recommendations

AI suggests relevant sources based on query intent. Backend agent scores available sources by relevance.

## Document Upload & Management

### Upload Flow

- Drag & drop or click to browse (PDF, XLSX, DOCX, TXT, CSV, max 50MB)
- Progress bar per file + overall progress
- Processing status: indexing/extracting/queued

### Active Documents Panel

Per document: active/inactive toggle, relevance score, usage count, preview/download/remove actions.

### Context Window Management

```
[============================------] 75% of 128K tokens
Active Documents (by token usage):
  Sales_Report.xlsx -> 35K (44%)
  Feedback.pdf -> 18K (23%)
  Conversation history -> 8K (10%)
Warning: Adding Budget.xlsx (45K) will exceed limit.
[Smart prioritize] [Manual select]
```

## Visual Response Components

### Charts (Interactive)

Types: bar (grouped/stacked), line (single/multi), pie/donut, scatter, combo, heatmap, Gantt. Tap bar for drill-down via `showModalBottomSheet`.

### Tables (Sortable, Filterable)

Column sorting, row filtering, column toggle, row selection, pagination, export (CSV/XLSX).

### Collapsible Sections

Expandable content blocks with arrow indicators. Default collapsed for long analyses.

### Tooltips for Technical Terms

Hover info icon next to jargon (CAGR, NPS) shows plain-language definition.

## Information Architecture

```
Enterprise AI Hub
+- Dashboard (active conversations, recent activity, quick actions, insights)
+- Conversations (sidebar + message stream + right panel: sources, docs, tree)
+- Data Sources (available, configure, analytics)
+- Uploaded Documents (library, search, bulk actions, storage)
+- Admin Panel (users/RBAC, source management, agent management, governance/compliance, analytics)
+- Settings (profile, preferences, API keys, privacy)
```

### Conversation View Layout (Desktop)

```
[Sidebar 15% 240px] [Conversation 60% flexible] [Right Panel 25% 300px collapsible]
```

Tablet: right panel becomes bottom sheet. Mobile: sidebar becomes hamburger, right panel = bottom sheet.

## Cognitive Load Management

| Strategy                   | Application                                                       |
| -------------------------- | ----------------------------------------------------------------- |
| Progressive disclosure     | Start minimal, expand on demand                                   |
| Visual grouping            | Group evidence UI (sources + confidence + verified)               |
| Defer non-essential        | Show answer first, methodology/related insights behind click      |
| Visual hierarchy           | H3 bold for key findings, body for detail, small text for actions |
| Limit choices (Hick's Law) | 3-5 visible filters + "Advanced filters" button                   |
| Smart defaults             | All sources, All confidence, Last 30 days                         |
| Inline help                | Contextual tips exactly where needed                              |

**NASA TLX target**: Mental 4/10, Physical 2/10, Temporal 3/10, Performance 8/10, Effort 4/10, Frustration 2/10. Overall <4/10.
