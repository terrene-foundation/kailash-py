#!/bin/bash

# Run MCP Ecosystem Demo
# This script sets up the environment and runs the ecosystem server

echo "🚀 Starting MCP Ecosystem Demo"
echo "================================"

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Set Python path to include src directory
export PYTHONPATH="${SCRIPT_DIR}/../../src:${PYTHONPATH}"

echo "📁 Working directory: ${SCRIPT_DIR}"
echo "🐍 Python path set to include Kailash SDK"
echo ""
echo "📡 Starting server..."
echo "📍 Open your browser to: http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo "================================"
echo ""

# Run the demo
cd "${SCRIPT_DIR}"
python mcp_ecosystem_demo.py