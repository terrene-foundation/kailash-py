# Developer Guide Consolidation Plan

## Current State: 20+ Fragmented Guides
- Inconsistent numbering (multiple 06, 08, 09, 13, 14 files)
- Overlapping content across multiple guides
- Difficult navigation and dependency tracking
- Content scattered across too many files

## Target State: 6 Focused Guides

### **01-fundamentals.md** - Core SDK Concepts
**Consolidates**: 01-node-basics.md, 02-parameter-types.md, 03-common-patterns.md
**Content**:
- Node creation and lifecycle
- Parameter types and constraints
- Basic workflow patterns
- Input/output mapping
- Validation rules

### **02-workflows.md** - Workflow Creation & Execution
**Consolidates**: 04-pythoncode-node.md, 05-directory-reader.md, 09-cyclic-workflows-guide.md, 13-workflow-builder-improvements.md
**Content**:
- PythonCodeNode patterns and best practices
- Directory and file processing
- Cyclic workflows and convergence
- Workflow builder patterns
- Data flow and connections

### **03-advanced-features.md** - Enterprise & Advanced Patterns
**Consolidates**: 08-async-database-patterns.md, 09-production-checklist.md, 09-workflow-resilience.md, 11-sharepoint-multi-auth.md, 12-session-067-enhancements.md
**Content**:
- Async database operations
- Production resilience patterns
- SharePoint multi-authentication
- Session management
- Enterprise features

### **04-production.md** - Production Deployment & Security
**Consolidates**: 08-security-guide.md, 10-credential-management.md, 15-middleware-integration.md, 16-middleware-integration-guide.md, 17-middleware-database-guide.md, 18-unified-runtime-guide.md
**Content**:
- Security configuration and best practices
- Credential management
- Middleware integration
- Production deployment
- Database patterns
- Unified runtime features

### **05-troubleshooting.md** - Debugging & Problem Solving
**Consolidates**: 07-troubleshooting.md, 08-workflow-design-patterns.md
**Content**:
- Common errors and solutions
- Debugging techniques
- Performance optimization
- Workflow design patterns
- Error recovery patterns

### **06-custom-development.md** - Extending the SDK
**Consolidates**: 06-enhanced-mcp-server.md, 08-why-enhanced-mcp-server.md, 13-advanced-rag-guide.md, 14-advanced-document-processing.md, 14-rag-best-practices.md, 19-mcp-gateway-integration.md, 20-comprehensive-rag-guide.md, custom-node-development-guide.md
**Content**:
- Custom node development
- MCP server creation
- RAG implementation patterns
- Document processing
- Gateway integration
- SDK extension patterns

## Benefits of Consolidation
1. **Clear Dependencies**: Each guide builds on previous ones
2. **Reduced Confusion**: No more duplicate numbering
3. **Better Navigation**: Logical progression from basic to advanced
4. **Comprehensive Coverage**: All content preserved and better organized
5. **Easier Maintenance**: Fewer files to update and maintain

## Migration Strategy
1. Create new consolidated guides with enhanced content
2. Update cross-references throughout documentation
3. Archive old numbered guides to maintain history
4. Update README.md with new structure
5. Test all links and references

## Cross-References Between New Guides
- 01-fundamentals → 02-workflows (workflow building)
- 02-workflows → 03-advanced-features (enterprise patterns)
- 03-advanced-features → 04-production (deployment)
- 04-production → 05-troubleshooting (debugging production issues)
- 05-troubleshooting → 06-custom-development (advanced customization)