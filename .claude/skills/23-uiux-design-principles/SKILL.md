---
name: uiux-design-principles
description: "Framework-agnostic UI/UX design principles and guidelines for enterprise applications. CRITICAL for ALL frontend work regardless of framework (React, Flutter, etc.). Use when asking about 'design principles', 'layout', 'visual hierarchy', 'information architecture', 'enterprise UX', 'responsive design', 'accessibility', 'design system', 'top-down design', 'component design', 'user experience', or any frontend design decisions."
---

# UI/UX Design Principles

Framework-agnostic design principles and patterns for building professional enterprise applications. This skill is **CRITICAL** for all frontend work and should be invoked proactively before any UI implementation.

## Overview

This skill provides:
- Top-down design methodology (layout → features → components → details)
- Layout and information architecture patterns
- Visual hierarchy principles (F-pattern, Z-pattern, inverted pyramid)
- Enterprise UX patterns (action hierarchy, search & filter, bulk actions)
- Component design guidelines (cards, buttons, empty states, loading states)
- Responsive design patterns for all breakpoints
- Accessibility standards (WCAG 2.1 AA compliance)
- Design system principles and naming conventions
- Common pitfalls and solutions

## Reference Documentation

### Core Principles
- **[design-principles](design-principles.md)** - Complete UI/UX design principles and guidelines
  - Top-down design methodology
  - Layout & information architecture
  - Visual hierarchy principles
  - Enterprise UX patterns
  - Component design guidelines
  - Responsive design patterns
  - Accessibility standards
  - Design system principles
  - Common pitfalls & solutions

## Quick Patterns

### Top-Down Design Order (ALWAYS Follow This)
```
LEVEL 1: FRAME/LAYOUT (Highest Priority)
  ↓ Space division, visual hierarchy, information architecture
LEVEL 2: FEATURE COMMUNICATION
  ↓ Discoverability, action hierarchy, navigation
LEVEL 3: COMPONENT EFFECTIVENESS
  ↓ Widget appropriateness, interaction patterns, feedback
LEVEL 4: VISUAL DETAILS (Lowest Priority)
  → Colors, shadows, animations, typography refinements
```

### The 70/30 Rule
- 70% of space = primary content (what user came to see/do)
- 30% of space = secondary UI (navigation, filters, chrome)

### Action Hierarchy
| Type | Size | Style | Position | Use |
|------|------|-------|----------|-----|
| Primary | 48px | Filled | Top-right | 1 per page (Save, Add) |
| Secondary | 40px | Outlined | Near primary | 2-3 per page (Cancel, Export) |
| Tertiary | 32px | Text | Contextual | Unlimited (Edit, View) |

### View Type Decision
| Data Type | Recommended View |
|-----------|------------------|
| Visual content (faces, photos) | Grid (2-4 columns) |
| Structured data (many fields) | Table (sortable) |
| Mobile/narrow screens | List (single column) |
| Mixed visual + data | Grid with Table toggle |

## CRITICAL Gotchas

| Rule | Why |
|------|-----|
| ❌ NEVER design bottom-up | Perfecting shadows on misplaced cards wastes effort |
| ✅ ALWAYS start with layout | Solve fundamental usability issues first |
| ❌ NEVER hide primary actions | Users must find main CTA without keyboard shortcuts |
| ✅ ALWAYS have persistent primary CTA | Visible button + keyboard shortcut for power users |
| ❌ NEVER use color as sole indicator | Accessibility requires icons + text for status |
| ✅ ALWAYS test on all breakpoints | Mobile, tablet, desktop must all work |

## When to Use This Skill

Use this skill **PROACTIVELY** when:
- Starting ANY frontend feature or page design
- Reviewing or auditing existing UI/UX
- Making layout or spacing decisions
- Designing navigation or information architecture
- Creating or extending design systems
- Implementing responsive layouts
- Ensuring accessibility compliance
- Resolving visual design problems

## Related Skills

- **[11-frontend-integration](../11-frontend-integration/SKILL.md)** - Technical integration patterns
- **[19-flutter-patterns](../19-flutter-patterns/SKILL.md)** - Flutter-specific implementation
- **[21-enterprise-ai-ux](../21-enterprise-ai-ux/SKILL.md)** - AI application UX patterns
- **[22-conversation-ux](../22-conversation-ux/SKILL.md)** - Conversation UI patterns

## Support

For UI/UX design questions, invoke:
- `uiux-designer` - Design analysis and recommendations
- `frontend-developer` - Implementation guidance
- `flutter-specialist` - Flutter/Material Design implementation
- `react-specialist` - React component implementation
