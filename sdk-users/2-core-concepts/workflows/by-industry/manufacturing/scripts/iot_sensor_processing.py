"""
IoT Sensor Processing Workflow

This workflow demonstrates real-time IoT sensor data processing for manufacturing:
1. Reads sensor data from multiple sources
2. Normalizes and aggregates sensor readings
3. Detects anomalies and generates alerts
4. Triggers predictive maintenance recommendations
5. Stores processed data for historical analysis

Real-world use case: Manufacturing plant monitoring system that processes
sensor data from production equipment to prevent failures and optimize performance.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from kailash.nodes import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.nodes.logic import SwitchNode
from kailash.nodes.transform import DataTransformer
from kailash.workflow import Workflow, WorkflowBuilder


