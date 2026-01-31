# Flutter Testing Patterns

**Purpose**: Mandatory testing patterns for Flutter widget and integration tests
**Status**: Production Standard ✅
**Last Updated**: October 21, 2025
**Applies To**: All Flutter test development

---

## Overview

This guide documents proven testing patterns for Flutter applications. These patterns have been validated through real-world bug fixes and test improvements.

---

## 1. Scroll-to-View Pattern (Off-Screen Widgets)

### Problem

Widgets rendered outside the test viewport (Y > 600px) fail when using `tester.tap()` because Flutter test cannot interact with off-screen elements.

**Symptoms**:
- Test fails with "Widget not found" or similar error
- Widget exists in widget tree but tap() fails
- Widget is below the fold in forms or scrollable areas

**Example Failure**:
```dart
// ❌ FAILS - Button at Y=696px exceeds viewport height of 600px
await tester.tap(find.text('Log In'));
await tester.pump();
```

### Solution

Use `ensureVisible()` before tapping to scroll widget into view:

```dart
// ✅ WORKS - Scrolls button into viewport before tapping
await tester.ensureVisible(find.text('Log In'));
await tester.pumpAndSettle();
await tester.tap(find.text('Log In'));
await tester.pumpAndSettle();
```

### When to Use

- ✅ Buttons in forms that may overflow viewport
- ✅ ListView items beyond visible area
- ✅ Bottom-sheet or dialog buttons
- ✅ Any widget that may be off-screen in test viewport (600px height)

### Real-World Impact

**Fixed in TODO-017**: 49 auth test failures resolved using this pattern
- **File**: `test/features/auth/presentation/screens/login_page_test.dart`
- **Tests Fixed**: Email validation, password validation, form submission tests

---

## 2. pumpAndSettle vs pump (Validation & Async)

### Problem

Using `pump()` instead of `pumpAndSettle()` prevents validation errors and async state updates from appearing in tests.

**Symptoms**:
- Validation error messages never appear in test
- Loading states don't complete
- Async operations don't finish
- Test passes incorrectly (false positive)

**Example Failure**:
```dart
// ❌ FAILS - Validation error never appears
await tester.tap(find.text('Log In'));
await tester.pump();
expect(find.text('This field is required'), findsOneWidget); // NEVER FOUND
```

### Solution

Use `pumpAndSettle()` to wait for all animations and async operations:

```dart
// ✅ WORKS - Waits for validation to complete and error to render
await tester.tap(find.text('Log In'));
await tester.pumpAndSettle();
expect(find.text('This field is required'), findsOneWidget); // ✅ FOUND
```

### When to Use

| Scenario | Use |
|----------|-----|
| **Validation errors** | `pumpAndSettle()` |
| **Loading states** | `pumpAndSettle()` |
| **Async operations** | `pumpAndSettle()` |
| **Animations** | `pumpAndSettle()` |
| **Simple widget updates** | `pump()` |
| **Testing animation frames** | `pump(Duration(...))` |

### Real-World Impact

**Fixed in TODO-017**: 49 auth test failures resolved by switching to `pumpAndSettle()`
- **Issue**: Validation errors not appearing because pump() didn't wait
- **Solution**: Changed all validation tests to use pumpAndSettle()

---

## 3. Complete Widget Test Pattern

### Standard Test Structure

```dart
testWidgets('should show validation error when field is empty', (tester) async {
  // 1. SETUP - Create widget with necessary providers
  await tester.pumpWidget(createTestWidget());

  // 2. SCROLL TO VIEW (if needed)
  await tester.ensureVisible(find.text('Submit'));
  await tester.pumpAndSettle();

  // 3. INTERACT - Perform user action
  await tester.tap(find.text('Submit'));
  await tester.pumpAndSettle(); // Wait for validation

  // 4. VERIFY - Check expected outcome
  expect(find.text('This field is required'), findsOneWidget);
});
```

### Key Principles

1. **Always use pumpAndSettle() after user interactions** that trigger validation or async operations
2. **Use ensureVisible() for off-screen widgets** before tapping
3. **Wait for animations to complete** before assertions
4. **Create helper methods** for common widget setups

---

## 4. Form Validation Testing Pattern

### Complete Form Test Example

```dart
group('LoginPage form validation', () {
  Widget createLoginPage() {
    return ProviderScope(
      child: MaterialApp(
        theme: AppTheme.lightTheme,
        home: const LoginPage(),
      ),
    );
  }

  testWidgets('should show error when email is empty', (tester) async {
    // Setup
    await tester.pumpWidget(createLoginPage());

    // Ensure button is visible
    await tester.ensureVisible(find.text('Log In'));
    await tester.pumpAndSettle();

    // Submit form without entering email
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    // Verify validation error appears
    expect(find.text('This field is required'), findsOneWidget);
  });

  testWidgets('should show error when email is invalid', (tester) async {
    // Setup
    await tester.pumpWidget(createLoginPage());

    // Enter invalid email
    await tester.enterText(find.byType(TextField).first, 'invalid-email');

    // Ensure button is visible and tap
    await tester.ensureVisible(find.text('Log In'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    // Verify validation error
    expect(find.text('Please enter a valid email'), findsOneWidget);
  });

  testWidgets('should submit when form is valid', (tester) async {
    // Setup
    await tester.pumpWidget(createLoginPage());

    // Enter valid credentials
    await tester.enterText(
      find.byType(TextField).first,
      'user@example.com',
    );
    await tester.enterText(
      find.byType(TextField).last,
      'password123',
    );

    // Submit form
    await tester.ensureVisible(find.text('Log In'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Log In'));
    await tester.pumpAndSettle();

    // Verify no validation errors
    expect(find.text('This field is required'), findsNothing);
    expect(find.text('Please enter a valid email'), findsNothing);
  });
});
```

---

## 5. Responsive Layout Testing Pattern

### Testing Multiple Breakpoints

```dart
group('ChatPage responsive layouts', () {
  testWidgets('should show drawer on mobile', (tester) async {
    // Set mobile viewport size
    await tester.binding.setSurfaceSize(const Size(375, 812));
    await tester.pumpWidget(createChatPage());

    // Verify mobile layout (drawer hidden, FAB visible)
    expect(find.byType(Drawer), findsNothing); // Drawer closed initially
    expect(find.byType(FloatingActionButton), findsOneWidget);
  });

  testWidgets('should show fixed sidebar on tablet', (tester) async {
    // Set tablet viewport size
    await tester.binding.setSurfaceSize(const Size(768, 1024));
    await tester.pumpWidget(createChatPage());

    // Verify tablet layout (240px sidebar)
    expect(find.byType(ChatSidebar), findsOneWidget);
    // Verify sidebar width is 240px
    final sidebar = tester.widget<SizedBox>(
      find.ancestor(
        of: find.byType(ChatSidebar),
        matching: find.byType(SizedBox),
      ).first,
    );
    expect(sidebar.width, AppDimensions.sidebarTabletWidth); // 240.0
  });

  testWidgets('should show collapsible sidebar on desktop', (tester) async {
    // Set desktop viewport size
    await tester.binding.setSurfaceSize(const Size(1440, 900));
    await tester.pumpWidget(createChatPage());

    // Verify desktop layout (collapsible sidebar)
    expect(find.byType(ChatSidebar), findsOneWidget);
    expect(find.byType(AnimatedContainer), findsWidgets);
  });
});
```

### Standard Breakpoints
- **Mobile**: 375x812 (iPhone 13)
- **Tablet**: 768x1024 (iPad)
- **Desktop**: 1440x900 (MacBook Air)

---

## 6. Provider Testing Pattern

### Testing with Riverpod Providers

```dart
testWidgets('should update state when button tapped', (tester) async {
  // Create test-specific provider override
  final container = ProviderContainer();

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: MyWidget(),
      ),
    ),
  );

  // Interact with widget
  await tester.tap(find.text('Increment'));
  await tester.pumpAndSettle();

  // Verify provider state changed
  final state = container.read(counterProvider);
  expect(state, 1);

  // Cleanup
  container.dispose();
});
```

---

## 7. Testing Checklist

Before submitting tests, verify:

- [ ] Used `ensureVisible()` for off-screen widgets
- [ ] Used `pumpAndSettle()` after taps that trigger validation/async
- [ ] Tested at all relevant breakpoints (mobile, tablet, desktop)
- [ ] Created helper methods for widget setup
- [ ] Disposed controllers and providers properly
- [ ] Used `findsOneWidget`, `findsNothing`, etc. correctly
- [ ] No magic numbers (use AppDimensions, AppSpacing constants)
- [ ] Meaningful test descriptions (should + expected behavior)

---

## Common Mistakes to Avoid

### ❌ Don't Do This

```dart
// 1. Tapping off-screen widgets without ensureVisible
await tester.tap(find.text('Bottom Button')); // FAILS if off-screen

// 2. Using pump() for validation tests
await tester.tap(find.text('Submit'));
await tester.pump(); // Validation error won't appear yet

// 3. Not waiting for async operations
await tester.tap(find.text('Load Data'));
expect(find.text('Data loaded'), findsOneWidget); // FAILS - data not loaded yet

// 4. Hardcoding viewport sizes
tester.binding.setSurfaceSize(const Size(768, 1024)); // What does this mean?
```

### ✅ Do This Instead

```dart
// 1. Scroll to view before tapping
await tester.ensureVisible(find.text('Bottom Button'));
await tester.pumpAndSettle();
await tester.tap(find.text('Bottom Button'));

// 2. Use pumpAndSettle for validation
await tester.tap(find.text('Submit'));
await tester.pumpAndSettle();
expect(find.text('Validation error'), findsOneWidget);

// 3. Wait for async operations
await tester.tap(find.text('Load Data'));
await tester.pumpAndSettle();
expect(find.text('Data loaded'), findsOneWidget);

// 4. Use named constants for viewport sizes
tester.binding.setSurfaceSize(AppBreakpoints.tablet); // Clear and maintainable
```

---

## Real-World Examples

### Example 1: Auth Test Fix (TODO-017)

**Before** (49 failures):
```dart
testWidgets('should show error when email is empty', (tester) async {
  await tester.pumpWidget(createLoginPage());
  await tester.tap(find.text('Log In')); // Button off-screen
  await tester.pump(); // Validation doesn't complete
  expect(find.text('This field is required'), findsOneWidget); // FAILS
});
```

**After** (0 failures):
```dart
testWidgets('should show error when email is empty', (tester) async {
  await tester.pumpWidget(createLoginPage());
  await tester.ensureVisible(find.text('Log In')); // Scroll to button
  await tester.pumpAndSettle();
  await tester.tap(find.text('Log In'));
  await tester.pumpAndSettle(); // Wait for validation
  expect(find.text('This field is required'), findsOneWidget); // PASSES ✅
});
```

**Result**: 49 tests fixed, 0 failures

---

## Summary

### Critical Patterns

1. **ensureVisible + pumpAndSettle** - For off-screen widget interactions
2. **pumpAndSettle** - For validation and async operations
3. **Responsive testing** - Test at all breakpoints
4. **Provider cleanup** - Dispose containers properly

### Impact Metrics

- **Tests Fixed**: 49 (auth tests in TODO-017)
- **Pass Rate Improvement**: 88.6% → 92.5% (+3.9%)
- **Pattern Reusability**: Used across all form validation tests

---

**Pattern Status**: Production-Ready ✅
**Validation**: 49 tests fixed using these patterns
**Next Review**: When new testing issues are identified
