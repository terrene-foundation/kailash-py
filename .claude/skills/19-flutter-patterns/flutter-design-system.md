# Flutter Design System Usage Guide

**Purpose**: Institutionalized directive for Claude Code and flutter-specialist to maintain design consistency across all Flutter features.

**Status**: Production Standard ✅
**Last Updated**: October 9, 2025
**Applies To**: All Flutter feature development

---

## 🎯 Core Directive

**MANDATORY**: All Flutter UI development MUST use the Design System components located in `lib/core/design/`.

**DO NOT** create UI components from scratch unless explicitly required for novel functionality not covered by the design system.

---

## 📚 Design System Location

```
lib/core/design/
├── design_system.dart          # Single import file - USE THIS
├── colors.dart                 # Color palette
├── colors_dark.dart            # Dark mode colors
├── typography.dart             # Text styles
├── spacing.dart                # Spacing constants
├── shadows.dart                # Elevation system
├── theme.dart                  # Material theme
├── responsive.dart             # Responsive widgets
├── components/                 # 16 production components
│   ├── app_button.dart
│   ├── app_card.dart
│   ├── app_input.dart
│   ├── app_app_bar.dart
│   ├── app_avatar.dart
│   ├── app_badge.dart
│   ├── app_chip.dart
│   ├── app_data_table.dart
│   ├── app_dialog.dart
│   ├── app_command_palette.dart
│   ├── app_form_controls.dart
│   ├── app_network_graph.dart
│   ├── app_skeleton.dart
│   ├── app_timeline.dart
│   └── [2 more components]
└── examples/
    └── component_showcase.dart  # Live demo app
```

---

## 🚀 Quick Start Pattern

### Step 1: Single Import
```dart
import 'package:<app>/core/design/design_system.dart';

// This imports:
// - All components (AppButton, AppCard, etc.)
// - Design tokens (AppColors, AppTypography, AppSpacing)
// - Responsive widgets (ResponsiveBuilder, AdaptiveGrid)
// - Theme configuration
```

### Step 2: Use Components Directly
```dart
// ✅ CORRECT - Use design system components
AppButton.primary(
  label: 'Save Changes',
  onPressed: _handleSave,
)

// ❌ WRONG - Do NOT create custom buttons
ElevatedButton(
  child: Text('Save Changes'),
  onPressed: _handleSave,
)
```

---

## 🎨 Design Tokens Usage

### Colors
```dart
// Primary actions
AppColors.primary
AppColors.primaryLight
AppColors.primaryDark

// Secondary actions
AppColors.secondary
AppColors.secondaryLight

// Semantic colors
AppColors.success
AppColors.warning
AppColors.error
AppColors.info

// Surfaces
AppColors.surface
AppColors.background
AppColors.cardBackground

// Text
AppColors.textPrimary
AppColors.textSecondary
AppColors.textDisabled

// Dark mode equivalents
AppColorsDark.primary
AppColorsDark.background
// ... etc.
```

### Typography
```dart
// Headings
AppTypography.h1
AppTypography.h2
AppTypography.h3
AppTypography.h4

// Body text
AppTypography.bodyLarge
AppTypography.bodyMedium
AppTypography.bodySmall

// Labels and captions
AppTypography.labelLarge
AppTypography.labelMedium
AppTypography.caption

// Usage
Text('Welcome', style: AppTypography.h2)
Text('Description', style: AppTypography.bodyMedium)
```

### Spacing
```dart
// Standard scale
AppSpacing.xs   // 4px
AppSpacing.sm   // 8px
AppSpacing.md   // 16px
AppSpacing.lg   // 24px
AppSpacing.xl   // 32px
AppSpacing.xxl  // 48px

// Gap widgets (for Column/Row)
AppSpacing.gapSm
AppSpacing.gapMd
AppSpacing.gapLg

// Padding helpers
AppSpacing.allMd  // EdgeInsets.all(16)
AppSpacing.horizontalLg  // EdgeInsets.horizontal(24)
AppSpacing.verticalMd  // EdgeInsets.vertical(16)

// Border radius
AppSpacing.borderRadiusSm   // Radius.circular(4)
AppSpacing.borderRadiusMd   // Radius.circular(8)
AppSpacing.borderRadiusLg   // Radius.circular(12)
```

### Shadows
```dart
// Elevation levels
AppShadows.none
AppShadows.card        // 2dp elevation
AppShadows.raised      // 4dp elevation
AppShadows.elevated    // 8dp elevation
AppShadows.modal       // 16dp elevation

// Specialized
AppShadows.appBar
AppShadows.bottomSheet
AppShadows.hover
AppShadows.focus
```

---

## 🧩 Component Patterns

### Button Variants
```dart
// Primary action (filled, high emphasis)
AppButton.primary(
  label: 'Submit',
  onPressed: _submit,
)

// Secondary action (tonal, medium emphasis)
AppButton.secondary(
  label: 'Cancel',
  onPressed: _cancel,
)

// Tertiary action (outlined, low emphasis)
AppButton.outlined(
  label: 'Learn More',
  onPressed: _learnMore,
)

// Text-only action (minimal emphasis)
AppButton.text(
  label: 'Skip',
  onPressed: _skip,
)

// With loading state
AppButton.primary(
  label: 'Saving...',
  onPressed: _save,
  isLoading: _isSaving,
)

// With icons
AppButton.primary(
  label: 'Download',
  leadingIcon: Icons.download,
  onPressed: _download,
)
```

### Card Layouts
```dart
// Standard card
AppCard(
  child: Column(
    children: [
      Text('Title', style: AppTypography.h4),
      AppSpacing.gapMd,
      Text('Content', style: AppTypography.bodyMedium),
    ],
  ),
)

// Card with header/footer
AppCard(
  header: Padding(
    padding: AppSpacing.allMd,
    child: Text('Header', style: AppTypography.h4),
  ),
  child: Text('Content'),
  footer: AppButton.primary(
    label: 'Action',
    onPressed: _action,
  ),
)

// Info card variants
AppCard.info(
  title: 'Success',
  message: 'Operation completed',
  type: InfoCardType.success,
)

// Stat card with trends
AppCard.stat(
  label: 'Total Users',
  value: '1,234',
  trend: TrendIndicator.up,
  trendValue: '+12%',
)
```

### Form Inputs
```dart
// Standard text input
AppInput(
  label: 'Full Name',
  hint: 'Enter your full name',
  controller: _nameController,
  isRequired: true,
)

// Specialized inputs
AppInput.email(
  label: 'Email Address',
  controller: _emailController,
)

AppInput.password(
  label: 'Password',
  controller: _passwordController,
)

AppInput.phone(
  label: 'Phone Number',
  controller: _phoneController,
)

AppInput.multiline(
  label: 'Description',
  controller: _descController,
  maxLines: 5,
)

// With validation
AppInput(
  label: 'Username',
  controller: _usernameController,
  validator: (value) {
    if (value == null || value.isEmpty) {
      return 'Username is required';
    }
    return null;
  },
)
```

### Data Display
```dart
// Data table
AppDataTable(
  columns: [
    DataColumn(label: Text('Name')),
    DataColumn(label: Text('Email')),
    DataColumn(label: Text('Role')),
  ],
  rows: contacts.map((contact) => DataRow(
    cells: [
      DataCell(Text(contact.name)),
      DataCell(Text(contact.email)),
      DataCell(Text(contact.role)),
    ],
  )).toList(),
)

// Timeline
AppTimeline(
  events: [
    TimelineEvent(
      title: 'Project Started',
      description: 'Initial kickoff meeting',
      timestamp: DateTime.now(),
      icon: Icons.rocket_launch,
    ),
    // ... more events
  ],
)

// Network graph
AppNetworkGraph(
  nodes: [
    NetworkNode(id: '1', label: 'Person A'),
    NetworkNode(id: '2', label: 'Person B'),
  ],
  connections: [
    NetworkConnection(fromNodeId: '1', toNodeId: '2'),
  ],
  layoutAlgorithm: GraphLayoutAlgorithm.force,
)
```

---

## 📱 Responsive Patterns

### Breakpoint-Based Layouts
```dart
ResponsiveBuilder(
  mobile: _buildMobileLayout(),
  tablet: _buildTabletLayout(),
  desktop: _buildDesktopLayout(),
)

// Breakpoints:
// - Mobile: < 600px
// - Tablet: 600-1024px
// - Desktop: >= 1024px
```

### Adaptive Grid
```dart
AdaptiveGrid(
  children: [
    _buildCard('Item 1'),
    _buildCard('Item 2'),
    _buildCard('Item 3'),
  ],
  // Automatically adjusts:
  // Mobile: 1 column
  // Tablet: 2 columns
  // Desktop: 3 columns
)

// Custom columns
AdaptiveGrid(
  mobileColumns: 1,
  tabletColumns: 2,
  desktopColumns: 4,
  children: [...],
)
```

### Adaptive Filter
```dart
AdaptiveFilter(
  filters: [
    FilterChip(label: Text('Active'), onSelected: _onFilter),
    FilterChip(label: Text('Inactive'), onSelected: _onFilter),
  ],
  // Mobile: Vertical list
  // Desktop: Horizontal grid/wrap
)
```

### Adaptive Form
```dart
AdaptiveForm(
  fields: [
    AppInput(label: 'Name'),
    AppInput(label: 'Email'),
    AppInput(label: 'Phone'),
  ],
  // Mobile: Stacked vertically
  // Desktop: Wrapped with fixed width (300px)
)
```

---

## 🎭 Dark Mode Support

### Theme Switching
```dart
// Use theme-aware colors
final isDark = Theme.of(context).brightness == Brightness.dark;

final backgroundColor = isDark
  ? AppColorsDark.background
  : AppColors.background;

// Better: Use theme directly
final backgroundColor = Theme.of(context).colorScheme.background;
```

### Component Dark Mode
All design system components support dark mode automatically:
```dart
// ✅ Automatically adapts
AppCard(
  child: Text('Content'),
)

// ✅ Uses theme colors
AppButton.primary(
  label: 'Action',
  onPressed: _action,
)
```

---

## ✅ Implementation Checklist

Before creating any UI feature, verify:

- [ ] Imported `design_system.dart` (single import)
- [ ] Used existing components (AppButton, AppCard, etc.)
- [ ] Used design tokens (AppColors, AppTypography, AppSpacing)
- [ ] Implemented responsive layout (ResponsiveBuilder, AdaptiveGrid)
- [ ] Tested in light AND dark mode
- [ ] Followed spacing system (no magic numbers)
- [ ] Used semantic colors (success, warning, error, info)
- [ ] Tested at all breakpoints (mobile, tablet, desktop)

---

## 🚫 Anti-Patterns (DO NOT DO)

### ❌ Creating Custom Components
```dart
// WRONG - Creating custom button
class MyCustomButton extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.blue,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text('Click me'),
    );
  }
}

// RIGHT - Use design system
AppButton.primary(
  label: 'Click me',
  onPressed: _action,
)
```

### ❌ Hardcoding Colors
```dart
// WRONG - Magic color values
Container(
  color: Color(0xFF1976D2),
)

// RIGHT - Use design tokens
Container(
  color: AppColors.primary,
)
```

### ❌ Hardcoding Spacing
```dart
// WRONG - Magic numbers
Padding(
  padding: EdgeInsets.all(16),
  child: ...
)

// RIGHT - Use spacing constants
Padding(
  padding: AppSpacing.allMd,
  child: ...
)
```

### ❌ Manual Responsive Logic
```dart
// WRONG - MediaQuery breakpoints
final width = MediaQuery.of(context).size.width;
if (width < 600) {
  return MobileLayout();
} else {
  return DesktopLayout();
}

// RIGHT - Use ResponsiveBuilder
ResponsiveBuilder(
  mobile: MobileLayout(),
  desktop: DesktopLayout(),
)
```

---

## 🔄 When to Extend the Design System

### Creating New Components

Only create new components when:
1. No existing component fits the use case
2. The component is reusable across 3+ features
3. You've verified with flutter-specialist

**Process**:
1. Create `lib/core/design/components/app_[component].dart`
2. Follow naming convention: `App` prefix
3. Support light/dark mode
4. Add to `design_system.dart` exports
5. Add to component showcase
6. Write widget tests
7. Document in README

### Extending Existing Components

If a component needs new features:
1. Add new parameters to existing component
2. Maintain backward compatibility
3. Update component showcase
4. Update tests
5. Document new features

---

## 📖 Reference Documentation

### Primary Resources
- **Component API**: `lib/core/design/README.md`
- **Live Examples**: Run `lib/core/design/examples/component_showcase.dart`
- **Design Guidelines**: `docs/DESIGN_GUIDELINES.md`
- **API Documentation**: `docs/API.md`

### Component List (16 components)
1. AppButton - Buttons with variants
2. AppCard - Cards with layouts
3. AppInput - Form inputs
4. AppAppBar - App bars
5. AppAvatar - User avatars
6. AppBadge - Notification badges
7. AppChip - Filter/selection chips
8. AppDataTable - Data tables
9. AppDialog - Modals/dialogs
10. AppCommandPalette - Command palette
11. AppFormControls - Checkboxes, switches, radio
12. AppNetworkGraph - Network visualization
13. AppSkeleton - Loading states
14. AppTimeline - Event timelines
15. [Component 15]
16. [Component 16]

---

## 🎯 Success Criteria

A feature properly uses the design system when:

✅ **Zero custom UI components** created (unless justified)
✅ **100% design token usage** (no hardcoded colors, spacing, typography)
✅ **Responsive across all breakpoints** (mobile, tablet, desktop)
✅ **Dark mode support** (automatic through theme)
✅ **Consistent with showcase** (same look and feel)
✅ **Accessible** (keyboard navigation, screen readers)
✅ **Performant** (60fps, no jank)

---

## 🤖 Flutter-Specialist Directives

When implementing Flutter features:

1. **ALWAYS** check `component_showcase.dart` first for examples
2. **ALWAYS** use `design_system.dart` single import
3. **ALWAYS** implement responsive layouts with `ResponsiveBuilder`
4. **ALWAYS** test in light AND dark mode
5. **NEVER** create custom UI components without justification
6. **NEVER** hardcode colors, spacing, or typography
7. **VERIFY** all breakpoints (360px mobile, 768px tablet, 1024px+ desktop)

---

**Last Reviewed**: October 9, 2025
**Next Review**: When adding new components or breaking changes
