# Workflow Comparison

This document compares two versions of a data processing workflow.

## Workflow v1 - Original

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    csv_reader["CSVReaderNode<br/>csv_reader"]
    json_reader["JSONReaderNode<br/>json_reader"]

    %% Processing nodes
    data_joiner["PythonCode<br/>data_joiner"]
    data_transformer["PythonCode<br/>data_transformer"]
    classifier["PythonCode<br/>classifier"]
    aggregator["PythonCode<br/>aggregator"]

    %% Data Output nodes
    csv_writer["CSVWriterNode<br/>csv_writer"]
    json_writer["JSONWriterNode<br/>json_writer"]

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

## Workflow v2 - Enhanced with Extra Processor

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    csv_reader["CSVReaderNode<br/>csv_reader"]
    json_reader["JSONReaderNode<br/>json_reader"]

    %% Processing nodes
    data_joiner["PythonCode<br/>data_joiner"]
    data_transformer["PythonCode<br/>data_transformer"]
    classifier["PythonCode<br/>classifier"]
    aggregator["PythonCode<br/>aggregator"]
    extra_processor["PythonCode<br/>extra_processor"]

    %% Data Output nodes
    csv_writer["CSVWriterNode<br/>csv_writer"]
    json_writer["JSONWriterNode<br/>json_writer"]

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
    classifier -->|data→data| extra_processor
    aggregator -->|metrics→data| json_writer
    extra_processor -->|data→data| csv_writer
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
    style extra_processor fill:#fffde7,stroke:#f57f17,stroke-width:2px
```

## Changes Summary

- **Added**: `extra_processor` node between `classifier` and `csv_writer`
- **Purpose**: Additional processing step for data enhancement
- **Impact**: Data now goes through an extra transformation before being written to CSV
