# Flutter Design System

**MANDATORY**: All Flutter UI MUST use Design System components in `lib/core/design/`. DO NOT create UI components from scratch unless explicitly required for novel functionality.

## Location

```
lib/core/design/
├── design_system.dart          # Single import file - USE THIS
├── colors.dart / colors_dark.dart / typography.dart / spacing.dart / shadows.dart
├── theme.dart / responsive.dart
├── components/                 # 16 production components
│   ├── app_button.dart, app_card.dart, app_input.dart, app_app_bar.dart
│   ├── app_avatar.dart, app_badge.dart, app_chip.dart, app_data_table.dart
│   ├── app_dialog.dart, app_command_palette.dart, app_form_controls.dart
│   ├── app_network_graph.dart, app_skeleton.dart, app_timeline.dart
│   └── [2 more]
└── examples/component_showcase.dart
```

## Single Import

```dart
import 'package:<app>/core/design/design_system.dart';
// Imports all components, tokens, responsive widgets, and theme
```

## Design Tokens

```dart
// Colors
AppColors.primary / primaryLight / primaryDark
AppColors.secondary / success / warning / error / info
AppColors.surface / background / cardBackground
AppColors.textPrimary / textSecondary / textDisabled
AppColorsDark.primary / background  // Dark mode equivalents

// Typography
AppTypography.h1 / h2 / h3 / h4
AppTypography.bodyLarge / bodyMedium / bodySmall
AppTypography.labelLarge / labelMedium / caption

// Spacing (standard scale)
AppSpacing.xs(4) / sm(8) / md(16) / lg(24) / xl(32) / xxl(48)
AppSpacing.gapSm / gapMd / gapLg          // SizedBox gaps
AppSpacing.allMd / horizontalLg / verticalMd  // EdgeInsets helpers
AppSpacing.borderRadiusSm(4) / borderRadiusMd(8) / borderRadiusLg(12)

// Shadows
AppShadows.none / card(2dp) / raised(4dp) / elevated(8dp) / modal(16dp)
AppShadows.appBar / bottomSheet / hover / focus
```

## Components

### Buttons

```dart
AppButton.primary(label: 'Submit', onPressed: _submit)
AppButton.secondary(label: 'Cancel', onPressed: _cancel)
AppButton.outlined(label: 'Learn More', onPressed: _learnMore)
AppButton.text(label: 'Skip', onPressed: _skip)
AppButton.primary(label: 'Saving...', onPressed: _save, isLoading: _isSaving)
AppButton.primary(label: 'Download', leadingIcon: Icons.download, onPressed: _download)
```

### Cards

```dart
AppCard(child: Column(children: [Text('Title', style: AppTypography.h4), AppSpacing.gapMd, Text('Content')]))
AppCard(header: ..., child: ..., footer: ...)
AppCard.info(title: 'Success', message: 'Done', type: InfoCardType.success)
AppCard.stat(label: 'Total Users', value: '1,234', trend: TrendIndicator.up, trendValue: '+12%')
```

### Inputs

```dart
AppInput(label: 'Full Name', hint: 'Enter name', controller: _ctrl, isRequired: true)
AppInput.email(label: 'Email', controller: _emailCtrl)
AppInput.password(label: 'Password', controller: _pwCtrl)
AppInput.phone(label: 'Phone', controller: _phoneCtrl)
AppInput.multiline(label: 'Description', controller: _descCtrl, maxLines: 5)
AppInput(label: 'Username', controller: _ctrl, validator: (v) => v?.isEmpty ?? true ? 'Required' : null)
```

### Data Display

```dart
AppDataTable(columns: [...], rows: contacts.map((c) => DataRow(cells: [...])).toList())
AppTimeline(events: [TimelineEvent(title: '...', timestamp: DateTime.now(), icon: Icons.rocket_launch)])
AppNetworkGraph(nodes: [...], connections: [...], layoutAlgorithm: GraphLayoutAlgorithm.force)
```

## Responsive Patterns

```dart
// Breakpoint layouts (Mobile <600, Tablet 600-1024, Desktop >=1024)
ResponsiveBuilder(mobile: _mobileLayout(), tablet: _tabletLayout(), desktop: _desktopLayout())

// Adaptive grid (auto-adjusts columns per breakpoint)
AdaptiveGrid(children: [...])
AdaptiveGrid(mobileColumns: 1, tabletColumns: 2, desktopColumns: 4, children: [...])

// Adaptive form/filter
AdaptiveForm(fields: [AppInput(label: 'Name'), AppInput(label: 'Email')])
AdaptiveFilter(filters: [FilterChip(label: Text('Active'), onSelected: _onFilter)])
```

## Dark Mode

All components adapt automatically. For manual checks:

```dart
final backgroundColor = Theme.of(context).colorScheme.background;
```

## MUST Rules

- ALWAYS import `design_system.dart` (single import)
- ALWAYS use existing components (AppButton, AppCard, etc.)
- ALWAYS use design tokens (no hardcoded colors, spacing, typography)
- ALWAYS use ResponsiveBuilder for layouts
- ALWAYS test light AND dark mode at all breakpoints (360px, 768px, 1024px+)
- NEVER create custom UI components without justification
- NEVER hardcode colors (`Color(0xFF1976D2)`) -- use `AppColors.primary`
- NEVER hardcode spacing (`EdgeInsets.all(16)`) -- use `AppSpacing.allMd`
- NEVER use manual MediaQuery breakpoints -- use `ResponsiveBuilder`

## Extending the Design System

Only create new components when: (1) no existing component fits, (2) reusable across 3+ features, (3) verified with flutter-specialist.

Process: Create `lib/core/design/components/app_[name].dart`, support light/dark, add to `design_system.dart` exports, add to showcase, write tests.
