# Kailash Python SDK v0.8.5 Release

## 🎉 Test Infrastructure & Application Framework Enhancement

This release marks a significant milestone in test infrastructure maturity and application framework readiness.

### Key Achievements
- ✅ **100% Tier 1 Test Pass Rate**: All 3,439+ unit tests passing with proper isolation
- 📦 **DataFlow v0.3.1**: Enhanced transaction support & schema management (90.7% test pass rate)
- 📦 **Nexus v1.0.3**: Production-ready with WebSocket transport (100% test pass rate)
- 🔧 **Test Isolation Framework**: Comprehensive `@pytest.mark.requires_isolation` implementation
- 📚 **SDK Gold Standards**: TODO-123 completed with enhanced validation

### Installation
```bash
# Core SDK
pip install kailash==0.8.5

# With application frameworks
pip install kailash[dataflow,nexus]==0.8.5

# Or install frameworks separately
pip install kailash-dataflow==0.3.1
pip install kailash-nexus==1.0.3
```

### What's Changed
- Test isolation framework prevents state pollution between tests
- Enhanced parameter validation with helpful error messages
- Critical bug fixes in MCP server, AsyncSQL, bulkhead, and health checks
- Transaction context propagation in DataFlow workflows
- WebSocket transport implementation for Nexus MCP
- 217 files updated with comprehensive improvements

### Breaking Changes
None - Full backward compatibility maintained

### Contributors
This release includes contributions from the SDK team with special focus on test infrastructure hardening and application framework maturity.

---

For detailed release notes, see: [v0.8.5 Release Notes](sdk-users/6-reference/changelogs/releases/v0.8.5-2025-01-22.md)

For questions or issues: https://github.com/anthropics/claude-code/issues