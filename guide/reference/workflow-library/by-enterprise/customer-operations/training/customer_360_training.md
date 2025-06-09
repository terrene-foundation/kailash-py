# Customer 360° Integration Workflow - Training Documentation

## Overview
This document captures the implementation process for a comprehensive Customer 360° data integration workflow using the Kailash SDK. The workflow demonstrates enterprise-grade patterns for multi-source data integration, validation, scoring, and routing.

## Wrong Code Examples → Correct Code Patterns

### ❌ Wrong: Using unsupported MergeNode merge_type
```python
# This fails because MergeNode doesn't support "left_join"
merge_node = MergeNode(id="merge", merge_type="left_join", key="customer_id")
```

**Error**: `ValueError: Unknown merge type: left_join`

### ✅ Correct: Using supported merge types
```python
# MergeNode supports: "concat", "zip", "merge_dict"
merge_node = MergeNode(id="merge", merge_type="concat")
# OR for dict merging with keys:
merge_node = MergeNode(id="merge", merge_type="merge_dict", key="customer_id")
```

### ❌ Wrong: Incorrect SwitchNode boolean condition syntax
```python
# This doesn't work - SwitchNode doesn't accept single condition parameter
switch_node = SwitchNode(id="router", condition="customer_value_score >= 80")
```

**Error**: SwitchNode doesn't recognize `condition` parameter

### ✅ Correct: Proper SwitchNode configuration
```python
# Boolean mode - uses condition_field, operator, value
switch_node = SwitchNode(
    id="router", 
    condition_field="customer_value_score", 
    operator=">=", 
    value=80
)

# OR Multi-case mode - uses condition_field and cases
switch_node = SwitchNode(
    id="router",
    condition_field="customer_segment", 
    cases=["VIP", "Premium"]
)
```

### ❌ Wrong: Incorrect SwitchNode connection syntax
```python
# This syntax doesn't work
workflow.connect("router", "high_value", condition="true_output", mapping={"true_output": "data"})
```

**Error**: `connect()` method doesn't accept `condition` parameter

### ✅ Correct: Proper SwitchNode output mapping
```python
# For boolean mode
workflow.connect("router", "high_value", mapping={"true_output": "data"})
workflow.connect("router", "standard", mapping={"false_output": "data"})

# For multi-case mode  
workflow.connect("router", "high_value", mapping={"case_VIP": "data"})
workflow.connect("router", "standard", mapping={"default": "data"})
```

### ❌ Wrong: Incorrect SwitchNode input parameter
```python
# SwitchNode expects "input_data" not "data"
workflow.connect("scoring", "router", mapping={"result": "data"})
```

**Error**: `Required parameter 'input_data' not provided at execution time`

### ✅ Correct: Proper SwitchNode input mapping
```python
workflow.connect("scoring", "router", mapping={"result": "input_data"})
```

### ❌ Wrong: Not handling DataTransformer dict output bug
```python
# This fails because DataTransformer outputs list of dict keys, not actual dicts
for customer in data:
    customer_id = customer.get('customer_id')  # AttributeError: 'list' object has no attribute 'get'
```

**Error**: `'list' object has no attribute 'get'`

### ✅ Correct: Handling flattened data from MergeNode concat
```python
# Handle flattened data structure from MergeNode concat
if isinstance(data, list) and len(data) > 0:
    # If data is a list of lists (from concat merge), flatten it
    if isinstance(data[0], list):
        flattened_data = []
        for sublist in data:
            if isinstance(sublist, list):
                flattened_data.extend(sublist)
            else:
                flattened_data.append(sublist)
        data = flattened_data
    
    # Process customer data - iterate through each customer record
    for customer in data:
        # Skip if customer is not a dict (safety check)
        if not isinstance(customer, dict):
            continue
        customer_id = customer.get('customer_id')
```

### ❌ Wrong: Regex escape sequence in raw string
```python
# SyntaxWarning: invalid escape sequence
if email and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$', email):
```

**Error**: `SyntaxWarning: invalid escape sequence '\.'`

### ✅ Correct: Proper regex escape sequence
```python
if email and re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
```

## Key Implementation Patterns

### 1. Enterprise Data Integration
- **Multi-source data loading**: CRM, transactions, support tickets, marketing data
- **Data validation and cleaning**: Email validation, phone standardization, date parsing
- **Data quality scoring**: Composite scoring based on completeness and validity

### 2. Customer Scoring Algorithm
```python
# Value Score (0-100) - based on spending and frequency
value_score = 0
if total_spent > 0:
    value_score += min(total_spent / 1000 * 50, 50)  # Up to 50 points for spending
if transaction_count > 0:
    value_score += min(transaction_count / 10 * 30, 30)  # Up to 30 points for frequency
if avg_order_value > 0:
    value_score += min(avg_order_value / 200 * 20, 20)  # Up to 20 points for AOV

# Overall Customer Value Score
customer_value_score = (value_score * 0.5 + engagement_score * 0.3 + (100 - risk_score) * 0.2)
```

### 3. Conditional Processing with SwitchNode
- **Multi-case routing**: Route customers by segment (VIP, Premium, Standard)
- **Differential processing**: VIP customers get enhanced attributes, standard customers get automation flags
- **Output generation**: Different output formats for different customer segments

## Workflow Architecture

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌─────────────┐
│ CRM Data    │    │ Transaction  │    │ Support Data  │    │ Marketing   │
│ (CSV)       │    │ Data (CSV)   │    │ (CSV)         │    │ Data (JSON) │
└─────────────┘    └──────────────┘    └───────────────┘    └─────────────┘
       │                   │                    │                    │
       ▼                   ▼                    ▼                    ▼
┌─────────────┐    ┌──────────────┐    ┌───────────────┐            │
│ CRM         │    │ Transaction  │    │ Support       │            │
│ Validator   │    │ Cleaner      │    │ Processor     │            │
└─────────────┘    └──────────────┘    └───────────────┘            │
       │                   │                    │                    │
       └───────┬───────────┴────────────────────┘                    │
               ▼                                                     │
        ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
        │ CRM+Trans    │    │ + Support    │    │ Final Customer   │◄─┘
        │ Merge        │───▶│ Merge        │───▶│ Merge            │
        └──────────────┘    └──────────────┘    └──────────────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │ Customer        │
                                                │ Scoring         │
                                                └─────────────────┘
                                                         │
                                                         ▼
                                                ┌─────────────────┐
                                                │ Customer        │
                                                │ Router          │
                                                │ (SwitchNode)    │
                                                └─────────────────┘
                                                    │         │
                                            ┌───────┘         └───────┐
                                            ▼                         ▼
                                    ┌──────────────┐         ┌─────────────────┐
                                    │ High Value   │         │ Standard        │
                                    │ Processor    │         │ Processor       │
                                    └──────────────┘         └─────────────────┘
                                            │                         │
                                            ▼                         ▼
                                    ┌──────────────┐         ┌─────────────────┐
                                    │ JSON Output  │         │ CSV Output      │
                                    │ (VIP/Premium)│         │ (Standard)      │
                                    └──────────────┘         └─────────────────┘
```

## Known Issues & Workarounds

### DataTransformer Dict Output Bug
**Issue**: When connecting DataTransformer nodes, dict outputs become list of keys instead of actual dictionaries.

**Workaround**: Use MergeNode with "concat" type and handle flattened list structure in subsequent transformations.

**Bug Report**: This is a high-priority bug in the DataTransformer implementation that needs to be addressed.

## File Structure
```
customer-operations/
├── scripts/
│   ├── customer_360_integration.py    # Main workflow script
│   └── data/
│       ├── crm_customers.csv         # CRM source data
│       ├── transactions.csv          # Transaction history
│       ├── support_tickets.csv       # Support ticket data
│       ├── marketing_engagement.json # Marketing engagement data
│       └── outputs/                  # Generated outputs
│           ├── high_value_customers.json
│           ├── standard_customers.csv
│           └── customer_360_complete.json
└── training/
    └── customer_360_training.md      # This training documentation
```

## Success Metrics
- ✅ Successfully processed 5 customers through the full pipeline
- ✅ Generated comprehensive customer scores with value, engagement, and risk components
- ✅ Correctly routed customers based on segments
- ✅ Produced multiple output formats (JSON for high-value, CSV for standard)
- ✅ Handled complex data merging and transformation scenarios
- ✅ Demonstrated enterprise-grade data validation and quality scoring

## Next Steps
1. **Fix DataTransformer dict output bug** to eliminate the need for flattened data handling
2. **Enhance customer scoring algorithm** with more sophisticated ML-based scoring
3. **Add real-time integration** with CRM and transaction systems
4. **Implement automated alerting** for high-risk customers
5. **Create dashboard visualization** for customer 360° insights