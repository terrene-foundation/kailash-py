# Manufacturing Workflows

This directory contains comprehensive manufacturing workflow examples that demonstrate real-world industrial applications using the Kailash SDK.

## Available Workflows

### 1. IoT Sensor Processing (`scripts/iot_sensor_processing.py`)
**Real-time sensor monitoring and predictive maintenance**

- **Purpose**: Process sensor data from manufacturing equipment to detect anomalies and predict maintenance needs
- **Data Sources**: Temperature, pressure, vibration, and power sensors
- **Key Features**:
  - Real-time anomaly detection with statistical thresholds
  - Multi-sensor aggregation and health scoring
  - Predictive maintenance recommendations
  - Critical alert generation for immediate issues
- **Business Value**: Prevent equipment failures, minimize downtime, optimize maintenance schedules

**Usage:**
```bash
python sdk-users/workflows/by-industry/manufacturing/scripts/iot_sensor_processing.py
```

**Outputs:**
- Anomaly analysis with sensor health scores
- Maintenance recommendations prioritized by urgency
- Critical alerts for immediate attention
- Historical sensor performance trends

### 2. Quality Control (`scripts/quality_control.py`)
**Six Sigma statistical process control and quality assurance**

- **Purpose**: Monitor production quality using Six Sigma methodology and control charts
- **Data Sources**: Production metrics (efficiency, defect rates, cycle times)
- **Key Features**:
  - Six Sigma control limit calculations (±3σ)
  - Process capability analysis (Cp/Cpk)
  - Out-of-control point detection
  - Operator performance tracking
- **Business Value**: Maintain quality standards, reduce defects, optimize processes

**Usage:**
```bash
python sdk-users/workflows/by-industry/manufacturing/scripts/quality_control.py
```

**Outputs:**
- Statistical process control analysis
- Quality scorecards by production line
- Process capability assessments
- Action plans for quality improvement

### 3. Supply Chain Optimization (`scripts/supply_chain_optimization.py`)
**Inventory optimization and supplier performance management**

- **Purpose**: Optimize inventory levels and evaluate supplier performance
- **Data Sources**: Inventory levels, supplier performance metrics, demand patterns
- **Key Features**:
  - Economic Order Quantity (EOQ) calculations
  - Safety stock optimization based on demand variability
  - Comprehensive supplier scorecards
  - Risk assessment and mitigation planning
- **Business Value**: Reduce inventory costs, minimize stockouts, improve supplier relationships

**Usage:**
```bash
python sdk-users/workflows/by-industry/manufacturing/scripts/supply_chain_optimization.py
```

**Outputs:**
- Inventory optimization recommendations
- Supplier performance evaluations
- Risk assessments with mitigation strategies
- Cost savings opportunities

### 4. Production Planning (`scripts/production_planning.py`)
**Capacity analysis and production schedule optimization**

- **Purpose**: Analyze production capacity and optimize machine utilization
- **Data Sources**: Machine schedules, production orders, capacity data
- **Key Features**:
  - Machine utilization analysis
  - Bottleneck identification
  - Schedule gap optimization
  - Capacity balancing recommendations
- **Business Value**: Maximize throughput, reduce idle time, improve delivery performance

**Usage:**
```bash
python sdk-users/workflows/by-industry/manufacturing/scripts/production_planning.py
```

**Outputs:**
- Capacity utilization analysis
- Production optimization recommendations
- Bottleneck identification and solutions
- Schedule efficiency improvements

## Data Requirements

All workflows use real manufacturing data located in `/data/inputs/manufacturing/`:

- `sensor_readings.csv` - IoT sensor data with timestamps and readings
- `production_metrics.csv` - Production line performance data
- `inventory_levels.csv` - Current inventory levels and parameters
- `supplier_performance.csv` - Supplier delivery and quality metrics
- `machine_schedule.csv` - Production schedules and machine assignments

## Key Features

### Production-Ready Patterns
- **Real Data Integration**: All workflows use actual manufacturing data, not mock data
- **Statistical Rigor**: Proper statistical methods (Six Sigma, EOQ, control charts)
- **Business Logic**: Implements actual manufacturing best practices
- **Error Handling**: Robust error handling for production environments

### Modern Code Patterns
- **Function-Based Processing**: Uses `PythonCodeNode.from_function()` for complex logic
- **Centralized Data Management**: Proper data path utilities
- **Type Safety**: Proper data type conversions and validation
- **Modular Design**: Clear separation of concerns and reusable functions

### Industrial Standards
- **Six Sigma Quality Control**: Statistical process control with proper control limits
- **Economic Order Quantity**: Scientifically-based inventory optimization
- **Predictive Maintenance**: Multi-factor equipment health assessment
- **Lean Manufacturing**: Focus on waste reduction and efficiency optimization

## Training Data

Corresponding training examples are available in:
See the Kailash SDK repository for training examples.

These provide wrong→correct pattern examples for LLM training, covering:
- Common mistakes in manufacturing workflow development
- Best practices for sensor data processing
- Proper statistical analysis techniques
- Production-ready error handling patterns

## Integration Examples

### With Existing Systems
- **ERP Integration**: Connect to SAP, Oracle, or other ERP systems
- **MES Integration**: Interface with Manufacturing Execution Systems
- **SCADA Integration**: Real-time data from supervisory control systems
- **Quality Management**: Integration with quality management software

### API Endpoints
All workflows can be exposed as REST APIs using the Kailash workflow API wrapper:

```python
from kailash.api.workflow_api import WorkflowAPI

# Expose IoT sensor processing as API
api = WorkflowAPI()
api.add_workflow("iot-sensor-processing", iot_workflow)
api.run(host="0.0.0.0", port=8000)

```

## Performance Considerations

- **Real-time Processing**: IoT workflow designed for sub-second response times
- **Batch Processing**: Quality control optimized for daily/shift-based analysis
- **Scalability**: All workflows support horizontal scaling
- **Memory Efficiency**: Optimized for large datasets typical in manufacturing

## Getting Started

1. **Ensure Data Availability**: Verify manufacturing data files exist in `/data/inputs/manufacturing/`
2. **Install Dependencies**: Ensure all required Python packages are installed
3. **Configure Paths**: Verify data path utilities point to correct directories
4. **Run Workflows**: Execute individual workflows or integrate into larger systems
5. **Review Outputs**: Check results in `/data/outputs/manufacturing/`

## Best Practices

- Use real production data whenever possible
- Implement proper error handling for sensor failures
- Follow statistical best practices for quality control
- Integrate with existing manufacturing systems
- Monitor workflow performance and optimize as needed
- Document any customizations for your specific manufacturing environment

## Support

For questions or issues with manufacturing workflows:
- Check the troubleshooting guide: `sdk-users/developer/07-troubleshooting.md`
- Review common mistakes: `shared/mistakes/`
- See the Kailash SDK repository for training examples
