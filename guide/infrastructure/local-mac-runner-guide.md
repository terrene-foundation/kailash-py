# Local Mac Runner Setup Guide

## Quick Start

This guide helps you use your local Mac as a GitHub Actions runner for faster test execution.

## Prerequisites

- macOS (Intel or Apple Silicon)
- GitHub account with repository access
- Python 3.11 (will be installed if missing)
- At least 8GB free RAM
- ~5GB free disk space

## Setup Steps

### 1. Run the Setup Script

```bash
cd kailash_python_sdk
./scripts/setup-mac-runner.sh
```

The script will:
1. Ask for your GitHub organization (default: terrene-foundation)
2. Ask for repository name (default: kailash_python_sdk)
3. Guide you to get a registration token from GitHub
4. Download and configure the runner
5. Optionally set up auto-start

### 2. Get Registration Token

1. Go to: https://github.com/terrene-foundation/kailash-py/settings/actions/runners
2. Click "New self-hosted runner"
3. Select "macOS"
4. Copy the token (starts with `AJRPV...` or similar)
5. Paste it when prompted by the script

### 3. Choose Runner Mode

When prompted, you can choose to:
- **Auto-start (Recommended)**: Runner starts automatically when you log in
- **Manual**: You'll need to start the runner manually each time

## Using Your Local Runner

### Manual Workflow Trigger

The `ci-local-mac.yml` workflow is designed for manual triggering:

1. Go to Actions tab in GitHub
2. Select "CI Pipeline (Local Mac)"
3. Click "Run workflow"
4. Choose options:
   - **Test type**: all, quick, unit, integration, or examples
   - **Use local**: ✓ (checked) to use your Mac

### Running Tests Locally

```bash
# Start runner manually (if not using auto-start)
~/start-runner.sh

# Check runner status
~/runner-status.sh

# Stop runner when done
~/stop-runner.sh
```

## Performance Tips

### 1. Keep Your Mac Awake
```bash
# Prevent sleep during tests (1 hour)
caffeinate -t 3600
```

### 2. Close Unnecessary Apps
Free up CPU and memory by closing:
- Browser tabs
- IDEs (if not needed)
- Slack/Discord
- Other heavy applications

### 3. Use Quick Test Mode
For rapid feedback during development:
- Select "quick" test type
- Runs only smoke tests
- Takes ~30 seconds

### 4. Monitor Resource Usage
```bash
# In a separate terminal
top -o cpu  # Watch CPU usage
```

## Advantages of Local Runner

1. **Speed**: Uses all your Mac's CPU cores
   - M1 Pro (8 cores): ~2-3 minutes for full suite
   - M2 Max (12 cores): ~1-2 minutes
   - Intel i9 (8 cores): ~3-4 minutes

2. **No Queue Time**: Instant start

3. **Cached Dependencies**: Reuses your local environment

4. **Cost**: Free! No GitHub Actions minutes used

## Limitations

1. **Availability**: Mac must be on and connected
2. **Resource Usage**: Can't use Mac heavily during tests
3. **Network**: Requires stable internet connection
4. **Security**: Your Mac has access to repository

## Troubleshooting

### Runner Offline in GitHub

```bash
# Check if runner is running
~/runner-status.sh

# Restart runner
~/stop-runner.sh
~/start-runner.sh

# Check logs
tail -f ~/actions-runner/runner.log
```

### Tests Failing Locally but Not on GitHub

1. **Environment differences**:
   ```bash
   # Ensure using correct Python
   which python3.11
   python3.11 --version
   ```

2. **Clean environment**:
   ```bash
   cd ~/actions-runner/_work/kailash_python_sdk
   rm -rf .venv
   uv sync --frozen
   ```

### Permission Issues

```bash
# Fix permissions
chmod -R u+w ~/actions-runner/_work
```

### High CPU Usage

1. Reduce parallel workers:
   ```bash
   # Edit the workflow to use fewer cores
   PYTEST_WORKERS: 4  # Instead of auto
   ```

2. Use nice to lower priority:
   ```bash
   nice -n 10 ~/start-runner.sh
   ```

## Best Practices

1. **Development Workflow**:
   - Use "quick" tests during development
   - Run "all" tests before pushing
   - Let GitHub runners handle PR tests

2. **Resource Management**:
   - Close heavy apps before running tests
   - Use Activity Monitor to check resources
   - Consider running overnight for large test suites

3. **Security**:
   - Only use for private repositories
   - Don't store secrets on runner
   - Regularly update runner software

## Removing the Runner

If you want to remove the runner:

```bash
# Stop the runner
~/stop-runner.sh

# Remove from GitHub
cd ~/actions-runner
./config.sh remove --token YOUR_REMOVAL_TOKEN

# Clean up files
rm -rf ~/actions-runner
rm ~/start-runner.sh ~/stop-runner.sh ~/runner-status.sh

# Remove LaunchAgent (if using auto-start)
launchctl unload ~/Library/LaunchAgents/github.runner.*
rm ~/Library/LaunchAgents/github.runner.*
```

## Summary

Your local Mac runner is perfect for:
- Quick feedback during development
- Running tests without using GitHub Actions minutes
- Taking advantage of your Mac's full CPU power

Just remember to keep your Mac awake and connected when using it!
