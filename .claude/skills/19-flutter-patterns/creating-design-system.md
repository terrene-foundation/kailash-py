# Creating a Flutter Design System from Scratch

Step-by-step guide for new Flutter projects.

---

## Critical Success Factors

1. Create design system BEFORE building features
2. Use design tokens (colors, spacing, typography) not hardcoded values
3. Build 8-16 core components before feature work
4. All components responsive + dark mode from day 1
5. Single import file for all design system access

---

## Phase 1: Project Structure

```
lib/core/
├── design/
│   ├── design_system.dart          # Single export file
│   ├── colors.dart                 # Light mode colors
│   ├── colors_dark.dart            # Dark mode colors
│   ├── typography.dart             # Text styles
│   ├── spacing.dart                # Spacing constants
│   ├── shadows.dart                # Elevation system
│   ├── theme.dart                  # Material theme config
│   ├── responsive.dart             # Responsive utilities
│   ├── components/                 # Component widgets
│   └── examples/component_showcase.dart
└── responsive/
    ├── breakpoints.dart
    ├── responsive_builder.dart
    ├── adaptive_grid.dart
    ├── adaptive_filter.dart
    └── adaptive_form.dart
```

### Single Import File (`design_system.dart`)

```dart
library design_system;
export 'colors.dart';
export 'colors_dark.dart';
export 'typography.dart';
export 'spacing.dart';
export 'shadows.dart';
export 'theme.dart';
export 'responsive.dart';
export '../responsive/breakpoints.dart';
export '../responsive/responsive_builder.dart';
export 'components/app_button.dart';
export 'components/app_card.dart';
export 'components/app_input.dart';
// ... add as you build
```

---

## Phase 2: Design Tokens

### Colors (`colors.dart`)

```dart
class AppColors {
  AppColors._();
  // Primary
  static const Color primary = Color(0xFF1976D2);
  static const Color primaryLight = Color(0xFF42A5F5);
  static const Color primaryDark = Color(0xFF0D47A1);
  // Secondary
  static const Color secondary = Color(0xFF00796B);
  // Surfaces
  static const Color surface = Color(0xFFFFFFFF);
  static const Color background = Color(0xFFF5F5F5);
  static const Color cardBackground = Color(0xFFFFFFFF);
  // Borders
  static const Color border = Color(0xFFE0E0E0);
  static const Color divider = Color(0xFFE0E0E0);
  // Text (WCAG AA compliant)
  static const Color textPrimary = Color(0xFF212121);
  static const Color textSecondary = Color(0xFF757575);
  static const Color textDisabled = Color(0xFFBDBDBD);
  static const Color textOnPrimary = Color(0xFFFFFFFF);
  // Semantic
  static const Color success = Color(0xFF2E7D32);
  static const Color warning = Color(0xFFF57C00);
  static const Color error = Color(0xFFC62828);
  static const Color info = Color(0xFF0277BD);
  // Utility
  static const Color overlay = Color(0x66000000);
  static const Color shadow = Color(0x1A000000);
}
```

### Dark Colors (`colors_dark.dart`)

```dart
class AppColorsDark {
  AppColorsDark._();
  static const Color primary = Color(0xFF90CAF9);
  static const Color surface = Color(0xFF1E1E1E);
  static const Color background = Color(0xFF121212);
  static const Color cardBackground = Color(0xFF2C2C2C);
  static const Color border = Color(0xFF3C3C3C);
  static const Color textPrimary = Color(0xFFE0E0E0);
  static const Color textSecondary = Color(0xFFB0B0B0);
  static const Color success = Color(0xFF66BB6A);
  static const Color warning = Color(0xFFFFB74D);
  static const Color error = Color(0xFFEF5350);
  static const Color info = Color(0xFF29B6F6);
  static const Color overlay = Color(0x99000000);
}
```

### Typography (`typography.dart`)

```dart
class AppTypography {
  AppTypography._();
  static const String fontFamily = 'Inter';
  static const List<String> fontFamilyFallback = ['Roboto', 'sans-serif'];

  // Display (hero text)
  static const TextStyle displayLarge = TextStyle(fontFamily: fontFamily, fontSize: 57, fontWeight: FontWeight.w400, height: 1.12, color: AppColors.textPrimary);
  static const TextStyle displayMedium = TextStyle(fontFamily: fontFamily, fontSize: 45, fontWeight: FontWeight.w400, height: 1.16, color: AppColors.textPrimary);
  // Headlines
  static const TextStyle h1 = TextStyle(fontFamily: fontFamily, fontSize: 32, fontWeight: FontWeight.w700, letterSpacing: -0.5, height: 1.25, color: AppColors.textPrimary);
  static const TextStyle h2 = TextStyle(fontFamily: fontFamily, fontSize: 24, fontWeight: FontWeight.w600, height: 1.33, color: AppColors.textPrimary);
  static const TextStyle h3 = TextStyle(fontFamily: fontFamily, fontSize: 20, fontWeight: FontWeight.w600, height: 1.4, color: AppColors.textPrimary);
  static const TextStyle h4 = TextStyle(fontFamily: fontFamily, fontSize: 18, fontWeight: FontWeight.w600, height: 1.44, color: AppColors.textPrimary);
  // Body
  static const TextStyle bodyLarge = TextStyle(fontFamily: fontFamily, fontSize: 16, fontWeight: FontWeight.w400, height: 1.5, color: AppColors.textPrimary);
  static const TextStyle bodyMedium = TextStyle(fontFamily: fontFamily, fontSize: 14, fontWeight: FontWeight.w400, height: 1.43, color: AppColors.textPrimary);
  static const TextStyle bodySmall = TextStyle(fontFamily: fontFamily, fontSize: 12, fontWeight: FontWeight.w400, height: 1.33, color: AppColors.textSecondary);
  // Labels
  static const TextStyle labelLarge = TextStyle(fontFamily: fontFamily, fontSize: 14, fontWeight: FontWeight.w600, height: 1.43, color: AppColors.textPrimary);
  static const TextStyle labelSmall = TextStyle(fontFamily: fontFamily, fontSize: 11, fontWeight: FontWeight.w500, height: 1.27, color: AppColors.textSecondary);
  // Utility
  static const TextStyle caption = TextStyle(fontFamily: fontFamily, fontSize: 12, fontWeight: FontWeight.w400, color: AppColors.textSecondary);
  static const TextStyle code = TextStyle(fontFamily: 'Courier New', fontSize: 14, height: 1.5, color: AppColors.textPrimary, backgroundColor: Color(0xFFF5F5F5));
}
```

### Spacing (`spacing.dart`)

```dart
class AppSpacing {
  AppSpacing._();
  // Scale (4px base)
  static const double xs = 4.0;
  static const double sm = 8.0;
  static const double md = 16.0;   // Most common
  static const double lg = 24.0;
  static const double xl = 32.0;
  static const double xxl = 48.0;
  static const double xxxl = 64.0;

  // Gap widgets
  static const SizedBox gapXs = SizedBox(height: xs);
  static const SizedBox gapSm = SizedBox(height: sm);
  static const SizedBox gapMd = SizedBox(height: md);
  static const SizedBox gapLg = SizedBox(height: lg);
  static const SizedBox gapXl = SizedBox(height: xl);

  // Padding helpers
  static const EdgeInsets allSm = EdgeInsets.all(sm);
  static const EdgeInsets allMd = EdgeInsets.all(md);
  static const EdgeInsets allLg = EdgeInsets.all(lg);
  static const EdgeInsets card = EdgeInsets.all(md);
  static const EdgeInsets button = EdgeInsets.symmetric(horizontal: lg, vertical: md);
  static const EdgeInsets page = EdgeInsets.all(lg);

  // Border radius
  static const double borderRadiusSm = sm;    // 8px
  static const double borderRadiusMd = 12.0;
  static const double borderRadiusLg = md;    // 16px
  static const BorderRadius borderRadiusSmall = BorderRadius.all(Radius.circular(8));
  static const BorderRadius borderRadiusMedium = BorderRadius.all(Radius.circular(12));
  static const BorderRadius borderRadiusLarge = BorderRadius.all(Radius.circular(16));
}
```

### Shadows (`shadows.dart`)

```dart
class AppShadows {
  AppShadows._();
  static const List<BoxShadow> none = [];
  static const List<BoxShadow> card = [BoxShadow(color: Color(0x1A000000), blurRadius: 4, offset: Offset(0, 2))];
  static const List<BoxShadow> raised = [BoxShadow(color: Color(0x1F000000), blurRadius: 8, offset: Offset(0, 4))];
  static const List<BoxShadow> elevated = [BoxShadow(color: Color(0x24000000), blurRadius: 16, offset: Offset(0, 8))];
  static const List<BoxShadow> modal = [BoxShadow(color: Color(0x33000000), blurRadius: 24, offset: Offset(0, 12))];
  static const List<BoxShadow> appBar = [BoxShadow(color: Color(0x0D000000), blurRadius: 4, offset: Offset(0, 2))];
  static const List<BoxShadow> hover = [BoxShadow(color: Color(0x29000000), blurRadius: 12, offset: Offset(0, 6), spreadRadius: 2)];
  static const List<BoxShadow> focus = [BoxShadow(color: Color(0x4D1976D2), blurRadius: 8, spreadRadius: 4)];
}
```

---

## Phase 3: Core Components

Build in order: AppButton, AppCard, AppInput, AppAppBar, AppAvatar, AppBadge, AppChip, AppFormControls.

### Component Template

```dart
import 'package:flutter/material.dart';
import '../colors.dart';
import '../colors_dark.dart';
import '../typography.dart';
import '../spacing.dart';

class [ComponentName] extends StatelessWidget {
  final String? someParameter;
  final VoidCallback? onTap;

  const [ComponentName]({Key? key, this.someParameter, this.onTap}) : super(key: key);

  // Named constructors for variants
  const [ComponentName].variant({Key? key, ...}) : this(key: key, ...);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark ? AppColorsDark.surface : AppColors.surface;
    return Container(/* implementation */);
  }
}
```

### Component Testing Pattern

```dart
void main() {
  group('App[Component]', () {
    testWidgets('renders correctly', (tester) async {
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: App[Component]())));
      expect(find.byType(App[Component]), findsOneWidget);
    });
    testWidgets('supports dark mode', (tester) async {
      await tester.pumpWidget(MaterialApp(theme: ThemeData.dark(), home: Scaffold(body: App[Component]())));
    });
  });
}
```

---

## Phase 4: Responsive System

### Breakpoints

```dart
class Breakpoints {
  Breakpoints._();
  static const double mobile = 600;
  static const double tablet = 1024;
  static const double desktop = 1440;
  static const double wide = 1920;

  static bool isMobile(BuildContext context) => MediaQuery.of(context).size.width < mobile;
  static bool isTablet(BuildContext context) => MediaQuery.of(context).size.width >= mobile && MediaQuery.of(context).size.width < desktop;
  static bool isDesktop(BuildContext context) => MediaQuery.of(context).size.width >= desktop;
}

enum DeviceType { mobile, tablet, desktop, wide }

DeviceType getDeviceType(BuildContext context) {
  final width = MediaQuery.of(context).size.width;
  if (width < Breakpoints.mobile) return DeviceType.mobile;
  if (width < Breakpoints.desktop) return DeviceType.tablet;
  if (width < Breakpoints.wide) return DeviceType.desktop;
  return DeviceType.wide;
}
```

### ResponsiveBuilder

```dart
class ResponsiveBuilder extends StatelessWidget {
  final Widget? mobile, tablet, desktop, wide;
  const ResponsiveBuilder({Key? key, this.mobile, this.tablet, this.desktop, this.wide}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    switch (getDeviceType(context)) {
      case DeviceType.mobile: return mobile ?? tablet ?? desktop ?? wide ?? const SizedBox.shrink();
      case DeviceType.tablet: return tablet ?? desktop ?? mobile ?? wide ?? const SizedBox.shrink();
      case DeviceType.desktop: return desktop ?? wide ?? tablet ?? mobile ?? const SizedBox.shrink();
      case DeviceType.wide: return wide ?? desktop ?? tablet ?? mobile ?? const SizedBox.shrink();
    }
  }
}

T responsiveValue<T>(BuildContext context, {required T mobile, T? tablet, T? desktop, T? wide}) {
  switch (getDeviceType(context)) {
    case DeviceType.mobile: return mobile;
    case DeviceType.tablet: return tablet ?? mobile;
    case DeviceType.desktop: return desktop ?? tablet ?? mobile;
    case DeviceType.wide: return wide ?? desktop ?? tablet ?? mobile;
  }
}
```

---

## Best Practices

### MUST

```dart
// Use design tokens
Container(color: AppColors.primary)          // Not Color(0xFF1976D2)

// Single import
import 'package:your_app/core/design/design_system.dart';

// Component composition
AppButton.primary(label: 'Save', onPressed: _save)  // Not custom ElevatedButton

// Responsive builder
ResponsiveBuilder(mobile: MobileLayout(), desktop: DesktopLayout())

// Theme-aware colors
final isDark = Theme.of(context).brightness == Brightness.dark;
final color = isDark ? AppColorsDark.surface : AppColors.surface;
```

### MUST NOT

- Hardcode colors, spacing, or typography values
- Create custom components without justification
- Skip dark mode support
- Ignore responsive design
- Build features before design system

---

## Implementation Timeline

| Phase           | Duration   | Deliverable                          |
| --------------- | ---------- | ------------------------------------ |
| Structure       | 30 min     | Directory, single import             |
| Design Tokens   | 2-3h       | Colors, typography, spacing, shadows |
| Core Components | 8-12h      | 8-16 components                      |
| Responsive      | 2-3h       | Breakpoints, responsive widgets      |
| Documentation   | 2-3h       | README, showcase app                 |
| Validation      | 2-3h       | Testing, visual QA                   |
| **Total**       | **16-24h** | **Production-ready design system**   |

**Minimum viable** (8h): Tokens (2h) + Button/Card/Input/AppBar (4h) + Breakpoints+ResponsiveBuilder (1h) + Basic README (1h).
