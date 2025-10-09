# Creating a Flutter Design System from Scratch

**Purpose**: Step-by-step guide for creating a professional design system for new Flutter projects.

**Status**: Production Standard ✅
**Last Updated**: October 9, 2025
**For**: New projects with no existing design system

---

## 🎯 Core Principles

### Design System Definition
A design system is a **complete set of reusable components, design tokens, and patterns** that ensures visual and behavioral consistency across an application.

**Key Benefits**:
- **Consistency**: Same look and feel across all features
- **Velocity**: Developers build features faster with pre-built components
- **Maintainability**: Changes propagate through entire app via tokens
- **Quality**: Professional UX baked into every component
- **Scalability**: New features inherit existing design standards

### Critical Success Factors

1. **Foundation First**: Create design system BEFORE building features
2. **Token-Based**: Use design tokens (colors, spacing, typography) not hardcoded values
3. **Component Library**: Build 8-16 core components before feature work
4. **Responsive by Default**: All components work at all screen sizes
5. **Dark Mode Built-In**: Support both themes from day 1
6. **Documentation Mandatory**: Create usage guide as you build
7. **Live Demo App**: Build showcase app to test and demonstrate components

---

## 📋 Pre-Implementation Checklist

Before starting, ensure you have:

- [ ] Flutter SDK installed (3.0+)
- [ ] Target platforms identified (web, iOS, Android, desktop)
- [ ] Brand colors defined (or use professional defaults)
- [ ] Typography preferences (or use Inter/Roboto)
- [ ] Screen size requirements (mobile, tablet, desktop)
- [ ] Accessibility requirements (WCAG 2.1 AA minimum)
- [ ] Design inspiration/references (Material Design, Apple HIG, etc.)

---

## 🏗️ Phase 1: Project Structure (30 min)

### Step 1: Create Directory Structure

```bash
lib/
├── core/
│   ├── design/
│   │   ├── design_system.dart          # Single export file
│   │   ├── colors.dart                 # Light mode colors
│   │   ├── colors_dark.dart            # Dark mode colors
│   │   ├── typography.dart             # Text styles
│   │   ├── spacing.dart                # Spacing constants
│   │   ├── shadows.dart                # Elevation system
│   │   ├── theme.dart                  # Material theme config
│   │   ├── responsive.dart             # Responsive utilities
│   │   ├── components/                 # Component widgets
│   │   │   └── [component files]
│   │   └── examples/
│   │       └── component_showcase.dart # Live demo app
│   └── responsive/                     # Responsive widgets
│       ├── breakpoints.dart
│       ├── responsive_builder.dart
│       ├── adaptive_grid.dart
│       ├── adaptive_filter.dart
│       └── adaptive_form.dart
```

### Step 2: Create Single Import File

Create `lib/core/design/design_system.dart`:

```dart
// Design System Single Import
// Import this file to get all design system components and tokens

library design_system;

// Design Tokens
export 'colors.dart';
export 'colors_dark.dart';
export 'typography.dart';
export 'spacing.dart';
export 'shadows.dart';
export 'theme.dart';

// Responsive Utilities
export 'responsive.dart';
export '../responsive/breakpoints.dart';
export '../responsive/responsive_builder.dart';
export '../responsive/adaptive_grid.dart';
export '../responsive/adaptive_filter.dart';
export '../responsive/adaptive_form.dart';

// Components (add as you create them)
export 'components/app_button.dart';
export 'components/app_card.dart';
export 'components/app_input.dart';
export 'components/app_app_bar.dart';
// ... add more as you build
```

**Why Single Import?**
- Developers only need one import line
- Easy to add/remove components
- Prevents import inconsistencies

---

## 🎨 Phase 2: Design Tokens (2-3h)

### Step 1: Color System

Create `lib/core/design/colors.dart`:

```dart
import 'package:flutter/material.dart';

/// Light mode color palette
///
/// Based on professional Material Design 3 principles.
/// Modify primary/secondary colors to match your brand.
class AppColors {
  // Prevent instantiation
  AppColors._();

  // ========== PRIMARY COLORS ==========
  // Main brand color - used for primary actions, headers, links
  static const Color primary = Color(0xFF1976D2);        // Professional blue
  static const Color primaryLight = Color(0xFF42A5F5);   // Light variant
  static const Color primaryDark = Color(0xFF0D47A1);    // Dark variant

  // ========== SECONDARY COLORS ==========
  // Accent color - used for CTAs, highlights, secondary actions
  static const Color secondary = Color(0xFF00796B);      // Teal
  static const Color secondaryLight = Color(0xFF26A69A); // Light teal

  // ========== SURFACE COLORS ==========
  // Background colors for different surface levels
  static const Color surface = Color(0xFFFFFFFF);        // White
  static const Color background = Color(0xFFF5F5F5);     // Light gray
  static const Color cardBackground = Color(0xFFFFFFFF); // Card surfaces

  // ========== BORDER & DIVIDER ==========
  static const Color border = Color(0xFFE0E0E0);         // Light gray border
  static const Color divider = Color(0xFFE0E0E0);        // Divider lines

  // ========== TEXT COLORS ==========
  // High contrast for accessibility (WCAG AA compliant)
  static const Color textPrimary = Color(0xFF212121);    // Almost black
  static const Color textSecondary = Color(0xFF757575);  // Medium gray
  static const Color textDisabled = Color(0xFFBDBDBD);   // Light gray
  static const Color textOnPrimary = Color(0xFFFFFFFF);  // White on primary

  // ========== SEMANTIC COLORS ==========
  // Convey meaning through color
  static const Color success = Color(0xFF2E7D32);        // Green
  static const Color successLight = Color(0xFF66BB6A);
  static const Color warning = Color(0xFFF57C00);        // Orange
  static const Color warningLight = Color(0xFFFFB74D);
  static const Color error = Color(0xFFC62828);          // Red
  static const Color errorLight = Color(0xFFEF5350);
  static const Color info = Color(0xFF0277BD);           // Light blue
  static const Color infoLight = Color(0xFF29B6F6);

  // ========== UTILITY COLORS ==========
  static const Color overlay = Color(0x66000000);        // 40% black overlay
  static const Color shadow = Color(0x1A000000);         // 10% black shadow
  static const Color transparent = Color(0x00000000);    // Fully transparent

  // ========== HELPER METHODS ==========
  /// Create a color with specified opacity
  static Color withOpacity(Color color, double opacity) {
    return color.withValues(alpha: opacity);
  }
}
```

Create `lib/core/design/colors_dark.dart`:

```dart
import 'package:flutter/material.dart';

/// Dark mode color palette
///
/// Follows Material Design 3 dark theme principles.
/// Higher contrast, muted saturation for eye comfort.
class AppColorsDark {
  AppColorsDark._();

  // ========== PRIMARY COLORS ==========
  static const Color primary = Color(0xFF90CAF9);        // Light blue (less intense)
  static const Color primaryLight = Color(0xFFBBDEFB);
  static const Color primaryDark = Color(0xFF42A5F5);

  // ========== SECONDARY COLORS ==========
  static const Color secondary = Color(0xFF4DB6AC);      // Light teal
  static const Color secondaryLight = Color(0xFF80CBC4);

  // ========== SURFACE COLORS ==========
  static const Color surface = Color(0xFF1E1E1E);        // Dark surface
  static const Color background = Color(0xFF121212);     // Pure dark background
  static const Color cardBackground = Color(0xFF2C2C2C); // Elevated card surface

  // ========== BORDER & DIVIDER ==========
  static const Color border = Color(0xFF3C3C3C);         // Subtle border
  static const Color divider = Color(0xFF3C3C3C);

  // ========== TEXT COLORS ==========
  static const Color textPrimary = Color(0xFFE0E0E0);    // Light gray (high contrast)
  static const Color textSecondary = Color(0xFFB0B0B0);  // Medium gray
  static const Color textDisabled = Color(0xFF6C6C6C);   // Dark gray
  static const Color textOnPrimary = Color(0xFF000000);  // Black on primary

  // ========== SEMANTIC COLORS ==========
  static const Color success = Color(0xFF66BB6A);        // Lighter green
  static const Color successLight = Color(0xFF81C784);
  static const Color warning = Color(0xFFFFB74D);        // Lighter orange
  static const Color warningLight = Color(0xFFFFCC80);
  static const Color error = Color(0xFFEF5350);          // Lighter red
  static const Color errorLight = Color(0xFFE57373);
  static const Color info = Color(0xFF29B6F6);           // Lighter blue
  static const Color infoLight = Color(0xFF4FC3F7);

  // ========== UTILITY COLORS ==========
  static const Color overlay = Color(0x99000000);        // 60% black (darker overlay)
  static const Color shadow = Color(0x33000000);         // 20% black (visible shadow)
  static const Color transparent = Color(0x00000000);

  // ========== HELPER METHODS ==========
  static Color withOpacity(Color color, double opacity) {
    return color.withValues(alpha: opacity);
  }
}
```

### Step 2: Typography System

Create `lib/core/design/typography.dart`:

```dart
import 'package:flutter/material.dart';
import 'colors.dart';

/// Typography system for consistent text styling
///
/// Based on Material Design 3 type scale.
/// Uses Inter font (clean, readable, professional).
///
/// Fallback hierarchy: Inter → Roboto → System Sans-Serif
class AppTypography {
  AppTypography._();

  // ========== FONT FAMILY ==========
  static const String fontFamily = 'Inter';
  static const List<String> fontFamilyFallback = ['Roboto', 'sans-serif'];

  // ========== DISPLAY STYLES (Large headers, hero text) ==========
  static const TextStyle displayLarge = TextStyle(
    fontFamily: fontFamily,
    fontSize: 57,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.25,
    height: 1.12,
    color: AppColors.textPrimary,
  );

  static const TextStyle displayMedium = TextStyle(
    fontFamily: fontFamily,
    fontSize: 45,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.16,
    color: AppColors.textPrimary,
  );

  static const TextStyle displaySmall = TextStyle(
    fontFamily: fontFamily,
    fontSize: 36,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.22,
    color: AppColors.textPrimary,
  );

  // ========== HEADLINE STYLES (Section headers) ==========
  static const TextStyle h1 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 32,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.5,
    height: 1.25,
    color: AppColors.textPrimary,
  );

  static const TextStyle h2 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 24,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.3,
    height: 1.33,
    color: AppColors.textPrimary,
  );

  static const TextStyle h3 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 20,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
    height: 1.4,
    color: AppColors.textPrimary,
  );

  static const TextStyle h4 = TextStyle(
    fontFamily: fontFamily,
    fontSize: 18,
    fontWeight: FontWeight.w600,
    letterSpacing: 0,
    height: 1.44,
    color: AppColors.textPrimary,
  );

  // ========== BODY STYLES (Paragraph text) ==========
  static const TextStyle bodyLarge = TextStyle(
    fontFamily: fontFamily,
    fontSize: 16,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.15,
    height: 1.5,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodyMedium = TextStyle(
    fontFamily: fontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.25,
    height: 1.43,
    color: AppColors.textPrimary,
  );

  static const TextStyle bodySmall = TextStyle(
    fontFamily: fontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.4,
    height: 1.33,
    color: AppColors.textSecondary,
  );

  // ========== LABEL STYLES (Buttons, tabs, chips) ==========
  static const TextStyle labelLarge = TextStyle(
    fontFamily: fontFamily,
    fontSize: 14,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.1,
    height: 1.43,
    color: AppColors.textPrimary,
  );

  static const TextStyle labelMedium = TextStyle(
    fontFamily: fontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.5,
    height: 1.33,
    color: AppColors.textPrimary,
  );

  static const TextStyle labelSmall = TextStyle(
    fontFamily: fontFamily,
    fontSize: 11,
    fontWeight: FontWeight.w500,
    letterSpacing: 0.5,
    height: 1.27,
    color: AppColors.textSecondary,
  );

  // ========== UTILITY STYLES ==========
  static const TextStyle caption = TextStyle(
    fontFamily: fontFamily,
    fontSize: 12,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.4,
    height: 1.33,
    color: AppColors.textSecondary,
  );

  static const TextStyle overline = TextStyle(
    fontFamily: fontFamily,
    fontSize: 10,
    fontWeight: FontWeight.w500,
    letterSpacing: 1.5,
    height: 1.6,
    color: AppColors.textSecondary,
  );

  // ========== CODE/MONO STYLES ==========
  static const TextStyle code = TextStyle(
    fontFamily: 'Courier New',
    fontSize: 14,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.5,
    color: AppColors.textPrimary,
    backgroundColor: Color(0xFFF5F5F5),
  );
}
```

### Step 3: Spacing System

Create `lib/core/design/spacing.dart`:

```dart
import 'package:flutter/material.dart';

/// Spacing system for consistent layout
///
/// Based on 4px base unit (4, 8, 12, 16, 24, 32, 48, 64).
/// All spacing should use these constants, never hardcoded numbers.
class AppSpacing {
  AppSpacing._();

  // ========== BASE SPACING SCALE ==========
  static const double xs = 4.0;    // Extra small (tight spacing)
  static const double sm = 8.0;    // Small (compact layouts)
  static const double md = 16.0;   // Medium (default spacing) ← MOST COMMON
  static const double lg = 24.0;   // Large (generous spacing)
  static const double xl = 32.0;   // Extra large (section spacing)
  static const double xxl = 48.0;  // 2X large (major sections)
  static const double xxxl = 64.0; // 3X large (hero sections)

  // ========== GAP WIDGETS (For Column/Row spacing) ==========
  // Vertical gaps
  static const SizedBox gapXs = SizedBox(height: xs);
  static const SizedBox gapSm = SizedBox(height: sm);
  static const SizedBox gapMd = SizedBox(height: md);
  static const SizedBox gapLg = SizedBox(height: lg);
  static const SizedBox gapXl = SizedBox(height: xl);
  static const SizedBox gapXxl = SizedBox(height: xxl);

  // Horizontal gaps
  static const SizedBox gapXsHorizontal = SizedBox(width: xs);
  static const SizedBox gapSmHorizontal = SizedBox(width: sm);
  static const SizedBox gapMdHorizontal = SizedBox(width: md);
  static const SizedBox gapLgHorizontal = SizedBox(width: lg);
  static const SizedBox gapXlHorizontal = SizedBox(width: xl);

  // ========== PADDING HELPERS ==========
  // All sides
  static const EdgeInsets allXs = EdgeInsets.all(xs);
  static const EdgeInsets allSm = EdgeInsets.all(sm);
  static const EdgeInsets allMd = EdgeInsets.all(md);
  static const EdgeInsets allLg = EdgeInsets.all(lg);
  static const EdgeInsets allXl = EdgeInsets.all(xl);

  // Horizontal only
  static const EdgeInsets horizontalXs = EdgeInsets.symmetric(horizontal: xs);
  static const EdgeInsets horizontalSm = EdgeInsets.symmetric(horizontal: sm);
  static const EdgeInsets horizontalMd = EdgeInsets.symmetric(horizontal: md);
  static const EdgeInsets horizontalLg = EdgeInsets.symmetric(horizontal: lg);
  static const EdgeInsets horizontalXl = EdgeInsets.symmetric(horizontal: xl);

  // Vertical only
  static const EdgeInsets verticalXs = EdgeInsets.symmetric(vertical: xs);
  static const EdgeInsets verticalSm = EdgeInsets.symmetric(vertical: sm);
  static const EdgeInsets verticalMd = EdgeInsets.symmetric(vertical: md);
  static const EdgeInsets verticalLg = EdgeInsets.symmetric(vertical: lg);
  static const EdgeInsets verticalXl = EdgeInsets.symmetric(vertical: xl);

  // ========== COMPONENT-SPECIFIC PADDING ==========
  static const EdgeInsets card = EdgeInsets.all(md);
  static const EdgeInsets cardCompact = EdgeInsets.all(sm);
  static const EdgeInsets cardGenerous = EdgeInsets.all(lg);

  static const EdgeInsets button = EdgeInsets.symmetric(
    horizontal: lg,
    vertical: md,
  );
  static const EdgeInsets buttonCompact = EdgeInsets.symmetric(
    horizontal: md,
    vertical: sm,
  );

  static const EdgeInsets input = EdgeInsets.symmetric(
    horizontal: md,
    vertical: md,
  );

  static const EdgeInsets page = EdgeInsets.all(lg);
  static const EdgeInsets section = EdgeInsets.all(xl);

  // ========== BORDER RADIUS ==========
  static const double borderRadiusSm = sm;   // 8px - Small elements
  static const double borderRadiusMd = 12.0; // 12px - Medium elements
  static const double borderRadiusLg = md;   // 16px - Large elements
  static const double borderRadiusXl = lg;   // 24px - Extra large elements

  static const Radius radiusSm = Radius.circular(borderRadiusSm);
  static const Radius radiusMd = Radius.circular(borderRadiusMd);
  static const Radius radiusLg = Radius.circular(borderRadiusLg);
  static const Radius radiusXl = Radius.circular(borderRadiusXl);

  static const BorderRadius borderRadiusSmall = BorderRadius.all(radiusSm);
  static const BorderRadius borderRadiusMedium = BorderRadius.all(radiusMd);
  static const BorderRadius borderRadiusLarge = BorderRadius.all(radiusLg);
  static const BorderRadius borderRadiusXLarge = BorderRadius.all(radiusXl);
}
```

### Step 4: Shadow System

Create `lib/core/design/shadows.dart`:

```dart
import 'package:flutter/material.dart';

/// Elevation and shadow system
///
/// Based on Material Design 3 elevation levels.
/// Use these instead of hardcoded BoxShadow values.
class AppShadows {
  AppShadows._();

  // ========== ELEVATION LEVELS ==========

  /// No shadow (elevation 0)
  static const List<BoxShadow> none = [];

  /// Card shadow (elevation 2)
  /// For: Cards, chips, small elevated elements
  static const List<BoxShadow> card = [
    BoxShadow(
      color: Color(0x1A000000), // 10% black
      blurRadius: 4,
      offset: Offset(0, 2),
      spreadRadius: 0,
    ),
  ];

  /// Raised shadow (elevation 4)
  /// For: Buttons, tabs, larger cards
  static const List<BoxShadow> raised = [
    BoxShadow(
      color: Color(0x1F000000), // 12% black
      blurRadius: 8,
      offset: Offset(0, 4),
      spreadRadius: 0,
    ),
  ];

  /// Elevated shadow (elevation 8)
  /// For: Floating action buttons, dropdown menus
  static const List<BoxShadow> elevated = [
    BoxShadow(
      color: Color(0x24000000), // 14% black
      blurRadius: 16,
      offset: Offset(0, 8),
      spreadRadius: 0,
    ),
  ];

  /// Modal shadow (elevation 16)
  /// For: Dialogs, modals, sheets
  static const List<BoxShadow> modal = [
    BoxShadow(
      color: Color(0x33000000), // 20% black
      blurRadius: 24,
      offset: Offset(0, 12),
      spreadRadius: 0,
    ),
  ];

  // ========== SPECIALIZED SHADOWS ==========

  /// AppBar shadow
  static const List<BoxShadow> appBar = [
    BoxShadow(
      color: Color(0x0D000000), // 5% black
      blurRadius: 4,
      offset: Offset(0, 2),
    ),
  ];

  /// Bottom sheet shadow (upward)
  static const List<BoxShadow> bottomSheet = [
    BoxShadow(
      color: Color(0x33000000), // 20% black
      blurRadius: 16,
      offset: Offset(0, -8),
      spreadRadius: 0,
    ),
  ];

  /// Hover shadow (interactive elements)
  static const List<BoxShadow> hover = [
    BoxShadow(
      color: Color(0x29000000), // 16% black
      blurRadius: 12,
      offset: Offset(0, 6),
      spreadRadius: 2,
    ),
  ];

  /// Focus shadow (keyboard navigation)
  static const List<BoxShadow> focus = [
    BoxShadow(
      color: Color(0x4D1976D2), // 30% primary color
      blurRadius: 8,
      offset: Offset(0, 0),
      spreadRadius: 4,
    ),
  ];
}
```

**Phase 2 Complete**: You now have a complete token system!

---

## 🧩 Phase 3: Core Components (8-12h)

Build components in this order (most essential first):

### Component Priority List

1. **AppButton** (1h) - Primary, secondary, outlined, text variants
2. **AppCard** (1h) - Standard, compact, generous variants
3. **AppInput** (1.5h) - Text, email, password, multiline
4. **AppAppBar** (1h) - Top navigation with actions
5. **AppAvatar** (30min) - User profile images
6. **AppBadge** (30min) - Notification counts
7. **AppChip** (45min) - Filter/selection chips
8. **AppFormControls** (1h) - Checkbox, radio, switch

### Component Template

Use this template for every component:

```dart
import 'package:flutter/material.dart';
import '../colors.dart';
import '../colors_dark.dart';
import '../typography.dart';
import '../spacing.dart';
import '../shadows.dart';

/// [ComponentName] - Brief description
///
/// Features:
/// - Feature 1
/// - Feature 2
/// - Feature 3
///
/// Usage:
/// ```dart
/// [ComponentName](
///   // parameters
/// )
/// ```
class [ComponentName] extends StatelessWidget {
  // Parameters (use final for immutability)
  final String? someParameter;
  final VoidCallback? onTap;

  const [ComponentName]({
    Key? key,
    this.someParameter,
    this.onTap,
  }) : super(key: key);

  // Named constructors for variants
  const [ComponentName].variant({
    Key? key,
    String? someParameter,
    VoidCallback? onTap,
  }) : this(
    key: key,
    someParameter: someParameter,
    onTap: onTap,
  );

  @override
  Widget build(BuildContext context) {
    // Get theme for dark mode support
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    // Use theme-aware colors
    final backgroundColor = isDark
        ? AppColorsDark.surface
        : AppColors.surface;

    return Container(
      // Implementation
    );
  }
}
```

### Testing Each Component

For each component, test:

```dart
// test/widget/app_[component]_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:your_app/core/design/design_system.dart';

void main() {
  group('App[Component] Tests', () {
    testWidgets('renders correctly', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: App[Component](),
          ),
        ),
      );

      expect(find.byType(App[Component]), findsOneWidget);
    });

    testWidgets('supports dark mode', (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData.dark(),
          home: Scaffold(
            body: App[Component](),
          ),
        ),
      );

      // Verify dark mode styling
    });
  });
}
```

---

## 📱 Phase 4: Responsive System (2-3h)

### Step 1: Define Breakpoints

Create `lib/core/responsive/breakpoints.dart`:

```dart
import 'package:flutter/material.dart';

/// Responsive breakpoints following Material Design guidelines
class Breakpoints {
  Breakpoints._();

  // ========== BREAKPOINT VALUES ==========
  static const double mobile = 600;    // 0-600px: Mobile phones
  static const double tablet = 1024;   // 600-1024px: Tablets
  static const double desktop = 1440;  // 1024-1440px: Laptops
  static const double wide = 1920;     // 1440+: Large screens

  // ========== DEVICE TYPE CHECKS ==========
  static bool isMobile(BuildContext context) {
    return MediaQuery.of(context).size.width < mobile;
  }

  static bool isTablet(BuildContext context) {
    return MediaQuery.of(context).size.width >= mobile &&
           MediaQuery.of(context).size.width < desktop;
  }

  static bool isDesktop(BuildContext context) {
    return MediaQuery.of(context).size.width >= desktop;
  }

  static bool isWide(BuildContext context) {
    return MediaQuery.of(context).size.width >= wide;
  }
}

/// Device type enum
enum DeviceType { mobile, tablet, desktop, wide }

/// Get device type from context
DeviceType getDeviceType(BuildContext context) {
  final width = MediaQuery.of(context).size.width;

  if (width < Breakpoints.mobile) return DeviceType.mobile;
  if (width < Breakpoints.desktop) return DeviceType.tablet;
  if (width < Breakpoints.wide) return DeviceType.desktop;
  return DeviceType.wide;
}
```

### Step 2: Responsive Builder

Create `lib/core/responsive/responsive_builder.dart`:

```dart
import 'package:flutter/material.dart';
import 'breakpoints.dart';

/// Responsive builder widget
///
/// Builds different widgets for different screen sizes.
/// Provides fallback hierarchy: mobile → tablet → desktop.
class ResponsiveBuilder extends StatelessWidget {
  final Widget? mobile;
  final Widget? tablet;
  final Widget? desktop;
  final Widget? wide;

  const ResponsiveBuilder({
    Key? key,
    this.mobile,
    this.tablet,
    this.desktop,
    this.wide,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final deviceType = getDeviceType(context);

    switch (deviceType) {
      case DeviceType.mobile:
        return mobile ?? tablet ?? desktop ?? wide ?? const SizedBox.shrink();
      case DeviceType.tablet:
        return tablet ?? desktop ?? mobile ?? wide ?? const SizedBox.shrink();
      case DeviceType.desktop:
        return desktop ?? wide ?? tablet ?? mobile ?? const SizedBox.shrink();
      case DeviceType.wide:
        return wide ?? desktop ?? tablet ?? mobile ?? const SizedBox.shrink();
    }
  }
}

/// Value-based responsive builder
///
/// Returns different values for different screen sizes.
/// Useful for responsive sizing, counts, etc.
T responsiveValue<T>(
  BuildContext context, {
  required T mobile,
  T? tablet,
  T? desktop,
  T? wide,
}) {
  final deviceType = getDeviceType(context);

  switch (deviceType) {
    case DeviceType.mobile:
      return mobile;
    case DeviceType.tablet:
      return tablet ?? mobile;
    case DeviceType.desktop:
      return desktop ?? tablet ?? mobile;
    case DeviceType.wide:
      return wide ?? desktop ?? tablet ?? mobile;
  }
}
```

### Step 3: Create Adaptive Widgets

Build 3 essential adaptive widgets:

1. **AdaptiveGrid** - Auto-adjusting grid columns
2. **AdaptiveFilter** - Grid on wide, list on narrow
3. **AdaptiveForm** - Stacked on mobile, wrapped on desktop

*(See flutter-design-system.md for complete implementations)*

---

## 📖 Phase 5: Documentation (2-3h)

### Step 1: Component Showcase App

Create `lib/core/design/examples/component_showcase.dart`:

```dart
import 'package:flutter/material.dart';
import '../design_system.dart';

/// Component Showcase
///
/// Live demonstration of all design system components.
/// Use this app to:
/// - Test components in isolation
/// - Verify dark mode support
/// - Test responsive behavior
/// - Copy component usage examples
void main() {
  runApp(const ComponentShowcaseApp());
}

class ComponentShowcaseApp extends StatelessWidget {
  const ComponentShowcaseApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Component Showcase',
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      home: const ShowcasePage(),
    );
  }
}

class ShowcasePage extends StatefulWidget {
  const ShowcasePage({Key? key}) : super(key: key);

  @override
  State<ShowcasePage> createState() => _ShowcasePageState();
}

class _ShowcasePageState extends State<ShowcasePage> {
  // Add sections for each component category
  final List<ShowcaseSection> _sections = [
    ShowcaseSection(
      title: 'Buttons',
      icon: Icons.touch_app,
      builder: (_) => ButtonShowcase(),
    ),
    ShowcaseSection(
      title: 'Cards',
      icon: Icons.credit_card,
      builder: (_) => CardShowcase(),
    ),
    // ... add more sections
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Component Showcase'),
        actions: [
          // Theme toggle
          IconButton(
            icon: const Icon(Icons.brightness_6),
            onPressed: () {
              // Toggle theme
            },
          ),
        ],
      ),
      body: ResponsiveBuilder(
        mobile: _buildMobileLayout(),
        desktop: _buildDesktopLayout(),
      ),
    );
  }

  // Layout implementations...
}

// Showcase section model
class ShowcaseSection {
  final String title;
  final IconData icon;
  final WidgetBuilder builder;

  const ShowcaseSection({
    required this.title,
    required this.icon,
    required this.builder,
  });
}
```

### Step 2: README Documentation

Create `lib/core/design/README.md` documenting:

- Component list with descriptions
- Usage examples for each component
- Design token reference
- Responsive patterns
- Dark mode guidelines
- Common pitfalls and anti-patterns

### Step 3: Institutional Directive

Create `.claude/guides/flutter-design-system.md` with:

- **MANDATORY** design system usage rules
- Single import pattern
- Design token usage
- Component patterns
- Anti-patterns to avoid
- Flutter-specialist directives

*(See existing flutter-design-system.md for complete template)*

---

## ✅ Phase 6: Validation & Testing (2-3h)

### Testing Checklist

- [ ] All components render without errors
- [ ] Light mode styling correct
- [ ] Dark mode styling correct
- [ ] Mobile layout works (< 600px)
- [ ] Tablet layout works (600-1024px)
- [ ] Desktop layout works (> 1024px)
- [ ] All design tokens used (no hardcoded values)
- [ ] Component showcase app runs
- [ ] All components documented
- [ ] Usage examples provided
- [ ] README complete
- [ ] Institutional directive created

### Widget Testing

Write tests for critical components:

```bash
flutter test test/widget/
```

### Visual Regression Testing

Manually test:
- 360px width (small mobile)
- 768px width (tablet)
- 1440px width (desktop)
- Portrait and landscape orientations

---

## 🎓 Best Practices

### DO ✅

1. **Use Design Tokens Everywhere**
   ```dart
   // ✅ CORRECT
   Container(color: AppColors.primary)

   // ❌ WRONG
   Container(color: Color(0xFF1976D2))
   ```

2. **Single Import Pattern**
   ```dart
   // ✅ CORRECT
   import 'package:your_app/core/design/design_system.dart';

   // ❌ WRONG
   import 'package:your_app/core/design/colors.dart';
   import 'package:your_app/core/design/typography.dart';
   import 'package:your_app/core/design/components/app_button.dart';
   ```

3. **Component Composition Over Custom UI**
   ```dart
   // ✅ CORRECT
   AppButton.primary(label: 'Save', onPressed: _save)

   // ❌ WRONG
   ElevatedButton(
     style: ElevatedButton.styleFrom(
       backgroundColor: Color(0xFF1976D2),
       // ... custom styling
     ),
     child: Text('Save'),
     onPressed: _save,
   )
   ```

4. **Responsive by Default**
   ```dart
   // ✅ CORRECT
   ResponsiveBuilder(
     mobile: MobileLayout(),
     desktop: DesktopLayout(),
   )

   // ❌ WRONG
   if (MediaQuery.of(context).size.width < 600) {
     return MobileLayout();
   }
   ```

5. **Theme-Aware Colors**
   ```dart
   // ✅ CORRECT
   final isDark = Theme.of(context).brightness == Brightness.dark;
   final color = isDark ? AppColorsDark.surface : AppColors.surface;

   // ❌ WRONG
   final color = AppColors.surface; // Ignores dark mode
   ```

### DON'T ❌

1. **Never Hardcode Colors**
2. **Never Hardcode Spacing**
3. **Never Hardcode Typography**
4. **Never Create Custom Components Without Justification**
5. **Never Skip Dark Mode Support**
6. **Never Ignore Responsive Design**
7. **Never Build Features Before Design System**

---

## 🚀 Implementation Timeline

### Recommended Schedule

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1: Structure | 30 min | Directory structure, single import file |
| Phase 2: Design Tokens | 2-3h | Colors, typography, spacing, shadows |
| Phase 3: Core Components | 8-12h | 8-16 essential components |
| Phase 4: Responsive | 2-3h | Breakpoints, responsive widgets |
| Phase 5: Documentation | 2-3h | README, showcase app, directives |
| Phase 6: Validation | 2-3h | Testing, visual QA, fixes |
| **TOTAL** | **16-24h** | **Production-ready design system** |

### Minimum Viable Design System (8h)

If time-constrained, build this minimal set:

1. **Tokens** (2h): Colors, typography, spacing only
2. **Components** (4h): Button, Card, Input, AppBar only
3. **Responsive** (1h): Breakpoints and ResponsiveBuilder only
4. **Documentation** (1h): Basic README and showcase

---

## 📚 Reference Materials

### Inspiration Sources

- **Material Design 3**: https://m3.material.io/
- **Apple Human Interface Guidelines**: https://developer.apple.com/design/human-interface-guidelines/
- **Shadcn/ui**: https://ui.shadcn.com/ (React but great patterns)
- **Tailwind CSS**: https://tailwindcss.com/ (Token system inspiration)

### Flutter Resources

- **Flutter Widget Catalog**: https://docs.flutter.dev/ui/widgets
- **Material Components**: https://docs.flutter.dev/ui/widgets/material
- **Responsive Design**: https://docs.flutter.dev/ui/layout/responsive

---

## 🔄 Iterative Enhancement

### After Foundation (Phase 1-6)

Enhance incrementally with:

1. **Advanced Components** (Timeline, Kanban, Calendar, Tree View)
2. **Animation Presets** (Page transitions, micro-interactions)
3. **Accessibility** (Screen reader support, keyboard navigation)
4. **Performance** (Optimization, profiling)
5. **Testing** (Widget tests, integration tests)
6. **Documentation** (API docs, design guidelines, examples)

### Continuous Improvement

- **Gather Feedback**: Ask developers what's missing
- **Track Pain Points**: Document where developers bypass design system
- **Regular Audits**: Check for hardcoded values sneaking in
- **Version Control**: Treat design system as versioned library
- **Migration Guides**: Document breaking changes

---

## 🎯 Success Criteria

A design system is successful when:

✅ **Zero Custom UI Components** created for 90% of features
✅ **100% Design Token Usage** (no hardcoded values)
✅ **Responsive Across All Breakpoints** (mobile, tablet, desktop)
✅ **Dark Mode Support** (automatic through theme)
✅ **Developer Velocity Increase** (features ship faster)
✅ **Visual Consistency** (same look across app)
✅ **Maintainability** (single place to change design)
✅ **Accessibility** (WCAG AA compliant)

---

**Last Updated**: October 9, 2025
**Next Review**: When starting new projects or major redesigns
