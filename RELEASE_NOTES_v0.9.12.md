# Kailash Core SDK v0.9.12 Release Notes

**Release Date:** January 11, 2025  
**Release Type:** Patch Release (Bug Fixes & Stability)

## 🎯 Overview

This maintenance release focuses on SQLite compatibility improvements and code quality enhancements, ensuring seamless database operations across both PostgreSQL and SQLite environments.

## ✨ Key Improvements

### Database Compatibility
- **Enhanced SQLite Support**: Improved AsyncSQLDatabaseNode compatibility with SQLite databases
- **Connection String Parsing**: Better handling of SQLite connection parameters
- **Cross-Database Consistency**: Maintained feature parity between PostgreSQL and SQLite

### Code Quality
- **Style Standardization**: Applied black, isort, and ruff formatting across entire codebase
- **Import Organization**: Standardized import ordering and structure
- **Linting Compliance**: Resolved 5 linting issues for cleaner code

## 🔧 Technical Details

### AsyncSQLDatabaseNode Enhancements
- Improved parameter handling for SQLite connections
- Better error handling for database-specific operations
- Enhanced connection pooling compatibility

### Development Experience
- Consistent code formatting across 1,920+ files
- Improved developer workflow with standardized tooling
- Better IDE support through consistent style

## 📦 Dependencies

- **Python**: >=3.12 (no change)
- **Core Dependencies**: All dependencies remain stable
- **Backwards Compatibility**: 100% compatible with v0.9.11

## 🚀 Upgrade Instructions

```bash
pip install --upgrade kailash==0.9.12
```

**Migration Notes:**
- No breaking changes
- No configuration updates required
- Existing workflows will continue to work unchanged

## 📋 What's Included

### Core Components
- ✅ WorkflowBuilder and LocalRuntime (stable)
- ✅ 110+ nodes including enhanced AsyncSQLDatabaseNode
- ✅ MCP integration (stable)
- ✅ Complete middleware and gateway systems

### Database Support
- ✅ PostgreSQL (full feature support)
- ✅ SQLite (enhanced compatibility)
- ✅ MySQL (alpha support)

## 🐛 Bug Fixes

- Fixed SQLite connection string parsing edge cases
- Resolved import ordering inconsistencies
- Improved code style compliance across modules

## 🔄 Compatibility

**Full Compatibility With:**
- DataFlow v0.4.1 (released simultaneously)
- Nexus v1.0.5+ 
- All existing workflow patterns
- MCP protocol v1.11.0

## 📚 Documentation

- [API Documentation](https://docs.kailash-sdk.com/)
- [Getting Started Guide](https://docs.kailash-sdk.com/quickstart)
- [Migration Guide](https://docs.kailash-sdk.com/migration)

## 🤝 Contributors

This release was made possible by comprehensive testing and quality assurance efforts.

---

**Next Release Preview:** v0.9.13 will focus on performance optimizations and additional node types.

For questions or support, please visit our [GitHub repository](https://github.com/terrene-foundation/kailash-py) or [documentation site](https://docs.kailash-sdk.com/).