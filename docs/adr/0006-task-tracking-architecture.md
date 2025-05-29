# Task Tracking Architecture

## Status
Accepted

## Context
The Kailash Python SDK needs to track workflow execution for debugging, monitoring, and analysis. Task tracking must:
- Capture execution state and timing
- Store results and errors
- Support multiple storage backends
- Enable execution history analysis
- Integrate seamlessly with runtime

## Decision
We will implement a task tracking system with:

1. **Data Models**:
   - `WorkflowRun`: Represents a workflow execution
   - `TaskRun`: Represents individual node executions 
   - `TaskMetrics`: Captures performance metrics for tasks
   - Status enums for execution states
   - Backward compatibility features in models (alias fields, legacy naming support)

2. **TaskManager**:
   - Central API for tracking operations
   - In-memory caching for performance
   - Delegates to storage backends
   - Metrics collection and management
   - Task dependency tracking

3. **Storage Backends**:
   - Abstract `StorageBackend` interface
   - `FileSystemStorage`: JSON files on disk with indexed access
   - `DatabaseStorage`: SQLite for efficient querying
   - Storage format versioning for backward compatibility
   - Extensible for other backends

4. **Integration Points**:
   - Runtime engines create runs/tasks
   - Nodes report execution status and metrics
   - CLI queries tracking data
   - Support for task retry and dependency tracking

## Consequences

### Positive
- Complete execution visibility
- Pluggable storage backends
- Performance through caching
- Support for debugging and analysis
- Clear separation of concerns
- Easy to extend
- Robust metrics collection
- Backward compatibility with legacy systems

### Negative
- Additional complexity
- Storage overhead
- Potential performance impact
- Synchronization considerations
- Maintenance of backward compatibility features

### Implementation Notes
The tracking system:
- Uses UUIDs for unique identification
- Stores all intermediate results
- Supports export/import of runs
- Enables task duration analysis
- Provides summary views
- Includes metrics collection for performance analysis
- Has in-memory caching for frequently accessed data
- Supports indexed access for faster querying
- Maintains backward compatibility with legacy field names

This design provides comprehensive tracking while maintaining flexibility for different deployment scenarios.