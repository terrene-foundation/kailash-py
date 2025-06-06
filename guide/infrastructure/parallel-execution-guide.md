# Parallel Execution on Local Mac Runner

## Overview

When using your local Mac runner, all checks run in parallel within a single job to maximize efficiency and utilize all 14 CPU cores.

## How It Works

### 1. Single Job Execution
Instead of running 4 separate jobs sequentially:
- ❌ Lint and Format Check (2 min)
- ❌ Test Python 3.11 (5 min)
- ❌ Test Python 3.12 (5 min)
- ❌ Validate Examples (3 min)
- **Total: ~15 minutes sequential**

The workflow runs one job with all checks in parallel:
- ✅ All Checks (Parallel) - runs everything at once
- **Total: ~5-7 minutes parallel**

### 2. Parallel Execution Script
The workflow creates a bash script that runs all checks simultaneously:
```bash
run_check "Black formatting" "uv run black --check src/ tests/" "black.log" &
run_check "Isort imports" "uv run isort --check-only src/ tests/" "isort.log" &
run_check "Ruff linting" "uv run ruff check src/ tests/" "ruff.log" &
run_check "Tests Python 3.11" "uv run pytest tests/ -n auto" "pytest.log" &
run_check "Example validation" "cd examples && uv run python _utils/test_all_examples.py" "examples.log" &
```

### 3. CPU Utilization
- Uses `pytest-xdist` with `-n auto` to run tests across all cores
- All linting/formatting checks run in parallel
- Example validation runs concurrently

## Benefits

1. **3x Faster**: ~5 minutes instead of ~15 minutes
2. **Better Resource Usage**: Utilizes all 14 CPU cores
3. **Single Log**: All results in one job log
4. **Fail Fast**: If any check fails, you know immediately

## Usage

### Trigger with Local Mac
```bash
gh workflow run unified-ci.yml -f runner-type=local-mac
```

### Monitor Progress
```bash
# Watch the parallel job
gh run watch <run-id> --job "All Checks (Parallel)"

# Check which processes are running
ps aux | grep -E "(pytest|black|isort|ruff)" | grep -v grep
```

## Troubleshooting

### If checks seem slow
1. Check CPU usage: `top` or `htop`
2. Ensure no other heavy processes are running
3. Check available disk space: `df -h`

### If a specific check fails
The workflow saves logs for each check:
- `black.log` - Formatting issues
- `isort.log` - Import order issues
- `ruff.log` - Linting issues
- `pytest.log` - Test failures
- `examples.log` - Example validation issues

## Running Multiple Runner Instances

For even more parallelism, you can run multiple runner instances:

```bash
# Start 3 runner instances
./scripts/start-parallel-runners.sh 3

# Each instance can handle a separate workflow run
```

This allows running multiple PRs or branches simultaneously.
