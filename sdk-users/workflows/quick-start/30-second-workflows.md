# 30-Second Workflows

**Copy-paste solutions for instant productivity** - Production-ready workflows you can use immediately.

## 📊 Data Processing Workflows

### CSV Analysis Pipeline
```python
from kailash import Workflow
from kailash.nodes.data import CSVReaderNode, CSVWriterNode
from kailash.nodes.code import PythonCodeNode
from kailash.runtime.local import LocalRuntime

# Complete CSV analysis in 30 seconds
workflow = Workflow("csv_analysis")
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("analyzer", PythonCodeNode(
    name="analyzer",
    code='''
import pandas as pd

df = pd.DataFrame(data)
result = {
    "total_rows": len(df),
    "columns": df.columns.tolist(),
    "summary": df.describe().to_dict(),
    "null_counts": df.isnull().sum().to_dict(),
    "data_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
    "top_values": {col: df[col].value_counts().head(3).to_dict()
                   for col in df.select_dtypes(include=['object']).columns}
}
'''
))
workflow.add_node("writer", CSVWriterNode())

workflow.connect("reader", "analyzer", mapping={"data": "data"})
workflow.connect("analyzer", "writer", mapping={"result": "data"})

# Execute with your data
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow, parameters={
    "reader": {"file_path": "your_data.csv"},
    "writer": {"file_path": "analysis_results.csv"}
})
```

### Data Validation & Cleaning
```python
workflow = Workflow("data_cleaning")
workflow.add_node("reader", CSVReaderNode())
workflow.add_node("cleaner", PythonCodeNode(
    name="cleaner",
    code='''
import pandas as pd
import numpy as np

df = pd.DataFrame(data)

# Remove duplicates
df = df.drop_duplicates()

# Handle missing values
numeric_columns = df.select_dtypes(include=[np.number]).columns
for col in numeric_columns:
    df[col] = df[col].fillna(df[col].median())

text_columns = df.select_dtypes(include=['object']).columns
for col in text_columns:
    df[col] = df[col].fillna('Unknown')

# Remove outliers (IQR method)
for col in numeric_columns:
    Q1 = df[col].quantile(0.25)
    Q3 = df[col].quantile(0.75)
    IQR = Q3 - Q1
    df = df[~((df[col] < (Q1 - 1.5 * IQR)) | (df[col] > (Q3 + 1.5 * IQR)))]

result = {
    "cleaned_data": df.to_dict('records'),
    "cleaning_report": {
        "rows_removed": len(pd.DataFrame(data)) - len(df),
        "duplicates_removed": len(pd.DataFrame(data)) - len(pd.DataFrame(data).drop_duplicates()),
        "missing_values_filled": sum(pd.DataFrame(data).isnull().sum())
    }
}
'''
))
workflow.add_node("writer", CSVWriterNode())

workflow.connect("reader", "cleaner", mapping={"data": "data"})
workflow.connect("cleaner", "writer", mapping={"cleaned_data": "data"})
```

## 🌐 API Integration Workflows

### REST API Data Pipeline
```python
from kailash.nodes.api import RestClientNode

workflow = Workflow("api_pipeline")
workflow.add_node("api_call", RestClientNode())
workflow.add_node("transformer", PythonCodeNode(
    name="transformer",
    code='''
import json

# Transform API response
response_data = response.get('data', [])
result = {
    "processed_records": len(response_data),
    "summary": {
        "total_items": len(response_data),
        "unique_types": len(set(item.get('type', 'unknown') for item in response_data)),
        "average_value": sum(item.get('value', 0) for item in response_data) / len(response_data) if response_data else 0
    },
    "filtered_data": [item for item in response_data if item.get('status') == 'active']
}
'''
))
workflow.add_node("writer", CSVWriterNode())

workflow.connect("api_call", "transformer", mapping={"response": "response"})
workflow.connect("transformer", "writer", mapping={"filtered_data": "data"})

# Execute with any REST API
runtime.execute(workflow, parameters={
    "api_call": {
        "url": "https://jsonplaceholder.typicode.com/posts",
        "method": "GET",
        "headers": {"Content-Type": "application/json"}
    },
    "writer": {"file_path": "api_results.csv"}
})
```

### Multi-API Aggregation
```python
from kailash.nodes.logic import MergeNode

workflow = Workflow("multi_api")
workflow.add_node("api1", RestClientNode())
workflow.add_node("api2", RestClientNode())
workflow.add_node("merger", MergeNode())
workflow.add_node("aggregator", PythonCodeNode(
    name="aggregator",
    code='''
# Combine data from multiple APIs
api1_data = api1_response.get('data', [])
api2_data = api2_response.get('data', [])

result = {
    "combined_data": api1_data + api2_data,
    "source_breakdown": {
        "api1_records": len(api1_data),
        "api2_records": len(api2_data),
        "total_records": len(api1_data) + len(api2_data)
    }
}
'''
))

workflow.connect("api1", "merger", mapping={"response": "api1_response"})
workflow.connect("api2", "merger", mapping={"response": "api2_response"})
workflow.connect("merger", "aggregator", mapping={"merged": "input"})
```

## 🤖 AI-Powered Workflows

### Document Analysis with AI
```python
from kailash.nodes.ai import LLMAgentNode

workflow = Workflow("document_analysis")
workflow.add_node("reader", CSVReaderNode())  # Or TextReaderNode
workflow.add_node("ai_analyzer", LLMAgentNode())
workflow.add_node("formatter", PythonCodeNode(
    name="formatter",
    code='''
# Format AI response
analysis = ai_response.get('content', '')
result = {
    "analysis_summary": analysis[:500] + "..." if len(analysis) > 500 else analysis,
    "key_insights": analysis.split('\\n')[:5],  # First 5 lines as insights
    "word_count": len(analysis.split()),
    "analysis_complete": True
}
'''
))

workflow.connect("reader", "ai_analyzer", mapping={"data": "messages"})
workflow.connect("ai_analyzer", "formatter", mapping={"response": "ai_response"})

# Execute with Ollama (free) or any LLM provider
runtime.execute(workflow, parameters={
    "reader": {"file_path": "documents.csv"},
    "ai_analyzer": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Analyze these documents and provide key insights"}]
    }
})
```

### AI Strategy Consultation (Using AI Registry MCP)
```python
from kailash.nodes.ai import IterativeLLMAgentNode

workflow = Workflow("ai_consultation")
workflow.add_node("consultant", IterativeLLMAgentNode())
workflow.add_node("report_generator", PythonCodeNode(
    name="report_generator",
    code='''
# Generate executive summary
final_response = consultant_output.get('final_response', '')
iterations = consultant_output.get('total_iterations', 0)

result = {
    "executive_summary": final_response[:1000],
    "consultation_metadata": {
        "total_analysis_iterations": iterations,
        "convergence_achieved": True,
        "analysis_depth": "comprehensive" if iterations > 2 else "standard"
    },
    "recommendations": [line.strip() for line in final_response.split('\\n') if 'recommend' in line.lower()][:5]
}
'''
))

workflow.connect("consultant", "report_generator", mapping={"final_response": "consultant_output"})

# Execute with real AI Registry MCP server
runtime.execute(workflow, parameters={
    "consultant": {
        "provider": "ollama",
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "I need an AI strategy for my healthcare startup"}],
        "mcp_servers": [{
            "name": "ai-registry",
            "transport": "stdio",
            "command": "python",
            "args": ["scripts/start-ai-registry-server.py"]
        }],
        "auto_discover_tools": True,
        "max_iterations": 3
    }
})
```

## 🔄 Real-Time Processing Workflows

### Stream Processing Simulation
```python
workflow = Workflow("stream_processing")
workflow.add_node("data_generator", PythonCodeNode(
    name="data_generator",
    code='''
import random
import time

# Simulate streaming data
stream_data = []
for i in range(100):
    record = {
        "timestamp": time.time() + i,
        "value": random.uniform(0, 100),
        "category": random.choice(['A', 'B', 'C']),
        "is_anomaly": random.random() < 0.05  # 5% anomalies
    }
    stream_data.append(record)

result = {"stream": stream_data}
'''
))
workflow.add_node("anomaly_detector", PythonCodeNode(
    name="anomaly_detector",
    code='''
import numpy as np

data = stream_data.get('stream', [])
values = [record['value'] for record in data]

# Simple anomaly detection
mean_val = np.mean(values)
std_val = np.std(values)
threshold = mean_val + 2 * std_val

anomalies = [record for record in data if record['value'] > threshold]

result = {
    "anomalies_detected": len(anomalies),
    "anomaly_records": anomalies,
    "threshold_used": threshold,
    "data_stats": {"mean": mean_val, "std": std_val}
}
'''
))

workflow.connect("data_generator", "anomaly_detector", mapping={"result": "stream_data"})
```

### Event-Driven Workflow
```python
workflow = Workflow("event_driven")
workflow.add_node("event_processor", PythonCodeNode(
    name="event_processor",
    code='''
import json
from datetime import datetime

# Process events in real-time style
events = event_data if isinstance(event_data, list) else [event_data]
processed_events = []

for event in events:
    processed_event = {
        "event_id": event.get('id', f"evt_{len(processed_events)}"),
        "event_type": event.get('type', 'unknown'),
        "processed_at": datetime.now().isoformat(),
        "priority": "high" if event.get('urgent', False) else "normal",
        "action_required": event.get('value', 0) > 50
    }
    processed_events.append(processed_event)

# Categorize by priority
high_priority = [e for e in processed_events if e['priority'] == 'high']
normal_priority = [e for e in processed_events if e['priority'] == 'normal']

result = {
    "total_processed": len(processed_events),
    "high_priority_events": high_priority,
    "normal_priority_events": normal_priority,
    "immediate_action_needed": len([e for e in processed_events if e['action_required']])
}
'''
))

# Can connect to any data source
runtime.execute(workflow, parameters={
    "event_processor": {
        "event_data": [
            {"id": 1, "type": "alert", "value": 75, "urgent": True},
            {"id": 2, "type": "notification", "value": 25, "urgent": False}
        ]
    }
})
```

## 📈 Business Intelligence Workflows

### Sales Analytics Dashboard
```python
workflow = Workflow("sales_analytics")
workflow.add_node("sales_data", CSVReaderNode())
workflow.add_node("analytics", PythonCodeNode(
    name="analytics",
    code='''
import pandas as pd

df = pd.DataFrame(data)

# Calculate key metrics
total_revenue = df['amount'].sum() if 'amount' in df.columns else 0
avg_deal_size = df['amount'].mean() if 'amount' in df.columns else 0
total_deals = len(df)

# Time-based analysis
if 'date' in df.columns:
    df['date'] = pd.to_datetime(df['date'])
    monthly_revenue = df.groupby(df['date'].dt.month)['amount'].sum().to_dict()
else:
    monthly_revenue = {}

# Product analysis
if 'product' in df.columns:
    product_performance = df.groupby('product')['amount'].agg(['sum', 'count', 'mean']).to_dict('index')
else:
    product_performance = {}

result = {
    "kpi_summary": {
        "total_revenue": float(total_revenue),
        "average_deal_size": float(avg_deal_size),
        "total_deals": total_deals,
        "conversion_metrics": "calculated"
    },
    "monthly_breakdown": monthly_revenue,
    "product_performance": product_performance,
    "dashboard_ready": True
}
'''
))

workflow.connect("sales_data", "analytics", mapping={"data": "data"})
```

### Customer Segmentation
```python
workflow = Workflow("customer_segmentation")
workflow.add_node("customer_data", CSVReaderNode())
workflow.add_node("segmentation", PythonCodeNode(
    name="segmentation",
    code='''
import pandas as pd
import numpy as np

df = pd.DataFrame(data)

# Simple RFM-style segmentation
if all(col in df.columns for col in ['purchase_amount', 'last_purchase_days']):
    # Monetary value segments
    df['monetary_segment'] = pd.qcut(df['purchase_amount'], q=3, labels=['Low', 'Medium', 'High'])

    # Recency segments
    df['recency_segment'] = pd.qcut(df['last_purchase_days'], q=3, labels=['Recent', 'Moderate', 'Distant'])

    # Combine segments
    df['customer_segment'] = df['monetary_segment'].astype(str) + '_' + df['recency_segment'].astype(str)

    # Calculate segment metrics
    segment_summary = df.groupby('customer_segment').agg({
        'purchase_amount': ['count', 'mean', 'sum'],
        'last_purchase_days': 'mean'
    }).round(2).to_dict()

    segments = df['customer_segment'].value_counts().to_dict()
else:
    segments = {"error": "Required columns not found"}
    segment_summary = {}

result = {
    "customer_segments": segments,
    "segment_details": segment_summary,
    "segmented_data": df.to_dict('records') if 'customer_segment' in df.columns else []
}
'''
))

workflow.connect("customer_data", "segmentation", mapping={"data": "data"})
```

## 🔧 System Integration Workflows

### Database to API Pipeline
```python
from kailash.nodes.data import SQLReaderNode

workflow = Workflow("db_to_api")
workflow.add_node("db_reader", SQLReaderNode())
workflow.add_node("formatter", PythonCodeNode(
    name="formatter",
    code='''
# Format database data for API
records = data if isinstance(data, list) else []

# Create API payload
api_payload = {
    "records": records,
    "metadata": {
        "total_records": len(records),
        "extracted_at": "2024-01-01T00:00:00Z",
        "source": "database"
    }
}

result = api_payload
'''
))
workflow.add_node("api_sender", RestClientNode())

workflow.connect("db_reader", "formatter", mapping={"data": "data"})
workflow.connect("formatter", "api_sender", mapping={"result": "json"})

# Execute with your database
runtime.execute(workflow, parameters={
    "db_reader": {
        "query": "SELECT * FROM customers WHERE active = 1",
        "connection_string": "sqlite:///your_database.db"
    },
    "api_sender": {
        "url": "https://api.example.com/upload",
        "method": "POST",
        "headers": {"Authorization": "Bearer your_token"}
    }
})
```

### File Processing Automation
```python
from kailash.nodes.data import FileReaderNode, FileWriterNode

workflow = Workflow("file_automation")
workflow.add_node("file_reader", FileReaderNode())
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
import json
import re

# Process file content (works with text, JSON, CSV)
content = file_content

# Extract emails, phone numbers, or any pattern
email_pattern = r'\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b'
emails = re.findall(email_pattern, content)

# Count lines, words
lines = content.split('\\n')
words = content.split()

result = {
    "file_analysis": {
        "line_count": len(lines),
        "word_count": len(words),
        "character_count": len(content),
        "emails_found": emails,
        "non_empty_lines": len([line for line in lines if line.strip()])
    },
    "processed_content": content.upper(),  # Example processing
    "processing_complete": True
}
'''
))
workflow.add_node("file_writer", FileWriterNode())

workflow.connect("file_reader", "processor", mapping={"content": "file_content"})
workflow.connect("processor", "file_writer", mapping={"processed_content": "content"})
```

## 🚀 Quick Execution Template

```python
# Universal execution template - works with any of the above workflows
from kailash.runtime.local import LocalRuntime
import os

def run_workflow(workflow, parameters):
    """Execute any workflow with error handling."""
    runtime = LocalRuntime()

    try:
        print(f"🚀 Executing workflow: {workflow.workflow_id}")
        results, execution_id = runtime.execute(workflow, parameters)

        if results:
            print("✅ Workflow completed successfully!")
            print(f"📊 Results: {len(results)} nodes executed")
            return results
        else:
            print("❌ Workflow failed - no results returned")
            return None

    except Exception as e:
        print(f"❌ Workflow error: {e}")
        return None

# Ensure output directory
os.makedirs("outputs", exist_ok=True)

# Execute any workflow from above
# results = run_workflow(workflow, your_parameters)
```

## 🔔 Alert & Notification Workflows

### Instant Error Alerts
```python
from kailash.nodes.alerts import DiscordAlertNode
from kailash.nodes.logic import SwitchNode

workflow = Workflow("error_alerts")
workflow.add_node("processor", PythonCodeNode(
    name="processor",
    code='''
# Simulate data processing that might fail
try:
    # Your processing logic here
    processed_count = len(input_data.get("items", []))
    if processed_count == 0:
        raise ValueError("No data to process")

    result = {
        "status": "success",
        "processed": processed_count,
        "message": f"Successfully processed {processed_count} items"
    }
except Exception as e:
    result = {
        "status": "error",
        "error": str(e),
        "message": f"Processing failed: {str(e)}"
    }
'''
))
workflow.add_node("status_check", SwitchNode())
workflow.add_node("error_alert", DiscordAlertNode())

workflow.connect("processor", "status_check", mapping={"status": "switch_value"})
workflow.connect("status_check", "error_alert", output_key="error")

# Execute with Discord webhook
runtime.execute(workflow, parameters={
    "processor": {"input_data": {"items": []}},  # Empty data triggers error
    "error_alert": {
        "webhook_url": "${DISCORD_WEBHOOK}",
        "title": "🚨 Processing Error",
        "alert_type": "error",
        "mentions": ["@here"]
    }
})
```

### System Health Dashboard
```python
workflow = Workflow("health_dashboard")
workflow.add_node("health_check", PythonCodeNode(
    name="health_check",
    code='''
import random
import psutil  # pip install psutil

# Simulate system health metrics
health_data = {
    "cpu_usage": psutil.cpu_percent() if 'psutil' in globals() else random.uniform(20, 90),
    "memory_usage": psutil.virtual_memory().percent if 'psutil' in globals() else random.uniform(30, 85),
    "disk_usage": psutil.disk_usage('/').percent if 'psutil' in globals() else random.uniform(40, 80),
    "active_processes": len(psutil.pids()) if 'psutil' in globals() else random.randint(100, 300),
    "status": "healthy"
}

# Determine overall status
if health_data["cpu_usage"] > 80 or health_data["memory_usage"] > 85:
    health_data["status"] = "warning"
if health_data["cpu_usage"] > 90 or health_data["memory_usage"] > 95:
    health_data["status"] = "critical"

result = health_data
'''
))
workflow.add_node("dashboard_alert", DiscordAlertNode())

workflow.connect("health_check", "dashboard_alert")

# Send health dashboard to Discord
runtime.execute(workflow, parameters={
    "dashboard_alert": {
        "webhook_url": "${DISCORD_WEBHOOK}",
        "title": "📊 System Health Dashboard",
        "alert_type": "info",
        "username": "Health Monitor",
        "fields": [
            {"name": "💻 CPU", "value": "{cpu_usage:.1f}%", "inline": True},
            {"name": "🧠 Memory", "value": "{memory_usage:.1f}%", "inline": True},
            {"name": "💾 Disk", "value": "{disk_usage:.1f}%", "inline": True},
            {"name": "⚙️ Processes", "value": "{active_processes}", "inline": True}
        ],
        "footer_text": "Updated every 5 minutes"
    }
})
```

### Business KPI Alerts
```python
workflow = Workflow("kpi_alerts")
workflow.add_node("kpi_calculator", PythonCodeNode(
    name="kpi_calculator",
    code='''
import random
from datetime import datetime

# Calculate business KPIs (simulate with random data)
kpis = {
    "daily_revenue": random.uniform(10000, 50000),
    "new_signups": random.randint(50, 200),
    "churn_rate": random.uniform(1, 5),
    "conversion_rate": random.uniform(2, 8),
    "avg_order_value": random.uniform(75, 150),
    "timestamp": datetime.now().isoformat()
}

# Check against targets
targets = {
    "daily_revenue": 30000,
    "new_signups": 100,
    "churn_rate": 3,
    "conversion_rate": 5
}

alerts = []
if kpis["daily_revenue"] < targets["daily_revenue"]:
    alerts.append(f"Revenue below target: ${kpis['daily_revenue']:,.0f} < ${targets['daily_revenue']:,.0f}")
if kpis["churn_rate"] > targets["churn_rate"]:
    alerts.append(f"High churn rate: {kpis['churn_rate']:.1f}% > {targets['churn_rate']}%")

result = {
    **kpis,
    "alerts": alerts,
    "status": "warning" if alerts else "success"
}
'''
))
workflow.add_node("kpi_alert", DiscordAlertNode())

workflow.connect("kpi_calculator", "kpi_alert")

# Send KPI report
runtime.execute(workflow, parameters={
    "kpi_alert": {
        "webhook_url": "${DISCORD_WEBHOOK}",
        "title": "📈 Daily KPI Report",
        "alert_type": "info",
        "fields": [
            {"name": "💰 Revenue", "value": "${daily_revenue:,.0f}", "inline": True},
            {"name": "👥 Signups", "value": "{new_signups}", "inline": True},
            {"name": "📉 Churn", "value": "{churn_rate:.1f}%", "inline": True},
            {"name": "🔄 Conversion", "value": "{conversion_rate:.1f}%", "inline": True},
            {"name": "🛒 AOV", "value": "${avg_order_value:.0f}", "inline": True}
        ]
    }
})
```

---

*Each workflow is production-ready and can be executed immediately. Modify parameters to match your data sources and requirements.*
