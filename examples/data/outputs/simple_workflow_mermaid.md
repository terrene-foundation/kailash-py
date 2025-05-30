## Simple ETL Pipeline Visualization

_A basic Extract-Transform-Load workflow_

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    reader["CSVReader<br/>reader"]

    %% Processing nodes
    transformer["DataTransformer<br/>transformer"]

    %% Data Output nodes
    writer["CSVWriter<br/>writer"]

    %% Output Data
    output_data([Output Data])

    %% Flow
    input_data --> reader
    reader -->|data→data| transformer
    transformer -->|transformed_data→data| writer
    writer --> output_data

    %% Styling
    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style reader fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style transformer fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style writer fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

### Nodes

| Node ID | Type | Description |
|---------|------|-------------|
| reader | CSVReader | Reads data from a CSV file. |
| transformer | DataTransformer | Transforms data using custom transformation functions provided as strings. |
| writer | CSVWriter | Writes data to a CSV file. |

### Connections

| From | To | Mapping |
|------|-----|---------|
| reader | transformer | data→data |
| transformer | writer | transformed_data→data |
