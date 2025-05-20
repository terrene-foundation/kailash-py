# Docker Runtime Architecture

## Status
Accepted

## Context
The Kailash Python SDK needs to align with Kailash's container-node architecture where each node runs as an independent container within a workflow orchestration. This architecture enables:

1. Isolated execution environments for each node
2. Independent resource allocation and scaling
3. Heterogeneous technology stacks within a workflow
4. Improved security through containerization
5. Infrastructure-agnostic deployment
6. Compatibility with Kubernetes and other container orchestration platforms

While the LocalRuntime is useful for development and testing, it does not reflect the production architecture of Kailash where nodes run in separate containers. We need a way to test and validate workflows in an environment that more closely resembles the production container architecture.

## Decision
We will implement a Docker-based runtime (`DockerRuntime`) that:

1. Executes each node in a separate Docker container
2. Provides workflow orchestration across containerized nodes
3. Handles data passing between containers
4. Manages resource constraints and network configuration
5. Integrates with task tracking for monitoring and debugging

The implementation will include:

1. **DockerNodeWrapper**: A class to handle the containerization of individual nodes:
   - Dockerfile generation specific to each node
   - SDK packaging into Docker context
   - Container execution with proper I/O mapping
   - Result extraction from containers

2. **DockerRuntime**: A class extending BaseRuntime for orchestrating containerized workflows:
   - Topological execution of nodes
   - Data passing between containerized nodes
   - Resource management (memory, CPU)
   - Network configuration for container communication
   - Error handling and reporting
   - Cleanup of Docker resources

3. **Data Transfer Mechanism**: Use volume mounts for passing data between containers:
   - JSON serialization for data interchange
   - Volume mounting for input/output directories
   - Connection mapping to route data correctly

4. **Resource Management**: Explicit resource constraints for each node:
   - Memory limits
   - CPU limits
   - Per-node configuration
   - Default settings with overrides

5. **Testing Support**: Comprehensive testing infrastructure:
   - Unit tests with mocked Docker commands
   - Integration tests with actual Docker execution
   - Comparison with local runtime results
   - Docker presence detection and test skipping

## Consequences

### Advantages

1. **Production-Like Testing**: Validates workflows in an environment similar to Kailash production
2. **Isolation**: Complete separation of dependencies, avoiding version conflicts
3. **Resource Control**: Fine-grained management of memory and CPU per node
4. **Scalability**: Groundwork for horizontal scaling across machines/clusters
5. **Resilience**: Node failures don't crash the entire workflow
6. **Security**: Reduced attack surface through containerization
7. **Technology Flexibility**: Enables mixing different language runtimes in a workflow
8. **Resource Distribution**: Allows CPU-intensive nodes to run on dedicated hardware

### Challenges

1. **Performance Overhead**: 
   - Container startup time (1-3s per container)
   - Memory overhead (~10-50MB per container)
   - Serialization/deserialization costs for data transfer

2. **Development Complexity**:
   - More complex debugging process
   - More infrastructure requirements for development
   - Docker dependency for testing

3. **I/O Bottlenecks**:
   - File system operations for data transfer
   - JSON serialization limitations for large datasets

4. **Resource Usage**:
   - Higher overall resource consumption
   - Potential disk space issues with Docker images

### Optimization Strategies

1. **Data Transfer Optimization**:
   - Use references to data (e.g., S3 URIs) instead of full datasets
   - Shared volumes for large data

2. **Container Efficiency**:
   - Minimize image size
   - Pre-warm containers when possible
   - Reuse containers for similar node types

3. **Parallelization**:
   - Execute independent workflow branches in parallel
   - Distribute containers across multiple hosts

### Implementation Notes

1. The Docker runtime is implemented using subprocess calls to the Docker CLI, providing simplicity and reducing dependencies on third-party Docker SDKs.

2. Data exchange uses volume mounts rather than network communication for reliability and simplicity, although this may not be optimal for distributed deployment.

3. SDK packaging copies the SDK files directly into the Docker context, which is suitable for development but would need refinement for production use.

4. Error handling captures both Docker-level errors and node execution errors, providing comprehensive debugging information.

5. Resource management allows explicit control of memory and CPU limits for production-like behavior testing.

## References

1. Docker Runtime Implementation (docs/todos/013-docker-runtime-implementation.md)
2. Local Execution Strategy (docs/adr/0005-local-execution-strategy.md)
3. Task Tracking Architecture (docs/adr/0006-task-tracking-architecture.md)