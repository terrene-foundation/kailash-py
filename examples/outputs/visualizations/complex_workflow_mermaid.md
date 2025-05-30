## Complex Processing Pipeline

_A sophisticated workflow with conditional routing and API integration_

```mermaid
flowchart TB

    %% Input Data
    input_data([Input Data])

    %% Data Input nodes
    customer_reader["CSVReader<br/>customer_reader"]
    transaction_reader["JSONReader<br/>transaction_reader"]

    %% Processing nodes
    data_validator["PythonCode<br/>data_validator"]
    premium_processor["DataTransformer<br/>premium_processor"]
    basic_filter["Filter<br/>basic_filter"]
    error_handler["PythonCode<br/>error_handler"]
    data_aggregator["DataTransformer<br/>data_aggregator"]
    data_normalizer["DataTransformer<br/>data_normalizer"]

    %% Routing/Decision nodes
    quality_router{"Switch<br/>quality_router"}

    %% Merge nodes
    result_merger(("Merge<br/>result_merger"))

    %% Data Output nodes
    final_output["JSONWriter<br/>final_output"]

    %% Output Data
    output_data([Output Data])

    %% Flow
    input_data --> customer_reader
    input_data --> transaction_reader
    customer_reader -->|data→input_data| data_validator
    transaction_reader -->|data→transactions| data_validator
    data_validator -->|validated_data→input| quality_router
    quality_router -->|High| premium_processor
    quality_router -->|Low| basic_filter
    quality_router -->|Error| error_handler
    premium_processor -->|transformed_data→data| data_aggregator
    basic_filter -->|filtered_data→input2| result_merger
    error_handler -->|handled_errors→input3| result_merger
    data_aggregator -->|transformed_data→data| data_normalizer
    data_normalizer -->|transformed_data→input1| result_merger
    result_merger -->|merged_data→data| final_output
    final_output --> output_data

    %% Styling
    style input_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style output_data fill:#e3f2fd,stroke:#1565c0,stroke-width:2px,stroke-dasharray: 5 5
    style customer_reader fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style transaction_reader fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    style data_validator fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style quality_router fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    style premium_processor fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style basic_filter fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style error_handler fill:#fffde7,stroke:#f57f17,stroke-width:2px
    style data_aggregator fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style data_normalizer fill:#fff3e0,stroke:#e65100,stroke-width:2px
    style result_merger fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    style final_output fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
```

### Nodes

| Node ID | Type | Description |
|---------|------|-------------|
| basic_filter | Filter | Filters data based on a condition. |
| customer_reader | CSVReader | Reads data from a CSV file. |
| data_aggregator | DataTransformer | Transforms data using custom transformation functions provided as strings. |
| data_normalizer | DataTransformer | Transforms data using custom transformation functions provided as strings. |
| data_validator | PythonCodeNode | Node for executing arbitrary Python code. |
| error_handler | PythonCodeNode | Node for executing arbitrary Python code. |
| final_output | JSONWriter | Writes data to a JSON file. |
| premium_processor | DataTransformer | Transforms data using custom transformation functions provided as strings. |
| quality_router | Switch | Routes data to different outputs based on conditions. |
| result_merger | Merge | Merges multiple data sources. |
| transaction_reader | JSONReader | Reads data from a JSON file. |

### Connections

| From | To | Mapping |
|------|-----|---------|
| customer_reader | data_validator | data→input_data |
| transaction_reader | data_validator | data→transactions |
| data_validator | quality_router | validated_data→input |
| quality_router | premium_processor | case_high→data |
| quality_router | basic_filter | case_low→data |
| quality_router | error_handler | case_error→data |
| premium_processor | data_aggregator | transformed_data→data |
| basic_filter | result_merger | filtered_data→input2 |
| error_handler | result_merger | handled_errors→input3 |
| data_aggregator | data_normalizer | transformed_data→data |
| data_normalizer | result_merger | transformed_data→input1 |
| result_merger | final_output | merged_data→data |
