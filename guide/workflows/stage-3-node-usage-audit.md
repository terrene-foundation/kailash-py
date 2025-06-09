# Stage 3 Node Usage Audit

## 📋 Stage 3 Pattern Guides Review

This audit examines all Stage 3 pattern guides to identify where PythonCodeNode was used when existing nodes could have been utilized.

## 🔍 Pattern Guide Analysis

### 1. ETL Pipeline Patterns (`data-processing/etl-pipelines.md`)

#### Current PythonCodeNode Usage:
1. **Data transformation and cleaning** (lines 28-56)
   - ✅ KEEP: Complex business logic for customer segmentation
   - ❌ REPLACE: Basic data cleaning could use DataTransformerNode

2. **RFM Analysis** (lines 119-169)
   - ✅ KEEP: Domain-specific RFM scoring algorithm

3. **Multi-source data integration** (lines 236-322)
   - ❌ REPLACE: Data merging should use MergeNode
   - ✅ KEEP: Complex deduplication logic

4. **Streaming ETL** (lines 342-383)
   - ❌ REPLACE: Should investigate if StreamingDataNode exists

5. **Data quality validation** (lines 799-943)
   - ❌ REPLACE: Candidate for new DataValidatorNode

#### Recommended Changes:
- Use **MergeNode** for combining data sources
- Use **DataTransformerNode** for simple transformations
- Create **DataValidatorNode** for quality checks

### 2. LLM Workflow Patterns (`ai-ml/llm-workflows.md`)

#### Current PythonCodeNode Usage:
1. **Content formatter** (lines 30-48)
   - ✅ KEEP: Specific formatting logic for LLM output

2. **Multi-step reasoning coordinator** (lines 80-265)
   - ❌ REPLACE: Should use A2ACoordinatorNode or IntelligentAgentOrchestratorNode

3. **MCP tool analyzer** (lines 308-509)
   - ✅ KEEP: Specialized MCP analysis logic

4. **Report data aggregator** (lines 551-715)
   - ❌ REPLACE: Could use DataTransformerNode with aggregation

5. **Multi-modal content adapter** (lines 978-1164)
   - ✅ KEEP: Complex content adaptation logic

#### Recommended Changes:
- Use **A2ACoordinatorNode** for agent coordination
- Use **DataTransformerNode** for data aggregation
- Use **IterativeLLMAgentNode** for multi-step reasoning

### 3. REST API Integration Patterns (`api-integration/rest-api-workflows.md`)

#### Current PythonCodeNode Usage:
1. **Response processor** (lines 30-49)
   - ❌ REPLACE: Simple data extraction, use DataTransformerNode

2. **API data correlator** (lines 79-356)
   - ✅ KEEP: Complex correlation logic across multiple APIs

3. **Rate limiter** (lines 389-608)
   - ❌ REPLACE: Strong candidate for new RateLimiterNode

4. **Smart API executor** (lines 612-844)
   - ❌ REPLACE: Should use RestClientNode with retry configuration

5. **Webhook validator** (lines 857-1151)
   - ❌ REPLACE: Candidate for new WebhookValidatorNode

6. **Metrics collector** (lines 1480-1898)
   - ❌ REPLACE: Candidate for new MetricsCollectorNode

#### Recommended Changes:
- Use **RestClientNode** with proper configuration
- Use **DataTransformerNode** for response processing
- Create **RateLimiterNode** for rate limiting
- Create **WebhookValidatorNode** for webhook handling
- Create **MetricsCollectorNode** for API metrics

### 4. File Processing Patterns (`file-processing/file-watchers.md`)

#### Current PythonCodeNode Usage:
1. **File watcher** (entire pattern)
   - ❌ REPLACE: Check if FileWatcherNode exists in data nodes

2. **Document parser** (PDF/Word processing)
   - ❌ REPLACE: Check if DocumentParserNode exists

3. **Image processor** (computer vision)
   - ✅ KEEP: Specialized image analysis requiring external libraries

4. **Archive manager** (compression/extraction)
   - ❌ REPLACE: Check if ArchiveNode exists

5. **S3 integration**
   - ❌ REPLACE: Check if S3Node or CloudStorageNode exists

#### Recommended Changes:
- Investigate existing file/document nodes
- Use cloud storage nodes if available
- Keep image processing as PythonCodeNode (specialized)

### 5. Monitoring Patterns (`monitoring/health-checks.md`)

#### Current PythonCodeNode Usage:
1. **Health checker** (entire pattern)
   - ❌ REPLACE: RestClientNode for API calls + DataTransformerNode

2. **Performance tracker**
   - ❌ REPLACE: Candidate for MetricsCollectorNode

3. **Alert manager**
   - ❌ REPLACE: Candidate for AlertingNode

4. **Log aggregator**
   - ✅ KEEP: Complex log parsing logic

5. **Dashboard generator**
   - ✅ KEEP: Complex visualization logic

#### Recommended Changes:
- Use **RestClientNode** for health checks
- Create **MetricsCollectorNode** for metrics
- Create **AlertingNode** for notifications

### 6. Security Patterns (`security/authentication-flows.md`)

#### Current PythonCodeNode Usage:
1. **JWT validator**
   - ❌ REPLACE: Check if JWTValidatorNode exists in auth nodes

2. **MFA orchestrator**
   - ✅ KEEP: Complex multi-factor logic

3. **Privacy processor** (GDPR/HIPAA)
   - ❌ REPLACE: Candidate for PrivacyComplianceNode

4. **RBAC engine**
   - ❌ REPLACE: Check if RBACNode exists in access_control

5. **Audit system**
   - ❌ REPLACE: Candidate for AuditLoggerNode

#### Recommended Changes:
- Investigate auth nodes for JWT handling
- Use access_control nodes for RBAC
- Create compliance and audit nodes

### 7. Event-Driven Patterns (`event-driven/event-sourcing.md`)

#### Current PythonCodeNode Usage:
1. **Event store**
   - ✅ KEEP: Complex event sourcing implementation

2. **Message publisher/consumer**
   - ❌ REPLACE: Check if MessageQueueNode exists

3. **CQRS handlers**
   - ✅ KEEP: Domain-specific command/query logic

4. **Saga orchestrator**
   - ❌ REPLACE: Could use WorkflowNode for sub-workflows

5. **Stream processor**
   - ❌ REPLACE: Check if StreamProcessorNode exists

#### Recommended Changes:
- Investigate messaging nodes
- Use WorkflowNode for saga orchestration
- Keep event sourcing as specialized logic

## 📊 Summary of Findings

### Existing Nodes We Should Have Used:
1. **MergeNode** - For combining data sources
2. **DataTransformerNode** - For data transformations
3. **RestClientNode** - For API calls with retry logic
4. **A2ACoordinatorNode** - For agent coordination
5. **WorkflowNode** - For sub-workflow orchestration

### New Nodes Needed (Repeated Patterns):
1. **DataValidatorNode** - Data quality validation (5+ occurrences)
2. **RateLimiterNode** - API rate limiting (3+ occurrences)
3. **MetricsCollectorNode** - Performance metrics (4+ occurrences)
4. **WebhookValidatorNode** - Webhook processing (2+ occurrences)
5. **AlertingNode** - Multi-channel notifications (3+ occurrences)
6. **AuditLoggerNode** - Compliance logging (3+ occurrences)
7. **FileWatcherNode** - Directory monitoring (2+ occurrences)
8. **PrivacyComplianceNode** - GDPR/HIPAA compliance (2+ occurrences)

### Nodes to Investigate:
1. File processing nodes (FileWatcherNode, DocumentParserNode)
2. Cloud storage nodes (S3Node, CloudStorageNode)
3. Messaging nodes (MessageQueueNode, EventBusNode)
4. Auth nodes (JWTValidatorNode, OAuthNode)
5. Streaming nodes (StreamProcessorNode, StreamingDataNode)

## 🎯 Action Items for Stage 3 Refactoring

1. **Immediate Replacements** (use existing nodes):
   - Replace simple data transformations with DataTransformerNode
   - Replace API calls with RestClientNode
   - Replace data merging with MergeNode
   - Replace agent coordination with A2ACoordinatorNode

2. **Investigation Required**:
   - Check nodes/ directory for file, auth, and streaming nodes
   - Review security mixins for existing capabilities
   - Check if any MCP nodes provide the functionality

3. **Keep as PythonCodeNode**:
   - Complex business logic (RFM analysis, customer segmentation)
   - Specialized algorithms (image processing, event sourcing)
   - External library integrations without dedicated nodes

## 📝 Stage 3 Scripts to Create

For each pattern guide, we need:

1. **ETL Pipeline**
   - `examples/patterns/etl_pipeline_example.py`
   - `docs/training/etl_pipeline_training.md`

2. **LLM Workflows**
   - `examples/patterns/llm_workflow_example.py`
   - `docs/training/llm_workflow_training.md`

3. **API Integration**
   - `examples/patterns/api_integration_example.py`
   - `docs/training/api_integration_training.md`

4. **File Processing**
   - `examples/patterns/file_processing_example.py`
   - `docs/training/file_processing_training.md`

5. **Monitoring**
   - `examples/patterns/monitoring_example.py`
   - `docs/training/monitoring_training.md`

6. **Security**
   - `examples/patterns/security_example.py`
   - `docs/training/security_training.md`

7. **Event-Driven**
   - `examples/patterns/event_driven_example.py`
   - `docs/training/event_driven_training.md`
