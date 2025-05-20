# Workflow Execution Improvements

## Status
Accepted

## Context
The initial implementation of the Kailash Python SDK's workflow execution system had several limitations that affected flexibility, usability, and robustness:

1. **Configuration Handling**: Workflow nodes were initialized with configuration but lacked a mechanism to accept additional runtime inputs during execution.

2. **Type Validation**: The type validation system was too rigid, particularly with `typing.Any` and complex types, leading to valid workflows being rejected.

3. **Parameter Requirements**: Some nodes (like writers) required parameters at initialization that should only be required at execution time, limiting their use in workflows.

4. **Output Schema Support**: The node system lacked formal support for output schemas and validation.

5. **Execution Pattern Inconsistency**: Different node types implemented execution differently, creating inconsistency and complicating workflow orchestration.

These issues particularly affected the ability of AI Business Coaches (ABCs) to create flexible workflows and led to confusing error messages and unexpected validation failures.

## Decision
We will implement several improvements to the workflow execution system:

1. **Enhanced Node Execution Contract**:
   - Add `execute(**runtime_inputs)` method signature to all nodes
   - Merge runtime inputs with stored configuration
   - Validate combined parameters
   - Maintain backward compatibility with existing node implementations

2. **Improved Type Validation**:
   - Skip validation for `typing.Any` types
   - Enhance type conversion for primitive types
   - Add support for validating complex types (List, Dict, Union)
   - Provide clear error messages for validation failures

3. **Optional Parameters for Workflow Usage**:
   - Make node parameters that represent data inputs/outputs optional at initialization
   - Only require these parameters at execution time
   - Update writer nodes to make data parameters optional for workflow connections

4. **Output Schema Support**:
   - Add output schema definition to nodes
   - Implement validation for node outputs
   - Support schema inference for PythonCodeNode

5. **Consistent Execution Pattern**:
   - Standardize `run()` and `execute()` methods across all node types
   - Ensure all nodes handle configuration and runtime inputs consistently
   - Add support for nested configuration

## Consequences

### Advantages

1. **Flexibility**: Nodes can accept both configuration and runtime inputs
2. **Usability**: Better error messages and more intuitive behavior
3. **Robustness**: More reliable type validation and execution
4. **Workflow Composability**: Easier to connect nodes in workflows
5. **Consistency**: Standardized execution pattern across all node types
6. **Type Safety**: Better handling of complex types and Any types
7. **Enhanced Debugging**: Clearer error messages for validation failures

### Challenges

1. **Backward Compatibility**:
   - Existing custom nodes may need updates
   - Documentation needs to reflect new patterns

2. **Implementation Complexity**:
   - More complex parameter merging and validation
   - Handling of edge cases with nested configurations

3. **Performance Implications**:
   - Additional validation and merging steps
   - More complex type checking

### Implementation Details

1. **Node Base Class Changes**:
   - Added `execute(**runtime_inputs)` method to merge and validate inputs
   - Enhanced type validation to handle Any types correctly
   - Improved error reporting for validation failures

2. **CSVWriter and Other Writer Nodes**:
   - Made `data` parameter non-required for workflow usage
   - Updated validation to check for required parameters at execution time

3. **PythonCodeNode Enhancements**:
   - Added support for input and output schemas
   - Fixed handling of configuration and runtime inputs
   - Updated to use base class execution pattern

4. **Workflow Class Updates**:
   - Improved handling of node connections
   - Enhanced error reporting for workflow validation
   - Added support for nested configuration

5. **LocalRuntime Improvements**:
   - Updated to use the enhanced execution pattern
   - Better error handling and reporting
   - Support for execution monitoring

### Handling of Special Cases

1. **typing.Any Parameters**:
   - Skip type validation
   - Accept any input value
   - Document this behavior clearly

2. **Complex Type Validation**:
   - Support for List[T], Dict[K, V], Union[T1, T2, ...]
   - Validation of nested structures
   - Clear error messages for validation failures

3. **Nested Configuration**:
   - Support for dictionary merging
   - Preservation of nested structure
   - Handling of conflicting keys

## References

1. Workflow Execution Fixes (docs/todos/004-workflow-execution-fixes.md)
2. Type Validation Fixes (docs/todos/008-type-validation-fixes.md)
3. Base Node Interface (docs/adr/0003-base-node-interface.md)
4. Workflow Representation (docs/adr/0004-workflow-representation.md)