---
name: conversation-ux
description: "Conversation UX patterns for AI applications including multi-conversation management, branching threads, context switching, and chat history organization. Use when asking about 'conversation UX', 'multi-conversation', 'chat threads', 'conversation branching', 'chat history', 'context switching', 'Lark-style chat', 'conversation management', or 'thread navigation'."
---

# Conversation UX Patterns

Production-ready UX patterns for managing complex conversational interfaces including multi-thread management, branching conversations, and context switching.

## Overview

Conversation UX patterns for:
- Multi-conversation management
- Thread branching and navigation
- Context switching strategies
- History organization
- Session persistence

## Reference Documentation

### Multi-Conversation Patterns
- **[multi-conversation-patterns](multi-conversation-patterns.md)** - Lark-style conversation UX
  - Research insights
  - Design patterns
  - Implementation strategies
  - Navigation patterns

## Quick Patterns

### Conversation List Structure
```dart
class ConversationList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      itemBuilder: (context, index) {
        return ConversationTile(
          title: conversation.title,
          preview: conversation.lastMessage,
          timestamp: conversation.updatedAt,
          unreadCount: conversation.unreadCount,
          isPinned: conversation.isPinned,
          avatar: conversation.avatar,
        );
      },
    );
  }
}
```

### Branching Conversation Model
```dart
class Conversation {
  final String id;
  final String? parentId;        // null for root conversations
  final List<Message> messages;
  final DateTime createdAt;
  final String title;
  final ConversationState state;

  // Branch from a specific message
  Conversation branch(Message fromMessage) {
    return Conversation(
      parentId: this.id,
      branchPoint: fromMessage.id,
      messages: [fromMessage.copy()], // Copy message as new root
    );
  }
}
```

### Context Switching Pattern
```dart
class ConversationProvider extends ChangeNotifier {
  Conversation? _active;
  final List<Conversation> _recent = [];

  void switchTo(Conversation conversation) {
    if (_active != null) {
      _addToRecent(_active!);
    }
    _active = conversation;
    notifyListeners();
  }

  // Quick switch maintains context
  void quickSwitch(int recentIndex) {
    if (recentIndex < _recent.length) {
      final target = _recent[recentIndex];
      _recent.removeAt(recentIndex);
      switchTo(target);
    }
  }
}
```

### Navigation Layout (Lark-Style)
```
┌───────────────┬─────────────────────────────────────────────┐
│               │                                             │
│  SIDEBAR      │              CONVERSATION                   │
│               │                                             │
│ ┌───────────┐ │  ┌─────────────────────────────────────┐   │
│ │ + New     │ │  │ Context: Project Alpha              │   │
│ └───────────┘ │  └─────────────────────────────────────┘   │
│               │                                             │
│ PINNED        │  ┌─────────────────────────────────────┐   │
│ ├─ Project A  │  │ User: How do I...                   │   │
│ └─ Important  │  └─────────────────────────────────────┘   │
│               │                                             │
│ TODAY         │  ┌─────────────────────────────────────┐   │
│ ├─ Chat 1     │  │ AI: Here's how...                   │   │
│ └─ Chat 2     │  │                                     │   │
│               │  │ [Branch from here]                   │   │
│ YESTERDAY     │  └─────────────────────────────────────┘   │
│ └─ Chat 3     │                                             │
│               │  ┌─────────────────────────────────────┐   │
│ OLDER         │  │ [Input Area]                        │   │
│ └─ Archive    │  └─────────────────────────────────────┘   │
│               │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

### Thread Branch Indicator
```dart
class BranchIndicator extends StatelessWidget {
  final int branchCount;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    if (branchCount == 0) return SizedBox.shrink();

    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: Colors.blue.withOpacity(0.1),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.call_split, size: 14),
            SizedBox(width: 4),
            Text('$branchCount branches'),
          ],
        ),
      ),
    );
  }
}
```

## Conversation States

| State | Description | Visual Indicator |
|-------|-------------|------------------|
| `active` | Currently selected | Highlighted background |
| `recent` | Used in last 24h | Normal styling |
| `archived` | Older conversations | Muted styling |
| `pinned` | User-marked important | Pin icon + top section |
| `branched` | Has child threads | Branch icon |

## CRITICAL Gotchas

| Rule | Why |
|------|-----|
| ❌ NEVER lose conversation context | User frustration |
| ✅ ALWAYS auto-save drafts | Prevent message loss |
| ❌ NEVER force linear navigation | Allow quick switching |
| ✅ ALWAYS show branch points | Navigation clarity |

## When to Use This Skill

Use this skill when:
- Building multi-conversation chat apps
- Implementing conversation branching
- Designing chat history management
- Creating context-aware navigation
- Building Slack/Discord-style interfaces

## Related Skills

- **[20-interactive-widgets](../20-interactive-widgets/SKILL.md)** - Widget systems
- **[21-enterprise-ai-ux](../21-enterprise-ai-ux/SKILL.md)** - Enterprise patterns
- **[19-flutter-patterns](../19-flutter-patterns/SKILL.md)** - Flutter implementation

## Support

For conversation UX questions, invoke:
- `uiux-designer` - UX decisions
- `flutter-specialist` - Flutter implementation
- `frontend-developer` - React/web implementation
