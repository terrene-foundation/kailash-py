# Self-Hosted GPU Runner — Maintenance Guide

**Scope:** `terrene-foundation/kailash-py` GitHub Actions self-hosted runner  
**Labels required:** `self-hosted`, `cuda`, `gpu`  
**Decision authority:** IT-1 (Decision 7, `specs/ml-backends.md § Hardware-gated CI`)

---

## 1. Runner Strategy

**Chosen path: persistent-but-controlled.**

A persistent runner (provisioned once, left running) is preferred over ephemerally-provisioned runners (created and destroyed per job) because:

- CUDA driver installation and `torch` package download are slow (~5–10 min). Ephemeral runners would pay this cost every job.
- The GPU hardware in scope (H100 / A100 / RTX 4090 class) is typically bare-metal or a dedicated VM — not pooled cloud instances where ephemeral is the natural model.
- Isolation is enforced at the workflow level via pre- and post-run `.venv` cleanup steps, not at the OS level (see § 5).

If future scale requires multiple runners or per-job ephemeral provisioning, revisit this decision and update this document.

---

## 2. Hardware Requirements

| Requirement | Minimum                                | Recommended            |
| ----------- | -------------------------------------- | ---------------------- |
| GPU         | Any NVIDIA CUDA 11.8+ capable card     | H100 / A100 / RTX 4090 |
| VRAM        | 8 GiB                                  | 40 GiB+                |
| RAM         | 32 GiB                                 | 64 GiB                 |
| Disk        | 100 GiB free                           | 500 GiB SSD            |
| OS          | Ubuntu 22.04 LTS                       | Ubuntu 22.04 LTS       |
| CUDA driver | 525+ (CUDA 12.x runtime)               | Latest stable          |
| Python      | 3.10–3.14 (via `actions/setup-python`) | 3.12 default           |

---

## 3. One-Time Provisioning Steps (Human)

These steps require credentials and billing decisions that cannot be automated.

### 3.1 Install NVIDIA driver + CUDA toolkit

```bash
# Ubuntu 22.04 — adjust version for your GPU
sudo apt-get update
sudo apt-get install -y nvidia-driver-535 nvidia-cuda-toolkit
sudo reboot
# After reboot:
nvidia-smi   # must return GPU info, not an error
```

### 3.2 Install GitHub Actions runner binary

```bash
mkdir ~/actions-runner && cd ~/actions-runner
# Download the latest runner — check https://github.com/actions/runner/releases
curl -o actions-runner-linux-x64-2.x.y.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.x.y/actions-runner-linux-x64-2.x.y.tar.gz
tar xzf ./actions-runner-linux-x64-2.x.y.tar.gz
```

### 3.3 Register the runner with required labels

**Get a fresh registration token from GitHub UI:**  
`github.com/terrene-foundation/kailash-py` → Settings → Actions → Runners → New self-hosted runner

```bash
# Replace RUNNER_TOKEN with the token from GitHub UI (expires in 1 hour)
# NEVER commit this token — it is a credential once registered
./config.sh \
  --url https://github.com/terrene-foundation/kailash-py \
  --token RUNNER_TOKEN \
  --labels "self-hosted,cuda,gpu" \
  --name "kailash-ml-cuda-runner-01" \
  --runnergroup Default \
  --unattended
```

### 3.4 Install as a persistent service

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # must show: active (running)
```

### 3.5 Verify runner appears in GitHub

Go to `github.com/terrene-foundation/kailash-py` → Settings → Actions → Runners.  
The runner `kailash-ml-cuda-runner-01` should appear with status **Idle**.

Alternatively:

```bash
gh api repos/terrene-foundation/kailash-py/actions/runners \
  --jq '.runners[] | {name, status, labels: [.labels[].name]}'
```

### 3.6 Run the canary smoke test

Dispatch `gpu-smoke.yml` manually from GitHub Actions UI or:

```bash
gh workflow run gpu-smoke.yml \
  --repo terrene-foundation/kailash-py \
  --field python_version=3.12
```

Watch the run:

```bash
gh run list --repo terrene-foundation/kailash-py --workflow=gpu-smoke.yml --limit 1
gh run watch <run-id>
```

**The runner is considered live when `gpu-smoke.yml` completes green.**

---

## 4. Flip CUDA from Non-Blocking to Blocking

Once `gpu-smoke.yml` has run green at least twice on consecutive days:

### 4.1 Find all non-blocking CUDA lines

```bash
grep -n 'continue-on-error: true.*IT-1' \
  /path/to/kailash-py/.github/workflows/test-kailash-ml.yml
```

Expected output (two lines):

```
<line>:    continue-on-error: true  # IT-1: non-blocking until runner live
<line>:    continue-on-error: true  # IT-1: non-blocking until runner live
```

### 4.2 Remove the non-blocking lines (one-liner)

```bash
sed -i '/continue-on-error: true.*IT-1/d' \
  .github/workflows/test-kailash-ml.yml
```

### 4.3 Commit and push

```bash
git add .github/workflows/test-kailash-ml.yml
git commit -m "chore(ci): IT1 — flip CUDA jobs from non-blocking to blocking

gpu-smoke.yml ran green on [date] and [date]. Runner kailash-ml-cuda-runner-01
is confirmed stable. Removing continue-on-error from test-cuda and
test-cuda-dl jobs per IT-1 completion criteria."
git push -u origin <branch>
```

---

## 5. Isolation Protocol (Invariant 1)

Each CI job enforces hermetic isolation at the workflow level:

**Pre-run step** (first step in every CUDA job):

```yaml
- name: Pre-run cleanup
  shell: bash
  run: |
    rm -rf .venv
    echo "Pre-run cleanup complete."
```

**Post-run step** (last step, runs on `if: always()`):

```yaml
- name: Post-run cleanup
  if: always()
  shell: bash
  run: |
    rm -rf .venv
    echo "Post-run cleanup complete."
```

**What this cleans:**

- `.venv/` — Python virtual environment (hermetic install per run)
- GPU memory is freed when the Python process exits; no explicit `cuda.empty_cache()` needed at the workflow level

**What is NOT cleaned between runs (by design):**

- `~/.cache/uv` — uv's content-addressed package cache (safe to share; hashes enforce correctness)
- NVIDIA driver state — persistent across jobs, managed by the OS
- System Python installations — not used; all jobs use `actions/setup-python` + `.venv`

---

## 6. Credential Rotation Protocol (Invariant 2)

All credentials are stored as GitHub org secrets, never committed to the repository.

### 6.1 Runner registration token

Registration tokens expire in 1 hour and become meaningless after registration. They do NOT need rotation post-registration. If you need to re-register the runner:

```bash
# De-register old runner first
cd ~/actions-runner
sudo ./svc.sh stop
./config.sh remove --token <removal-token-from-github-ui>
# Then follow § 3.3 to re-register
```

### 6.2 RUNNER_REGISTRATION_TOKEN org secret

If you automate runner provisioning using a GitHub org secret:

- Navigate to `github.com/organizations/terrene-foundation/settings/secrets/actions`
- Secret name: `RUNNER_REGISTRATION_TOKEN`
- Rotation schedule: every 90 days (tokens expire after 1 hour at use-time, but the org secret value itself should be rotated)
- After rotation: update the secret value in GitHub UI; no runner restart needed (the new token is only used when registering a new runner, not for ongoing operation)

### 6.3 NVIDIA driver credentials (if using NGC registry)

If pulling CUDA images from NGC:

- Store `NGC_API_KEY` as a GitHub org secret
- Rotation schedule: every 90 days

---

## 7. Maintenance Schedule

| Task                                               | Frequency             | Who       |
| -------------------------------------------------- | --------------------- | --------- |
| Verify runner shows Idle in GitHub UI              | Weekly                | On-call   |
| Check `nvidia-smi` output (driver version, memory) | Weekly                | On-call   |
| Apply NVIDIA driver security patches               | Monthly               | Infra     |
| Rotate `RUNNER_REGISTRATION_TOKEN` org secret      | Quarterly             | Infra     |
| OS security patches (unattended-upgrades)          | Continuous            | Automated |
| Review runner hardware (thermal, disk space)       | Monthly               | Infra     |
| Dispatch `gpu-smoke.yml` manual canary             | After any maintenance | On-call   |

### 7.1 Runner health check command

Run this from the runner host after any maintenance:

```bash
# 1. GPU health
nvidia-smi

# 2. Runner service status
cd ~/actions-runner && sudo ./svc.sh status

# 3. Runner visible to GitHub
gh api repos/terrene-foundation/kailash-py/actions/runners \
  --jq '.runners[] | select(.name | startswith("kailash-ml-cuda")) | {name, status}'
```

---

## 8. Re-Provisioning SLA

| Trigger                          | Target recovery time                         |
| -------------------------------- | -------------------------------------------- |
| Runner crashes (service restart) | < 15 minutes (automated systemd restart)     |
| Driver update required           | < 2 hours (scheduled maintenance window)     |
| Hardware failure (bare-metal)    | < 24 hours (replacement provisioning)        |
| Cloud VM preemption              | < 30 minutes (if using spot/preemptible VMs) |

**During outage:** CUDA jobs have `continue-on-error: true` as long as the non-blocking flag is present. Once flipped to blocking (§ 4), a runner outage will block PR merges — monitor the runner health dashboard.

---

## 9. Troubleshooting

### Runner shows Offline in GitHub UI

```bash
# On runner host
cd ~/actions-runner
sudo ./svc.sh status   # check if service is running
sudo ./svc.sh start    # if stopped
# Check logs
journalctl -u actions.runner.terrene-foundation-kailash-py.*.service -n 50
```

### `nvidia-smi` fails after OS update

```bash
# Re-install NVIDIA driver (Ubuntu)
sudo apt-get install --reinstall nvidia-driver-535
sudo reboot
```

### GPU smoke test fails: `cuda backend status != ok`

```bash
# Check torch CUDA installation
cd ~/actions-runner && source .venv/bin/activate
python -c "import torch; print(torch.version.cuda, torch.cuda.is_available())"
# If False: reinstall torch with CUDA support
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

### Runner auto-updated and jobs are orphaned

Per `rules/ci-runners.md` § Rule 4:

```bash
# Restart the runner service after auto-update
cd ~/actions-runner
sudo ./svc.sh stop
sudo ./svc.sh start
# Trigger a fresh run to unstick any orphaned jobs
gh workflow run gpu-smoke.yml --repo terrene-foundation/kailash-py
```

---

## 10. Decision Record

**Date:** 2026-04-23  
**Decision:** Persistent-but-controlled runner (not ephemeral per-job)  
**Reason:** CUDA driver + torch install time (~5–10 min) makes ephemeral runners impractical for per-PR CI. Isolation is enforced via per-job `.venv` cleanup at the workflow level.  
**Review trigger:** Re-evaluate if runner pool exceeds 3 machines or if ephemeral GPU cloud instances become cost-competitive with persistent hosts.

**IT-1 scope:** This document covers the code/docs side of IT-1. The actual act of provisioning a GPU VM and registering with GitHub is a human step requiring billing authorization and GitHub org admin credentials.
