# Workflow Execution Status

**Run ID**: `57675fcc-44c9-4f10-bfc9-85ba475ff5b5`
**Workflow**: data_processing_pipeline
**Timestamp**: 2025-05-30 12:36:55.011871+00:00

## Execution Diagram

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    csv_reader["CSVReader<br/>csv_reader ✅"]
    json_reader["JSONReader<br/>json_reader ✅"]

    %% Processing nodes
    data_joiner["PythonCode<br/>data_joiner ✅"]
    data_transformer["PythonCode<br/>data_transformer 🔄"]
    classifier["PythonCode<br/>classifier ⏳"]
    aggregator["PythonCode<br/>aggregator ⏳"]

    %% Data Output nodes
    csv_writer["CSVWriter<br/>csv_writer ⏳"]
    json_writer["JSONWriter<br/>json_writer ⏳"]

    %% Output Data
    output_data([Output Data])

    %% Flow
    input_data --> csv_reader
    input_data --> json_reader
    csv_reader -->|data→customer_data| data_joiner
    json_reader -->|data→transaction_data| data_joiner
    data_joiner -->|data→data| data_transformer
    data_transformer -->|data→data| classifier
    classifier -->|data→data| aggregator
    classifier -->|data→data| csv_writer
    aggregator -->|metrics→data| json_writer
    csv_writer --> output_data
    json_writer --> output_data

    %% Styling
    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style csv_reader fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style json_reader fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style data_joiner fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style data_transformer fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style classifier fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style aggregator fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style csv_writer fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style json_writer fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

## Status Legend

| Status | Symbol | Description |
|--------|--------|-------------|
| Pending | ⏳ | Task is waiting to be executed |
| Running | 🔄 | Task is currently executing |
| Completed | ✅ | Task completed successfully |
| Failed | ❌ | Task failed during execution |
| Skipped | ⏭️ | Task was skipped |

## Task Details

| Node ID | Status | Start Time | End Time | Duration |
|---------|--------|------------|----------|----------|
| csv_reader | completed ✅ | N/A | N/A | N/A |
| classifier | pending ⏳ | N/A | N/A | N/A |
| data_transformer | running 🔄 | N/A | N/A | N/A |
| json_reader | completed ✅ | N/A | N/A | N/A |
| csv_writer | pending ⏳ | N/A | N/A | N/A |
| data_joiner | completed ✅ | N/A | N/A | N/A |
| json_writer | pending ⏳ | N/A | N/A | N/A |
| aggregator | pending ⏳ | N/A | N/A | N/A |
