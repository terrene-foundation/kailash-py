# ADR-0051: VS Code TypeScript Bridge Architecture

## Status
**Proposed** - Awaiting implementation

## Context

### Current State
Kailash Studio has a **complete Python GLSP server implementation** for visual workflow editing:

**Evidence** (`apps/kailash-studio/vscode-extension/`):
- **GLSPServerManager** (`glsp_server.py:30-214`): Server lifecycle, connection management, port validation
- **WorkflowDiagramLanguage** (`glsp_server.py:216-594`): Node registration, validation, cycle detection
- **NodePalette** (`node_palette.py:28-618`): Dynamic loading of 113 SDK nodes with auto-refresh
- **DiagramEditor** (`diagram_editor.py:52-303`): Canvas operations, zoom/pan, node drag-drop
- **PropertyPanel** (`property_panel.py:40-198`): Type-specific parameter editors
- **BackendAPIClient** (`backend_client.py:28-158`): Authentication, workflow execution
- **WorkflowFileManager** (`file_operations.py:37-226`): .kailash file format serialization
- **KailashExtension** (`extension.py:12-120`): Component lifecycle management

**Test Status**: 31/31 tests passing (100%), all performance targets exceeded
**Documentation**: Complete implementation summary at `VSCODE_EXTENSION_COMPLETE.md`

### The Gap
While the Python GLSP server is production-ready, it **cannot run in VS Code** without a TypeScript bridge layer:

**Missing Components**:
1. **TypeScript Extension Entry Point** (`extension.ts`) - VS Code extension activation/deactivation
2. **Language Client Setup** - LSP communication between VS Code and Python server
3. **Custom Editor Provider** - Visual editor for .kailash files
4. **Command Implementations** - 6 commands defined in package.json (create, open, execute, validate, export, connect)
5. **Webview Providers** - Node palette and property panel UI in VS Code
6. **Error Diagnostics Integration** - VS Code Problems panel integration
7. **.vsix Packaging** - Bundling TypeScript + Python for distribution

**Business Impact**:
- **No Distribution**: Cannot ship to developers without .vsix package
- **No VS Code Integration**: Developers cannot use visual workflow editor in their IDE
- **Limited Adoption**: Web platform exists, but developers prefer native IDE tools
- **Strategic Priority**: User feedback emphasized "VS Code extension should be prioritized for developers BEFORE web platform"

### Technical Challenge
The TypeScript bridge must:
1. **Spawn Python GLSP server** as a subprocess
2. **Establish IPC** using Language Server Protocol (LSP)
3. **Marshal messages** between VS Code events and GLSP protocol
4. **Manage lifecycle** of Python process (start, stop, crash recovery)
5. **Provide UI** through VS Code webviews (node palette, property panel)
6. **Handle errors** gracefully with clear diagnostics

## Decision

We will implement a **TypeScript bridge layer** using the **Language Server Protocol (LSP)** pattern with the following architecture:

### 1. Communication Architecture: Language Server Protocol

**Decision**: Use VS Code's Language Server Protocol (LSP) for TypeScript-Python IPC

**Rationale**:
- **Industry Standard**: LSP is the proven pattern for editor-server communication
- **VS Code Native**: `vscode-languageclient` provides robust LSP client implementation
- **Process Isolation**: Python server runs in separate process, crash won't affect VS Code
- **Message-Based**: JSON-RPC 2.0 messaging protocol (same as Python GLSP server already uses)
- **Bidirectional**: Supports both requests (TypeScript → Python) and notifications (Python → TypeScript)

**Integration Point**: Python GLSP server already implements message handling at `glsp_server.py:182-214` (handle_client_message method)

**Architecture**:
```
┌─────────────────────────────────────────────────────────────┐
│                      VS Code Extension                      │
│  ┌────────────────┐         ┌─────────────────────────┐    │
│  │  extension.ts  │────────▶│  Language Client (LSP)  │    │
│  │  - Activate    │         │  - vscode-languageclient│    │
│  │  - Spawn Py    │         │  - JSON-RPC 2.0         │    │
│  │  - Commands    │         │  - stdio/socket         │    │
│  └────────────────┘         └───────────┬─────────────┘    │
│         │                               │                   │
│         │                               │ LSP Messages      │
│         ▼                               ▼                   │
│  ┌────────────────┐         ┌─────────────────────────┐    │
│  │  Webviews      │         │  GLSP Protocol Handler  │    │
│  │  - Node Palette│         │  - Marshal messages     │    │
│  │  - Properties  │         │  - Error handling       │    │
│  └────────────────┘         └───────────┬─────────────┘    │
└──────────────────────────────────────────┼──────────────────┘
                                           │
                                           │ IPC (stdio)
                                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Python GLSP Server (Subprocess)                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  glsp_server.py - GLSPServerManager                  │  │
│  │  - handle_client_message() → Process LSP messages   │  │
│  │  - Node operations, validation, execution           │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Components: node_palette, diagram_editor, etc.     │  │
│  │  - 113 SDK nodes, auto-refresh, parameter editing   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2. Extension Activation Strategy: Fast Startup

**Decision**: Lazy initialization with <500ms activation time

**Implementation**:
```typescript
// extension.ts
export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // Phase 1: Immediate (0-50ms) - Register critical components
    context.subscriptions.push(
        vscode.workspace.registerTextDocumentContentProvider(...),
        vscode.commands.registerCommand('kailash.createWorkflow', createWorkflow)
    );

    // Phase 2: Background (50-200ms) - Spawn Python server
    const serverProcess = spawnPythonGLSPServer(); // Non-blocking

    // Phase 3: Deferred (200-500ms) - Language client connection
    const client = new LanguageClient('kailash-glsp', serverOptions, clientOptions);
    await client.start(); // Wait for server ready

    // Phase 4: On-Demand - Webviews and heavy components load when needed
}
```

**Performance Targets**:
- **Extension activation**: <500ms (Python baseline: 40ms, TypeScript overhead budget: 460ms)
- **Python server spawn**: <200ms (process creation + port binding)
- **LSP connection**: <300ms (handshake + initialization)
- **Webview load**: <200ms (on-demand when visual editor opened)

**Evidence**: Python extension lifecycle tested at `extension.py:27-40`, achieves 40ms activation

### 3. Custom Editor Provider: Webview-Based Visual Editor

**Decision**: Implement `CustomTextEditorProvider` for .kailash files with embedded webview

**Rationale**:
- **Native VS Code Pattern**: CustomTextEditorProvider is the standard for visual editors
- **File Synchronization**: Automatically syncs webview state with .kailash file content
- **Dirty Tracking**: VS Code handles dirty state and prompts for save
- **Context Integration**: Editor appears in tab, integrates with VS Code UI naturally

**Implementation**:
```typescript
// workflowEditor.ts
export class WorkflowEditorProvider implements vscode.CustomTextEditorProvider {
    async resolveCustomTextEditor(
        document: vscode.TextDocument,
        webviewPanel: vscode.WebviewPanel,
        token: vscode.CancellationToken
    ): Promise<void> {
        // 1. Parse .kailash file (JSON format from file_operations.py:52-98)
        const workflow = JSON.parse(document.getText());

        // 2. Create webview HTML with diagram canvas
        webviewPanel.webview.html = this.getWebviewContent(workflow);

        // 3. Bidirectional messaging
        webviewPanel.webview.onDidReceiveMessage(msg => {
            // User action in webview → Send to Python via LSP
            languageClient.sendRequest('glsp/action', msg);
        });

        // 4. Update document on changes
        workspace.onDidChangeTextDocument(e => {
            if (e.document === document) {
                this.updateWebview(webviewPanel, JSON.parse(document.getText()));
            }
        });
    }
}
```

**Integration Point**: Python file operations at `file_operations.py:37-226` (serialize/deserialize .kailash format)

### 4. Command Implementation: Bridge Pattern

**Decision**: TypeScript commands as thin wrappers forwarding to Python GLSP server

**Rationale**:
- **Minimal Logic in TypeScript**: Business logic stays in Python (already tested)
- **Type Safety**: TypeScript provides type-safe command signatures
- **Error Handling**: Centralized error translation (Python errors → VS Code diagnostics)

**Command Mapping**:
| Command | TypeScript Handler | Python Integration |
|---------|-------------------|-------------------|
| `kailash.createWorkflow` | `commands.ts:createWorkflow()` | File operations: `file_operations.py:137-152` |
| `kailash.openVisualEditor` | `commands.ts:openVisualEditor()` | Custom editor provider (TypeScript only) |
| `kailash.executeWorkflow` | `commands.ts:executeWorkflow()` | Backend client: `backend_client.py:124-158` |
| `kailash.validateWorkflow` | `commands.ts:validateWorkflow()` | Validation: `glsp_server.py:334-380` |
| `kailash.exportToPython` | `commands.ts:exportToPython()` | Code generation (TypeScript logic) |
| `kailash.connectToStudio` | `commands.ts:connectToStudio()` | Backend auth: `backend_client.py:66-99` |

**Evidence**: Commands defined in `package.json:41-71`

### 5. Webview Architecture: Dual Webview Pattern

**Decision**: Separate webviews for Node Palette and Property Panel, both communicating via LSP

**Node Palette Webview**:
```typescript
// webviews/nodePalette.ts
export class NodePaletteWebviewProvider implements vscode.WebviewViewProvider {
    async resolveWebviewView(webviewView: vscode.WebviewView): Promise<void> {
        // 1. Fetch 113 SDK nodes from Python
        const nodes = await languageClient.sendRequest('kailash/listNodes');
        // Python handler: node_palette.py:34-83 (initialize_from_sdk)

        // 2. Render searchable list with virtual scrolling
        webviewView.webview.html = this.getNodeListHTML(nodes);

        // 3. Handle drag-start events
        webviewView.webview.onDidReceiveMessage(msg => {
            if (msg.type === 'dragStart') {
                // Send to diagram editor via LSP
            }
        });

        // 4. Support refresh for custom nodes
        // Python: node_palette.py:495-513 (refresh_from_sdk)
    }
}
```

**Property Panel Webview**:
```typescript
// webviews/propertyPanel.ts
export class PropertyPanelWebviewProvider implements vscode.WebviewViewProvider {
    async resolveWebviewView(webviewView: vscode.WebviewView): Promise<void> {
        // 1. Listen for node selection events (from diagram editor)
        this.onNodeSelected(async nodeId => {
            // 2. Load parameters from Python
            const params = await languageClient.sendRequest('kailash/getNodeParameters', { nodeId });
            // Python handler: property_panel.py:40-80

            // 3. Render type-specific editors
            webviewView.webview.html = this.getEditorHTML(params);
            // Python types: property_panel.py:99-125

            // 4. Validate on input
            webviewView.webview.onDidReceiveMessage(async msg => {
                if (msg.type === 'parameterChanged') {
                    const validation = await languageClient.sendRequest('kailash/validateParameter', msg);
                    // Python validation: property_panel.py:148-198
                    this.showValidationFeedback(validation);
                }
            });
        });
    }
}
```

**Integration Points**:
- Node palette: `node_palette.py:34-83` (SDK nodes) and `node_palette.py:495-538` (auto-refresh)
- Property panel: `property_panel.py:40-198` (parameter editing and validation)

### 6. Error Handling: Diagnostic Translation Layer

**Decision**: Centralized error translation from Python exceptions to VS Code diagnostics

**Implementation**:
```typescript
// diagnostics.ts
export class DiagnosticManager {
    private diagnosticCollection: vscode.DiagnosticCollection;

    async translatePythonError(error: PythonError): Promise<vscode.Diagnostic> {
        // Map Python error types to VS Code diagnostic severities
        const severity = {
            'ValidationError': vscode.DiagnosticSeverity.Error,
            'ValidationWarning': vscode.DiagnosticSeverity.Warning,
            'CycleDetected': vscode.DiagnosticSeverity.Information
        }[error.type] || vscode.DiagnosticSeverity.Error;

        // Create diagnostic with range (if available)
        const range = error.location
            ? new vscode.Range(error.line, error.column, error.line, error.column + error.length)
            : new vscode.Range(0, 0, 0, 0);

        return new vscode.Diagnostic(range, error.message, severity);
    }

    async updateFromPythonValidation(uri: vscode.Uri, validationResult: any): Promise<void> {
        // Python validation: glsp_server.py:334-380
        const diagnostics = validationResult.errors.map(e => this.translatePythonError(e));
        this.diagnosticCollection.set(uri, diagnostics);
    }
}
```

**Error Types from Python**:
- **Validation errors**: `glsp_server.py:382-456` (node/parameter validation)
- **Connection errors**: `diagram_editor.py:159-183` (invalid connections)
- **Cycle detection**: `glsp_server.py:486-537` (workflow cycles)
- **Backend failures**: `backend_client.py:66-99` (API errors)

### 7. Packaging Strategy: Python Bundle + TypeScript Compilation

**Decision**: Bundle Python GLSP server with compiled TypeScript in .vsix

**Implementation**:
```bash
# Build process
1. npm run compile          # TypeScript → JavaScript (out/)
2. Copy Python files        # src/vscode_extension/*.py → out/python/
3. Bundle dependencies      # requirements.txt → out/python/site-packages/
4. vsce package            # Create kailash-studio-0.1.0.vsix

# Directory structure in .vsix
kailash-studio-0.1.0.vsix/
├── extension/
│   ├── out/
│   │   ├── extension.js                    # Compiled TypeScript
│   │   ├── languageClient.js
│   │   ├── glspProtocol.js
│   │   ├── workflowEditor.js
│   │   ├── commands.js
│   │   ├── diagnostics.js
│   │   └── webviews/
│   │       ├── nodePalette.js
│   │       └── propertyPanel.js
│   └── python/
│       ├── vscode_extension/
│       │   ├── glsp_server.py              # Python GLSP server
│       │   ├── node_palette.py
│       │   ├── diagram_editor.py
│       │   ├── property_panel.py
│       │   ├── backend_client.py
│       │   ├── file_operations.py
│       │   └── extension.py
│       └── site-packages/                  # Python dependencies
├── package.json                            # Extension manifest
└── README.md
```

**Python Discovery**:
- **Bundled Python**: Check `extension/python/venv/bin/python` first
- **System Python**: Fallback to `python3` or `python` in PATH
- **User Configured**: Allow override via `kailash.pythonPath` setting

**Security**:
- Python subprocess runs with restricted permissions
- CSP configured for webviews (no inline scripts)
- Input validation for all messages from webviews
- File access scoped to workspace only

## Alternatives Considered

### Alternative 1: Direct HTTP/WebSocket Communication

**Description**: Instead of LSP, use direct HTTP REST API or WebSocket between TypeScript and Python

**Pros**:
- Simpler message format (JSON over HTTP)
- Easier debugging (can use curl/Postman)
- More flexible protocol (not bound to LSP spec)

**Cons**:
- **No Standard**: Need to design custom protocol
- **Port Management**: Additional complexity for HTTP port allocation
- **Error Handling**: No standard error format (LSP has well-defined errors)
- **Tooling**: No existing VS Code integration (languageclient provides LSP client)
- **Overhead**: HTTP has higher overhead than stdio IPC

**Rejection Reason**: LSP is industry-standard, proven, and VS Code provides excellent LSP client support. Custom protocol would be reinventing the wheel.

### Alternative 2: Embed Python in TypeScript (pyodide/wasm)

**Description**: Compile Python GLSP server to WebAssembly and run in Node.js

**Pros**:
- No subprocess management
- No Python installation required
- Easier distribution (single .vsix)
- Cross-platform without system dependencies

**Cons**:
- **Immaturity**: pyodide/wasm for Python is still experimental
- **Performance**: WASM slower than native Python for compute-heavy tasks
- **Compatibility**: Many Python libraries don't work in WASM (numpy, etc.)
- **Size**: WASM bundle would be 50-100MB (vs. current 5MB Python code)
- **Debugging**: Very difficult to debug WASM Python code

**Rejection Reason**: Too experimental, performance concerns, and debugging complexity outweigh benefits. Native Python subprocess is proven and performant.

### Alternative 3: TypeScript-Only Rewrite

**Description**: Rewrite entire GLSP server logic in TypeScript, eliminating Python

**Pros**:
- Single language (TypeScript)
- No IPC complexity
- Easier debugging (one process)
- Smaller .vsix package

**Cons**:
- **Massive Effort**: 2,117 lines of Python to rewrite (6-8 weeks of work)
- **Loss of Integration**: Python GLSP server integrates with Kailash SDK (NodeRegistry, etc.)
- **Duplicate Logic**: Would duplicate validation/execution logic from backend
- **Maintenance**: Two codebases (TypeScript extension + Python backend) to maintain
- **Testing**: All 31 tests would need rewriting

**Rejection Reason**: Python GLSP server is complete, tested, and working. Rewriting would be wasteful and lose SDK integration.

### Alternative 4: Electron App Instead of VS Code Extension

**Description**: Build standalone Electron app with embedded Python server

**Pros**:
- Full control over UI/UX
- No VS Code dependency
- Can bundle Python runtime
- Richer UI possibilities

**Cons**:
- **User Preference**: Developers prefer IDE integration over standalone apps
- **Context Switching**: Forces developers to leave VS Code
- **Distribution**: Separate app to install and update
- **Integration**: No access to VS Code features (Git, debugging, etc.)
- **Strategic Misalignment**: User feedback emphasized "VS Code extension should be prioritized"

**Rejection Reason**: Violates strategic priority to provide native VS Code integration for developers. Standalone app doesn't solve the core need.

## Consequences

### Positive Consequences

#### Immediate Benefits
- **Fast Implementation**: Leverages 100% of existing Python GLSP server (2,117 lines, 31 tests passing)
- **Proven Architecture**: LSP is industry-standard with extensive tooling and documentation
- **Type Safety**: TypeScript provides compile-time type checking for VS Code API usage
- **Developer Experience**: Native VS Code integration (visual editor, commands, diagnostics)
- **Distribution Ready**: .vsix package enables VS Code marketplace distribution

#### Technical Benefits
- **Process Isolation**: Python crash doesn't affect VS Code, auto-recovery possible
- **Performance**: Native Python performance (no WASM overhead)
- **Maintainability**: Business logic stays in Python (single source of truth)
- **Testability**: TypeScript unit tests + existing Python tests (integration tests cover IPC)
- **Extensibility**: Easy to add new commands/features (thin TypeScript wrapper pattern)

#### Business Benefits
- **Market Access**: Opens VS Code marketplace to 14M+ developers
- **Strategic Alignment**: Delivers on "developers FIRST" priority from user feedback
- **Competitive Advantage**: Only visual workflow editor with full Python SDK integration
- **Lower Barrier**: Visual workflow creation reduces learning curve for new users
- **Enterprise Appeal**: Native IDE integration essential for enterprise developer adoption

### Negative Consequences

#### Development Complexity
- **IPC Layer**: TypeScript-Python communication adds complexity (mitigated by LSP standard)
- **Process Management**: Subprocess spawning, lifecycle, crash recovery (mitigated by battle-tested patterns)
- **State Synchronization**: Keeping TypeScript and Python state in sync (mitigated by message-based architecture)
- **Error Translation**: Mapping Python errors to VS Code diagnostics (mitigated by centralized translator)

#### Operational Challenges
- **Python Dependency**: Users must have Python 3.8+ installed (or use bundled Python)
- **Multi-Platform**: Need to test on Windows, macOS, Linux (mitigated by CI/CD)
- **Debugging**: Harder to debug across TypeScript-Python boundary (mitigated by LSP message logging)
- **Package Size**: .vsix larger with bundled Python (estimated 30-50MB, acceptable for marketplace)

#### Technical Debt
- **Dual Language**: TypeScript + Python requires different expertise (mitigated by clear separation)
- **Message Protocol**: Changes to GLSP protocol require updates in both languages (mitigated by versioning)
- **Testing**: Integration tests more complex (TypeScript + Python, mitigated by E2E test framework)
- **Documentation**: Need to document TypeScript extension + Python server (mitigated by existing Python docs)

### Risk Mitigation Strategies

#### Technical Risks
1. **IPC Reliability**:
   - Mitigation: Use proven LSP library (vscode-languageclient)
   - Prevention: Test message roundtrip early (Day 2)
   - Fallback: Direct HTTP if LSP fails (unlikely)

2. **Python Process Management**:
   - Mitigation: Auto-restart on crash (max 3 retries)
   - Prevention: Robust spawn logic with timeout
   - Fallback: Clear error message with manual restart option

3. **Performance Degradation**:
   - Mitigation: Lazy initialization, virtual scrolling for large lists
   - Prevention: Performance benchmarks from start
   - Fallback: Pagination if virtual scrolling insufficient

4. **Cross-Platform Issues**:
   - Mitigation: Test on Windows, macOS, Linux early
   - Prevention: Use platform-agnostic Node.js APIs
   - Fallback: Platform-specific code paths if needed

#### Business Risks
1. **User Adoption**:
   - Mitigation: Beta program with key users
   - Prevention: User research throughout development
   - Fallback: Iterate based on feedback

2. **Marketplace Approval**:
   - Mitigation: Follow VS Code extension guidelines strictly
   - Prevention: Review checklist before submission
   - Fallback: Address rejection reasons quickly

3. **Support Burden**:
   - Mitigation: Comprehensive documentation and troubleshooting guide
   - Prevention: Clear error messages with actionable steps
   - Fallback: Community support forum

## Implementation Timeline

### Phase 1: Foundation (Days 1-3)
- Extension entry point (extension.ts)
- Language client setup (languageClient.ts)
- GLSP protocol messaging (glspProtocol.ts)
- 15+ unit tests passing

### Phase 2: Visual Editor (Days 4-6)
- Custom editor provider (workflowEditor.ts)
- Node palette webview (webviews/nodePalette.ts)
- Property panel webview (webviews/propertyPanel.ts)
- 20+ integration tests passing

### Phase 3: Commands & Features (Days 7-9)
- Command implementation (commands.ts)
- Error handling & diagnostics (diagnostics.ts)
- File operations integration
- 25+ E2E tests passing

### Phase 4: Build & Package (Days 10-11)
- Build configuration
- .vsix packaging
- Installation validation
- Documentation

### Phase 5: Testing & Documentation (Days 12-14)
- Complete test coverage (100+ tests)
- User guide
- Developer guide
- Troubleshooting guide

**Total Duration**: 14 days (2 weeks)
**Estimated Effort**: 112 hours (8 hours/day)

## Success Metrics

### Performance Metrics
- **Extension Activation**: <500ms (95th percentile)
- **Python Server Spawn**: <200ms
- **LSP Connection**: <300ms
- **Message Latency**: <50ms per GLSP message
- **Webview Rendering**: <200ms for 113 nodes
- **Memory Usage**: <150MB total

### Quality Metrics
- **Test Coverage**: >80% TypeScript code coverage
- **Test Success Rate**: 100% (all tests passing)
- **Error Handling**: All failure scenarios covered
- **Documentation**: Complete user + developer guides

### Adoption Metrics (Post-Launch)
- **Installations**: >100 in first month
- **Active Users**: >50 daily active developers
- **User Satisfaction**: >4.5/5 stars on marketplace
- **Issue Resolution**: <48h average for bugs

## Dependencies

### Technical Dependencies
- **Python 3.8+**: Required for GLSP server (user must install or use bundled)
- **Node.js 18+**: Required for TypeScript compilation (dev only)
- **VS Code 1.80.0+**: Target VS Code version (user must have)
- **vscode-languageclient**: NPM package for LSP client (^8.1.0)

### Component Dependencies
- **Python GLSP Server**: `apps/kailash-studio/vscode-extension/src/vscode_extension/` (complete, 31 tests passing)
- **Backend API**: `apps/kailash-studio/backend/` (complete, for workflow execution)
- **Kailash SDK**: `src/kailash/` (NodeRegistry for 113 SDK nodes)

### Development Dependencies
- TypeScript 5.0+, Mocha 10.0+, @vscode/test-electron 2.3+, @vscode/vsce 2.19+ (for packaging)

## Conclusion

The TypeScript bridge architecture using Language Server Protocol provides the optimal balance between:

1. **Leveraging Existing Work**: 100% reuse of Python GLSP server (2,117 lines, 31 tests passing)
2. **Industry Standards**: LSP is proven, well-documented, with excellent VS Code support
3. **Developer Experience**: Native VS Code integration with visual editor, commands, diagnostics
4. **Business Value**: Enables distribution via VS Code marketplace to 14M+ developers
5. **Technical Excellence**: Type-safe TypeScript + performant Python, process isolation, auto-recovery

This architecture decision enables rapid delivery (14 days) of a production-ready VS Code extension that brings visual workflow editing to developers in their preferred IDE, while maintaining all the power and flexibility of the Kailash SDK.

The alternative approaches (HTTP/WebSocket, WASM, TypeScript rewrite, Electron app) were considered but rejected due to higher complexity, lower performance, or misalignment with strategic priorities.

**Next Steps**: Begin implementation following the 5-phase plan outlined in TODO-GAP-002.md

---

**Related Documents**:
- Implementation Plan: `/apps/kailash-studio/.claude/active/TODO-GAP-002.md`
- Python GLSP Server: `/apps/kailash-studio/VSCODE_EXTENSION_COMPLETE.md`
- Strategic Roadmap: `/apps/kailash-studio/VS_CODE_EXTENSION_ROADMAP.md`
- Platform Architecture: `/docs/adr/0050-kailash-studio-visual-workflow-platform.md`
