# Stage 4-5 Implementation Tracker

## 📋 Implementation Requirements

1. **Use Existing Nodes First**: Always check node catalog before using PythonCodeNode
2. **Track Custom Node Needs**: Document repeated PythonCodeNode patterns for new node creation
3. **Create Working Scripts**: Every workflow must have a runnable .py script
4. **Test Everything**: Run and validate each script before documenting
5. **Create Training Data**: For each script, create corresponding .md with wrong/correct code examples

## 🗂️ Node Usage Tracking

### Existing Nodes to Prioritize
- **Data I/O**: CSVReaderNode, JSONWriterNode, SQLReaderNode, SQLWriterNode
- **API**: RestClientNode, GraphQLClientNode, HTTPRequestNode
- **Transform**: FilterNode, DataTransformerNode, MergeNode
- **AI**: LLMAgentNode, IterativeLLMAgentNode, A2ACoordinatorNode
- **Logic**: SwitchNode, LoopNode, ConvergenceCheckerNode

### Repeated PythonCodeNode Patterns (New Node Candidates)
1. **Data Validation**: Schema validation, format checking → `DataValidatorNode`
2. **Rate Limiting**: API rate limiting logic → `RateLimiterNode`
3. **Event Processing**: Event parsing and routing → `EventProcessorNode`
4. **Metric Collection**: Performance metrics aggregation → `MetricsCollectorNode`
5. **Security Checks**: Auth validation, encryption → `SecurityValidatorNode`

## 📁 Stage 4: Production-Ready Templates

### Template 1: Enterprise Data Pipeline
- **Script**: `examples/production_templates/enterprise_data_pipeline.py`
- **Training MD**: `docs/training/enterprise_data_pipeline_training.md`
- **Nodes Used**: CSVReaderNode, SQLWriterNode, DataTransformerNode, FilterNode
- **PythonCodeNode Uses**: Data quality validation (candidate for DataValidatorNode)

### Template 2: Multi-API Integration Hub
- **Script**: `examples/production_templates/multi_api_integration.py`
- **Training MD**: `docs/training/multi_api_integration_training.md`
- **Nodes Used**: RestClientNode, GraphQLClientNode, MergeNode, SwitchNode
- **PythonCodeNode Uses**: Rate limiting (candidate for RateLimiterNode)

### Template 3: AI-Powered Customer Service
- **Script**: `examples/production_templates/ai_customer_service.py`
- **Training MD**: `docs/training/ai_customer_service_training.md`
- **Nodes Used**: IterativeLLMAgentNode, A2ACoordinatorNode, JSONWriterNode
- **PythonCodeNode Uses**: Intent classification (existing nodes sufficient)

### Template 4: Real-Time Event Processing
- **Script**: `examples/production_templates/realtime_event_processing.py`
- **Training MD**: `docs/training/realtime_event_processing_training.md`
- **Nodes Used**: CyclicWorkflow nodes, SwitchNode, MergeNode
- **PythonCodeNode Uses**: Event parsing (candidate for EventProcessorNode)

### Template 5: Security & Compliance Automation
- **Script**: `examples/production_templates/security_compliance_automation.py`
- **Training MD**: `docs/training/security_compliance_automation_training.md`
- **Nodes Used**: Existing security mixins, JSONWriterNode
- **PythonCodeNode Uses**: Compliance checks (candidate for ComplianceValidatorNode)

## 📁 Stage 5: Quick-Start Patterns

### Pattern 1: CSV to Database in 30 Seconds
- **Script**: `examples/quick_start/csv_to_database.py`
- **Training MD**: `docs/training/csv_to_database_training.md`
- **Nodes Used**: CSVReaderNode, SQLWriterNode
- **PythonCodeNode Uses**: None (pure existing nodes)

### Pattern 2: API Data Aggregator
- **Script**: `examples/quick_start/api_data_aggregator.py`
- **Training MD**: `docs/training/api_data_aggregator_training.md`
- **Nodes Used**: RestClientNode (multiple), MergeNode
- **PythonCodeNode Uses**: None (pure existing nodes)

### Pattern 3: LLM-Powered Analysis
- **Script**: `examples/quick_start/llm_analysis.py`
- **Training MD**: `docs/training/llm_analysis_training.md`
- **Nodes Used**: LLMAgentNode, JSONWriterNode
- **PythonCodeNode Uses**: None (pure existing nodes)

### Pattern 4: File Watcher Automation
- **Script**: `examples/quick_start/file_watcher_automation.py`
- **Training MD**: `docs/training/file_watcher_training.md`
- **Nodes Used**: FileWatcherNode (if exists), CSVReaderNode
- **PythonCodeNode Uses**: File watching logic (check if FileWatcherNode exists)

### Pattern 5: Simple Health Monitor
- **Script**: `examples/quick_start/health_monitor.py`
- **Training MD**: `docs/training/health_monitor_training.md`
- **Nodes Used**: RestClientNode, LoopNode, JSONWriterNode
- **PythonCodeNode Uses**: Health check logic (minimal)

## 📊 Training Data Format

Each training MD file should contain:

```markdown
# [Workflow Name] Training Data

## ❌ Common Mistakes

### Mistake 1: Using PythonCodeNode for CSV reading
```python
# WRONG
workflow.add_node("reader", PythonCodeNode(
    name="reader",
    code='''
import csv
with open(file_path) as f:
    data = list(csv.DictReader(f))
result = data
'''
))
```

### ✅ Correct Implementation
```python
# CORRECT
workflow.add_node("reader", CSVReaderNode())
```

### Mistake 2: [Next mistake pattern]
...
```

## 🎯 Implementation Checklist

For each workflow:
- [ ] Review node catalog for existing nodes
- [ ] Create .py script using maximum existing nodes
- [ ] Run and test the script
- [ ] Document any PythonCodeNode usage
- [ ] Create training .md with wrong/correct examples
- [ ] Update this tracker with findings
- [ ] Note patterns for new node candidates

## 🔄 New Node Recommendations

Based on repeated patterns, recommend creating:
1. **DataValidatorNode**: For schema validation and data quality checks
2. **RateLimiterNode**: For API rate limiting with backoff strategies
3. **EventProcessorNode**: For parsing and routing various event types
4. **MetricsCollectorNode**: For aggregating performance metrics
5. **ComplianceValidatorNode**: For regulatory compliance checks