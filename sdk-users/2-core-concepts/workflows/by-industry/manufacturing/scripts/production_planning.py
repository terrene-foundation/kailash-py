"""
Production Planning Workflow

This workflow demonstrates production planning optimization for manufacturing:
1. Reads machine schedules, capacity data, and order information
2. Analyzes production capacity and bottlenecks
3. Optimizes production scheduling and resource allocation
4. Generates Gantt charts and production timelines
5. Provides capacity utilization analysis and recommendations

Real-world use case: Manufacturing production planning system that optimizes
machine utilization, schedules orders efficiently, and identifies capacity
constraints to maximize throughput and minimize delays.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from kailash.nodes import PythonCodeNode
from kailash.nodes.data import CSVReaderNode, JSONWriterNode
from kailash.workflow import Workflow

