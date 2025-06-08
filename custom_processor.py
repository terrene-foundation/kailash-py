import numpy as np
import pandas as pd


def advanced_processing(data: pd.DataFrame, threshold: float = 0.5) -> pd.DataFrame:
    """Apply advanced processing with configurable threshold."""
    # Convert to DataFrame if needed
    if isinstance(data, list):
        data = pd.DataFrame(data)

    # Convert string columns to numeric where possible
    for col in ["value", "quantity"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce")

    result = data.copy()

    # Apply transformations
    for col in data.select_dtypes(include=[np.number]).columns:
        # Normalize values
        result[f"{col}_normalized"] = (data[col] - data[col].mean()) / data[col].std()

        # Apply threshold
        result[f"{col}_above_threshold"] = data[col] > (
            data[col].mean() + threshold * data[col].std()
        )

    # Add composite score
    numeric_cols = result.select_dtypes(include=[np.number]).columns
    result["composite_score"] = result[numeric_cols].mean(axis=1)

    # Convert DataFrame to JSON-serializable format
    return result.to_dict("records")


class DataProcessor:
    """Stateful data processor with memory."""

    def __init__(self):
        self.history = []

    def process(self, data: pd.DataFrame) -> pd.DataFrame:
        # Convert to DataFrame if needed
        if isinstance(data, list):
            data = pd.DataFrame(data)

        # Convert string columns to numeric where possible
        for col in ["value", "quantity"]:
            if col in data.columns:
                data[col] = pd.to_numeric(data[col], errors="coerce")

        self.history.append(len(data))

        result = data.copy()
        result["record_count"] = len(data)
        result["total_processed"] = sum(self.history)
        result["batch_number"] = len(self.history)

        # Convert DataFrame to JSON-serializable format
        return result.to_dict("records")
