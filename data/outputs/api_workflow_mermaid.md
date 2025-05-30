## API Integration Workflow

_Demonstrates API data fetching and processing_

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    fetch_data["JSONReader<br/>fetch_data"]

    %% Processing nodes
    process_data["PythonCode<br/>process_data"]
    transform_data["DataTransformer<br/>transform_data"]

    %% Data Output nodes
    save_results["JSONWriter<br/>save_results"]

    %% Output Data
    output_data([Output Data])

    %% Flow
    input_data --> fetch_data
    fetch_data -->|data→data| process_data
    process_data -->|processed→data| transform_data
    transform_data -->|transformed_data→data| save_results
    save_results --> output_data

    %% Styling
    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style fetch_data fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style process_data fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style transform_data fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style save_results fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

### Nodes

| Node ID | Type | Description |
|---------|------|-------------|
| fetch_data | JSONReader | Reads data from a JSON file. |
| process_data | PythonCodeNode | Node for executing arbitrary Python code. |
| save_results | JSONWriter | Writes data to a JSON file. |
| transform_data | DataTransformer | Transforms data using custom transformation functions provided as strings. |

### Connections

| From | To | Mapping |
|------|-----|---------|
| fetch_data | process_data | data→data |
| process_data | transform_data | processed→data |
| transform_data | save_results | transformed_data→data |
