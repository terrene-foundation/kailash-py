---
name: enterprise-ai-ux
description: "Enterprise AI application UX patterns including conversational interfaces, context management, challenge resolution, and professional design systems. Use when asking about 'enterprise AI UX', 'AI chat UX', 'enterprise design system', 'professional UI', 'conversation design', 'context indicators', 'challenge taxonomy', or 'AI application design'."
---

# Enterprise AI Application UX

Production-ready UX patterns for building enterprise-grade AI applications with professional aesthetics, conversational interfaces, and comprehensive context management.

## Overview

Enterprise AI UX patterns for:
- Professional conversational interfaces
- Context and challenge taxonomy
- Design system implementation
- Information hierarchy
- Responsive enterprise layouts

## Reference Documentation

### Enterprise Design
- **[enterprise-design](enterprise-design.md)** - Complete enterprise AI UX guide
  - Challenge taxonomy (7 categories)
  - Design patterns and layouts
  - Component specifications
  - Implementation roadmap

## Quick Patterns

### Challenge Taxonomy
```
┌─────────────────────────────────────────────────────────────┐
│                     CHALLENGE TAXONOMY                       │
├─────────────────────────────────────────────────────────────┤
│ 1. INFORMATION RETRIEVAL                                     │
│    └── "What is X?" "Show me Y" "Find Z"                    │
│                                                              │
│ 2. ANALYSIS & INSIGHT                                        │
│    └── "Analyze X" "Compare Y" "Why is Z?"                  │
│                                                              │
│ 3. CREATION & GENERATION                                     │
│    └── "Create X" "Generate Y" "Draft Z"                    │
│                                                              │
│ 4. WORKFLOW & PROCESS                                        │
│    └── "How to X" "Steps for Y" "Process Z"                 │
│                                                              │
│ 5. CONFIGURATION & SETTINGS                                  │
│    └── "Configure X" "Set up Y" "Enable Z"                  │
│                                                              │
│ 6. TROUBLESHOOTING                                           │
│    └── "Fix X" "Debug Y" "Resolve Z"                        │
│                                                              │
│ 7. LEARNING & GUIDANCE                                       │
│    └── "Teach me X" "Explain Y" "Guide Z"                   │
└─────────────────────────────────────────────────────────────┘
```

### Context Indicator Pattern
```dart
class ContextIndicator extends StatelessWidget {
  final List<ContextItem> contexts;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(Icons.folder_open, size: 14),
        SizedBox(width: 4),
        for (final ctx in contexts)
          ContextChip(label: ctx.name, type: ctx.type),
      ],
    );
  }
}
```

### Professional Color Palette
```dart
// Enterprise AI color scheme
abstract class EnterpriseColors {
  // Primary - Trust and professionalism
  static const primary = Color(0xFF1E3A5F);      // Deep blue
  static const primaryLight = Color(0xFF2E5A8F);

  // AI accent - Intelligence indicator
  static const aiAccent = Color(0xFF6366F1);    // Indigo

  // Semantic
  static const success = Color(0xFF059669);      // Teal
  static const warning = Color(0xFFD97706);      // Amber
  static const error = Color(0xFFDC2626);        // Red

  // Neutrals - Enterprise gray scale
  static const surface = Color(0xFFFAFAFA);
  static const border = Color(0xFFE5E5E5);
  static const textPrimary = Color(0xFF1F2937);
  static const textSecondary = Color(0xFF6B7280);
}
```

### Conversation Layout
```
┌────────────────────────────────────────────────────────────┐
│ [Context Bar: Project | Session | Agent Status]            │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ USER MESSAGE                                         │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
│  ┌─────────────────────────────────────────────────────┐  │
│  │ AI RESPONSE                                          │  │
│  │ ┌─────────────────────────────────────────────────┐ │  │
│  │ │ [Interactive Widget]                             │ │  │
│  │ └─────────────────────────────────────────────────┘ │  │
│  │ [Action Buttons] [Share] [Save]                     │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                            │
├────────────────────────────────────────────────────────────┤
│ [Input Area] [Attachments] [Send]                          │
└────────────────────────────────────────────────────────────┘
```

## CRITICAL Gotchas

| Rule | Why |
|------|-----|
| ❌ NEVER use consumer-style colors | Enterprise = professional palette |
| ✅ ALWAYS show context indicators | Users need orientation |
| ❌ NEVER hide AI thinking process | Transparency builds trust |
| ✅ ALWAYS provide action feedback | Professional responsiveness |

## When to Use This Skill

Use this skill when:
- Building enterprise AI chat applications
- Designing professional AI interfaces
- Implementing context management systems
- Creating challenge-based conversation flows
- Building executive-facing AI tools

## Related Skills

- **[19-flutter-patterns](../19-flutter-patterns/SKILL.md)** - Flutter implementation
- **[20-interactive-widgets](../20-interactive-widgets/SKILL.md)** - Widget systems
- **[22-conversation-ux](../22-conversation-ux/SKILL.md)** - Conversation patterns

## Support

For enterprise AI UX questions, invoke:
- `uiux-designer` - Design decisions
- `flutter-specialist` - Implementation
- `kaizen-specialist` - AI patterns
