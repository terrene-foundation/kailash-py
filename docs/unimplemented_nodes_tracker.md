# Unimplemented Nodes Tracker

## Overview

This document tracks nodes that are planned for implementation to support current client use cases, particularly **Agentic workflows using LangChain and Langgraph**.

## Current Status (12 High-Priority Nodes)

**Client Focus**: Agentic workflows, AI orchestration, and enterprise integrations

### 🔥 HIGHEST PRIORITY - Agentic AI Nodes

#### MCP (Model Context Protocol) Nodes
- **Priority**: 🔴 **URGENT** (Emerging standard for AI workflows)
- **Use Case**: Integration with Model Context Protocol Python SDK for advanced context sharing
- **Features**:
  - MCP client/server node implementations
  - Context sharing between models and tools
  - Resource management (files, databases, APIs)
  - Prompt template sharing and versioning
  - Integration with Claude, GPT, and other MCP-compatible models
- **Client Impact**: Future-proofs agentic workflows with emerging standard
- **Estimated Effort**: 2-3 weeks

#### A2A (Agent-to-Agent) Communication Nodes
- **Priority**: 🔴 **URGENT** (Multi-agent orchestration)
- **Use Case**: Direct agent communication and coordination for multi-agent workflows
- **Features**:
  - Message passing between agents
  - Agent discovery and registry
  - Coordination protocols (consensus, delegation, auction)
  - State synchronization across agents
  - Conflict resolution mechanisms
- **Client Impact**: Enables complex multi-agent workflows
- **Estimated Effort**: 2-3 weeks

#### LLMAgent Node
- **Priority**: 🔴 **URGENT** (Active client need)
- **Use Case**: LangChain/Langgraph integration for agentic workflows
- **Features**:
  - OpenAI, Anthropic, Azure OpenAI integration
  - Conversation memory and context management
  - Tool calling and function execution
  - Prompt templating and optimization
  - LangChain compatibility layer
  - MCP protocol support
- **Client Impact**: Core requirement for current agentic projects
- **Estimated Effort**: 2-3 weeks

#### EmbeddingGenerator Node
- **Priority**: 🔴 **URGENT** (Active client need)
- **Use Case**: Vector search, RAG systems, semantic similarity
- **Features**:
  - OpenAI, HuggingFace, Azure embeddings
  - Batch processing for efficiency
  - Vector similarity calculations
  - Embedding caching and storage
  - MCP resource sharing support
- **Client Impact**: Required for RAG implementations
- **Estimated Effort**: 1-2 weeks

### 🟠 HIGH PRIORITY - API & Integration Nodes

#### HTTPClient & RESTClient Nodes
- **Priority**: 🟠 **HIGH** (Frequent client requirement)
- **Use Case**: API integrations, webhook handling, external service calls
- **Features**:
  - Authentication handling (Bearer, Basic, OAuth)
  - Retry logic and error handling
  - Request/response logging
  - Rate limiting support
- **Client Impact**: Essential for enterprise integrations
- **Estimated Effort**: 1-2 weeks each

#### GraphQLClient Node
- **Priority**: 🟡 **MEDIUM** (Some client interest)
- **Use Case**: Modern API integrations
- **Features**:
  - Query and mutation support
  - Variable binding and validation
  - Schema introspection
- **Estimated Effort**: 1 week

### 🟡 MEDIUM PRIORITY - Data Processing Nodes

#### DataFilter, DataMapper, DataSorter Nodes
- **Priority**: 🟡 **MEDIUM** (Can use PythonCodeNode for now)
- **Use Case**: Data preprocessing for AI workflows
- **Features**:
  - Column-based filtering with operators
  - Data transformation and mapping
  - Efficient sorting algorithms
- **Client Impact**: Nice-to-have, workarounds exist
- **Estimated Effort**: 1 week each

#### Validator Node
- **Priority**: 🟡 **MEDIUM** (Data quality checks)
- **Use Case**: Data validation in ML pipelines
- **Features**:
  - Schema validation using JSON Schema
  - Data quality checks
  - Custom validation rules
- **Estimated Effort**: 1 week

### 🟢 LOW PRIORITY - Future Enhancements

#### TestingRuntime
- **Priority**: 🟢 **LOW** (Development tooling)
- **Use Case**: Unit testing workflows
- **Estimated Effort**: 1 week

#### NodeRegistry & WorkflowTemplates
- **Priority**: 🟢 **LOW** (Developer experience)
- **Use Case**: Easier node discovery and workflow creation
- **Estimated Effort**: 2 weeks

## Implementation Roadmap

### Phase 1: Agentic AI Foundation (8-10 weeks) 🔴
**Target**: Support current client Agentic workflows with future-ready architecture

1. **MCP (Model Context Protocol) Nodes** (2-3 weeks)
   - MCP client/server implementations
   - Context sharing infrastructure
   - Resource management
   - Future-proof design for AI workflows

2. **A2A (Agent-to-Agent) Communication Nodes** (2-3 weeks)
   - Multi-agent coordination protocols
   - Message passing infrastructure
   - Agent discovery and registry
   - Conflict resolution mechanisms

3. **LLMAgent Node** (2-3 weeks)
   - OpenAI/Anthropic integration
   - LangChain compatibility
   - Tool calling support
   - MCP protocol integration

4. **EmbeddingGenerator Node** (1-2 weeks)
   - Multiple provider support
   - Vector operations
   - Caching layer
   - MCP resource sharing

### Phase 2: Enterprise Integration (3-4 weeks) 🟠
**Target**: Robust API and data integration

1. **HTTPClient Node** (1-2 weeks)
2. **RESTClient Node** (1-2 weeks)
3. **GraphQLClient Node** (1 week)

### Phase 3: Data Processing Enhancement (3-4 weeks) 🟡
**Target**: Advanced data manipulation

1. **DataFilter Node** (1 week)
2. **DataMapper Node** (1 week)
3. **DataSorter Node** (1 week)
4. **Validator Node** (1 week)

### Phase 4: Developer Experience (3 weeks) 🟢
**Target**: Improved development workflow

1. **TestingRuntime** (1 week)
2. **NodeRegistry** (1 week)
3. **WorkflowTemplates** (1 week)

## Client-Driven Priority Updates

### Current Client Needs (Q1 2025)
- ✅ **PythonCodeNode**: Already implemented (can handle custom logic)
- 🔴 **LLMAgent**: Required for all agentic workflows
- 🔴 **EmbeddingGenerator**: Required for RAG implementations
- 🟠 **HTTPClient/RESTClient**: Required for API integrations
- 🟡 **DataFilter/Mapper**: Nice-to-have (workarounds exist)

### Recommended Next Steps

1. **Immediate (Next Sprint)**:
   - Start LLMAgent node implementation
   - Design EmbeddingGenerator interface

2. **Short-term (Next Month)**:
   - Complete Phase 1 (Agentic AI Foundation)
   - Begin Phase 2 (Enterprise Integration)

3. **Medium-term (Next Quarter)**:
   - Complete Phases 2-3
   - Gather client feedback for Phase 4

## GitHub Issues Strategy

Create epics for each phase:
- **Epic #100**: 🔴 Agentic AI Foundation (LLMAgent, EmbeddingGenerator)
- **Epic #101**: 🟠 Enterprise Integration (HTTP/REST/GraphQL clients)
- **Epic #102**: 🟡 Data Processing Enhancement (Filter/Map/Sort/Validate)
- **Epic #103**: 🟢 Developer Experience (Testing, Registry, Templates)

## Success Metrics

### Phase 1 Success Criteria:
- [ ] LLMAgent can integrate with LangChain workflows
- [ ] EmbeddingGenerator supports OpenAI and HuggingFace
- [ ] Client agentic workflows can be implemented without PythonCodeNode workarounds
- [ ] Performance meets client requirements (< 2s for LLM calls, < 500ms for embeddings)

### Overall Success:
- [ ] 80% reduction in PythonCodeNode usage for common patterns
- [ ] Client satisfaction scores > 4.5/5 for workflow development experience
- [ ] Documentation completion with working examples
- [ ] Zero critical bugs in production client deployments
