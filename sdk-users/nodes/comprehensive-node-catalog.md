# Comprehensive Node Catalog - Kailash SDK

This reference guide lists all available nodes in the Kailash SDK and their primary use cases. **Always prefer using these specialized nodes over PythonCodeNode when possible.**

*Total: 110+ specialized nodes across 12 categories*

## ⭐ Core SDK Improvements

**Dynamic Workflow Compatibility**: All nodes in this catalog now work seamlessly with `WorkflowBuilder.from_dict()` thanks to automatic parameter mapping. The SDK automatically handles constructor differences between nodes, ensuring robust dynamic workflow creation.

**✅ Enhanced Features**:
- Automatic `id` ↔ `name` parameter mapping
- Constructor validation during node registration
- Improved error diagnostics with signature details
- Full compatibility with middleware dynamic workflows

## Table of Contents
- [AI/ML Nodes](#aiml-nodes) - 30+ nodes for LLM agents, embeddings, self-organizing agents
- [Data Processing Nodes](#data-processing-nodes) - 23+ nodes for files, databases, streaming, advanced retrieval
- [RAG Toolkit Nodes](#rag-toolkit-nodes) - ⭐ NEW: 47+ nodes for comprehensive RAG implementations
- [API Integration Nodes](#api-integration-nodes) - 15+ nodes for HTTP, REST, GraphQL, rate limiting
- [Logic & Control Nodes](#logic--control-nodes) - 10+ nodes for routing, merging, loops, async operations
- [Transform Nodes](#transform-nodes) - 15+ nodes for data transformation, advanced chunking, intelligent compression
- [Admin & Security Nodes](#admin--security-nodes) - 15+ nodes for user management, permissions, audit, security monitoring
- [Authentication Nodes](#authentication-nodes) - ⭐ NEW: 6+ nodes for enterprise authentication & authorization
- [Compliance Nodes](#compliance-nodes) - ⭐ NEW: 2+ nodes for regulatory compliance (GDPR, data retention)
- [Middleware Nodes](#middleware-nodes) - ⭐ ENTERPRISE: 5+ nodes for production applications
- [Enterprise Workflow Nodes](#enterprise-workflow-nodes) - ⭐ NEW: 4+ nodes for enterprise automation
- [Testing Nodes](#testing-nodes) - 1+ nodes for credential and workflow testing
- [Code Execution Nodes](#code-execution-nodes) - 1 node for custom Python code
- [When to Use PythonCodeNode](#when-to-use-pythoncodenode)

## AI/ML Nodes

### LLM Agents
- **LLMAgentNode**: General-purpose LLM agent with unified provider support
  ```python
  # Use instead of PythonCodeNode calling OpenAI/Anthropic APIs
  node = LLMAgentNode(provider="openai", model="gpt-4")
  ```
- **MonitoredLLMAgentNode**: LLM agent with cost tracking and budget controls
  ```python
  # Track costs and enforce budget limits
  node = MonitoredLLMAgentNode(model="gpt-4", budget_limit=10.0, alert_threshold=0.8)
  ```
- **IterativeLLMAgentNode**: LLM agent with iterative refinement capabilities
- **ChatAgent**: Conversational agent with context management
- **RetrievalAgent**: RAG-enabled agent for document retrieval
- **FunctionCallingAgent**: Agent with function calling capabilities
- **PlanningAgent**: Agent specialized for planning and orchestration

### Agent Coordination & Communication
- **A2AAgentNode**: Agent-to-agent communication node
- **A2ACoordinatorNode**: Coordinates multiple A2A agents
- **SharedMemoryPoolNode**: Shared memory for agent coordination

### Self-Organizing Agents
- **AgentPoolManagerNode**: Manages pools of agents dynamically
- **ProblemAnalyzerNode**: Analyzes problems for optimal agent assignment
- **SelfOrganizingAgentNode**: Self-organizing agent with adaptive behavior
- **SolutionEvaluatorNode**: Evaluates solutions from multiple agents
- **TeamFormationNode**: Forms teams of agents for complex tasks

### Intelligent Orchestration
- **OrchestrationManagerNode**: Manages complex multi-agent orchestrations
- **QueryAnalysisNode**: Analyzes queries for intelligent routing
- **ConvergenceDetectorNode**: Detects convergence in iterative processes
- **IntelligentCacheNode**: Smart caching for LLM responses
- **MCPAgentNode**: MCP-enabled agent with enhanced capabilities

### Embeddings & ML Models
- **EmbeddingGeneratorNode**: Generate text embeddings with caching
  ```python
  # Use instead of PythonCodeNode with OpenAI embeddings
  node = EmbeddingGeneratorNode(provider="openai", model="text-embedding-ada-002")
  ```
- **TextClassifier**: Classify text into categories
- **SentimentAnalyzer**: Analyze sentiment in text
- **NamedEntityRecognizer**: Extract named entities from text
- **TextSummarizer**: Summarize long text documents
- **ModelPredictor**: General ML model predictions

## Data Processing Nodes

### File Readers
- **CSVReaderNode**: Read CSV files with configurable options
  ```python
  # Use instead of PythonCodeNode with pd.read_csv()
  node = CSVReaderNode(file_path="data.csv", headers=True, delimiter=",")
  ```
- **JSONReaderNode**: Read JSON files into Python objects
  ```python
  # Use instead of PythonCodeNode with json.load()
  node = JSONReaderNode(file_path="data.json")
  ```
- **TextReaderNode**: Read plain text files
  ```python
  # Use instead of PythonCodeNode with open().read()
  node = TextReaderNode(file_path="document.txt")
  ```

### File Writers
- **CSVWriterNode**: Write data to CSV files
- **JSONWriterNode**: Write data to JSON files
- **TextWriterNode**: Write text to files

### Database Operations
- **SQLDatabaseNode**: Execute SQL queries and commands
  ```python
  # Use instead of PythonCodeNode with database connections
  node = SQLDatabaseNode(
      connection_string="postgresql://user:pass@host/db",
      query="SELECT * FROM customers WHERE age > 30"
  )
  ```
- **AsyncSQLDatabaseNode**: ⭐ NEW: High-performance async database operations
  ```python
  # Use for high-concurrency database operations (Session 065)
  node = AsyncSQLDatabaseNode(
      database_type="postgresql",
      host="localhost", database="app_db",
      query="SELECT * FROM portfolios",
      pool_size=20, max_pool_size=50
  )
  ```
- **AsyncPostgreSQLVectorNode**: ⭐ NEW: pgvector similarity search
  ```python
  # Use for AI/ML vector operations (Session 065)
  node = AsyncPostgreSQLVectorNode(
      connection_string="postgresql://user:pass@host/vectordb",
      table_name="embeddings",
      operation="search",
      vector=[0.1, 0.2, ...],
      distance_metric="cosine"
  )
  ```

### SharePoint Integration
- **SharePointGraphReader**: Read files from SharePoint via Graph API
- **SharePointGraphWriter**: Write files to SharePoint via Graph API
- **SharePointGraphReaderEnhanced**: ⭐ NEW: Multiple authentication methods (Session 067)
  ```python
  # Certificate authentication (most secure)
  node = SharePointGraphReaderEnhanced(
      auth_method="certificate",
      certificate_path="/path/to/cert.pem",
      tenant_id="your-tenant-id",
      client_id="your-app-id"
  )

  # Managed Identity (Azure-hosted apps)
  node = SharePointGraphReaderEnhanced(
      auth_method="managed_identity",
      site_url="https://company.sharepoint.com/sites/project"
  )
  ```

### Vector Database & Embeddings
- **EmbeddingNode**: Generate embeddings from text
- **VectorDatabaseNode**: Store and query vector embeddings
- **TextSplitterNode**: Split text into chunks for embedding

### Advanced Retrieval & RAG ⭐ **NEW**
- **HybridRetrieverNode**: State-of-the-art hybrid retrieval combining dense and sparse methods
  ```python
  # Use for production RAG systems - 20-30% better performance
  node = HybridRetrieverNode(
      fusion_strategy="rrf",  # Reciprocal Rank Fusion (gold standard)
      dense_weight=0.6,       # Semantic search weight
      sparse_weight=0.4,      # Keyword search weight
      top_k=5
  )
  ```
- **RelevanceScorerNode**: Advanced relevance scoring with embeddings
  ```python
  # Use instead of PythonCodeNode for relevance ranking
  node = RelevanceScorerNode(
      similarity_method="cosine",
      top_k=3
  )
  ```

### Streaming Data
- **KafkaConsumerNode**: Consume messages from Kafka topics
- **StreamPublisherNode**: Publish messages to streams
- **WebSocketNode**: Handle WebSocket connections
- **EventStreamNode**: Process event streams

### Data Sources & Discovery
- **DocumentSourceNode**: Load documents as workflow input
- **QuerySourceNode**: Generate queries as workflow input
- **DirectoryReaderNode**: Read directory contents and discover files
- **FileDiscoveryNode**: Discover files matching patterns
- **EventGeneratorNode**: Generate events for workflows

### Data Retrieval
- **RelevanceScorerNode**: Score document relevance for RAG pipelines

## RAG Toolkit Nodes

### Core RAG Strategy Nodes
- **SemanticRAGNode**: Semantic chunking with dense embeddings for conceptual queries
  ```python
  # Best for narrative content, general Q&A, conceptual queries
  node = SemanticRAGNode(config=RAGConfig(chunk_size=1000, retrieval_k=5))
  ```
- **StatisticalRAGNode**: Statistical chunking with sparse retrieval for technical content
  ```python
  # Best for technical docs, code, structured content
  node = StatisticalRAGNode(config=RAGConfig(chunk_size=800, retrieval_k=3))
  ```
- **HybridRAGNode**: Combines semantic + statistical for optimal coverage (20-30% better performance)
  ```python
  # Best for mixed content, general purpose, maximum coverage
  node = HybridRAGNode(config=RAGConfig(), fusion_method="rrf")
  ```
- **HierarchicalRAGNode**: Multi-level processing preserving document structure
  ```python
  # Best for long documents, structured content, complex queries
  node = HierarchicalRAGNode(config=RAGConfig(chunk_size=1200))
  ```

### RAG Workflow Nodes
- **SimpleRAGWorkflowNode**: Basic chunk → embed → store → retrieve pipeline
  ```python
  # Perfect for getting started or simple document Q&A
  workflow = SimpleRAGWorkflowNode(config=RAGConfig())
  ```
- **AdvancedRAGWorkflowNode**: Multi-stage with quality checks and strategy selection
  ```python
  # Production-ready with monitoring and validation
  workflow = AdvancedRAGWorkflowNode(config=RAGConfig())
  ```
- **AdaptiveRAGWorkflowNode**: AI-driven strategy selection using LLM analysis
  ```python
  # Fully automated with intelligent optimization
  workflow = AdaptiveRAGWorkflowNode(llm_model="gpt-4", config=RAGConfig())
  ```
- **RAGPipelineWorkflowNode**: Configurable pipeline for custom requirements
  ```python
  # Flexible runtime configuration
  workflow = RAGPipelineWorkflowNode(default_strategy="hybrid", config=RAGConfig())
  ```

### RAG Router & Analysis Nodes
- **RAGStrategyRouterNode**: LLM-powered intelligent strategy selection
  ```python
  # Automatically select optimal RAG strategy based on content analysis
  router = RAGStrategyRouterNode(llm_model="gpt-4", provider="openai")
  ```
- **RAGQualityAnalyzerNode**: Quality assessment and optimization recommendations
  ```python
  # Analyze RAG results and suggest improvements
  analyzer = RAGQualityAnalyzerNode()
  ```
- **RAGPerformanceMonitorNode**: Performance tracking and insights over time
  ```python
  # Monitor system performance and generate optimization insights
  monitor = RAGPerformanceMonitorNode()
  ```

### RAG Registry & Discovery
- **RAGWorkflowRegistry**: Central registry for discovering and creating RAG components
  ```python
  # Unified interface for RAG component discovery and recommendations
  from kailash.nodes.rag import RAGWorkflowRegistry
  registry = RAGWorkflowRegistry()

  # Get strategy recommendation
  recommendation = registry.recommend_strategy(
      document_count=100, is_technical=True, performance_priority="accuracy"
  )

  # Create recommended components
  strategy = registry.create_strategy(recommendation["recommended_strategy"])
  workflow = registry.create_workflow("adaptive")
  ```

## API Integration Nodes

### HTTP Clients
- **HTTPRequestNode**: Make HTTP requests with full configuration
  ```python
  # Use instead of PythonCodeNode with requests library
  node = HTTPRequestNode(
      url="https://api.example.com/data",
      method="GET",
      headers={"Authorization": "Bearer token"}
  )
  ```
- **AsyncHTTPRequestNode**: Asynchronous HTTP requests

### REST API Clients
- **RESTClientNode**: RESTful API client with built-in patterns
  ```python
  # Use instead of PythonCodeNode for REST APIs
  node = RESTClientNode(
      base_url="https://api.example.com",
      endpoint="/users",
      method="POST"
  )
  ```
- **AsyncRESTClientNode**: Asynchronous REST client

### GraphQL Clients
- **GraphQLClientNode**: GraphQL API client
- **AsyncGraphQLClientNode**: Asynchronous GraphQL client

### Authentication
- **BasicAuthNode**: Basic authentication handling
- **OAuth2Node**: OAuth 2.0 authentication flow
- **APIKeyNode**: API key authentication management

### Rate Limiting & Monitoring
- **RateLimitedAPINode**: API client with built-in rate limiting
- **AsyncRateLimitedAPINode**: Async rate-limited API client
- **HealthCheckNode**: API health monitoring
- **SecurityScannerNode**: Security scanning for APIs

## Logic & Control Nodes

### Control Flow
- **SwitchNode**: Conditional routing (if/else logic)
  ```python
  # Use instead of PythonCodeNode with if/else
  node = SwitchNode(
      condition="status == 'success'",
      true_output="success_path",
      false_output="error_path"
  )
  ```
- **AsyncSwitchNode**: Asynchronous conditional routing

### Data Merging
- **MergeNode**: Merge multiple data streams
  ```python
  # Use instead of PythonCodeNode combining multiple inputs
  node = MergeNode(merge_strategy="concat")
  ```
- **AsyncMergeNode**: Asynchronous data merging

### Loops & Convergence
- **LoopNode**: Execute nodes in a loop with conditions
- **ConvergenceCheckerNode**: Check for convergence conditions
- **MultiCriteriaConvergenceNode**: Multi-criteria convergence detection

### Workflow Composition
- **WorkflowNode**: Embed workflows within workflows

## Transform Nodes

### Data Processing
- **FilterNode**: Filter data based on conditions
  ```python
  # Use instead of PythonCodeNode with df[df['column'] > value]
  node = FilterNode(condition="age > 30")
  ```
- **Filter**: Basic filter operation
- **Map**: Apply transformations to each item
  ```python
  # Use instead of PythonCodeNode with list comprehensions or df.apply()
  node = Map(function=lambda x: x.upper())
  ```
- **Sort**: Sort data by specified criteria
  ```python
  # Use instead of PythonCodeNode with sorted() or df.sort_values()
  node = Sort(key="timestamp", reverse=True)
  ```
- **DataTransformer**: General-purpose data transformation

### Text Processing & Advanced Chunking
- **SemanticChunkerNode**: ⭐ **NEW** Intelligent chunking based on semantic similarity
  ```python
  # Use for narrative text and general documents
  node = SemanticChunkerNode(
      chunk_size=1000,           # Target chunk size
      similarity_threshold=0.75,  # Topic boundary detection
      chunk_overlap=100,         # Context preservation
      window_size=3              # Similarity calculation window
  )
  ```
- **StatisticalChunkerNode**: ⭐ **NEW** Variance-based chunking for structured content
  ```python
  # Use for technical documents and structured content
  node = StatisticalChunkerNode(
      chunk_size=1000,
      variance_threshold=0.5,     # Boundary sensitivity
      min_sentences_per_chunk=3,  # Coherence control
      max_sentences_per_chunk=15  # Size control
  )
  ```
- **ContextualCompressorNode**: ⭐ **NEW** Intelligent content compression for LLM context optimization
  ```python
  # Use for RAG systems and token budget management
  node = ContextualCompressorNode(
      compression_target=2000,     # Target token count
      relevance_threshold=0.75,    # Minimum relevance score
      compression_strategy="extractive_summarization",  # or "abstractive_synthesis", "hierarchical_organization"
      compression_ratio=0.6        # 40% reduction target
  )
  # Achieves 50-70% token reduction while preserving relevance
  ```
- **HierarchicalChunkerNode**: Split documents into hierarchical chunks
- **ChunkTextExtractorNode**: Extract text from document chunks
- **QueryTextWrapperNode**: Wrap queries with additional context
- **ContextFormatterNode**: Format context for LLM consumption

## Authentication Nodes

### Enterprise Authentication & Authorization
- **MultiFactorAuthNode**: ⭐ NEW: Complete MFA implementation with TOTP, SMS, email
  ```python
  # Enterprise-grade multi-factor authentication
  node = MultiFactorAuthNode(
      operation="verify_mfa",
      mfa_methods=["totp", "sms", "email"],
      backup_codes_enabled=True,
      session_binding=True
  )
  ```

- **SessionManagementNode**: ⭐ NEW: Advanced session management with security controls
  ```python
  # Secure session handling with anomaly detection
  node = SessionManagementNode(
      operation="create_session",
      max_concurrent_sessions=3,
      ip_binding=True,
      device_fingerprinting=True,
      anomaly_detection=True
  )
  ```

- **SSOAuthenticationNode**: ⭐ NEW: Single sign-on with multiple identity providers
  ```python
  # Enterprise SSO with SAML, OIDC, Azure AD support
  node = SSOAuthenticationNode(
      auth_provider="azure_ad",  # or "okta", "auth0", "saml", "oidc"
      auto_provision_users=True,
      role_mapping_enabled=True,
      group_sync=True
  )
  ```

- **DirectoryIntegrationNode**: ⭐ NEW: Active Directory and LDAP integration
  ```python
  # Enterprise directory integration with group sync
  node = DirectoryIntegrationNode(
      directory_type="active_directory",  # or "ldap", "azure_ad"
      sync_groups=True,
      sync_attributes=["department", "title", "manager"],
      auto_disable_users=True
  )
  ```

- **EnterpriseAuthProviderNode**: ⭐ NEW: Unified authentication provider interface
  ```python
  # Centralized authentication with multiple providers
  node = EnterpriseAuthProviderNode(
      primary_provider="azure_ad",
      fallback_providers=["local", "ldap"],
      provider_failover=True,
      audit_all_attempts=True
  )
  ```

- **RiskAssessmentNode**: ⭐ NEW: Real-time authentication risk assessment
  ```python
  # AI-powered authentication risk scoring
  node = RiskAssessmentNode(
      operation="assess_login_risk",
      risk_factors=["location", "device", "behavior", "time"],
      ml_model_enabled=True,
      adaptive_auth=True
  )
  ```

## Compliance Nodes

### Regulatory Compliance & Data Protection
- **GDPRComplianceNode**: ⭐ NEW: Complete GDPR compliance automation
  ```python
  # Comprehensive GDPR compliance workflows
  node = GDPRComplianceNode(
      operation="process_data_request",  # or "audit_consent", "anonymize_data", "export_data"
      request_type="data_export",  # or "deletion", "rectification", "portability"
      automated_verification=True,
      retention_policy_check=True,
      audit_trail=True
  )
  ```

- **DataRetentionPolicyNode**: ⭐ NEW: Automated data retention and lifecycle management
  ```python
  # Enterprise data retention with automated cleanup
  node = DataRetentionPolicyNode(
      operation="apply_retention_policy",
      retention_rules=[
          {"data_type": "customer_data", "retention_days": 2555},  # 7 years
          {"data_type": "log_data", "retention_days": 90},
          {"data_type": "temp_data", "retention_days": 30}
      ],
      automated_cleanup=True,
      compliance_reporting=True
  )
  ```

## Admin & Security Nodes

### User Management
- **UserManagementNode**: Complete user CRUD operations with ABAC
  ```python
  # Use instead of PythonCodeNode for user operations
  node = UserManagementNode(operation="create", abac_enabled=True)
  ```
- **RoleManagementNode**: Hierarchical role management with permissions
  ```python
  # Use instead of custom role logic
  node = RoleManagementNode(operation="assign_permissions")
  ```

### Security & Permissions
- **PermissionCheckNode**: Complex permission evaluation with ABAC
  ```python
  # Use instead of manual permission checks
  node = PermissionCheckNode(resource="document", action="read")
  ```
- **AuditLogNode**: ⭐ NEW: Enterprise audit logging with structured format (Session 067)
  ```python
  # Use instead of manual logging for compliance
  node = AuditLogNode(
      name="workflow_audit",
      log_level="INFO",
      include_timestamp=True,
      output_format="json"
  )
  # Usage: await node.process({"action": "user_login", "user_id": "user123"})
  ```
- **SecurityEventNode**: ⭐ NEW: Security event monitoring with alerting (Session 067)
  ```python
  # Use for security monitoring with automatic alerting
  node = SecurityEventNode(
      name="security_monitor",
      severity_threshold="MEDIUM",
      enable_alerting=True
  )
  # Usage: await node.process({"event_type": "unauthorized_access", "severity": "HIGH"})
  ```
- **CredentialManagerNode**: ⭐ NEW: Enterprise credential management (Session 067)
  ```python
  # Multi-source credential management with validation
  node = CredentialManagerNode(
      credential_name="api_service",
      credential_type="oauth2",
      credential_sources=["vault", "aws_secrets", "env"],
      validate_on_fetch=True,
      cache_duration_seconds=3600
  )
  ```
- **RotatingCredentialNode**: ⭐ NEW: Automatic credential rotation (Session 067)
  ```python
  # Zero-downtime credential rotation with notifications
  node = RotatingCredentialNode(
      operation="start_rotation",
      credential_name="api_token",
      check_interval=3600,  # Check every hour
      expiration_threshold=86400,  # Rotate 24h before expiry
      refresh_sources=["vault", "aws_secrets"],
      notification_webhooks=["https://alerts.company.com/webhook"],
      zero_downtime=True
  )
  ```

### Advanced Security Monitoring
- **ThreatDetectionNode**: ⭐ NEW: AI-powered threat detection and response
  ```python
  # Real-time threat detection with ML models
  node = ThreatDetectionNode(
      detection_models=["anomaly", "signature", "behavioral"],
      auto_response=True,
      threat_intelligence_feeds=["crowdstrike", "virustotal"],
      risk_scoring=True
  )
  ```

- **ABACPermissionEvaluatorNode**: ⭐ NEW: Advanced attribute-based access control
  ```python
  # Complex permission evaluation with 16+ operators
  node = ABACPermissionEvaluatorNode(
      policy_engine="cedar",  # or "opa", "native"
      attributes=["user.department", "resource.sensitivity", "time.hour"],
      operators=["equals", "contains", "greater_than", "in_set"],
      dynamic_evaluation=True
  )
  ```

- **BehaviorAnalysisNode**: ⭐ NEW: User behavior analytics for security
  ```python
  # ML-powered behavior analysis for anomaly detection
  node = BehaviorAnalysisNode(
      analysis_type="user_behavior",  # or "network", "application"
      baseline_learning_days=30,
      anomaly_threshold=0.75,
      real_time_analysis=True
  )
  ```

### Audit & Compliance
- **AuditLogNode**: Comprehensive audit logging with compliance tags
  ```python
  # Use instead of custom logging
  node = AuditLogNode(compliance_tags=["SOC2", "HIPAA"])
  ```

## Middleware Nodes

### Enterprise Middleware (Production Applications)

**Purpose**: Enterprise-grade middleware for building production applications with real-time agent-frontend communication, session management, and comprehensive security.

**Test Coverage**: 17/17 integration tests passing for production reliability

- **AgentUIMiddleware**: Central orchestration hub for frontend communication
  ```python
  # Use for production frontend applications
  from kailash.middleware import AgentUIMiddleware

  middleware = AgentUIMiddleware(
      enable_dynamic_workflows=True,
      max_sessions=1000,
      session_timeout_minutes=60,
      enable_persistence=True,
      database_url="postgresql://..."
  )

  # Create session for frontend client
  session_id = await middleware.create_session(user_id="user123")

  # Create dynamic workflow from frontend configuration
  workflow_id = await middleware.create_dynamic_workflow(
      session_id, workflow_config
  )
  ```

- **RealtimeMiddleware**: Multi-protocol real-time communication
  ```python
  # WebSocket, SSE, and webhook support
  from kailash.middleware import RealtimeMiddleware

  realtime = RealtimeMiddleware(agent_ui_middleware)

  # WebSocket connections with automatic reconnection
  # Server-Sent Events for unidirectional streaming
  # Webhook management for external integrations
  ```

- **APIGateway**: RESTful API layer with authentication
  ```python
  # Production API gateway with OpenAPI docs
  from kailash.middleware import create_gateway

  gateway = create_gateway(
      title="My Kailash API",
      cors_origins=["https://myapp.com"],
      enable_docs=True
  )
  gateway.agent_ui = agent_ui_middleware
  ```

- **AIChatMiddleware**: AI-powered conversation management
  ```python
  # AI chat with semantic search and context
  from kailash.middleware import AIChatMiddleware

  ai_chat = AIChatMiddleware(
      agent_ui_middleware,
      enable_vector_search=True,
      vector_database_url="postgresql://...",
      default_model_provider="ollama"
  )

  # Natural language to workflow conversion
  response = await ai_chat.send_message(
      session_id,
      "Create a workflow to process CSV data"
  )
  ```

- **EventStream**: Comprehensive event management system
  ```python
  # Real-time event streaming for UI synchronization
  from kailash.middleware.events import EventStream, EventType

  # Subscribe to workflow events
  async def event_handler(event):
      print(f"Workflow {event.workflow_id}: {event.type}")

  await middleware.subscribe_to_events(
      "subscriber_id",
      event_handler,
      event_types=[EventType.WORKFLOW_COMPLETED]
  )
  ```

**Key Features**:
- **Session Management**: Multi-tenant isolation with automatic cleanup
- **Dynamic Workflows**: Runtime workflow creation using WorkflowBuilder.from_dict()
- **Real-time Communication**: WebSocket, SSE, and webhook support
- **Enterprise Security**: JWT authentication, RBAC/ABAC access control
- **Database Integration**: Persistent storage with audit trails
- **AI Integration**: Natural language workflow creation and chat interfaces

**Performance**: Sub-200ms latency, 1000+ concurrent sessions tested

**Use Instead Of**: Custom FastAPI/Flask apps, manual WebSocket handling, custom session management

## Enterprise Workflow Nodes

### Business Workflow Templates
- **BusinessWorkflowTemplates**: ⭐ NEW: Pre-built enterprise workflow templates (Session 067)
  ```python
  # Investment data pipeline template
  template = BusinessWorkflowTemplates.investment_data_pipeline(
      workflow,
      data_sources=["bloomberg", "yahoo"],
      analysis_types=["risk", "performance", "compliance"],
      notification_channels=["email", "slack", "teams"]
  )

  # Document AI processing template
  template = BusinessWorkflowTemplates.document_ai_pipeline(
      workflow,
      document_types=["invoice", "contract", "receipt"],
      ai_providers=["azure", "aws", "google"],
      output_formats=["json", "structured_data"],
      compliance_required=True
  )
  ```

### Data Lineage & Processing
- **DataLineageNode**: ⭐ NEW: Comprehensive data lineage tracking (Session 067)
  ```python
  # Track data transformations with compliance checking
  node = DataLineageNode(
      operation="track_transformation",
      source_info={"system": "CRM", "table": "customers"},
      transformation_type="anonymization",
      compliance_frameworks=["GDPR", "CCPA", "SOX", "HIPAA"],
      include_access_patterns=True,
      audit_trail_enabled=True
  )
  ```
- **BatchProcessorNode**: ⭐ NEW: Intelligent batch processing (Session 067)
  ```python
  # High-performance batch processing with optimization
  node = BatchProcessorNode(
      operation="process_data_batches",
      data_source="large_dataset",
      batch_size=1000,  # Auto-optimized based on data
      processing_strategy="parallel",
      max_concurrent_batches=10,
      rate_limit_per_second=50,
      error_handling="continue_with_logging"
  )
  ```

## Testing Nodes

### Credential Testing
- **CredentialTestingNode**: Test authentication flows without external services
  ```python
  # Use for testing OAuth2, API keys, JWT, Basic auth
  node = CredentialTestingNode(
      credential_type="oauth2",
      scenario="expired"  # success, expired, invalid, network_error
  )
  ```

## Code Execution Nodes

### Python Execution
- **PythonCodeNode**: Execute arbitrary Python code
  - Use when no specialized node exists
  - For custom business logic
  - For complex data transformations not covered by transform nodes
  - For integrations without dedicated nodes

## When to Use PythonCodeNode

Use PythonCodeNode **only** when:

1. **No specialized node exists** for your use case
2. **Complex custom logic** that doesn't fit existing nodes
3. **Temporary prototyping** before creating a custom node
4. **Mathematical computations** not covered by transform nodes
5. **Custom data validation** beyond filter nodes
6. **Integration with libraries** without dedicated nodes

### Examples of When NOT to Use PythonCodeNode

❌ **Reading/Writing Files**
```python
# Don't use PythonCodeNode:
with open('data.csv') as f:
    data = pd.read_csv(f)

# Use CSVReaderNode instead:
node = CSVReaderNode(file_path='data.csv')
```

❌ **API Calls**
```python
# Don't use PythonCodeNode:
response = requests.get('https://api.example.com/data')

# Use HTTPRequestNode instead:
node = HTTPRequestNode(url='https://api.example.com/data', method='GET')
```

❌ **Data Filtering**
```python
# Don't use PythonCodeNode:
filtered = [x for x in data if x['age'] > 30]

# Use FilterNode instead:
node = FilterNode(condition="age > 30")
```

❌ **LLM Calls**
```python
# Don't use PythonCodeNode:
response = openai.ChatCompletion.create(...)

# Use LLMAgentNode instead:
node = LLMAgentNode(provider="openai", model="gpt-4")
```

### Examples of When to Use PythonCodeNode

✅ **Complex Business Logic**
```python
# Custom pricing calculation with multiple rules
node = PythonCodeNode(
    name="custom_pricing",
    code='''
    # Complex pricing logic specific to business
    base_price = product['price']
    if customer['tier'] == 'platinum':
        discount = 0.20
    elif customer['tier'] == 'gold' and order['quantity'] > 10:
        discount = 0.15
    else:
        discount = 0.05

    final_price = base_price * (1 - discount) * order['quantity']
    result = {"final_price": final_price, "discount_applied": discount}
    '''
)
```

✅ **Scientific Computations**
```python
# Statistical analysis not covered by existing nodes
node = PythonCodeNode(
    name="statistical_analysis",
    code='''
    import numpy as np
    from scipy import stats

    # Custom statistical test
    statistic, p_value = stats.ks_2samp(sample1, sample2)
    result = {
        "statistic": statistic,
        "p_value": p_value,
        "significant": p_value < 0.05
    }
    '''
)
```

## Best Practices

1. **Always check for existing nodes first** - Review this catalog before using PythonCodeNode
2. **Use specialized nodes for better:**
   - Error handling
   - Performance optimization
   - Integration testing
   - Documentation
   - Maintenance

3. **Create custom nodes** instead of repeated PythonCodeNode usage for the same logic
4. **Leverage node composition** - Combine multiple specialized nodes instead of one complex PythonCodeNode

## Node Discovery Tips

1. Check node imports: `from kailash.nodes import ...`
2. Use IDE autocomplete after `from kailash.nodes.`
3. Review examples in `/examples` directory
4. Check node docstrings for usage details
5. Look at test files for usage patterns
