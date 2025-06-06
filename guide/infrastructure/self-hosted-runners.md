# Self-Hosted Runners Setup Guide

## Overview

This guide helps you set up self-hosted runners for faster CI/CD execution of the Kailash Python SDK test suite.

## Why Self-Hosted Runners?

Current issues with GitHub-hosted runners:
- **Slow execution**: 591 tests take too long on 2-core runners
- **Limited parallelization**: Default runners have only 2 cores
- **Queue times**: Waiting for available runners during peak times

Benefits of self-hosted runners:
- **More cores**: Use 8, 16, or more cores for parallel test execution
- **Persistent cache**: Dependencies stay cached between runs
- **No queue times**: Dedicated runners always available
- **Cost effective**: Can be cheaper than GitHub's larger runners

## Setup Options

### Option 1: Local Machine (Development)

Quick setup for testing on your development machine:

```bash
# Run the setup script
./scripts/setup-self-hosted-runner.sh

# The script will:
# 1. Download GitHub Actions runner
# 2. Configure it for your repository
# 3. Install as a service (optional)
# 4. Install Python and UV
```

### Option 2: Dedicated VM (Recommended)

For production use, set up on a dedicated VM:

#### AWS EC2 Example:
```bash
# Recommended instance types:
# - t3.xlarge (4 vCPU, 16 GB RAM) - Good for basic needs
# - c5.2xlarge (8 vCPU, 16 GB RAM) - Better for parallel tests
# - c5.4xlarge (16 vCPU, 32 GB RAM) - Best performance

# Launch Ubuntu 22.04 LTS instance
# SSH into the instance and run:
curl -O https://raw.githubusercontent.com/terrene-foundation/kailash-py/main/scripts/setup-self-hosted-runner.sh
chmod +x setup-self-hosted-runner.sh
./setup-self-hosted-runner.sh
```

#### Azure VM Example:
```bash
# Recommended VM sizes:
# - Standard_D4s_v3 (4 vCPU, 16 GB RAM)
# - Standard_D8s_v3 (8 vCPU, 32 GB RAM)
# - Standard_D16s_v3 (16 vCPU, 64 GB RAM)
```

#### Google Cloud Example:
```bash
# Recommended machine types:
# - n2-standard-4 (4 vCPU, 16 GB RAM)
# - n2-standard-8 (8 vCPU, 32 GB RAM)
# - n2-standard-16 (16 vCPU, 64 GB RAM)
```

### Option 3: Docker Container

Run the runner in a Docker container:

```dockerfile
# Dockerfile for self-hosted runner
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    curl \
    sudo \
    git \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    build-essential

# Create runner user
RUN useradd -m runner && \
    usermod -aG sudo runner && \
    echo "runner ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER runner
WORKDIR /home/runner

# Copy and run setup script
COPY scripts/setup-self-hosted-runner.sh .
RUN chmod +x setup-self-hosted-runner.sh

# Run the runner
CMD ["./actions-runner/run.sh"]
```

### Option 4: Kubernetes

For scalable runners, use Actions Runner Controller:

```yaml
apiVersion: actions.summerwind.dev/v1alpha1
kind: RunnerDeployment
metadata:
  name: kailash-runner-deployment
spec:
  replicas: 2
  template:
    spec:
      repository: terrene-foundation/kailash-py
      labels:
        - self-hosted
        - linux
        - x64
        - large
      resources:
        requests:
          cpu: "4"
          memory: "8Gi"
        limits:
          cpu: "8"
          memory: "16Gi"
```

## Configuration

### 1. Runner Labels

Configure your runners with appropriate labels:

```bash
# During setup, use labels like:
self-hosted,linux,x64,large      # For 8+ cores
self-hosted,linux,x64,xlarge     # For 16+ cores
self-hosted,linux,x64,gpu        # If GPU available
```

### 2. Update Workflow Files

Use the new workflow file:

```yaml
# .github/workflows/ci-self-hosted.yml
runs-on: [self-hosted, linux, x64, large]
```

Or allow fallback to GitHub runners:

```yaml
runs-on: ${{ matrix.runner }}
strategy:
  matrix:
    runner:
      - [self-hosted, linux, x64]
      - ubuntu-latest  # Fallback
```

### 3. Optimize for Performance

The included workflow uses several optimizations:

1. **Parallel pytest execution**: `-n auto` uses all available cores
2. **Parallel linting**: Runs black, isort, and ruff simultaneously
3. **UV package manager**: Faster than pip
4. **Dependency caching**: Reuses virtual environments
5. **Load balancing**: `--dist loadgroup` for better test distribution

## Monitoring

### Check Runner Status

```bash
# If installed as service
sudo systemctl status actions.runner.*

# View logs
journalctl -u actions.runner.* -f

# In GitHub UI
# Go to Settings > Actions > Runners
```

### Performance Metrics

Monitor your runner performance:

```bash
# CPU usage during tests
htop

# Test execution time
time uv run pytest tests/ -n auto

# Compare with GitHub runners
# GitHub (2 cores): ~15 minutes
# Self-hosted (8 cores): ~3-4 minutes
# Self-hosted (16 cores): ~2 minutes
```

## Security Considerations

1. **Network Security**:
   - Runners only need outbound HTTPS (443) to GitHub
   - No inbound connections required
   - Use security groups/firewalls appropriately

2. **Access Control**:
   - Runners get a limited-scope token
   - Can only run workflows from your repository
   - Use separate runners for public/private repos

3. **Isolation**:
   - Use containers or VMs for isolation
   - Don't run on production servers
   - Regular security updates

## Cost Comparison

### GitHub Larger Runners (Team/Enterprise)
- 4-core: $0.08/minute
- 8-core: $0.16/minute
- 16-core: $0.32/minute

### Self-Hosted (AWS EC2 On-Demand)
- t3.xlarge (4 vCPU): ~$0.17/hour = $0.003/minute
- c5.2xlarge (8 vCPU): ~$0.34/hour = $0.006/minute
- c5.4xlarge (16 vCPU): ~$0.68/hour = $0.011/minute

### Break-even Analysis
If you run CI more than ~30 minutes/day, self-hosted becomes cost-effective.

## Troubleshooting

### Runner Goes Offline
```bash
# Restart the service
sudo systemctl restart actions.runner.*

# Check logs for errors
journalctl -u actions.runner.* -n 100
```

### Tests Still Slow
```bash
# Check CPU cores available
nproc

# Ensure pytest is using all cores
ps aux | grep pytest  # Should show multiple processes

# Check for resource constraints
free -h
df -h
```

### Permission Issues
```bash
# Fix permissions for runner work directory
sudo chown -R runner:runner /home/runner/actions-runner/_work
```

## Next Steps

1. **Set up your first runner** using the setup script
2. **Test with the new workflow** by pushing to a feature branch
3. **Monitor performance** and adjust runner size as needed
4. **Consider autoscaling** for variable workloads

For questions or issues, please open a GitHub issue.
