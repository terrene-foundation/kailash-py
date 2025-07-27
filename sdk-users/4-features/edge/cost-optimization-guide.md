# Cost Optimization Guide

## Overview

The Kailash SDK's Cost Optimization feature (Phase 4.3) provides intelligent multi-cloud cost management for edge computing resources. This includes spot instance management, reserved capacity planning, right-sizing recommendations, and ROI-based allocation decisions.

## Key Components

### 1. Cost Optimizer
- Multi-cloud cost analysis
- Spot instance recommendations
- Reserved capacity planning
- Right-sizing optimization
- ROI calculation and forecasting

### 2. Optimization Strategies
- **Minimize Cost**: Aggressive cost reduction
- **Balance Cost Performance**: Optimal cost/performance ratio
- **Maximize Performance**: Performance-first with cost awareness
- **Predictable Cost**: Stable, predictable pricing
- **Risk Averse**: Conservative optimization approach

### 3. Resource Optimizer Node
- Workflow integration for cost operations
- Cost recording and analysis
- Optimization recommendations

## Quick Start

### Basic Cost Optimization

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()

# Start the optimizer background service
workflow.add_node("ResourceOptimizerNode", "optimizer_start", {
    "operation": "start_optimizer",
    "savings_threshold": 0.1,  # 10% minimum savings
    "risk_tolerance": "medium"
})

# Record cost data
workflow.add_node("ResourceOptimizerNode", "cost_recorder", {
    "operation": "record_cost",
    "edge_node": "edge-west-1",
    "resource_type": "cpu",
    "provider": "aws",
    "instance_type": "on_demand",
    "cost_per_hour": 0.10,
    "usage_hours": 24
})

# Generate cost optimizations
workflow.add_node("ResourceOptimizerNode", "cost_optimizer", {
    "operation": "optimize_costs",
    "strategy": "balance_cost_performance",
    "edge_nodes": ["edge-west-1", "edge-west-2"]
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
    CostOptimizer,
    OptimizationStrategy,
    CloudProvider,
    InstanceType,
    CostMetric
)
from datetime import datetime

# Initialize optimizer
optimizer = CostOptimizer(
    cost_history_days=30,        # 30 days of cost history
    optimization_interval=3600,  # Optimize hourly
    savings_threshold=0.1,       # 10% minimum savings
    risk_tolerance="medium"
)

# Start background optimization
await optimizer.start()

# Record cost data
cost_metric = CostMetric(
    timestamp=datetime.now(),
    edge_node="edge-west-1",
    resource_type="cpu",
    provider=CloudProvider.AWS,
    instance_type=InstanceType.ON_DEMAND,
    cost_per_hour=0.10,
    usage_hours=24,
    total_cost=2.40
)

await optimizer.record_cost(cost_metric)

# Get optimization recommendations
optimizations = await optimizer.optimize_costs(
    strategy=OptimizationStrategy.BALANCE_COST_PERFORMANCE
)

for opt in optimizations:
    print(f"Optimization: {opt.optimization_id}")
    print(f"Savings: ${opt.estimated_savings:.2f} ({opt.savings_percentage:.1f}%)")
    print(f"Risk: {opt.risk_level}")
```

## Optimization Strategies

### 1. Minimize Cost
```python
# Aggressive cost reduction
workflow.add_node("ResourceOptimizerNode", "cost_minimizer", {
    "operation": "optimize_costs",
    "strategy": "minimize_cost",
    "savings_threshold": 0.05,  # Accept 5% savings
    "risk_tolerance": "high"    # Accept higher risk
})
```

### 2. Balance Cost Performance (Recommended)
```python
# Optimal balance between cost and performance
workflow.add_node("ResourceOptimizerNode", "balanced_optimizer", {
    "operation": "optimize_costs",
    "strategy": "balance_cost_performance",
    "savings_threshold": 0.1,   # 10% minimum savings
    "risk_tolerance": "medium"
})
```

### 3. Predictable Cost
```python
# Stable, predictable pricing preferred
workflow.add_node("ResourceOptimizerNode", "predictable_cost", {
    "operation": "optimize_costs",
    "strategy": "predictable_cost",
    "savings_threshold": 0.15,  # Higher threshold for certainty
    "risk_tolerance": "low"
})
```

### 4. Risk Averse
```python
# Conservative optimization approach
workflow.add_node("ResourceOptimizerNode", "conservative", {
    "operation": "optimize_costs",
    "strategy": "risk_averse",
    "savings_threshold": 0.2,   # High threshold
    "risk_tolerance": "low"
})
```

## Spot Instance Optimization

### 1. Spot Instance Analysis
```python
# Get spot instance recommendations
workflow.add_node("ResourceOptimizerNode", "spot_analyzer", {
    "operation": "get_spot_recommendations",
    "edge_nodes": ["edge-west-1", "edge-west-2"]
})

# Example response:
{
    "edge_node": "edge-west-1",
    "current_on_demand_cost": 100.0,
    "spot_cost": 30.0,
    "potential_savings": 70.0,
    "savings_percentage": 70.0,
    "interruption_risk": 0.15,
    "recommended_strategy": "mixed_spot_on_demand",
    "backup_plan": {
        "strategy": "auto_fallback",
        "fallback_instances": "on_demand",
        "max_interruptions_per_day": 2,
        "auto_restart": True
    }
}
```

### 2. Spot Instance Strategies
```python
# Different spot strategies based on interruption risk

# Low risk: Full spot
{
    "interruption_risk": 0.05,
    "recommended_strategy": "full_spot"
}

# Medium risk: Mixed approach
{
    "interruption_risk": 0.20,
    "recommended_strategy": "mixed_spot_on_demand"
}

# High risk: Diversified spot
{
    "interruption_risk": 0.40,
    "recommended_strategy": "diversified_spot"
}
```

### 3. Backup Plans
```python
# Automatic failover configurations
backup_plans = {
    "auto_fallback": {
        "fallback_instances": "on_demand",
        "auto_restart": True,
        "max_interruptions_per_day": 3
    },
    "multi_az_spot": {
        "availability_zones": ["us-west-1a", "us-west-1b", "us-west-1c"],
        "distribute_load": True
    },
    "scheduled_backup": {
        "backup_window": "02:00-04:00",
        "daily_snapshots": True
    }
}
```

## Reserved Capacity Planning

### 1. Reservation Analysis
```python
# Get reserved capacity recommendations
workflow.add_node("ResourceOptimizerNode", "reservation_analyzer", {
    "operation": "get_reservation_recommendations",
    "providers": ["aws", "gcp", "azure"]
})

# Example response:
{
    "resource_type": "cpu",
    "provider": "aws",
    "commitment_length": 12,
    "upfront_cost": 500.0,
    "monthly_cost": 70.0,
    "on_demand_equivalent": 100.0,
    "total_savings": 360.0,
    "savings_percentage": 30.0,
    "breakeven_months": 6,
    "utilization_requirement": 0.7
}
```

### 2. Commitment Lengths
```python
# Different reservation terms
reservations = {
    "1_year": {
        "commitment_months": 12,
        "savings_percentage": 30,
        "upfront_payment": "partial"
    },
    "3_year": {
        "commitment_months": 36,
        "savings_percentage": 50,
        "upfront_payment": "full"
    },
    "savings_plan": {
        "commitment_months": 12,
        "savings_percentage": 25,
        "flexibility": "high"
    }
}
```

### 3. Utilization Requirements
```python
# Minimum utilization needed for ROI
utilization_thresholds = {
    "1_year_no_upfront": 0.6,  # 60% utilization
    "1_year_partial": 0.7,     # 70% utilization
    "1_year_full": 0.8,        # 80% utilization
    "3_year_full": 0.85        # 85% utilization
}
```

## Right-Sizing Optimization

### 1. Resource Utilization Analysis
```python
# Analyze actual resource usage
workflow.add_node("ResourceOptimizerNode", "rightsizing", {
    "operation": "optimize_costs",
    "strategy": "balance_cost_performance",
    "include_rightsizing": True
})

# Right-sizing recommendations based on utilization:
# - <50% utilization: Aggressive right-sizing
# - 50-70% utilization: Conservative right-sizing
# - >70% utilization: Monitor only
```

### 2. Right-Sizing Strategies
```python
rightsizing_approaches = {
    "conservative": {
        "target_utilization": 0.6,  # 60% target
        "buffer_percentage": 0.4,   # 40% buffer
        "implementation": "gradual"
    },
    "aggressive": {
        "target_utilization": 0.8,  # 80% target
        "buffer_percentage": 0.2,   # 20% buffer
        "implementation": "immediate"
    },
    "performance_first": {
        "target_utilization": 0.5,  # 50% target
        "buffer_percentage": 0.5,   # 50% buffer
        "implementation": "monitored"
    }
}
```

## ROI Analysis and Forecasting

### 1. ROI Calculation
```python
# Calculate ROI for optimizations
workflow.add_node("ResourceOptimizerNode", "roi_calculator", {
    "operation": "calculate_roi",
    "optimization_id": "opt_12345",
    "implementation_cost": 500.0
})

# ROI analysis response:
{
    "monthly_savings": 75.0,
    "annual_savings": 900.0,
    "implementation_cost": 500.0,
    "payback_months": 6.67,
    "roi_percentage": 80.0,
    "risk_adjusted_roi": 68.0,
    "recommendation": "Recommended"
}
```

### 2. Cost Forecasting
```python
# Get cost forecast with optimizations
workflow.add_node("ResourceOptimizerNode", "forecaster", {
    "operation": "get_cost_forecast",
    "forecast_months": 12,
    "include_optimizations": True
})

# Forecast response:
{
    "current_monthly_spend": 1000.0,
    "baseline_forecast": [1000, 1050, 1100, ...],  # 12 months
    "optimized_forecast": [750, 787, 825, ...],     # With optimizations
    "total_baseline_cost": 13650.0,
    "total_optimized_cost": 10237.0,
    "total_projected_savings": 3413.0,
    "savings_percentage": 25.0
}
```

### 3. Investment Priorities
```python
# ROI-based recommendation categories
roi_categories = {
    "strongly_recommended": {
        "roi_percentage": "> 100%",
        "payback_months": "< 6",
        "risk_level": "low"
    },
    "recommended": {
        "roi_percentage": "> 50%",
        "payback_months": "< 12",
        "risk_level": "medium"
    },
    "consider": {
        "roi_percentage": "> 20%",
        "payback_months": "< 18",
        "risk_level": "high"
    },
    "not_recommended": {
        "roi_percentage": "< 20%",
        "payback_months": "> 18",
        "risk_level": "any"
    }
}
```

## Multi-Cloud Cost Management

### 1. Provider Comparison
```python
# Compare costs across providers
provider_costs = {
    "aws": {
        "cpu_hourly": 0.10,
        "memory_hourly": 0.01,
        "spot_discount": 0.70,
        "reserved_discount": 0.30
    },
    "gcp": {
        "cpu_hourly": 0.09,
        "memory_hourly": 0.009,
        "preemptible_discount": 0.75,
        "committed_discount": 0.35
    },
    "azure": {
        "cpu_hourly": 0.11,
        "memory_hourly": 0.011,
        "spot_discount": 0.65,
        "reserved_discount": 0.32
    }
}
```

### 2. Provider-Specific Optimizations
```python
# AWS optimizations
aws_optimizations = [
    "EC2 Spot Instances",
    "Reserved Instances",
    "Savings Plans",
    "Right-sizing with CloudWatch"
]

# GCP optimizations
gcp_optimizations = [
    "Preemptible VMs",
    "Committed Use Discounts",
    "Sustained Use Discounts",
    "Custom Machine Types"
]

# Azure optimizations
azure_optimizations = [
    "Azure Spot VMs",
    "Reserved VM Instances",
    "Azure Hybrid Benefit",
    "Dev/Test Pricing"
]
```

### 3. Migration Recommendations
```python
# Cross-provider migration analysis
migration_analysis = {
    "current_provider": "aws",
    "recommended_provider": "gcp",
    "cost_difference": -15.0,  # 15% savings
    "migration_effort": "medium",
    "migration_cost": 2000.0,
    "payback_months": 8,
    "considerations": [
        "Network latency differences",
        "Service compatibility",
        "Data transfer costs"
    ]
}
```

## Advanced Features

### 1. Custom Cost Models
```python
# Define custom pricing
custom_pricing = {
    "edge_local": {
        "cpu": {
            "base_cost": 0.05,      # Lower base cost for edge
            "scaling_factor": 1.2,   # Increases with load
            "maintenance_cost": 0.01 # Fixed maintenance
        }
    }
}

# Register custom pricing
optimizer.provider_pricing.update(custom_pricing)
```

### 2. Budget Alerts
```python
# Set up budget monitoring
budget_config = {
    "monthly_budget": 5000.0,
    "alert_thresholds": [0.5, 0.8, 0.9, 1.0],
    "alert_actions": {
        "50%": "notify",
        "80%": "recommend_optimizations",
        "90%": "pause_non_critical",
        "100%": "emergency_shutdown"
    }
}
```

### 3. Policy-Based Optimization
```python
# Define optimization policies
optimization_policies = {
    "production": {
        "strategy": "predictable_cost",
        "risk_tolerance": "low",
        "savings_threshold": 0.15
    },
    "development": {
        "strategy": "minimize_cost",
        "risk_tolerance": "high",
        "savings_threshold": 0.05
    },
    "staging": {
        "strategy": "balance_cost_performance",
        "risk_tolerance": "medium",
        "savings_threshold": 0.1
    }
}
```

## Integration with Other Edge Features

### 1. With Resource Analysis
```python
# Combine cost and performance analysis
workflow.add_node("ResourceAnalyzerNode", "analyzer", {
    "operation": "analyze",
    "include_patterns": True
})

workflow.add_node("ResourceOptimizerNode", "optimizer", {
    "operation": "optimize_costs",
    "strategy": "balance_cost_performance"
})

# Use analysis to inform cost decisions
workflow.add_connection("analyzer", "bottlenecks", "optimizer", "performance_context")
```

### 2. With Predictive Scaling
```python
# Cost-aware scaling decisions
workflow.add_node("ResourceScalerNode", "scaler", {
    "operation": "predict_scaling",
    "strategy": "hybrid"
})

workflow.add_node("ResourceOptimizerNode", "cost_aware_scaler", {
    "operation": "optimize_costs",
    "strategy": "balance_cost_performance"
})

workflow.add_connection("scaler", "decisions", "cost_aware_scaler", "scaling_context")
```

### 3. With Edge Migration
```python
# Cost-optimized migration planning
workflow.add_node("ResourceOptimizerNode", "cost_analyzer", {
    "operation": "optimize_costs",
    "strategy": "minimize_cost"
})

workflow.add_node("EdgeMigrationNode", "migrator", {
    "operation": "plan_migration",
    "strategy": "cost_optimized"
})

workflow.add_connection("cost_analyzer", "optimizations", "migrator", "cost_constraints")
```

## Best Practices

### 1. Data Collection
```python
# Continuous cost monitoring
import asyncio

async def cost_monitoring():
    while True:
        # Collect cost data from cloud APIs
        aws_costs = get_aws_costs()
        gcp_costs = get_gcp_costs()
        azure_costs = get_azure_costs()

        # Record costs
        for cost_data in [aws_costs, gcp_costs, azure_costs]:
            optimizer_node.execute(
                operation="record_cost",
                **cost_data
            )

        await asyncio.sleep(3600)  # Every hour
```

### 2. Optimization Frequency
```python
# Schedule regular optimizations
optimization_schedule = {
    "hourly": ["spot_price_updates", "usage_monitoring"],
    "daily": ["right_sizing_analysis", "spot_recommendations"],
    "weekly": ["reservation_analysis", "provider_comparison"],
    "monthly": ["roi_evaluation", "budget_review"]
}
```

### 3. Risk Management
```python
# Implement risk controls
risk_controls = {
    "spot_instance_limits": {
        "max_percentage": 70,  # Max 70% spot instances
        "critical_workloads": "on_demand_only"
    },
    "reservation_limits": {
        "max_commitment": "12_months",
        "min_utilization": 0.7
    },
    "budget_controls": {
        "hard_limit": 10000.0,
        "soft_limit": 8000.0
    }
}
```

### 4. Performance Monitoring
```python
# Monitor optimization impact
async def optimization_monitoring():
    # Track optimization effectiveness
    implemented_opts = get_implemented_optimizations()

    for opt in implemented_opts:
        # Measure actual vs predicted savings
        actual_savings = calculate_actual_savings(opt)
        predicted_savings = opt.estimated_savings

        accuracy = actual_savings / predicted_savings

        # Learn from results
        await optimizer.evaluate_optimization(
            opt.optimization_id,
            actual_savings,
            accuracy
        )
```

## Cost Optimization Decision Structure

### Example Cost Optimization
```json
{
    "optimization_id": "opt_spot_edge-west-1_cpu_1642678900",
    "edge_node": "edge-west-1",
    "current_setup": {
        "instance_type": "on_demand",
        "cost": 240.0,
        "resource_type": "cpu"
    },
    "recommended_setup": {
        "instance_type": "spot",
        "cost": 72.0,
        "resource_type": "cpu",
        "interruption_risk": 0.15
    },
    "estimated_savings": 168.0,
    "savings_percentage": 70.0,
    "confidence": 0.8,
    "implementation_effort": "low",
    "risk_level": "medium",
    "reasoning": [
        "Spot instances offer 70.0% cost savings",
        "Interruption risk is 15.0%",
        "Workload appears suitable for spot instances"
    ]
}
```

## Performance Considerations

1. **Cost Data Volume**: Efficient storage with configurable retention
2. **Optimization Frequency**: Background processing with configurable intervals
3. **Provider API Limits**: Rate limiting and caching for pricing data
4. **Accuracy**: Improves over time with feedback and learning

## Troubleshooting

### Common Issues

1. **Poor Optimization Recommendations**
   - Ensure sufficient cost history (30+ days)
   - Verify accurate cost data
   - Check optimization thresholds

2. **High Implementation Costs**
   - Review migration complexity
   - Consider phased implementation
   - Evaluate automation opportunities

3. **Inaccurate ROI Calculations**
   - Validate implementation cost estimates
   - Monitor actual vs predicted savings
   - Update models with feedback

4. **Risk Assessment Issues**
   - Review workload characteristics
   - Adjust risk tolerance settings
   - Implement proper backup plans

## Summary

The Cost Optimization system provides:
- Multi-cloud cost analysis and comparison
- Spot instance and reserved capacity optimization
- Right-sizing and resource optimization
- ROI analysis and cost forecasting
- Risk-aware optimization strategies
- Integration with other edge features

This enables intelligent cost management that balances savings opportunities with performance requirements and risk tolerance across your edge computing infrastructure.
