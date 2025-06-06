#!/bin/bash
# Start multiple GitHub Actions runner instances for parallel job execution

RUNNER_COUNT=${1:-3}  # Default to 3 runners
RUNNER_BASE_DIR="$HOME/actions-runners"

echo "🚀 Starting $RUNNER_COUNT parallel GitHub Actions runners"

# Create base directory
mkdir -p "$RUNNER_BASE_DIR"

# Function to setup and start a runner
start_runner() {
    local index=$1
    local runner_dir="$RUNNER_BASE_DIR/runner-$index"

    echo "Setting up runner $index in $runner_dir"

    # Create runner directory
    mkdir -p "$runner_dir"
    cd "$runner_dir"

    # Download runner if not exists
    if [ ! -f "run.sh" ]; then
        echo "Downloading runner for instance $index..."
        curl -o actions-runner-osx-arm64-2.324.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.324.0/actions-runner-osx-arm64-2.324.0.tar.gz
        tar xzf ./actions-runner-osx-arm64-2.324.0.tar.gz
        rm actions-runner-osx-arm64-2.324.0.tar.gz

        echo "⚠️  Runner $index needs configuration. Run:"
        echo "cd $runner_dir && ./config.sh --url https://github.com/terrene-foundation --name self-hosted-secondary-$index"
        return
    fi

    # Start runner in background
    echo "Starting runner $index..."
    nohup ./run.sh > runner-$index.log 2>&1 &
    echo "Runner $index started with PID $!"
}

# Start multiple runners
for i in $(seq 1 $RUNNER_COUNT); do
    start_runner $i
done

echo ""
echo "✅ Runner startup initiated"
echo ""
echo "To check runner status:"
echo "  ps aux | grep Runner.Listener"
echo ""
echo "To stop all runners:"
echo "  pkill -f Runner.Listener"
echo ""
echo "To view logs:"
echo "  tail -f $RUNNER_BASE_DIR/runner-*/runner-*.log"
