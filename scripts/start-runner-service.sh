#!/bin/bash
# Start GitHub Actions runner as a service

# Configuration with defaults
RUNNER_NAME=${RUNNER_NAME:-self-hosted-primary}
RUNNER_DIR=${RUNNER_DIR:-"$HOME/actions-runner"}

echo "🚀 Starting GitHub Actions runner service for $RUNNER_NAME"
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

# Check if service is already installed
if ./svc.sh status 2>&1 | grep -q "not installed"; then
    echo "📦 Installing runner service..."
    sudo ./svc.sh install
else
    echo "✓ Service already installed"
fi

# Check if service is running
if ./svc.sh status 2>&1 | grep -q "Active: active (running)"; then
    echo "✓ Service is already running"
else
    echo "▶️  Starting runner service..."
    sudo ./svc.sh start
fi

# Show status
echo ""
echo "📊 Service status:"
./svc.sh status

echo ""
echo "✅ GitHub Actions runner service is running!"
echo ""
echo "📝 Useful commands:"
echo "  Check status:  cd $RUNNER_DIR && ./svc.sh status"
echo "  View logs:     cd $RUNNER_DIR && sudo journalctl -u actions.runner.* -f"
echo "  Stop service:  cd $RUNNER_DIR && sudo ./svc.sh stop"
echo "  Start service: cd $RUNNER_DIR && sudo ./svc.sh start"
echo ""
echo "🏷️  Runner name: $RUNNER_NAME"
echo "💪 This runner will utilize all $(sysctl -n hw.ncpu) CPU cores for parallel test execution"
echo ""
echo "💡 To use a different runner name:"
echo "   RUNNER_NAME=your-runner-name $0"