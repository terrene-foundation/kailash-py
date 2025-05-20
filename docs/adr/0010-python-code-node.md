# Python Code Node

## Status
Accepted

## Context
The Kailash Python SDK provides a framework for creating nodes and workflows that align with Kailash's container-node architecture. While predefined node types (CSVReader, JSONWriter, etc.) cover many common use cases, users often need to implement custom logic that doesn't fit neatly into existing node categories.

We need to provide a flexible mechanism for users to:
1. Execute arbitrary Python code within workflows
2. Use existing Python functions without rewriting them as nodes
3. Maintain stateful operations across workflow executions
4. Prototype custom node logic quickly

This is particularly important for AI Business Coaches (ABCs) who need to rapidly prototype workflows without deep technical knowledge of the node architecture or creating custom node classes from scratch.

## Decision
We will implement a `PythonCodeNode` that allows executing arbitrary Python code within Kailash workflows, with the following key features:

1. **Multiple Execution Modes**:
   - **Function Wrapping**: Convert existing Python functions to nodes
   - **Class Wrapping**: Convert Python classes to stateful nodes
   - **Code String Execution**: Execute arbitrary Python code strings
   - **File-based Execution**: Load and execute code from external files

2. **Type System Integration**:
   - Automatic type inference from function signatures
   - Input/output schema generation
   - Type validation on execution

3. **Safety Mechanisms**:
   - Module whitelisting for code execution
   - Execution timeouts
   - Resource usage monitoring
   - Exception handling and reporting

4. **Integration with Workflow System**:
   - Configuration and runtime input merging
   - Connection with upstream/downstream nodes
   - Result processing for downstream consumption

5. **Static Analysis Support**:
   - Parameter detection from function signatures
   - Return type inference
   - Documentation extraction

The implementation will consist of:
1. `CodeExecutor`: A safe Python code execution environment
2. `FunctionWrapper`: For converting functions to nodes
3. `ClassWrapper`: For converting classes to stateful nodes
4. `PythonCodeNode`: The main node implementation

## Consequences

### Advantages

1. **Rapid Prototyping**: Users can quickly integrate custom logic into workflows
2. **Code Reuse**: Existing Python functions can be used without modification
3. **Simplicity**: No need to understand the full node architecture for basic customization
4. **Flexibility**: Support for different code integration patterns
5. **Development Speed**: Faster workflow development and iteration
6. **Reduced Boilerplate**: Automatic handling of node contract requirements
7. **Type Safety**: Automatic type inference and validation

### Challenges

1. **Security Concerns**:
   - Executing arbitrary code carries inherent risks
   - Need for sandboxing and isolation
   - Module access control

2. **Performance Implications**:
   - Dynamic code execution may be slower than native nodes
   - Type inference adds overhead

3. **Debugging Complexity**:
   - Errors in dynamic code can be harder to trace
   - Stack traces may be less intuitive

4. **Maintainability**:
   - Inline code is harder to maintain than proper node classes
   - May lead to "spaghetti workflow" anti-patterns

### Mitigations

1. **Code Isolation**:
   - Implement module whitelisting
   - Add execution timeouts
   - Monitor resource usage

2. **Documentation and Examples**:
   - Provide clear guidance on when to use PythonCodeNode vs. custom nodes
   - Document best practices for code organization
   - Encourage migration to proper nodes for production code

3. **Developer Experience**:
   - Enhanced error reporting
   - Integration with debugging tools
   - Template generation for common patterns

4. **Migration Path**:
   - Tools to convert PythonCodeNode implementations to proper node classes
   - Linting and static analysis integration

### Implementation Notes

1. **Type Handling**:
   - Uses Python's typing module for type annotations
   - Handles `typing.Any` gracefully for flexible parameters
   - Special handling for complex types (List, Dict, Union, etc.)

2. **Performance Considerations**:
   - Caches function signatures and parameter definitions
   - Minimizes dynamic lookups where possible
   - Optimizes for repeated execution

3. **Integration with Workflow System**:
   - Follows the same node contract as custom nodes
   - Proper parameter definition and validation
   - Consistent execution pattern

4. **Error Reporting**:
   - Rich error context for debugging
   - Line number preservation for code strings
   - User-friendly error messages

## References

1. PythonCodeNode Implementation (docs/todos/005-python-code-node.md)
2. Base Node Interface (docs/adr/0003-base-node-interface.md)
3. Workflow Execution Fixes (docs/todos/004-workflow-execution-fixes.md)
4. Type Validation Fixes (docs/todos/008-type-validation-fixes.md)