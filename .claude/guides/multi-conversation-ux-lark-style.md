# Part 4: Multi-Conversation UX (Lark-Style)

**Version**: 1.0
**Created**: 2025-10-18
**Status**: Production Design Standard
**Applies To**: Enterprise AI Hub - Multi-Conversation Management

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Research Insights: Lark & Industry Patterns](#research-insights-lark--industry-patterns)
3. [Conversation List UX](#conversation-list-ux)
4. [Turn-Level Branching](#turn-level-branching)
5. [Conversation Tree Visualization](#conversation-tree-visualization)
6. [Cross-Conversation Context](#cross-conversation-context)
7. [Multi-Conversation Workspace](#multi-conversation-workspace)
8. [Mobile Adaptation](#mobile-adaptation)
9. [Implementation Guide](#implementation-guide)
10. [User Research & Validation](#user-research--validation)

---

## Executive Summary

### The Problem
Enterprise users need to manage complex multi-conversation workflows that current linear AI chat interfaces don't support:
- **Research workflows**: Build understanding across multiple conversation threads
- **Exploration workflows**: Branch from specific turns to explore alternative directions
- **Synthesis workflows**: Combine insights from different conversations
- **Comparison workflows**: View multiple conversations side-by-side

### The Solution
A **Lark-inspired conversation management system** that treats conversations like Git branches:
- **Turn-level branching**: Create new conversation from any message
- **Conversation tree visualization**: Git-style branch diagram with interactive navigation
- **Cross-conversation references**: Link and synthesize context from multiple conversations
- **Multi-conversation workspace**: Side-by-side comparison and quick switching

### Success Metrics
- Users can branch from any turn in < 2 clicks
- Users can navigate conversation tree without confusion (90%+ task completion)
- Users can reference other conversations without leaving context
- Cross-conversation synthesis requires < 3 clicks
- Mobile users can manage conversations with touch gestures (swipe, tap, long-press)

---

## Research Insights: Lark & Industry Patterns

### Key Findings from Lark/Feishu

**Lark's Approach to Conversation Management**:
1. **Integrated collaboration**: Conversations aren't isolated—they connect to documents, calendars, and tasks
2. **Persistent context**: Important dialogues can be pinned for quick access
3. **Asynchronous communication**: Team members process information thoughtfully, not reactively
4. **Cloud-based history**: All messages stored in cloud for easy retrieval

**What Lark Does Well**:
- Nested conversation organization (channels → threads → replies)
- Pinning important conversations for visibility
- Search-driven retrieval (find any conversation quickly)
- Contextual actions within conversations (insert docs, check schedules)

**What Lark Doesn't Do (Opportunity for Enterprise AI Hub)**:
- Turn-level branching (create new conversation from any message)
- Conversation tree visualization
- Cross-conversation context synthesis
- AI-assisted conversation management

### Industry Patterns: ChatGPT Branching (Sept 2025)

**ChatGPT's Implementation**:
- **Branch creation**: Hover over any message → "Branch in new chat"
- **Branch labeling**: Clear indication of where fork originated
- **Sidebar organization**: Branches displayed with parent-child relationship
- **Performance impact**: 28% reduction in task completion time
- **User satisfaction**: 4.6/5 vs 3.2/5 for linear chats

**Key Learnings**:
1. **Discoverability**: Branching must be obvious (hover menu on every message)
2. **Visual hierarchy**: Main conversation vs branches must be clear
3. **Context preservation**: Branch inherits context up to branch point
4. **Fast switching**: Sidebar allows quick navigation between branches

### Industry Patterns: Lobe Chat

**Lobe Chat's Approach**:
- **Conversation forking**: Transform linear conversations into tree structures
- **Visual styles**: Choice between chat bubble mode and document mode
- **Export flexibility**: Multiple formats (CSV, PNG, PDF)
- **Drill-down**: Interactive elements for deeper exploration

**Key Learnings**:
1. **Flexibility**: Users need multiple view modes (list, tree, document)
2. **Export matters**: Users want to take conversation data elsewhere
3. **Interactive elements**: Embedded actions reduce context switching

### Git Branch Visualization Patterns

**What We Can Borrow from Git UIs**:
1. **Branch graph visualization**: Dots connected by lines showing parent-child relationships
2. **Color coding**: Different branches have different colors for clarity
3. **Collapse/expand**: Hide inactive branches to reduce clutter
4. **Diff/comparison**: Show what changed between branches
5. **Merge capabilities**: Combine insights from multiple branches

**Tools for Inspiration**:
- **GitKraken**: Clear graphical format with drag-drop merging
- **Git Graph (VS Code)**: Commits visualized relative to each other
- **SourceTree**: Detailed graph of branches and commits
- **GitUp**: Real-time graph updates with perfect clarity

---

## Conversation List UX

### Design Principles

**P1: Content-First Hierarchy**
- Most important conversations (active) occupy 70% of sidebar space
- Less important (archived, old) are collapsed or hidden by default

**P2: Progressive Disclosure**
- Default: Show 5-7 active conversations
- Expand: Show recent (10-20), starred, archived
- Search: Full conversation history

**P3: Visual Hierarchy**
- Active conversations: Bold, colored dot, large text
- Recent conversations: Regular weight, gray dot
- Archived conversations: Light gray, small text

### Layout: Conversation Sidebar

**Desktop (240px width)**:
```
┌─ CONVERSATIONS ─────────────────────┐
│ [🔍 Search] [+ New] [⚙ Settings]   │
│                                     │
│ ┌─ Active (3) ──────────────────┐  │
│ │ ● Q2 Sales Analysis            │  │ ← Current conversation (bold, blue dot)
│ │   └─⑂ Regional Breakdown       │  │ ← Branch (indented, lighter)
│ │   └─⑂ Customer Segments        │  │
│ │                                 │  │
│ │ ○ HR Policy Questions           │  │ ← Other active (regular, gray dot)
│ │                                 │  │
│ │ ○ Product Roadmap Review        │  │
│ │   └─⑂ Feature Prioritization   │  │
│ └─────────────────────────────────┘  │
│                                     │
│ ┌─ Recent (5) ▼ ───────────────┐   │ ← Collapsible
│ │ Oct 17 - Budget Planning       │   │
│ │ Oct 16 - Vendor Analysis       │   │
│ │ Oct 15 - Team Standup Notes    │   │
│ │ ...                            │   │
│ └─────────────────────────────────┘  │
│                                     │
│ ┌─ Starred (2) ▼ ───────────────┐   │
│ │ ★ Template: Weekly Report      │   │
│ │ ★ Knowledge Base Setup         │   │
│ └─────────────────────────────────┘  │
│                                     │
│ [📁 Archived (12)] [🗑 Trash (3)]   │ ← Collapsed by default
└─────────────────────────────────────┘
```

**Key Features**:
1. **Nested hierarchy**: Parent conversation → Branches (indented with ⑂ icon)
2. **Status indicators**:
   - ● Active (colored dot)
   - ○ Inactive (gray dot)
   - ⑂ Branch (fork icon)
   - ★ Starred (star icon)
3. **Badge counts**: Unread messages, new branches
4. **Collapsible sections**: Recent, Starred, Archived

### Visual Indicators

**Conversation Status** (Color-Coded Dots):
```
● Active (Blue)       = Currently viewing or edited in last hour
● Recent (Green)      = Edited in last 24 hours
● Stale (Orange)      = Edited 1-7 days ago
● Inactive (Gray)     = Edited >7 days ago
● Archived (Muted)    = User-archived (light gray, small)
```

**Conversation Metadata** (Shown on hover):
```
Hover over "Q2 Sales Analysis":

┌─ Q2 Sales Analysis ─────────────────┐
│ Created: Oct 15, 2025 (3 days ago)  │
│ Last edited: 2 hours ago             │
│ Messages: 12 turns                   │
│ Branches: 2 active                   │
│ Sources: SharePoint, CRM, 3 uploads  │
│                                      │
│ Quick Actions:                       │
│ [Rename] [Star] [Archive] [Delete]  │
│ [Share] [Export] [Duplicate]        │
└──────────────────────────────────────┘
```

### Organization: Folders, Tags, Search

**Folder Structure** (Optional, Advanced):
```
┌─ CONVERSATIONS ─────────────────────┐
│ [+ New] [🔍 Search] [📁 Folders ▼]  │
│                                     │
│ ┌─ 📁 Sales Team ────────────────┐  │
│ │ ● Q2 Sales Analysis            │  │
│ │ ○ Customer Churn Study         │  │
│ │ [+ New in folder]              │  │
│ └─────────────────────────────────┘  │
│                                     │
│ ┌─ 📁 HR & Compliance ───────────┐  │
│ │ ○ Policy Updates Q4            │  │
│ │ ○ Onboarding Process           │  │
│ └─────────────────────────────────┘  │
│                                     │
│ ┌─ 🏷 Tags ──────────────────────┐   │
│ │ #finance (5) #strategy (3)     │   │
│ │ #urgent (2) #review-needed (1) │   │
│ └─────────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Tag System**:
- User-created tags: #finance, #urgent, #review-needed
- Auto-generated tags: AI suggests based on conversation content
- Tag filtering: Click tag → Show all conversations with that tag

**Search**:
```
┌─ Search Conversations ──────────────┐
│ [Search: "sales revenue Q2"______]  │
│                                     │
│ Results (3):                        │
│                                     │
│ ┌─ Q2 Sales Analysis ────────────┐  │
│ │ "...revenue increased 23%..."  │  │ ← Snippet preview
│ │ Match: Message #3, #7          │  │ ← Turn numbers
│ │ [Open ▸]                        │  │
│ └─────────────────────────────────┘  │
│                                     │
│ ┌─ Budget Planning ──────────────┐  │
│ │ "...Q2 revenue projections..." │  │
│ │ Match: Message #2              │  │
│ │ [Open ▸]                        │  │
│ └─────────────────────────────────┘  │
│                                     │
│ Filters: [All time ▼] [All tags ▼] │
└─────────────────────────────────────┘
```

**Search Features**:
1. **Full-text search**: Search message content, not just titles
2. **Snippet preview**: Show matching text with highlighting
3. **Jump to turn**: Click result → Jump to specific message in conversation
4. **Advanced filters**: Date range, tags, sources used, confidence level

### Quick Actions (Right-Click / Long-Press)

**Context Menu**:
```
Right-click on "Q2 Sales Analysis":

┌─ Actions ───────────────────────────┐
│ ✏️ Rename                            │
│ ⭐ Star / Unstar                     │
│ 📁 Move to folder                    │
│ 🏷 Add tags                          │
│ ───────────────────────────────────  │
│ 📋 Duplicate                         │
│ 📤 Export (PDF, MD, JSON)            │
│ 🔗 Share (Get link, Email)           │
│ ───────────────────────────────────  │
│ 📦 Archive                           │
│ 🗑 Delete                            │
└──────────────────────────────────────┘
```

**Keyboard Shortcuts**:
- `Cmd/Ctrl + N` = New conversation
- `Cmd/Ctrl + K` = Search conversations
- `Cmd/Ctrl + Shift + S` = Star/unstar current conversation
- `Cmd/Ctrl + E` = Export current conversation
- `Cmd/Ctrl + [1-9]` = Jump to conversation #1-9 in sidebar
- `Cmd/Ctrl + Shift + D` = Duplicate conversation
- `Cmd/Ctrl + Backspace` = Archive conversation

---

## Turn-Level Branching

### Conceptual Model

**Mental Model**: Git branches for conversations
- **Main conversation** = main branch
- **Branch point** = specific turn/message where you fork
- **Branch conversation** = feature branch with independent history
- **Context inheritance** = Branch inherits all context up to branch point

**User Story**:
> "As a research analyst, I want to explore an alternative line of questioning from Turn 3 of my conversation without losing the main conversation thread. I want the AI to remember everything up to Turn 3, but allow me to take a different direction from there."

### UI Pattern: Branch Creation

**Step 1: Hover Over Message** (Desktop)
```
┌─────────────────────────────────────────────────────┐
│ User: Show me Q2 sales breakdown                    │
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ AI: Here's the Q2 breakdown: [Chart Widget]         │
│ Revenue grew 23% compared to Q1.                    │
│                                                      │
│ ┌─ Quick Actions (appear on hover) ──────────────┐  │
│ │ [⑂ Branch from here] [📋 Copy] [🔄 Regenerate] │  │
│ └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
        ↑ Hover reveals branching option
```

**Step 2: Click "Branch from here"**
```
┌─────────────────────────────────────────────────────┐
│ ┌─ Create Branch from Turn 2 ────────────────────┐  │
│ │                                                 │  │
│ │ Branch Name:                                    │  │
│ │ [Regional Deep Dive___________________]         │  │
│ │                                                 │  │
│ │ Starting Context:                               │  │
│ │ ┌─────────────────────────────────────────────┐ │  │
│ │ │ Turn 1: User asked for Q2 sales breakdown   │ │  │
│ │ │ Turn 2: AI showed chart (23% growth)        │ │  │
│ │ │                                             │ │  │
│ │ │ ✓ This context will be copied to new branch│ │  │
│ │ └─────────────────────────────────────────────┘ │  │
│ │                                                 │  │
│ │ Options:                                        │  │
│ │ ☑ Inherit active data sources (4 sources)      │  │
│ │ ☑ Inherit uploaded documents (2 docs)          │  │
│ │ ☐ Share future edits between branches          │  │
│ │                                                 │  │
│ │ ⓘ Main conversation will remain unchanged.     │  │
│ │                                                 │  │
│ │ [Cancel]  [Create & Open Branch →]             │  │
│ └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

**Step 3: Branch Created**
```
MAIN CONVERSATION                   BRANCH CONVERSATION
(Original remains unchanged)        (New direction from Turn 2)

┌───────────────────────┐           ┌─────────────────────────────┐
│ Turn 1: User asks     │           │ Turn 1: User asks           │
│ Turn 2: AI responds   │ ──⑂───→   │ Turn 2: AI responds         │
│         ⑂ Branch here │           │ ┌─────────────────────────┐ │
│ Turn 3: Continue main │           │ │ Now in: Regional Deep   │ │
│ Turn 4: ...           │           │ │ Dive (Branch)           │ │
└───────────────────────┘           │ └─────────────────────────┘ │
                                    │ Turn 3: [New question here] │
                                    │ ...                         │
                                    └─────────────────────────────┘

Sidebar Updates:
┌─ Active (2) ─────────────┐
│ ● Regional Deep Dive     │ ← New branch (active)
│ ○ Q2 Sales Analysis      │ ← Parent conversation
│   └─⑂ Regional Deep Dive │ ← Nested under parent
└──────────────────────────┘
```

### Mobile Pattern: Long-Press to Branch

**Mobile Interaction**:
```
┌─────────────────────────────────────┐
│ AI: Here's the Q2 breakdown:        │
│ Revenue grew 23% compared to Q1.    │
│                                     │
│ [Long press this message]           │
└─────────────────────────────────────┘
            ↓
┌─────────────────────────────────────┐
│ ┌─ Actions ────────────────────────┐│
│ │ ⑂ Branch from here               ││
│ │ 📋 Copy message                  ││
│ │ 🔄 Regenerate response           ││
│ │ 🔗 Share turn                    ││
│ └───────────────────────────────────┘│
└─────────────────────────────────────┘
            ↓ User taps "Branch from here"
┌─────────────────────────────────────┐
│ Branch Name:                        │
│ [Regional Deep Dive________]        │
│                                     │
│ ☑ Inherit context (Turns 1-2)       │
│ ☑ Inherit data sources              │
│                                     │
│ [Cancel] [Create →]                 │
└─────────────────────────────────────┘
```

### Branch Naming & Organization

**Auto-Generated Names** (AI suggests):
- Based on topic: "Regional Analysis", "North Region Deep Dive"
- Based on question: "Customer Churn Study"
- Based on date: "Q2 Sales - Oct 18 Branch"

**User Renaming**:
```
┌─ Rename Branch ─────────────────────┐
│ Current: "Regional Deep Dive"       │
│ New: [North Region Focus_______]    │
│                                     │
│ [Cancel] [Save]                     │
└─────────────────────────────────────┘
```

**Branch Metadata** (Stored in database):
```typescript
interface ConversationBranch {
  id: string;
  parentConversationId: string;
  branchPointTurnId: string; // Turn where branch started
  branchName: string;
  createdAt: Date;
  inheritedContext: {
    turns: Turn[]; // All turns up to branch point
    dataSources: DataSource[];
    uploadedDocs: Document[];
  };
  divergenceCount: number; // How many turns since branch
}
```

### Parent-Child Relationship Display

**In Conversation Header**:
```
┌─ Conversation Header ───────────────────────────────┐
│ ⑂ Regional Deep Dive                                │
│ ↳ Branched from: Q2 Sales Analysis (Turn 2)         │
│                                                      │
│ [← Back to parent] [View tree ⚙]                    │
└─────────────────────────────────────────────────────┘
```

**In Conversation Tree** (See next section)

---

## Conversation Tree Visualization

### Design Principles

**P1: Git-Style Graph**
- Conversations are nodes, branches are edges
- Visual parent-child relationships with connecting lines
- Color-coded branches for clarity

**P2: Interactive Navigation**
- Click node → Jump to that conversation
- Hover node → Preview conversation summary
- Right-click → Context menu (branch, merge, delete)

**P3: Collapse/Expand**
- Hide inactive branches to reduce clutter
- Expand to see full tree
- Focus mode: Show only current branch lineage

### Layout: Tree View Panel

**Access**:
- Click "🌲 Tree View" icon in conversation header
- Keyboard shortcut: `Cmd/Ctrl + Shift + T`
- Auto-open when conversation has 2+ branches

**Full Tree View** (Modal overlay):
```
┌─ Conversation Tree: Q2 Sales Analysis ──────────────────────────────────┐
│ [⊖ Collapse All] [⊕ Expand All] [🎯 Focus Current] [📥 Export]         │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                                                                  │   │
│  │  ● Q2 Sales Analysis (Main) ─────────────────────────────────   │   │
│  │    │                                                             │   │
│  │    ├─ Turn 1: User asks for sales data                          │   │
│  │    │                                                             │   │
│  │    ├─ Turn 2: AI shows chart (23% growth) ◀── YOU ARE HERE      │   │
│  │    │   │                                                         │   │
│  │    │   ├──⑂ Regional Deep Dive (Branch 1, Active)              │   │
│  │    │   │    │                                                    │   │
│  │    │   │    ├─ Turn 3: North region analysis                    │   │
│  │    │   │    │                                                    │   │
│  │    │   │    ├─ Turn 4: Customer segments in North               │   │
│  │    │   │    │                                                    │   │
│  │    │   │    └─ Turn 5: Churn analysis                           │   │
│  │    │   │                                                         │   │
│  │    │   └──⑂ Customer Segments (Branch 2, Active)               │   │
│  │    │        │                                                    │   │
│  │    │        ├─ Turn 3: Overall segment breakdown                │   │
│  │    │        │                                                    │   │
│  │    │        └─ Turn 4: Segment profitability                    │   │
│  │    │                                                             │   │
│  │    ├─ Turn 3: Continue main analysis (YoY comparison)           │   │
│  │    │                                                             │   │
│  │    └─ Turn 4: Forecast Q3                                       │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│ Legend: ● Active  ○ Inactive  ⑂ Branch  ◀ Current Position             │
│                                                                          │
│ [Close] [Export Tree Diagram]                                           │
└──────────────────────────────────────────────────────────────────────────┘
```

**Compact Tree View** (Sidebar panel):
```
┌─ Tree: Q2 Sales ────────────┐
│                             │
│ ● Main (4 turns)            │
│   ├─⑂ Regional (5 turns)    │ ← Active
│   │                         │
│   └─⑂ Segments (4 turns)    │
│                             │
│ [Expand ▸]                  │
└─────────────────────────────┘
```

### Visual Design: Graph Rendering

**Node Styles**:
```
ACTIVE CONVERSATION (Current):
┌────────────────────────────┐
│ ● Regional Deep Dive       │ ← Blue border, bold text
│   5 turns | 2h ago         │
└────────────────────────────┘

ACTIVE CONVERSATION (Other):
┌────────────────────────────┐
│ ○ Customer Segments        │ ← Gray border, regular text
│   4 turns | 3h ago         │
└────────────────────────────┘

MAIN CONVERSATION (Parent):
┌────────────────────────────┐
│ ◆ Q2 Sales Analysis        │ ← Green border, bold text
│   4 turns | 5h ago         │
└────────────────────────────┘

INACTIVE BRANCH:
┌────────────────────────────┐
│ ○ Old Exploration          │ ← Light gray, faded
│   3 turns | 2 days ago     │
└────────────────────────────┘
```

**Connection Lines**:
```
Solid line (━━━) = Active branch path
Dotted line (┈┈┈) = Inactive branch path
Thick line (━━━━) = Current conversation lineage
```

**Color Coding** (Optional):
```
Main conversation = Green
Branch 1 = Blue
Branch 2 = Purple
Branch 3 = Orange
(Automatically assigned colors)
```

### Interactions

**Click Node → Jump to Conversation**:
```
User clicks "Regional Deep Dive" node:
→ Tree view closes
→ Conversation switches to "Regional Deep Dive"
→ Scroll to most recent message
```

**Hover Node → Preview**:
```
Hover over "Customer Segments":

┌─ Customer Segments (Preview) ───────┐
│ Created: 3 hours ago                │
│ Branched from: Turn 2               │
│ Messages: 4 turns                   │
│                                     │
│ Last message:                       │
│ "AI: High-value segment accounts    │
│  for 45% of revenue..."             │
│                                     │
│ [Open →]                            │
└─────────────────────────────────────┘
```

**Right-Click Node → Context Menu**:
```
┌─ Actions ───────────────────────────┐
│ 📂 Open conversation                │
│ 📂 Open in new window               │
│ ───────────────────────────────────  │
│ ⑂ Create branch from here           │
│ 🔗 Merge into parent                │
│ ───────────────────────────────────  │
│ ✏️ Rename                            │
│ 🗑 Delete branch                    │
└──────────────────────────────────────┘
```

### Collapse/Expand Controls

**Collapse All**:
```
BEFORE:
● Main
  ├─⑂ Regional (5 turns)
  │  ├─ Turn 3
  │  ├─ Turn 4
  │  └─ Turn 5
  └─⑂ Segments (4 turns)
     ├─ Turn 3
     └─ Turn 4

AFTER (Collapsed):
● Main
  ├─⑂ Regional (5 turns) [+]
  └─⑂ Segments (4 turns) [+]
```

**Focus Mode** (Show only current lineage):
```
BEFORE (Full tree with 5 branches):
● Main
  ├─⑂ Regional
  ├─⑂ Segments
  ├─⑂ Products
  ├─⑂ Forecast
  └─⑂ Old Exploration

AFTER (Focus on "Regional"):
● Main
  └─⑂ Regional ◀ Current
     └─ Turn 3
     └─ Turn 4
     └─ Turn 5

[Show all branches]
```

### Mobile Tree View

**Mobile Adaptation**:
```
┌─ Tree: Q2 Sales ─────────────────────┐
│ [Swipe left/right to navigate]      │
│                                      │
│     ● Main                           │
│       │                              │
│       ├──┐                           │
│       │  ⑂ Regional ◀ YOU            │
│       │  (5 turns)                   │
│       │                              │
│       └──┐                           │
│          ⑂ Segments                  │
│          (4 turns)                   │
│                                      │
│ [Tap node to open]                   │
│ [Pinch to zoom]                      │
└──────────────────────────────────────┘
```

**Mobile Gestures**:
- **Tap node** = Open conversation
- **Long-press node** = Context menu
- **Pinch to zoom** = Zoom in/out on tree
- **Swipe left/right** = Pan across large tree
- **Double-tap** = Focus on that node (collapse others)

---

## Cross-Conversation Context

### User Flow: Referencing Another Conversation

**Step 1: User Types Reference**
```
┌─ Regional Deep Dive (Current) ──────────────────────┐
│ User: In conversation "Q2 Sales Analysis", you     │
│ showed me revenue growth by region. Can you combine │
│ that with the customer churn data from "HR          │
│ Analytics" conversation to identify at-risk regions?│
└─────────────────────────────────────────────────────┘
```

**Step 2: AI Detects References**
```
Backend (Python + Kailash SDK):

from kaizen.agents import BaseAgent

class ConversationReferenceDetector(BaseAgent):
    async def detect_references(self, user_message: str):
        # NLP detection:
        # - "In conversation X"
        # - "From our chat about Y"
        # - "@ConversationName"

        return [
            ConversationReference(
                conversation_id='uuid-sales',
                conversation_name='Q2 Sales Analysis',
                referenced_turns=[2], # Which turns referenced
                context_needed='revenue growth by region'
            ),
            ConversationReference(
                conversation_id='uuid-hr',
                conversation_name='HR Analytics',
                referenced_turns=[5],
                context_needed='customer churn data'
            )
        ]
```

**Step 3: Visual Indicator in Message**
```
┌─────────────────────────────────────────────────────┐
│ User: In conversation [Q2 Sales ▸] you showed me    │
│ revenue growth. Combine with [HR Analytics ▸] churn │
│ data to identify at-risk regions.                   │
└─────────────────────────────────────────────────────┘
        ↑ Clickable links to referenced conversations
```

**Step 4: AI Fetches Context & Responds**
```
┌─────────────────────────────────────────────────────┐
│ AI: I've analyzed data from both conversations:     │
│                                                      │
│ ┌─ Context Used ────────────────────────────────┐  │
│ │ 📂 Q2 Sales Analysis                          │  │
│ │   └─ Turn 2: Regional revenue chart           │  │
│ │   └─ Turn 3: North region details             │  │
│ │                                                │  │
│ │ 📂 HR Analytics                                │  │
│ │   └─ Turn 5: Churn by department/region       │  │
│ │                                                │  │
│ │ [View source conversations ▸]                 │  │
│ └────────────────────────────────────────────────┘  │
│                                                      │
│ At-risk regions (high revenue, high churn):         │
│                                                      │
│ ┌─ Combined Analysis Widget ──────────────────┐    │
│ │ [Chart showing regions with high rev + churn]│    │
│ │                                              │    │
│ │ 🔴 North: $450K revenue, 18% churn (HIGH RISK)│   │
│ │ 🟡 South: $380K revenue, 12% churn (MEDIUM)  │    │
│ │ 🟢 East: $290K revenue, 5% churn (LOW)       │    │
│ │ 🟢 West: $110K revenue, 3% churn (LOW)       │    │
│ └──────────────────────────────────────────────┘    │
│                                                      │
│ [3 sources from 2 conversations ▼]                  │
└─────────────────────────────────────────────────────┘
```

### Context Selection UI

**Manual Context Selection** (Advanced):
```
User wants to manually select which turns to include:

┌─ Select Context from Other Conversations ───────────┐
│                                                      │
│ ┌─ Q2 Sales Analysis ─────────────────────────────┐ │
│ │ ☐ Turn 1: User asks for sales data              │ │
│ │ ☑ Turn 2: AI shows chart (23% growth)           │ │
│ │ ☑ Turn 3: North region analysis                 │ │
│ │ ☐ Turn 4: South region analysis                 │ │
│ │                                                  │ │
│ │ [Select all] [Select none]                      │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ HR Analytics ──────────────────────────────────┐ │
│ │ ☐ Turn 1: User asks about churn                 │ │
│ │ ☐ Turn 2-4: Various churn analyses              │ │
│ │ ☑ Turn 5: Churn by region                       │ │
│ │                                                  │ │
│ │ [Select all] [Select none]                      │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ⓘ Selected: 3 turns (approx. 2,500 tokens)          │
│                                                      │
│ [Cancel] [Add to Context]                           │
└──────────────────────────────────────────────────────┘
```

**Access**:
- Click "Add context from..." button in input area
- Keyboard shortcut: `Cmd/Ctrl + Shift + C`

### Context Merge Visualization

**Merged Context Indicator**:
```
┌─ Active Context (Current Conversation) ─────────────┐
│                                                      │
│ ┌─ This Conversation ─────────────────────────────┐ │
│ │ • 5 turns from "Regional Deep Dive"             │ │
│ │ • 2 uploaded documents                          │ │
│ │ • 4 active data sources                         │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ Merged from Other Conversations ───────────────┐ │
│ │ 📂 Q2 Sales Analysis (2 turns)                  │ │
│ │    └─ Turn 2, Turn 3                            │ │
│ │                                                  │ │
│ │ 📂 HR Analytics (1 turn)                        │ │
│ │    └─ Turn 5                                    │ │
│ │                                                  │ │
│ │ [Remove Q2 Sales] [Remove HR Analytics]         │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ Total Context: 8 turns (~6,800 tokens / 128K limit) │
└──────────────────────────────────────────────────────┘
```

### Conflict Detection UI

**Scenario**: Two conversations have contradictory data

**Detection**:
```python
class ConflictDetector(BaseAgent):
    async def detect_conflicts(self, contexts: List[ConversationContext]):
        # Check for:
        # 1. Same metric, different values
        # 2. Same entity, different attributes
        # 3. Temporal inconsistencies

        conflicts = []

        # Example: Revenue growth differs
        if contexts[0].revenue_growth == 0.23 and contexts[1].revenue_growth == 0.19:
            conflicts.append(Conflict(
                type='data_mismatch',
                field='revenue_growth',
                values=[0.23, 0.19],
                sources=[contexts[0].source, contexts[1].source]
            ))

        return conflicts
```

**UI Treatment**:
```
┌─────────────────────────────────────────────────────┐
│ ⚠ Conflict Detected: Revenue Growth Rate            │
│                                                      │
│ ┌─ Conversation 1: Q2 Sales Analysis ─────────────┐ │
│ │ Revenue growth: 23%                             │ │
│ │ Source: Q2_Sales_Report.xlsx (95% confidence)   │ │
│ │ Date: Oct 15, 2025 (3 days ago)                │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ ┌─ Conversation 2: Budget Planning ───────────────┐ │
│ │ Revenue growth: 19%                             │ │
│ │ Source: Budget_Forecast.pdf (78% confidence)    │ │
│ │ Date: Jan 10, 2025 (9 months ago)              │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ AI Recommendation:                                   │
│ Conversation 1 has higher confidence and more recent│
│ data. The 23% figure is more reliable.              │
│                                                      │
│ How to resolve:                                      │
│ [Use Conversation 1] [Use Conversation 2]           │
│ [Ask me to clarify] [Dismiss]                       │
└─────────────────────────────────────────────────────┘
```

---

## Multi-Conversation Workspace

### Design Principles

**P1: Side-by-Side Comparison**
- View 2-3 conversations simultaneously
- Synchronized scrolling (optional)
- Cross-reference highlighting

**P2: Quick Switching**
- Keyboard shortcuts (Cmd+1, Cmd+2, etc.)
- Recent conversations menu
- Conversation tabs

**P3: Persistent Workspace**
- Save workspace layout
- Restore on next session
- Named workspaces ("Sales Research", "HR Review")

### Layout: Side-by-Side View

**Desktop (2-conversation split)**:
```
┌────────────────────────────────────────────────────────────────────┐
│ SIDEBAR │ CONVERSATION 1 (50%)      │ CONVERSATION 2 (50%)         │
├─────────┼───────────────────────────┼──────────────────────────────┤
│         │ Q2 Sales Analysis         │ HR Analytics                 │
│ Active  │ ────────────────────────  │ ─────────────────────────    │
│ (3)     │                           │                              │
│         │ User: Show me Q2 sales... │ User: Customer churn...      │
│ ● Q2    │                           │                              │
│   Sales │ AI: Here's breakdown...   │ AI: Churn by region...       │
│         │ [Chart Widget]            │ [Table Widget]               │
│ ● HR    │                           │                              │
│   Analy │ User: What about North?   │ User: Why is North high?     │
│   tics  │                           │                              │
│         │ AI: North region shows... │ AI: High turnover in...      │
│ ○ Prod  │                           │                              │
│   Road  │ [Type message...]         │ [Type message...]            │
│   map   │                           │                              │
└─────────┴───────────────────────────┴──────────────────────────────┘
         Drag divider ↕ to resize panels
```

**Desktop (3-conversation grid)**:
```
┌────────────────────────────────────────────────────────────────────┐
│ SIDEBAR │ CONV 1 (33%)  │ CONV 2 (33%)  │ CONV 3 (33%)            │
├─────────┼───────────────┼───────────────┼─────────────────────────┤
│         │ Q2 Sales      │ HR Analytics  │ Product Roadmap         │
│         │ ─────────────  │ ────────────  │ ────────────────        │
│ Active  │               │               │                         │
│ (3)     │ [Messages]    │ [Messages]    │ [Messages]              │
│         │               │               │                         │
│ ● Q2    │               │               │                         │
│ ● HR    │               │               │                         │
│ ● Prod  │               │               │                         │
│         │               │               │                         │
│         │ [Input]       │ [Input]       │ [Input]                 │
└─────────┴───────────────┴───────────────┴─────────────────────────┘
```

**Controls**:
```
┌─ Workspace Controls ────────────────────────────────┐
│ Layout: [● 1 col] [○ 2 col] [○ 3 col] [○ Grid]     │
│ Sync scroll: [☐] Pin conversations: [☑]            │
│ [Save workspace] [Load workspace ▼]                │
└─────────────────────────────────────────────────────┘
```

### Tab-Based Navigation

**Alternative Layout** (for users who prefer tabs):
```
┌─────────────────────────────────────────────────────┐
│ [Q2 Sales ●] [HR Analytics] [Product Roadmap] [+]  │ ← Active tab
└─────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ Q2 Sales Analysis                                   │
│ ─────────────────────────────────────────────────   │
│                                                      │
│ User: Show me Q2 sales breakdown                    │
│                                                      │
│ AI: Here's the Q2 breakdown...                      │
│ [Chart Widget]                                       │
│                                                      │
│ User: What about North region?                      │
│                                                      │
│ AI: North region shows...                           │
│                                                      │
│ [Type message...]                                    │
└─────────────────────────────────────────────────────┘
```

**Tab Features**:
- **Drag to reorder** tabs
- **Close tab**: X button (conversation remains in sidebar)
- **Duplicate tab**: Right-click → "Duplicate in new tab"
- **Pin tab**: Prevent accidental closing
- **Tab overflow**: When >5 tabs, show dropdown menu

### Quick Switching

**Keyboard Shortcuts**:
```
Cmd/Ctrl + 1-9 = Switch to conversation #1-9 in sidebar
Cmd/Ctrl + Tab = Next conversation (recent order)
Cmd/Ctrl + Shift + Tab = Previous conversation
Cmd/Ctrl + T = New conversation (new tab)
Cmd/Ctrl + W = Close current tab (keep conversation)
```

**Recent Conversations Menu**:
```
Press Cmd/Ctrl + R:

┌─ Recent Conversations ──────────────────────────────┐
│ 1. Q2 Sales Analysis (2 min ago) ◀ Current         │
│ 2. HR Analytics (15 min ago)                        │
│ 3. Product Roadmap (1 hour ago)                     │
│ 4. Budget Planning (3 hours ago)                    │
│ 5. Vendor Analysis (1 day ago)                      │
│                                                      │
│ Type number or click to switch                      │
└─────────────────────────────────────────────────────┘
```

### Synchronized Scrolling

**Use Case**: Compare responses side-by-side

**Enable**:
```
┌─ Workspace Controls ────────────────────────────────┐
│ ☑ Sync scroll (Conversations 1 & 2)                │
└─────────────────────────────────────────────────────┘
```

**Behavior**:
- Scroll in Conversation 1 → Conversation 2 scrolls in sync
- Scroll position maintained relative to conversation length
- Disable for independent scrolling

### Named Workspaces

**Save Workspace**:
```
┌─ Save Workspace ────────────────────────────────────┐
│ Workspace Name:                                     │
│ [Sales Research Q2________________]                 │
│                                                      │
│ Current Layout:                                      │
│ • 2-column split                                     │
│ • Conversations: Q2 Sales, HR Analytics             │
│ • Sync scroll: Enabled                              │
│                                                      │
│ [Cancel] [Save]                                      │
└─────────────────────────────────────────────────────┘
```

**Load Workspace**:
```
┌─ Workspaces ▼ ──────────────────────────────────────┐
│ ★ Sales Research Q2 (saved 2h ago)                  │
│   Marketing Review (saved 1 day ago)                │
│   HR Onboarding (saved 3 days ago)                  │
│ ────────────────────────────────────────────────────  │
│ [Create new workspace]                               │
└─────────────────────────────────────────────────────┘
```

### Breadcrumb Navigation

**Show User's Path** (for complex multi-conversation workflows):
```
┌─ Breadcrumb ────────────────────────────────────────┐
│ Q2 Sales Analysis → Regional Deep Dive → North...  │
│                     ↑ You are here                  │
│                                                      │
│ [← Back to Regional] [↑ Back to Q2 Sales]           │
└─────────────────────────────────────────────────────┘
```

**Benefits**:
- User always knows where they are in conversation hierarchy
- Quick navigation back to parent conversations
- Visual reminder of branching structure

---

## Mobile Adaptation

### Design Principles

**P1: Simplified Conversation Management**
- Mobile = 1 conversation at a time (no split-screen)
- Conversation list optimized for small screens
- Swipe gestures for common actions

**P2: Bottom Sheet for Tree View**
- Tree view as slide-up bottom sheet
- Touch-friendly node sizes
- Pinch-to-zoom on large trees

**P3: Swipe Gestures**
- Swipe right on message → Branch from here
- Swipe left on conversation → Archive
- Long-press message → Context menu

### Layout: Mobile Conversation List

**Mobile Sidebar** (Full screen when open):
```
┌─────────────────────────────────┐
│ ☰ Conversations      [+ New]    │
├─────────────────────────────────┤
│ 🔍 Search conversations...      │
├─────────────────────────────────┤
│                                 │
│ ● Q2 Sales Analysis             │ ← Tap to open
│   └─⑂ Regional Deep Dive        │
│   3h ago • 8 turns              │
│                                 │
│ ○ HR Analytics                  │
│   15m ago • 12 turns            │ ← Swipe left to archive
│                                 │
│ ○ Product Roadmap               │
│   └─⑂ Feature Priorities        │
│   1h ago • 5 turns              │
│                                 │
│ [Recent ▼] [Starred ▼]          │
└─────────────────────────────────┘
```

**Swipe Actions on Conversation**:
```
Swipe left on "HR Analytics":

┌─────────────────────────────────┐
│ ○ HR Analytics  [📦] [🗑] [★]  │ ← Archive, Delete, Star
│   15m ago • 12 turns            │
└─────────────────────────────────┘
```

### Mobile Conversation View

**Simplified Header**:
```
┌─────────────────────────────────┐
│ ☰ Q2 Sales Analysis    ⋮       │ ← Menu (tree, settings, etc.)
├─────────────────────────────────┤
│ User: Show me Q2 sales...       │
│                                 │
│ AI: Here's the breakdown...     │
│ [Chart Widget]                  │
│                                 │
│ User: North region?             │
│                                 │
│ AI: North shows...              │
│                                 │
│                                 │
│                                 │
├─────────────────────────────────┤
│ [📎] Type message... [Send ➤]  │
└─────────────────────────────────┘
```

### Mobile Branching: Long-Press

**Step 1: Long-press message**
```
┌─────────────────────────────────┐
│ AI: Here's the Q2 breakdown...  │ ← User long-presses this
│ [Chart Widget]                  │
└─────────────────────────────────┘
        ↓
┌─────────────────────────────────┐
│ ┌─ Actions ───────────────────┐ │
│ │ ⑂ Branch from here          │ │
│ │ 📋 Copy message             │ │
│ │ 🔄 Regenerate               │ │
│ │ 🔗 Share                    │ │
│ └─────────────────────────────┘ │
└─────────────────────────────────┘
```

**Step 2: Tap "Branch from here"**
```
┌─────────────────────────────────┐
│ Create Branch                   │
├─────────────────────────────────┤
│ Name:                           │
│ [Regional Deep Dive_______]     │
│                                 │
│ Options:                        │
│ ☑ Inherit context (Turns 1-2)   │
│ ☑ Inherit data sources          │
│                                 │
│ [Cancel] [Create →]             │
└─────────────────────────────────┘
```

### Mobile Tree View: Bottom Sheet

**Access**: Tap "🌲 Tree" icon in conversation header

**Layout**:
```
┌─────────────────────────────────┐
│ (Conversation view dimmed)      │
│                                 │
│                                 │
├─────────────────────────────────┤ ← Swipe down to close
│ ──────── (Drag handle)          │
│                                 │
│ Tree: Q2 Sales Analysis         │
│ ────────────────────────────    │
│                                 │
│ ● Main (4 turns)                │
│   │                             │
│   ├─⑂ Regional (5 turns) ◀ YOU │ ← Tap to open
│   │                             │
│   └─⑂ Segments (4 turns)        │
│                                 │
│ [Expand All] [Focus Current]    │
│                                 │
│ [Close]                         │
└─────────────────────────────────┘
```

**Interactions**:
- **Swipe down** = Close bottom sheet
- **Tap node** = Open that conversation
- **Long-press node** = Context menu (rename, delete, etc.)
- **Pinch-to-zoom** = Zoom in/out on large trees

### Mobile Drawer for Conversation Tree

**Alternative**: Slide-in drawer (from right edge)

```
Swipe from right edge:

┌─────────────────────────────────┐
│ Conversation │ Tree View        │
│ (dimmed 50%) │ ────────────     │
│              │                  │
│              │ ● Main           │
│              │   ├─⑂ Regional   │
│              │   └─⑂ Segments   │
│              │                  │
│              │ [Close ✕]        │
└─────────────────────────────────┘
   ← Tap outside to close
```

### Mobile Quick Switching

**Swipe Gestures**:
- **Swipe right** (from left edge) = Open conversation list
- **Swipe left** (from right edge) = Open tree view
- **Swipe down** (from top) = Recent conversations menu

**Recent Conversations** (Pull down from top):
```
┌─────────────────────────────────┐
│ Recent Conversations            │
├─────────────────────────────────┤
│ 1. Q2 Sales ◀ Current           │
│ 2. HR Analytics                 │
│ 3. Product Roadmap              │
│ 4. Budget Planning              │
│                                 │
│ Tap to switch                   │
└─────────────────────────────────┘
```

### Mobile Cross-Conversation References

**Auto-Detection** (same as desktop):
```
User types: "In conversation Q2 Sales, you showed..."

┌─────────────────────────────────┐
│ User: In conversation           │
│ [Q2 Sales ▸] you showed me...   │ ← Tap to view
└─────────────────────────────────┘
```

**Tap reference link**:
```
┌─────────────────────────────────┐
│ Q2 Sales Analysis (Preview)     │
│ ────────────────────────────    │
│ Turn 2: AI showed chart         │
│ Revenue grew 23%...             │
│                                 │
│ [View full conversation →]      │
│ [Use this context]              │
│ [Cancel]                        │
└─────────────────────────────────┘
```

### Mobile Performance Optimizations

**Lazy Loading**:
- Load only visible conversations in list
- Load messages on-demand (scroll to load more)
- Defer tree rendering until user opens tree view

**Caching**:
- Cache last 3 conversations in memory
- Cache tree structure for fast rendering
- Pre-fetch likely next conversations

**Gesture Debouncing**:
- Prevent accidental swipes (debounce 100ms)
- Confirm destructive actions (archive, delete)

---

## Implementation Guide

### Backend: Database Schema (DataFlow)

**Conversation Model**:
```python
from dataflow import DataFlow

db = DataFlow()

@db.model
class Conversation:
    id: str  # UUID
    user_id: str  # Foreign key
    title: str
    parent_conversation_id: str | None  # Null = main conversation
    branch_point_turn_id: str | None  # Turn where branch started
    created_at: datetime
    updated_at: datetime
    is_active: bool
    is_starred: bool
    is_archived: bool
    tags: List[str]
    folder_id: str | None

@db.model
class ConversationTurn:
    id: str  # UUID
    conversation_id: str  # Foreign key
    turn_number: int  # 1, 2, 3...
    sender: str  # 'user' or 'ai'
    message: str
    widgets: List[dict] | None  # Widget descriptors (JSON)
    citations: List[dict] | None  # Citation data (JSON)
    created_at: datetime

@db.model
class ConversationContext:
    id: str
    conversation_id: str
    data_sources: List[str]  # Active data source IDs
    uploaded_docs: List[str]  # Uploaded document IDs
    referenced_conversations: List[str]  # Cross-conversation refs
    context_tokens: int  # Total token count
```

**Branch Relationship Queries** (using DataFlow auto-generated nodes):
```python
# Get all branches of a conversation
branches = await db.query_conversation(
    parent_conversation_id=parent_id,
    is_archived=False
)

# Get branch lineage (conversation tree)
def get_conversation_tree(conversation_id: str):
    # Recursive query to build tree
    conversation = db.get_conversation(conversation_id)

    tree = {
        'id': conversation.id,
        'title': conversation.title,
        'turns': db.query_conversation_turn(conversation_id=conversation.id),
        'branches': []
    }

    # Get child branches
    branches = db.query_conversation(parent_conversation_id=conversation.id)
    for branch in branches:
        tree['branches'].append(get_conversation_tree(branch.id))

    return tree
```

### Frontend: Flutter State Management

**Conversation Provider**:
```dart
import 'package:flutter/foundation.dart';

class ConversationProvider extends ChangeNotifier {
  // Current conversation
  Conversation? _currentConversation;
  List<ConversationTurn> _turns = [];

  // Conversation list
  List<Conversation> _activeConversations = [];
  List<Conversation> _recentConversations = [];
  List<Conversation> _starredConversations = [];

  // Multi-conversation workspace
  List<Conversation> _workspaceConversations = [];
  WorkspaceLayout _layout = WorkspaceLayout.single;

  // Getters
  Conversation? get currentConversation => _currentConversation;
  List<ConversationTurn> get turns => _turns;
  List<Conversation> get activeConversations => _activeConversations;

  // Methods
  Future<void> loadConversation(String conversationId) async {
    _currentConversation = await _fetchConversation(conversationId);
    _turns = await _fetchTurns(conversationId);
    notifyListeners();
  }

  Future<void> createBranch({
    required String parentConversationId,
    required String branchPointTurnId,
    required String branchName,
    bool inheritContext = true,
  }) async {
    // Create branch in backend
    final branch = await _api.createBranch(
      parentId: parentConversationId,
      branchPointTurnId: branchPointTurnId,
      name: branchName,
      inheritContext: inheritContext,
    );

    // Add to active conversations
    _activeConversations.insert(0, branch);

    // Switch to branch
    await loadConversation(branch.id);

    notifyListeners();
  }

  Future<ConversationTree> getConversationTree(String conversationId) async {
    return await _api.getConversationTree(conversationId);
  }

  void addToWorkspace(Conversation conversation) {
    if (!_workspaceConversations.contains(conversation)) {
      _workspaceConversations.add(conversation);
      notifyListeners();
    }
  }

  void setWorkspaceLayout(WorkspaceLayout layout) {
    _layout = layout;
    notifyListeners();
  }
}

enum WorkspaceLayout { single, twoColumn, threeColumn, grid }
```

### Frontend: Tree Visualization Component

**Tree View Widget**:
```dart
class ConversationTreeView extends StatelessWidget {
  final ConversationTree tree;
  final String? currentConversationId;
  final Function(String conversationId) onNodeTap;

  Widget build(BuildContext context) {
    return Column(
      children: [
        // Header
        Row(
          children: [
            Text('Conversation Tree: ${tree.rootConversation.title}',
                style: AppTypography.h3),
            Spacer(),
            AppButton.text(
              label: 'Collapse All',
              onPressed: _collapseAll,
            ),
            AppButton.text(
              label: 'Focus Current',
              onPressed: _focusCurrent,
            ),
          ],
        ),
        AppSpacing.gapMd,

        // Tree graph
        Expanded(
          child: SingleChildScrollView(
            child: _buildTreeNode(tree.rootConversation),
          ),
        ),
      ],
    );
  }

  Widget _buildTreeNode(ConversationNode node, {int depth = 0}) {
    final isCurrentConversation = node.id == currentConversationId;
    final hasChildren = node.branches.isNotEmpty;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Node card
        Padding(
          padding: EdgeInsets.only(left: depth * 24.0),
          child: GestureDetector(
            onTap: () => onNodeTap(node.id),
            child: AppCard(
              border: isCurrentConversation
                  ? Border.all(color: AppColors.primary, width: 2)
                  : null,
              child: Row(
                children: [
                  // Icon
                  Icon(
                    node.parentId == null ? Icons.circle : Icons.fork_right,
                    color: isCurrentConversation
                        ? AppColors.primary
                        : AppColors.textSecondary,
                  ),
                  AppSpacing.gapSm,

                  // Title & metadata
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(node.title, style: AppTypography.bodyMedium),
                        AppSpacing.gapXs,
                        Text(
                          '${node.turnCount} turns • ${_formatDate(node.updatedAt)}',
                          style: AppTypography.caption.copyWith(
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),

                  // Current indicator
                  if (isCurrentConversation)
                    Text('◀ YOU', style: TextStyle(
                      color: AppColors.primary,
                      fontWeight: FontWeight.w600,
                    )),
                ],
              ),
            ),
          ),
        ),

        // Child branches
        if (hasChildren) ...[
          AppSpacing.gapSm,
          for (var branch in node.branches)
            _buildTreeNode(branch, depth: depth + 1),
        ],
      ],
    );
  }
}
```

### Backend: Cross-Conversation Reference Detection

**Using Kailash Kaizen AI Agent**:
```python
from kaizen.agents import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class ConversationReferenceSignature(Signature):
    user_message: str = InputField(desc="User's message")
    available_conversations: List[dict] = InputField(desc="List of user's conversations")

    references: List[dict] = OutputField(desc="Detected conversation references")

class ConversationReferenceDetector(BaseAgent):
    def __init__(self):
        super().__init__(
            signature=ConversationReferenceSignature,
            name="Conversation Reference Detector",
            instructions="""
            Detect when a user references another conversation.

            Patterns to detect:
            - "In conversation X"
            - "From our chat about Y"
            - "As you said in [conversation name]"
            - "@ConversationName"

            Return a list of referenced conversations with:
            - conversation_id
            - conversation_name
            - referenced_context (what user wants from that conversation)
            """
        )

    async def detect(self, user_message: str, user_conversations: List[dict]):
        result = await self.execute(
            user_message=user_message,
            available_conversations=user_conversations
        )

        return result.references

# Usage
detector = ConversationReferenceDetector()
references = await detector.detect(
    user_message="In conversation Q2 Sales, you showed revenue growth...",
    user_conversations=[
        {'id': 'uuid-1', 'title': 'Q2 Sales Analysis'},
        {'id': 'uuid-2', 'title': 'HR Analytics'},
        # ...
    ]
)

# Result:
# [
#   {
#     'conversation_id': 'uuid-1',
#     'conversation_name': 'Q2 Sales Analysis',
#     'referenced_context': 'revenue growth data'
#   }
# ]
```

### API: Nexus Endpoints

**Multi-Conversation Endpoints**:
```python
from nexus import Nexus

nexus = Nexus()

@nexus.endpoint("/conversations/{conversation_id}/branch")
async def create_branch(
    conversation_id: str,
    branch_point_turn_id: str,
    branch_name: str,
    inherit_context: bool = True
):
    """Create a branch from a specific turn in a conversation"""
    # Fetch parent conversation
    parent = db.get_conversation(conversation_id)

    # Get context up to branch point
    context_turns = db.query_conversation_turn(
        conversation_id=conversation_id,
        turn_number__lte=branch_point_turn_id
    )

    # Create new conversation (branch)
    branch = db.create_conversation(
        title=branch_name,
        user_id=parent.user_id,
        parent_conversation_id=conversation_id,
        branch_point_turn_id=branch_point_turn_id
    )

    # Copy context if requested
    if inherit_context:
        for turn in context_turns:
            db.create_conversation_turn(
                conversation_id=branch.id,
                turn_number=turn.turn_number,
                sender=turn.sender,
                message=turn.message,
                widgets=turn.widgets,
                citations=turn.citations
            )

    return branch

@nexus.endpoint("/conversations/{conversation_id}/tree")
async def get_conversation_tree(conversation_id: str):
    """Get full conversation tree (branches, lineage)"""
    def build_tree(conv_id):
        conversation = db.get_conversation(conv_id)
        turns = db.query_conversation_turn(conversation_id=conv_id)
        branches = db.query_conversation(parent_conversation_id=conv_id)

        return {
            'id': conversation.id,
            'title': conversation.title,
            'parentId': conversation.parent_conversation_id,
            'branchPointTurnId': conversation.branch_point_turn_id,
            'turns': [turn.to_dict() for turn in turns],
            'branches': [build_tree(branch.id) for branch in branches]
        }

    return build_tree(conversation_id)

@nexus.endpoint("/conversations/{conversation_id}/context/merge")
async def merge_conversation_context(
    conversation_id: str,
    source_conversation_ids: List[str],
    selected_turn_ids: List[str] = None
):
    """Merge context from other conversations into current conversation"""
    merged_context = []

    for source_id in source_conversation_ids:
        if selected_turn_ids:
            # User manually selected specific turns
            turns = db.query_conversation_turn(
                conversation_id=source_id,
                id__in=selected_turn_ids
            )
        else:
            # Use all turns from source conversation
            turns = db.query_conversation_turn(conversation_id=source_id)

        merged_context.extend(turns)

    # Update current conversation context
    db.update_conversation_context(
        conversation_id=conversation_id,
        referenced_conversations=source_conversation_ids
    )

    return {
        'merged_turns': len(merged_context),
        'total_tokens': sum(turn.token_count for turn in merged_context)
    }
```

---

## User Research & Validation

### Usability Testing Plan

**Phase 1: Mockup Testing (Week 1)**
- **Goal**: Validate core concepts (branching, tree view, cross-references)
- **Method**: 5-second tests, first-click tests, navigation testing
- **Participants**: 10 enterprise users (analysts, managers, knowledge workers)
- **Deliverable**: Iteration on wireframes

**Phase 2: Prototype Testing (Week 3)**
- **Goal**: Test interactive prototype (Figma/Flutter prototype)
- **Method**: Task-based usability testing
- **Tasks**:
  1. Create a branch from Turn 3 of a conversation
  2. Navigate conversation tree to find a specific branch
  3. Reference another conversation in your query
  4. Open 2 conversations side-by-side for comparison
  5. Switch between conversations using keyboard shortcuts
- **Metrics**:
  - Task completion rate (target: >90%)
  - Time on task (branch creation: <30 seconds)
  - Error rate (misclicks, navigation errors)
  - User satisfaction (SUS score: target >80)

**Phase 3: Alpha Testing (Week 6)**
- **Goal**: Test working implementation with real data
- **Method**: In-app feedback, analytics tracking
- **Participants**: 20 enterprise users (2-week usage period)
- **Metrics**:
  - Branching feature usage rate
  - Cross-conversation reference frequency
  - Workspace layout preferences
  - User-reported issues

### Key Metrics to Track

**Adoption Metrics**:
- % of users who create at least 1 branch per week
- Average branches per conversation
- % of conversations with cross-references
- Workspace usage (single vs multi-conversation)

**Performance Metrics**:
- Time to create branch (target: <30 seconds)
- Time to navigate tree (target: <10 seconds)
- Time to switch conversations (target: <2 seconds)

**User Satisfaction**:
- NASA TLX cognitive load score (target: <4/10)
- SUS (System Usability Scale) score (target: >80)
- NPS (Net Promoter Score) for multi-conversation feature

### Success Criteria

**Launch Criteria** (Phase 1 MVP):
- ✅ Turn-level branching works on desktop & mobile
- ✅ Conversation tree visualization renders correctly
- ✅ Cross-conversation references detected & linked
- ✅ Usability testing shows >85% task completion rate
- ✅ Performance benchmarks met (branching <30s, switching <2s)

**Success Criteria** (6 months post-launch):
- ✅ 60% of active users create at least 1 branch per week
- ✅ 40% of conversations use cross-conversation references
- ✅ SUS score >80 (excellent usability)
- ✅ <5% error rate in branching/navigation tasks
- ✅ User-reported productivity improvement >30%

---

## Appendix: Research References

### Lark/Feishu
- [Lark Suite Overview](https://www.larksuite.com/)
- [ByteDance Work Culture with Lark](https://www.larksuite.com/en_us/blog/bytedance-work-tips)
- Lark MCP Server (GitHub): [larksuite/lark-openapi-mcp](https://github.com/larksuite/lark-openapi-mcp)

### ChatGPT Branching (Sept 2025)
- [ChatGPT Branching Feature Guide](https://www.geeky-gadgets.com/chatgpt-5-branching-feature-guide/)
- [Branching Boosts Conversation Flexibility](https://www.webpronews.com/openais-chatgpt-branching-feature-boosts-conversation-flexibility/)
- Performance impact: 28% reduction in task completion time, 4.6/5 satisfaction vs 3.2/5 for linear chats

### Lobe Chat
- [Lobe Chat GitHub](https://github.com/lobehub/lobe-chat)
- Features: Conversation forking, visual styles (chat bubble vs document mode), multi-modal support

### Git Branch Visualization
- GitKraken: Drag-drop merging, visual branch graphs
- Git Graph (VS Code): Commit visualization relative to each other
- SourceTree: Detailed branch and commit graphs
- GitUp: Real-time graph updates with perfect clarity

### Academic Research
- ["Branching Conversations Enable Nonlinear Exploration"](https://medium.com/@nikivergis/ai-chat-tools-dont-match-how-we-actually-think-exploring-the-ux-of-branching-conversations-259107496afb) - Medium article analyzing why branching matters
- ["How AI Is Transforming User Interfaces"](https://promptengineering.org/how-ai-is-transforming-user-interfaces-the-conversation/) - Conversational UI design patterns

---

**Document Version**: 1.0
**Created**: 2025-10-18
**Next Review**: After usability testing (Phase 2)
**Maintainer**: UI/UX Designer Agent

**Related Documents**:
- [Part 1: Enterprise AI Hub UI/UX Design](./enterprise-ai-hub-uiux-design.md)
- [Part 2: Interactive Widget Response System](./widget-response-technical-spec.md)
- [Part 3: UI/UX Design Principles](./uiux-design-principles.md)
- [Flutter Design System](./flutter-design-system.md)
