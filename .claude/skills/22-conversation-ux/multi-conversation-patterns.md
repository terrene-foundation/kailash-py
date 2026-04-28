# Multi-Conversation UX Patterns

## Core Concept

Conversations as Git branches: main thread = main branch, turn-level branching = feature branches, context inheritance = fork with history, cross-conversation references = cherry-pick context.

## Conversation List UX

### Sidebar Layout (Desktop 240px)

```
CONVERSATIONS [Search] [+ New] [Settings]
Active (3):
  * Q2 Sales Analysis (blue dot, bold)
    |- Regional Breakdown (branch, indented)
    |- Customer Segments (branch)
  o HR Policy Questions (gray dot)
  o Product Roadmap Review
    |- Feature Prioritization
Recent (5): collapsible
Starred (2): collapsible
[Archived (12)] [Trash (3)]
```

### Status Indicators

| Status   | Color  | Condition             |
| -------- | ------ | --------------------- |
| Active   | Blue   | Viewing or edited <1h |
| Recent   | Green  | Edited <24h           |
| Stale    | Orange | 1-7 days              |
| Inactive | Gray   | >7 days               |
| Archived | Muted  | User-archived         |

### Organization

- **Folders**: Optional grouping (Sales Team, HR & Compliance)
- **Tags**: User-created (#finance, #urgent) + AI-suggested. Click to filter.
- **Search**: Full-text with snippet preview, jump-to-turn, filters (date, tags, sources, confidence)

### Quick Actions (right-click/long-press)

Rename, Star, Move to folder, Add tags, Duplicate, Export (PDF/MD/JSON), Share, Archive, Delete.

### Keyboard Shortcuts

`Cmd+N` new, `Cmd+K` search, `Cmd+Shift+S` star, `Cmd+E` export, `Cmd+1-9` jump to conversation, `Cmd+Backspace` archive.

## Turn-Level Branching

### Mental Model

Main conversation = main branch. Branch point = specific turn. Branch inherits all context up to that point. Main conversation unchanged.

### Desktop: Hover to Branch

1. **Hover message** -> Quick actions appear: [Branch from here] [Copy] [Regenerate]
2. **Click Branch** -> Dialog: branch name, context preview, options (inherit sources, inherit docs)
3. **Branch created** -> Sidebar shows nested branch under parent, new conversation opens

### Mobile: Long-Press to Branch

1. Long-press message -> Action sheet: Branch, Copy, Regenerate, Share
2. Tap "Branch from here" -> Name + options bottom sheet
3. Branch created -> Opens in full screen

### Branch Header

```
[fork icon] Regional Deep Dive
  Branched from: Q2 Sales Analysis (Turn 2)
  [Back to parent] [View tree]
```

### Branch Data Model

```typescript
interface ConversationBranch {
  id: string;
  parentConversationId: string;
  branchPointTurnId: string;
  branchName: string;
  createdAt: Date;
  inheritedContext: {
    turns: Turn[];
    dataSources: DataSource[];
    uploadedDocs: Document[];
  };
  divergenceCount: number;
}
```

## Conversation Tree Visualization

### Design Principles

- Git-style graph with nodes (conversations) and edges (branches)
- Click node to jump, hover for preview, right-click for context menu
- Collapse/expand, focus mode (current lineage only)

### Access

Click tree icon in header, or `Cmd+Shift+T`. Auto-open when 2+ branches exist.

### Full Tree View

```
Conversation Tree: Q2 Sales Analysis
[Collapse All] [Expand All] [Focus Current] [Export]

* Q2 Sales Analysis (Main)
  |- Turn 1: User asks for sales data
  |- Turn 2: AI shows chart <-- YOU ARE HERE
  |   |- [branch] Regional Deep Dive (Active, 5 turns)
  |   |- [branch] Customer Segments (Active, 4 turns)
  |- Turn 3: Continue main analysis
  |- Turn 4: Forecast Q3
```

### Compact Tree (Sidebar)

```
* Main (4 turns)
  |- Regional (5 turns) <-- Active
  |- Segments (4 turns)
[Expand]
```

### Node Styles

| Node Type            | Visual               |
| -------------------- | -------------------- |
| Current conversation | Blue border, bold    |
| Other active         | Gray border, regular |
| Main/parent          | Green border, bold   |
| Inactive             | Light gray, faded    |

Connection lines: Solid = active, Dotted = inactive, Thick = current lineage. Auto-assigned colors per branch.

### Interactions

- **Click** -> Jump to conversation
- **Hover** -> Preview: created date, turn count, last message snippet
- **Right-click** -> Open, Open in new window, Branch, Merge, Rename, Delete
- **Collapse All** -> Show only branch names with [+] expanders
- **Focus Mode** -> Show only current branch lineage

### Mobile Tree

Bottom sheet with touch-friendly nodes. Tap to open, long-press for context menu, pinch to zoom, swipe to pan.

## Cross-Conversation Context

### Reference Detection

```python
class ConversationReferenceDetector(BaseAgent):
    """Detects patterns: 'In conversation X', 'From our chat about Y', '@ConversationName'"""
    async def detect(self, user_message: str, user_conversations: List[dict]):
        result = await self.execute(user_message=user_message,
                                     available_conversations=user_conversations)
        return result.references
        # Returns: [{conversation_id, conversation_name, referenced_context}]
```

### Visual Treatment

User message: clickable links `[Q2 Sales >]` to referenced conversations.

AI response: "Context Used" panel showing which turns from which conversations were used, with "View source conversations" link.

### Manual Context Selection

"Add context from..." button or `Cmd+Shift+C`:

- Checkbox list of turns from each conversation
- Token count estimate for selected context
- [Cancel] [Add to Context]

### Merged Context Indicator

```
Active Context:
  This Conversation: 5 turns, 2 docs, 4 sources
  Merged:
    Q2 Sales Analysis (2 turns) [Remove]
    HR Analytics (1 turn) [Remove]
  Total: 8 turns (~6,800 tokens / 128K limit)
```

### Conflict Detection

When merged conversations have contradictory data (same metric, different values):

- Warning panel with side-by-side comparison
- Confidence scores and recency for each source
- AI recommendation on which to trust
- [Use Source 1] [Use Source 2] [Ask to clarify] [Dismiss]

## Multi-Conversation Workspace

### Side-by-Side View (Desktop)

```
[Sidebar] [Conversation 1 (50%)] [Conversation 2 (50%)]
```

3-column and grid layouts also supported. Drag divider to resize.

### Controls

Layout: 1-col | 2-col | 3-col | Grid. Options: sync scroll, pin conversations. [Save workspace] [Load workspace]

### Tab Navigation

Tabs across top: drag to reorder, close (conversation stays in sidebar), pin, duplicate. Overflow dropdown for 5+ tabs.

### Quick Switching

`Cmd+1-9` jump, `Cmd+Tab` next, `Cmd+Shift+Tab` previous, `Cmd+T` new tab, `Cmd+W` close tab.

Recent menu (`Cmd+R`): numbered list of recent conversations, click to switch.

### Named Workspaces

Save layout + conversation set as named workspace ("Sales Research Q2"). Load to restore.

### Breadcrumb Navigation

`Q2 Sales Analysis > Regional Deep Dive > North...` with back links to parent conversations.

## Mobile Adaptation

### Principles

- One conversation at a time (no split-screen)
- Bottom sheet for tree view
- Swipe gestures: right on message = branch, left on conversation = archive, long-press = context menu

### Mobile Conversation List (Full Screen)

Search bar, tap to open, swipe left for archive/delete/star actions. Branches shown indented under parent.

### Mobile Branching

Long-press message -> action sheet -> "Branch from here" -> name + options bottom sheet.

### Mobile Tree View

Bottom sheet (swipe down to close): simplified tree with tap-to-open nodes, pinch-to-zoom.

### Mobile Quick Switching

Swipe right = conversation list, swipe left = tree view, pull down = recent conversations.

## Backend Implementation

### Database Schema (DataFlow)

```python
@db.model
class Conversation:
    id: str; user_id: str; title: str
    parent_conversation_id: str | None  # null = main
    branch_point_turn_id: str | None
    created_at: datetime; updated_at: datetime
    is_active: bool; is_starred: bool; is_archived: bool
    tags: List[str]; folder_id: str | None

@db.model
class ConversationTurn:
    id: str; conversation_id: str; turn_number: int
    sender: str  # 'user' or 'ai'
    message: str; widgets: List[dict] | None; citations: List[dict] | None
    created_at: datetime

@db.model
class ConversationContext:
    id: str; conversation_id: str
    data_sources: List[str]; uploaded_docs: List[str]
    referenced_conversations: List[str]; context_tokens: int
```

### Tree Query

```python
def get_conversation_tree(conversation_id: str):
    conversation = db.get_conversation(conversation_id)
    return {
        'id': conversation.id, 'title': conversation.title,
        'turns': db.query_conversation_turn(conversation_id=conversation.id),
        'branches': [get_conversation_tree(b.id)
                     for b in db.query_conversation(parent_conversation_id=conversation.id)]
    }
```

### Nexus API Endpoints

```python
@nexus.endpoint("/conversations/{id}/branch")
async def create_branch(conversation_id, branch_point_turn_id, branch_name, inherit_context=True):
    """Create branch: copy context up to branch point into new conversation."""

@nexus.endpoint("/conversations/{id}/tree")
async def get_conversation_tree(conversation_id):
    """Return full tree with branches and turns."""

@nexus.endpoint("/conversations/{id}/context/merge")
async def merge_conversation_context(conversation_id, source_conversation_ids, selected_turn_ids=None):
    """Merge selected turns from other conversations into current context."""
```

## Frontend: Flutter State Management

```dart
class ConversationProvider extends ChangeNotifier {
  Conversation? _currentConversation;
  List<ConversationTurn> _turns = [];
  List<Conversation> _activeConversations = [];
  List<Conversation> _workspaceConversations = [];
  WorkspaceLayout _layout = WorkspaceLayout.single;

  Future<void> createBranch({
    required String parentConversationId,
    required String branchPointTurnId,
    required String branchName,
    bool inheritContext = true,
  }) async {
    final branch = await _api.createBranch(...);
    _activeConversations.insert(0, branch);
    await loadConversation(branch.id);
    notifyListeners();
  }
}

enum WorkspaceLayout { single, twoColumn, threeColumn, grid }
```

## Frontend: Tree View Component

```dart
class ConversationTreeView extends StatelessWidget {
  final ConversationTree tree;
  final String? currentConversationId;
  final Function(String) onNodeTap;

  Widget _buildTreeNode(ConversationNode node, {int depth = 0}) {
    return Column(children: [
      Padding(
        padding: EdgeInsets.only(left: depth * 24.0),
        child: GestureDetector(
          onTap: () => onNodeTap(node.id),
          child: AppCard(
            border: node.id == currentConversationId
                ? Border.all(color: AppColors.primary, width: 2) : null,
            child: Row(children: [
              Icon(node.parentId == null ? Icons.circle : Icons.fork_right),
              Text(node.title),
              if (node.id == currentConversationId) Text('< YOU'),
            ]),
          ),
        ),
      ),
      for (var branch in node.branches)
        _buildTreeNode(branch, depth: depth + 1),
    ]);
  }
}
```
