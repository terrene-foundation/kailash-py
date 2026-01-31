---
name: interactive-widgets
description: "Interactive widget systems for AI applications including LLM-driven widget generation, dynamic UI components, form builders, and streaming response widgets. Use when asking about 'interactive widgets', 'dynamic UI', 'LLM widgets', 'widget generation', 'streaming widgets', 'form widgets', 'AI response widgets', 'structured responses', or 'widget protocol'."
---

# Interactive Widget System

Production-ready patterns for building interactive widget systems that integrate with AI/LLM backends for dynamic, structured user interfaces.

## Overview

Interactive widget patterns for:
- LLM-driven widget generation
- Streaming response with structured components
- Dynamic form builders
- Action-response patterns
- Widget protocol design

## Reference Documentation

### System Overview
- **[overview](overview.md)** - Widget system architecture and navigation
  - System components
  - Documentation structure
  - Quick reference

### Technical Specification
- **[technical-spec](technical-spec.md)** - Complete technical specification
  - Widget protocol design
  - Backend integration
  - Frontend rendering
  - State management
  - Error handling

### Implementation Guide
- **[implementation-guide](implementation-guide.md)** - Step-by-step implementation
  - Backend widget generation
  - Frontend widget rendering
  - Event handling
  - Real-world examples

## Quick Patterns

### Widget Protocol (JSON)
```json
{
  "type": "form",
  "id": "user-input-form",
  "content": {
    "fields": [
      {
        "type": "text",
        "name": "query",
        "label": "Enter your question",
        "required": true
      }
    ],
    "actions": [
      {
        "type": "submit",
        "label": "Send",
        "action": "submit_query"
      }
    ]
  }
}
```

### Backend Widget Generation (Python)
```python
def generate_widget_response(user_query: str) -> dict:
    """Generate structured widget response from LLM."""
    response = llm.generate(
        prompt=f"Generate a widget response for: {user_query}",
        output_schema=WidgetSchema
    )
    return {
        "type": response.widget_type,
        "content": response.content,
        "actions": response.available_actions
    }
```

### Frontend Widget Renderer (Dart)
```dart
Widget buildWidget(Map<String, dynamic> widgetData) {
  switch (widgetData['type']) {
    case 'form':
      return FormWidget(data: widgetData['content']);
    case 'card':
      return CardWidget(data: widgetData['content']);
    case 'table':
      return TableWidget(data: widgetData['content']);
    default:
      return TextWidget(data: widgetData['content']);
  }
}
```

## Widget Types

| Type | Purpose | Use Case |
|------|---------|----------|
| `text` | Plain text response | Simple answers |
| `card` | Structured information | Entity displays |
| `form` | User input collection | Queries, settings |
| `table` | Tabular data | Lists, comparisons |
| `chart` | Data visualization | Analytics, metrics |
| `action` | Clickable actions | Workflows, confirmations |
| `progress` | Progress indication | Long-running tasks |

## CRITICAL Gotchas

| Rule | Why |
|------|-----|
| ❌ NEVER trust widget IDs from client | Security - validate server-side |
| ✅ ALWAYS validate widget schemas | Prevent malformed rendering |
| ❌ NEVER block UI on widget generation | Use streaming for responsiveness |
| ✅ ALWAYS handle unknown widget types | Graceful degradation |

## When to Use This Skill

Use this skill when:
- Building AI chat interfaces with structured responses
- Creating dynamic form systems
- Implementing streaming UI components
- Designing widget protocols for LLM integration
- Building action-response patterns

## Related Skills

- **[04-kaizen](../04-kaizen/SKILL.md)** - AI agent framework
- **[19-flutter-patterns](../19-flutter-patterns/SKILL.md)** - Flutter components
- **[22-conversation-ux](../22-conversation-ux/SKILL.md)** - Conversation UX

## Support

For widget system questions, invoke:
- `kaizen-specialist` - LLM integration patterns
- `flutter-specialist` - Widget rendering
- `pattern-expert` - Protocol design
