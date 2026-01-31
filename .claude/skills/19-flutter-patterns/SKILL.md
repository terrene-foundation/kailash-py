---
name: flutter-patterns
description: "Flutter development patterns including design system creation, responsive layouts, state management, and cross-platform best practices. Use when asking about 'Flutter design system', 'Flutter patterns', 'responsive Flutter', 'Flutter components', 'Flutter theming', 'dark mode', 'Flutter architecture', or 'cross-platform Flutter'."
---

# Flutter Development Patterns

Production-ready patterns for Flutter application development including design systems, responsive layouts, and enterprise-grade component libraries.

## Overview

Flutter patterns for:
- Design system creation and management
- Responsive layout strategies
- Component library architecture
- State management patterns
- Cross-platform considerations

## Reference Documentation

### Design System Creation
- **[creating-design-system](creating-design-system.md)** - Complete guide to creating Flutter design systems
  - Phase-based implementation approach
  - Token systems (colors, typography, spacing)
  - Component architecture
  - Responsive patterns
  - Dark mode support
  - Documentation standards

### Design System Usage
- **[flutter-design-system](flutter-design-system.md)** - Institutionalized design system usage directive
  - Design system location and structure
  - Single import pattern
  - Component usage examples
  - Mandatory usage rules

### Testing Patterns
- **[flutter-testing-patterns](flutter-testing-patterns.md)** - Flutter testing strategies
  - Widget testing patterns
  - Integration testing
  - Golden tests
  - Test organization

## Quick Patterns

### Design Token System
```dart
abstract class AppColors {
  // Primary palette
  static const primary = Color(0xFF2563EB);
  static const primaryLight = Color(0xFF3B82F6);
  static const primaryDark = Color(0xFF1D4ED8);

  // Semantic colors
  static const success = Color(0xFF10B981);
  static const warning = Color(0xFFF59E0B);
  static const error = Color(0xFFEF4444);
}

abstract class AppSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
}
```

### Responsive Breakpoints
```dart
class Breakpoints {
  static const mobile = 600.0;
  static const tablet = 900.0;
  static const desktop = 1200.0;

  static bool isMobile(BuildContext context) =>
    MediaQuery.of(context).size.width < mobile;
}
```

### Component Base Pattern
```dart
class AppButton extends StatelessWidget {
  final String label;
  final VoidCallback onPressed;
  final ButtonVariant variant;

  const AppButton({
    required this.label,
    required this.onPressed,
    this.variant = ButtonVariant.primary,
  });

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: onPressed,
      style: _getStyle(variant),
      child: Text(label),
    );
  }
}
```

## CRITICAL Gotchas

| Rule | Why |
|------|-----|
| ❌ NEVER hardcode colors | Use design tokens |
| ✅ ALWAYS use const constructors | Performance optimization |
| ❌ NEVER use magic numbers | Use spacing tokens |
| ✅ ALWAYS test on multiple screen sizes | Responsive verification |

## When to Use This Skill

Use this skill when:
- Creating a new Flutter design system
- Building reusable component libraries
- Implementing responsive layouts
- Setting up theme systems (light/dark mode)
- Architecting Flutter applications

## Related Skills

- **[11-frontend-integration](../11-frontend-integration/SKILL.md)** - Frontend integration patterns
- **[17-gold-standards](../17-gold-standards/SKILL.md)** - Best practices
- **[21-enterprise-ai-ux](../21-enterprise-ai-ux/SKILL.md)** - Enterprise UX patterns
- **[23-uiux-design-principles](../23-uiux-design-principles/SKILL.md)** - Framework-agnostic design principles (CRITICAL)

## Support

For Flutter pattern questions, invoke:
- `flutter-specialist` - Flutter-specific implementation
- `uiux-designer` - Design system decisions
- `pattern-expert` - Architecture patterns
