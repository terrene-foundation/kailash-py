# Current Release Status

## Next Release: v0.3.0

**Planned Date**: June 10, 2025
**Status**: 🟡 In Preparation
**Type**: Minor Release (Parameter Lifecycle Architecture)
**PR**: TBD
**PyPI**: TBD
**GitHub**: TBD

### Release Theme
Parameter Lifecycle Architecture & Data Consolidation - Major architectural improvements for flexible node construction and centralized data management

### Key Features
1. **Parameter Lifecycle Architecture** (Session 061/062)
   - Nodes can be created without required parameters
   - Parameters validated at execution time
   - Clear separation: Construction → Configuration → Execution
   - More flexible workflow construction patterns

2. **Data Consolidation**
   - Centralized `/data/` directory structure
   - Standardized data access utilities
   - Backward compatibility maintained
   - 2,487+ files reorganized

3. **Runtime Architecture Fixes**
   - Fixed critical bug: `execute()` → `run()`
   - Workflow validation supports runtime parameters
   - Improved error handling and messages

4. **PythonCodeNode Enhancements**
   - Better `from_function()` with full IDE support
   - Enhanced data science capabilities
   - Improved type inference
   - Best practices documentation

5. **Enterprise Workflow Library**
   - Production-ready workflow patterns
   - Control flow implementations
   - Industry-specific examples
   - Migration guides from code-heavy patterns

### Breaking Changes
- Runtime method change (`execute()` → `run()`)
- Workflow validation API accepts runtime parameters
- Data file reorganization (backward compatible)

## Previous Release: v0.2.2

**Release Date**: 2025-06-10
**Status**: ✅ Released
**Type**: Minor Release (Documentation & API Modernization)
**PR**: #109
**PyPI**: https://pypi.org/project/kailash/0.2.2/
**GitHub**: https://github.com/terrene-foundation/kailash-py/releases/tag/v0.2.2

### Release Theme
Major documentation restructuring and comprehensive migration to new CycleBuilder API

### Key Features
1. **Documentation Restructuring**
   - Reorganized into `sdk-users/` and `# contrib (removed)/` directories
   - Production-ready workflow library with industry-specific examples
   - Improved navigation with CLAUDE.md files at each level
   - Clear separation between building WITH the SDK vs developing the SDK

2. **CycleBuilder API Migration**
   - 130+ test updates from deprecated `workflow.connect(..., cycle=True)` to new fluent API
   - Improved readability with method chaining
   - Backward compatibility for complex conditional cycles

3. **Enhanced Workflow Library**
   - By Pattern: API integration, data processing, file processing workflows
   - By Industry: Healthcare, finance-specific implementations
   - By Enterprise: Customer operations, multi-system integrations
   - Quick Start: 30-second workflow patterns for rapid prototyping

### Release Statistics
- **Total Tests**: 751 passing (99.3% pass rate)
- **Deprecation Warnings Fixed**: 130
- **Documentation Files Updated**: 50+
- **Breaking Changes**: None

## Next Release: v0.2.3

**Planned Date**: TBD
**Status**: 🔵 Planning
**Type**: Minor Release

### Planned Features
1. Enhanced visualization for cyclic workflows
2. More pre-built cycle patterns
3. Integration with popular ML frameworks
4. Performance optimizations for nested cycles

### Release History
- v0.2.2 - 2025-06-10 - Documentation Restructuring & CycleBuilder Migration
- v0.2.1 - 2025-06-09 - DirectoryReaderNode, DataTransformer fixes, Real-world examples
- v0.2.0 - 2025-06-08 - Universal Hybrid Cyclic Graph Architecture
- v0.1.6 - 2025-06-05 - Security & Production Hardening + CI/CD
- v0.1.5 - 2025-06-05 - Self-Organizing Agents + Test Fixes
- v0.1.4 - 2025-06-04 - MCP Integration & A2A Communication
- v0.1.3 - 2025-05-28 - API Integration & Immutable State
- v0.1.2 - 2025-05-27 - Conditional Routing & Docker Runtime
- v0.1.1 - 2025-05-26 - Error Handling & Import Fixes
- v0.1.0 - 2025-05-24 - Initial Release
