#!/bin/bash
# Start GitHub Actions runner in foreground

# Configuration - check for available runners
if [ -z "$RUNNER_NAME" ]; then
    # Check which runner directory exists
    if [ -f "$HOME/actions-runner/.runner" ] && grep -q "self-hosted-secondary" "$HOME/actions-runner/.runner" 2>/dev/null; then
        RUNNER_NAME="self-hosted-secondary"
    elif [ -f "$HOME/actions-runner/.runner" ] && grep -q "self-hosted-primary" "$HOME/actions-runner/.runner" 2>/dev/null; then
        RUNNER_NAME="self-hosted-primary"
    elif [ -f "$HOME/actions-runner/.runner" ] && grep -q "local" "$HOME/actions-runner/.runner" 2>/dev/null; then
        RUNNER_NAME="local"
    else
        # Default fallback
        RUNNER_NAME="local"
    fi
fi

RUNNER_DIR=${RUNNER_DIR:-"$HOME/actions-runner"}

echo "🚀 Starting GitHub Actions runner for $RUNNER_NAME"
echo ""

# Check if runner directory exists
if [ ! -d "$RUNNER_DIR" ]; then
    echo "❌ Runner directory not found at $RUNNER_DIR"
    echo "Please ensure the runner is installed at ~/actions-runner"
    exit 1
fi

cd "$RUNNER_DIR"

# Check if runner is configured
if [ ! -f ".runner" ]; then
    echo "❌ Runner is not configured in $RUNNER_DIR"
    echo "Please run ./config.sh first with your GitHub token"
    exit 1
fi

echo "▶️  Starting runner in foreground..."
echo "🏷️  Runner name: $RUNNER_NAME"
echo "💪 This runner will utilize all $(sysctl -n hw.ncpu) CPU cores for parallel test execution"
echo ""
echo "Press Ctrl+C to stop the runner"
echo ""
echo "💡 To use a different runner name:"
echo "   RUNNER_NAME=your-runner-name $0"
echo ""

# Start the runner
./run.sh
