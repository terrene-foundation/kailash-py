"""
⚠️  MIGRATION NOTICE ⚠️

This example uses the LEGACY kailash.api module which has been consolidated
into the new kailash.middleware layer. 

For NEW projects, use: examples/feature_examples/middleware/middleware_comprehensive_example.py

Migration guide: sdk-users/middleware/MIGRATION.md

---

Comprehensive Multi-Workflow Gateway Demo (LEGACY).

This example demonstrates a production-ready multi-workflow gateway setup with:
1. Multiple workflows for different domains
2. MCP integration for AI-powered tools
3. Proper error handling and validation
4. Real-world use cases

NOTE: This pattern is deprecated. Use kailash.middleware for new development.
"""

import logging
from datetime import datetime
from typing import Any

from kailash.middleware import APIGateway, create_gateway
from kailash.middleware import MiddlewareMCPServer as MCPIntegration
from kailash.nodes.code import PythonCodeNode