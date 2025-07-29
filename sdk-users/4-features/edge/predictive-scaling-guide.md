# Predictive Resource Scaling Guide

## Overview

The Kailash SDK's Predictive Scaling feature (Phase 4.2) provides ML-based demand prediction and proactive scaling decisions for edge computing resources. This enables intelligent, preemptive resource management that prevents performance bottlenecks before they occur.

## Key Components

### 1. Predictive Scaler
- ML-based demand prediction
- Multiple prediction horizons (5min to 24hr)
- Time series forecasting with ARIMA models
- Confidence-based scaling decisions

### 2. Scaling Strategies
- **Reactive**: Scale based on current metrics
- **Predictive**: Scale based on predictions
- **Scheduled**: Scale based on time patterns
- **Hybrid**: Combine multiple strategies
- **Aggressive**: Scale early and generously
- **Conservative**: Scale cautiously

### 3. Resource Scaler Node
- Workflow integration for predictive scaling
- Usage recording and forecast generation
- Decision evaluation and learning

## Quick Start

### Basic Predictive Scaling

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Start the scaler background service
workflow.add_node("ResourceScalerNode", "scaler_start", {
    "operation": "start_scaler",
    "confidence_threshold": 0.7,
    "scale_up_threshold": 0.8,
    "scale_down_threshold": 0.3
})

# Record resource usage over time
workflow.add_node("ResourceScalerNode", "recorder", {
    "operation": "record_usage",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "usage": 3.2,
    "capacity": 4.0
})

# Generate scaling predictions
workflow.add_node("ResourceScalerNode", "predictor", {
    "operation": "predict_scaling",
    "strategy": "hybrid",
    "horizons": ["immediate", "short_term", "medium_term"]
})

# Connect workflow
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters
workflow.add_connection("source", "result", "target", "input")  # Fixed complex parameters

# Execute
runtime = LocalRuntime()
results, run_id = await runtime.execute_async(workflow.build())
```

### Service-Level Integration

```python
from kailash.edge.resource import (
    PredictiveScaler,
    ScalingStrategy,
    PredictionHorizon
)

# Initialize scaler
scaler = PredictiveScaler(
    prediction_window=3600,      # 1 hour history
    update_interval=60,          # Update every minute
    confidence_threshold=0.7,    # 70% confidence minimum
    scale_up_threshold=0.8,      # Scale up at 80% usage
    scale_down_threshold=0.3     # Scale down at 30% usage
)

# Start background predictions
await scaler.start()

# Record usage data
await scaler.record_usage(
    edge_node="edge-west-1",
    resource_type="cpu",
    usage=3.4,
    capacity=4.0
)

# Get scaling decisions
decisions = await scaler.predict_scaling_needs(
    strategy=ScalingStrategy.HYBRID,
    horizons=[PredictionHorizon.IMMEDIATE, PredictionHorizon.SHORT_TERM]
)

for decision in decisions:
    print(f"Decision: {decision.decision_id}")
    print(f"Actions: {len(decision.action_plan['actions'])}")
    print(f"Estimated cost: ${decision.estimated_cost}")
```

## Scaling Strategies

### 1. Reactive Scaling
```python
# Scale based on current metrics only
workflow.add_node("ResourceScalerNode", "reactive", {
    "operation": "predict_scaling",
    "strategy": "reactive",
    "horizons": ["immediate"]  # Only immediate response
})
```

### 2. Predictive Scaling
```python
# Scale based on predictions
workflow.add_node("ResourceScalerNode", "predictive", {
    "operation": "predict_scaling",
    "strategy": "predictive",
    "horizons": ["short_term", "medium_term"]
})
```

### 3. Hybrid Scaling (Recommended)
```python
# Combine current metrics with predictions
workflow.add_node("ResourceScalerNode", "hybrid", {
    "operation": "predict_scaling",
    "strategy": "hybrid",
    "horizons": ["immediate", "short_term", "medium_term"]
})
```

### 4. Aggressive vs Conservative
```python
# Aggressive: Scale early with larger capacity
workflow.add_node("ResourceScalerNode", "aggressive", {
    "operation": "predict_scaling",
    "strategy": "aggressive",
    "scale_up_threshold": 0.6,    # Scale up at 60%
    "confidence_threshold": 0.5   # Lower confidence OK
})

# Conservative: Scale cautiously
workflow.add_node("ResourceScalerNode", "conservative", {
    "operation": "predict_scaling",
    "strategy": "conservative",
    "scale_up_threshold": 0.9,    # Scale up at 90%
    "confidence_threshold": 0.8   # High confidence required
})
```

## Prediction Horizons

### 1. Immediate (5 minutes)
- For reactive responses
- High confidence predictions
- Critical scaling decisions

### 2. Short Term (15 minutes)
- Tactical scaling decisions
- Pattern-based predictions
- Load balancing optimization

### 3. Medium Term (1 hour)
- Strategic capacity planning
- Scheduled workload preparation
- Cost optimization decisions

### 4. Long Term (24 hours)
- Capacity planning
- Infrastructure scaling
- Budget forecasting

## Forecasting Features

### 1. Resource Forecast
```python
# Get detailed forecast for specific resource
workflow.add_node("ResourceScalerNode", "forecaster", {
    "operation": "get_forecast",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "forecast_minutes": 120  # 2 hours ahead
})

# Response includes:
# - Current utilization
# - Forecast points with timestamps
# - Confidence intervals (95%, 68%)
# - Prediction confidence scores
```

### 2. Multiple Resource Forecasting
```python
# Forecast multiple resources
resources = ["cpu", "memory", "storage"]

for resource in resources:
    workflow.add_node("ResourceScalerNode", f"forecast_{resource}", {
        "operation": "get_forecast",
        "edge_node": "edge-west-1",
        "resource_type": resource,
        "forecast_minutes": 60
    })
```

### 3. Cross-Node Forecasting
```python
# Forecast across multiple edge nodes
nodes = ["edge-west-1", "edge-west-2", "edge-east-1"]

for node in nodes:
    workflow.add_node("ResourceScalerNode", f"forecast_{node}", {
        "operation": "get_forecast",
        "edge_node": node,
        "resource_type": "cpu",
        "forecast_minutes": 60
    })
```

## Decision Evaluation and Learning

### 1. Evaluate Scaling Decisions
```python
# After scaling action, evaluate accuracy
workflow.add_node("ResourceScalerNode", "evaluator", {
    "operation": "evaluate_decision",
    "decision_id": "edge-1_1234567890",
    "actual_usage": {
        "edge-1:cpu": 85.5,
        "edge-1:memory": 70.2
    },
    "feedback": "Scaling was appropriate, prevented bottleneck"
})

# The scaler learns from this feedback and improves future predictions
```

### 2. Continuous Learning
```python
# Set up continuous evaluation loop
async def evaluate_predictions():
    # Run periodically to evaluate past decisions
    recent_decisions = get_recent_scaling_decisions()

    for decision in recent_decisions:
        actual_usage = get_actual_usage(decision.timestamp)

        scaler_node.execute(
            operation="evaluate_decision",
            decision_id=decision.decision_id,
            actual_usage=actual_usage
        )
```

## Advanced Configuration

### 1. Custom Thresholds
```python
# Fine-tune scaling thresholds per use case
workflow.add_node("ResourceScalerNode", "custom_scaler", {
    "operation": "predict_scaling",
    "scale_up_threshold": 0.75,      # Scale up at 75%
    "scale_down_threshold": 0.25,    # Scale down at 25%
    "confidence_threshold": 0.8,     # High confidence required
    "min_data_points": 50           # More data for better predictions
})
```

### 2. Prediction Window Configuration
```python
# Adjust historical data window
workflow.add_node("ResourceScalerNode", "long_window", {
    "operation": "start_scaler",
    "prediction_window": 7200,       # 2 hours of history
    "update_interval": 30           # Update every 30 seconds
})
```

### 3. Multi-Model Ensemble
```python
# Use multiple strategies for robust predictions
strategies = ["reactive", "predictive", "scheduled"]

for strategy in strategies:
    workflow.add_node("ResourceScalerNode", f"scaler_{strategy}", {
        "operation": "predict_scaling",
        "strategy": strategy
    })

# Aggregate and compare results
workflow.add_node("PythonCodeNode", "aggregator", {
    "code": """
    # Combine predictions from multiple strategies
    all_predictions = []
    for strategy in ['reactive', 'predictive', 'scheduled']:
        predictions = parameters.get(f'{strategy}_predictions', [])
        all_predictions.extend(predictions)

    # Weight by confidence and strategy
    weighted_decisions = weight_predictions(all_predictions)
    result = {'ensemble_decisions': weighted_decisions}
    """
})
```

## Integration with Other Edge Features

### 1. With Resource Analysis
```python
# Combine analysis with scaling
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "analyze",
    "include_patterns": True
})

workflow.add_node("ResourceScalerNode", "scaler", {
    "operation": "predict_scaling",
    "strategy": "hybrid"
})

# Use analysis to inform scaling
workflow.add_connection("analyzer", "patterns", "scaler", "context")
```

### 2. With Edge Monitoring
```python
# Real-time metrics feed scaling decisions
workflow.add_node("EdgeMonitoringNode", "monitor", {
    "operation": "record_metric",
    "edge_node": "edge-west-1",
    "metric_type": "latency",
    "value": 150
})

workflow.add_node("ResourceScalerNode", "scaler", {
    "operation": "record_usage",
    "edge_node": "edge-west-1"
})

workflow.add_connection("monitor", "metric", "scaler", "performance_context")
```

### 3. With Predictive Warming
```python
# Scale before warming new nodes
workflow.add_node("ResourceScalerNode", "predictor", {
    "operation": "predict_scaling",
    "strategy": "predictive",
    "horizons": ["medium_term"]
})

workflow.add_node("EdgeWarmingNode", "warmer", {
    "operation": "warm_nodes",
    "auto_execute": True
})

workflow.add_connection("predictor", "decisions", "warmer", "capacity_hints")
```

## Scaling Decision Structure

### Example Scaling Decision
```json
{
    "decision_id": "edge-west-1_1642678900",
    "predictions": [
        {
            "timestamp": "2024-01-20T10:00:00Z",
            "horizon": 900,
            "resource_type": "cpu",
            "edge_node": "edge-west-1",
            "current_usage": 75.0,
            "predicted_usage": 92.0,
            "confidence": 0.85,
            "recommended_capacity": 16.0,
            "scaling_action": "scale_up",
            "scaling_factor": 1.23,
            "urgency": "soon",
            "reasoning": [
                "Predicted utilization (92.0%) exceeds threshold (80.0%)",
                "Upward trend detected (2.5% per interval)"
            ]
        }
    ],
    "strategy": "hybrid",
    "action_plan": {
        "edge_node": "edge-west-1",
        "actions": [
            {
                "action": "increase_capacity",
                "resource_type": "cpu",
                "current_capacity": 8.0,
                "target_capacity": 16.0,
                "urgency": "soon",
                "execute_at": "2024-01-20T10:07:30Z"
            }
        ]
    },
    "estimated_cost": 15.50,
    "risk_assessment": {
        "risk_level": "low",
        "risks": [],
        "mitigation_suggestions": []
    },
    "approval_required": false
}
```

## Machine Learning Models

### 1. ARIMA Time Series
- Automatic seasonality detection
- Trend analysis and forecasting
- Statistical confidence intervals

### 2. Linear Regression Fallback
- Simple trend-based predictions
- Exponential smoothing
- R-squared confidence scoring

### 3. Ensemble Methods
```python
# Multiple models for robust predictions
scaler = PredictiveScaler()

# Models automatically selected based on:
# - Data availability (ARIMA needs more data)
# - Prediction accuracy (learned from feedback)
# - Time horizon (different models for different ranges)
```

## Best Practices

### 1. Data Collection
```python
# Collect metrics frequently for better predictions
import asyncio

async def continuous_monitoring():
    while True:
        # Get current resource usage
        cpu_usage = get_cpu_usage()
        memory_usage = get_memory_usage()

        # Record for predictions
        scaler_node.execute(
            operation="record_usage",
            resource_type="cpu",
            usage=cpu_usage.used,
            capacity=cpu_usage.total
        )

        scaler_node.execute(
            operation="record_usage",
            resource_type="memory",
            usage=memory_usage.used,
            capacity=memory_usage.total
        )

        await asyncio.sleep(30)  # Every 30 seconds
```

### 2. Strategy Selection
```python
# Choose strategy based on workload characteristics

# For predictable workloads
strategy = "scheduled"

# For variable workloads
strategy = "hybrid"

# For critical workloads
strategy = "aggressive"

# For cost-sensitive workloads
strategy = "conservative"
```

### 3. Confidence Thresholds
```python
# Adjust confidence based on risk tolerance

# High-risk applications (financial, healthcare)
confidence_threshold = 0.9

# Standard applications
confidence_threshold = 0.7

# Development/testing
confidence_threshold = 0.5
```

### 4. Evaluation and Tuning
```python
# Regular evaluation for model improvement
async def weekly_evaluation():
    # Get all decisions from past week
    decisions = get_past_decisions(days=7)

    for decision in decisions:
        # Get actual usage that occurred
        actual = get_historical_usage(
            decision.timestamp,
            decision.predictions[0].horizon
        )

        # Evaluate accuracy
        await scaler.evaluate_scaling_decision(
            decision.decision_id,
            actual
        )
```

## Performance Considerations

1. **Prediction Overhead**: Models run asynchronously in background
2. **Memory Usage**: Configurable history window limits memory
3. **CPU Impact**: Efficient algorithms with caching
4. **Accuracy**: Improves over time with more data and feedback

## Troubleshooting

### Common Issues

1. **Poor Predictions**
   - Ensure sufficient historical data (30+ points)
   - Check confidence thresholds
   - Verify data quality and consistency

2. **Delayed Scaling**
   - Reduce prediction horizons for faster response
   - Lower confidence thresholds for quicker action
   - Use reactive strategy for immediate needs

3. **Over-scaling**
   - Increase confidence thresholds
   - Use conservative strategy
   - Review scale-up thresholds

4. **Under-scaling**
   - Lower scale-up thresholds
   - Use aggressive strategy
   - Check for data lag or gaps

## Summary

The Predictive Scaling system provides:
- ML-based demand forecasting
- Multiple scaling strategies
- Confidence-based decisions
- Continuous learning and improvement
- Integration with edge infrastructure

This enables proactive resource management that prevents bottlenecks, optimizes costs, and maintains high performance across your edge computing infrastructure.
