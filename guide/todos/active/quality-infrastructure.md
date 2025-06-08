# Active Todos: Quality & Infrastructure

## 📖 Documentation & Migration

### Migration Guide from v1.0
**Status**: 🔴 TO DO | **Priority**: High
- Document API changes and breaking changes
- Create step-by-step migration instructions
- Provide code examples for common migration scenarios

### Security Guidelines Documentation
**Status**: 🔴 TO DO | **Priority**: High
- Document Python Code Node security best practices
- Add security guidelines for safe code execution
- Create security checklist for production deployments

---

## 🔧 Development Infrastructure

### Fix Async Test Configuration
**Status**: 🔴 TO DO | **Priority**: Medium
- Configure pytest-asyncio properly for async node tests
- Fix AsyncSwitch and AsyncMerge tests (10 tests currently skipped)
- Ensure all async patterns work correctly

### Re-enable Pre-commit Hooks
**Status**: 🔴 TO DO | **Priority**: Medium
- Re-enable Trivy, detect-secrets, and mypy in pre-commit
- Optimize hook performance for faster commits
- Currently disabled for development speed

---

## 🛠️ CLI & Tools

### Complete CLI Command Implementations
**Status**: 🔴 TO DO | **Priority**: Medium
- Implement missing CLI commands
- Improve error handling and help documentation
- Add comprehensive CLI testing

---

## 🔗 API Integration

### Complete API Integration Testing
**Status**: 🔴 TO DO | **Priority**: Medium
- Test api_integration_comprehensive.py with live endpoints
- Add 'responses' library for comprehensive mock testing
- Currently 52 tests skipped due to missing dependencies

---

## 📦 Optional Dependencies

### Optional Dependency Tests
**Status**: 🔴 TO DO | **Priority**: Low
- Resolve 52 skipped tests due to missing 'responses' library
- Add responses to test dependencies or document as optional
- Ensure graceful degradation when optional deps missing

---

*Last Updated: 2025-06-07*
