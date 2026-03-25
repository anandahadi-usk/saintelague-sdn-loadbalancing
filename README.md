# Sainte-Laguë Proportional Allocation for SDN Load Balancing

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Mininet 2.3](https://img.shields.io/badge/mininet-2.3-green.svg)](http://mininet.org/)
[![OpenFlow 1.3](https://img.shields.io/badge/OpenFlow-1.3-orange.svg)](https://opennetworking.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **"Post-Reconfiguration Convergence in SDN Load Balancing:
> A Comparative Empirical Study of WRR, IWRR, WLC, and Sainte-Laguë"**

---

## Overview

This repository contains the complete implementation, experimental data,
and analysis scripts for a controlled empirical study comparing four
weighted load balancing algorithms in Software-Defined Networking (SDN)
environments under dynamic weight-change conditions.

**Key finding:** Sainte-Laguë is the only algorithm that achieves
*sustained convergence* after weight changes (τ = 88.8 flows, 107
consecutive flows below 5% MAPE), with complete stochastic dominance
over all competitors (Cliff's δ = 1.000).

---

## Algorithms Compared

| Algorithm | Mechanism on Weight Change | Failure Mode |
|-----------|---------------------------|--------------|
| **WRR** | Rebuild sequence + reset counter | Structural Lock |
| **IWRR** | Rebuild sequence + reset counter | Sequence Reset |
| **WLC** | Clear session affinity → greedy select | Greedy Overshoot |
| **Sainte-Laguë** | Preserve n(i), update divisor only | ✅ None |

---

## Network Topology

```
10 Clients (10.0.1.1 – 10.0.1.10)
           │
      VIP: 10.0.0.100
      Ryu SDN Controller
           │
      OVS Switch (OpenFlow 1.3)
      ┌────┼────┐
      │    │    │
     S1   S2   S3
  30 Mbps 50 Mbps 20 Mbps
  (w=3)   (w=5)   (w=2)
```

---

## Experimental Design

| Scenario | Description | Runs/algo | Weight Change |
|----------|-------------|-----------|---------------|
| **S1** | Steady-state baseline | 15 | None |
| **S2** | Single weight change | 20 | [3,5,2]→[6,5,2] at t=45s |
| **S3** | Frequent weight changes | 20 | 4 changes at t=30,60,90,120s |

**Total:** 219 controlled runs (1 WLC-S3 excluded — OVS crash)

---

## Key Results

### S2 — Single Weight Change (Primary Test)

| Algorithm | MAPE (%) | τ (flows) | Sustained? | Cliff's δ vs SL |
|-----------|----------|-----------|------------|-----------------|
| **Sainte-Laguë** | **3.61 ± 0.88** | **88.8** | ✅ **107 flows** | — |
| IWRR | 11.07 ± 1.08 | ∞ | ❌ | 0.625 (large) |
| WRR | 22.11 ± 0.91 | ∞ | ❌ | 1.000 (complete) |
| WLC | 50.47 ± 0.94 | 29.1* | ❌ | 1.000 (complete) |

> *τ_WLC = 29.1 flows is **transient only** — WLC re-diverges to 50.47%

All comparisons: p < 0.0001 (Mann-Whitney U), |δ| ≥ 0.625

### QoS Cascade from WLC Failure (S2)

| Metric | Sainte-Laguë | WLC | Difference |
|--------|-------------|-----|------------|
| Throughput (Mbps) | 3.111 | 2.808 | **−10.7%** |
| Latency (ms) | 14.07 | 17.66 | **+25.5%** |

---

## Repository Structure

```
saintelague-sdn-loadbalancing/
├── config/                      # Experiment configuration
│   ├── experiment_config.py     # Algorithms, scenarios, seeds, metrics
│   ├── algo_config.py           # Per-algorithm parameters
│   └── network_config.py        # Topology (VIP, servers, capacities)
│
├── controller/                  # Ryu SDN controller
│   ├── main_controller.py       # Main controller + REST API
│   └── algorithms/
│       ├── wrr.py               # WRR implementation
│       ├── iwrr.py              # IWRR implementation
│       ├── wlc.py               # WLC implementation
│       └── saintelague.py       # Sainte-Laguë implementation
│
├── mn_traffic/                  # Mininet + traffic generation
│   └── traffic/
│       ├── base_traffic.py      # Base class + latency probing
│       ├── normal_traffic.py    # Steady-state (S1)
│       ├── bursty_traffic.py    # Single weight change (S2)
│       └── flash_crowd_traffic.py  # Frequent changes (S3)
│
├── evaluation/                  # Analysis and statistics
│   ├── run_experiment.py        # Main experiment runner
│   ├── convergence_analyzer.py  # τ computation, MAPE analysis
│   ├── statistical_tests.py     # Mann-Whitney U, Cliff's delta
│   ├── qos_analyzer.py          # Throughput, latency, jitter, loss
│   └── plot_results.py          # Publication figures
│
├── docs/
│   ├── figures/              # Publication figures (300 DPI PNG)
│   ├── paper_draft.md           # Manuscript source (Markdown)
│   ├── references.bib        # BibTeX references (34 entries, verified DOI)
│   └── create_figures.py     # Figure generation script
│
├── results/
│   └── processed/               # Aggregated CSV results (219 runs)
│       ├── aggregated_mape.csv
│       ├── convergence_summary.csv
│       └── statistical_tests.csv
│
├── requirements.txt
└── README.md
```

---

## Installation

### Option A — Automated (recommended)

```bash
git clone https://github.com/anandahadi-usk/saintelague-sdn-loadbalancing.git
cd saintelague-sdn-loadbalancing
bash setup.sh
```

`setup.sh` automatically installs all system packages (Mininet, OVS, iperf3, Python 3.8),
creates the virtual environment, and installs all Python dependencies.
Supports Ubuntu 20.04 / 22.04 / 24.04. Options:
- `bash setup.sh --dry-run` — check requirements only, no changes
- `bash setup.sh --skip-apt` — skip system packages, only create venv

### Option B — Manual

```bash
# Step 1: System packages (Mininet MUST be installed via apt — NOT pip)
sudo apt install python3.8 python3.8-venv mininet openvswitch-switch iperf3

# Step 2: Clone and create venv
git clone https://github.com/anandahadi-usk/saintelague-sdn-loadbalancing.git
cd saintelague-sdn-loadbalancing
python3.8 -m venv venv
source venv/bin/activate

# Step 3: Python dependencies
pip install --upgrade pip wheel setuptools
pip install -r requirements.txt
```

> **Important — Mininet and venv:**
> Mininet is a system package (`/usr/lib/python3/dist-packages/mininet/`) and
> is **not available inside the virtual environment**.
> The traffic scripts automatically add the system path — no extra action needed.
> Do **not** run `pip install mininet` inside the venv; it will install an
> incompatible stub package and cause `ImportError` at runtime.

### Verify installation

```bash
# Quick end-to-end test (~30 seconds, requires sudo)
SUDO_PASS=your_password bash test_quick.sh
```

Expected output: `SUCCESS: Pipeline validated!`

---

## Setting SUDO_PASS

Mininet requires root privileges. This project uses the `SUDO_PASS` environment
variable to pass the sudo password non-interactively to subprocesses.

**Why `SUDO_PASS`?**
Mininet traffic generators run inside Linux network namespaces and must be
launched with `sudo`. The `SUDO_PASS` variable avoids interactive password
prompts during long automated experiments.

### How to set it

**Option 1 — Inline (one-time, not stored)**
```bash
SUDO_PASS=your_sudo_password bash test_quick.sh
SUDO_PASS=your_sudo_password python3 evaluation/run_experiment.py --scenario all
```

**Option 2 — Shell session variable (not written to disk)**
```bash
read -s -p "Sudo password: " SUDO_PASS && export SUDO_PASS
# Enter password — it will not be echoed
```

**Option 3 — `.env` file (local only, never commit)**
```bash
echo "SUDO_PASS=your_sudo_password" > .env
source .env
```
> ⚠️ Add `.env` to `.gitignore` — **never commit passwords to version control.**

### Security notes

- `SUDO_PASS` is used only at runtime; it is **never written to any file**
  by the experiment scripts.
- Do **not** hardcode your password in any script or config file.
- If running on a shared machine, prefer Option 2 (session variable) so the
  password disappears when the terminal closes.
- The project has been audited: no passwords are stored in source code or
  committed to this repository.

### Passwordless sudo (alternative for CI/lab environments)

If you prefer not to use `SUDO_PASS`, grant passwordless sudo for Mininet only:

```bash
# Add to /etc/sudoers via visudo:
your_username ALL=(ALL) NOPASSWD: /usr/bin/mn, /usr/bin/python3
```

Then run without `SUDO_PASS`:
```bash
python3 evaluation/run_experiment.py --scenario all --yes
```

---

## Reproduce Experiments

### Quick start — single run

```bash
# Terminal 1: Start Ryu controller
PYTHONPATH=. ryu-manager controller/main_controller.py \
    --algorithm saintelague --scenario single_change

# Terminal 2: Run traffic (requires sudo)
sudo PYTHONPATH=. python3 mn_traffic/traffic/bursty_traffic.py \
    --run-id 1 --seed 42
```

### Full experiment — all algorithms × all scenarios × 20 runs

```bash
# Estimated runtime: ~18 hours on a single machine
# Replace 'your_password' with your sudo password, or use:
#   read -s -p "Sudo password: " SUDO_PASS && export SUDO_PASS
PYTHONPATH=. SUDO_PASS=your_password \
nohup python3 evaluation/run_experiment.py \
    --scenario all --runs 20 --yes \
    > logs/full_experiment.log 2>&1 &
```

### Re-run or recovering from a failed experiment

If a previous run was interrupted or failed, clean up all processes first
to prevent port conflicts and OVS bridge corruption:

```bash
# Step 1: Kill all leftover processes
sudo pkill -9 -f ryu-manager
sudo pkill -f iperf3
sudo mn --clean
sleep 3

# Step 2: Verify port 6653 is free
sudo ss -tlnp | grep 6653   # should return nothing

# Step 3: Re-run (existing successful runs are preserved, failed ones are retried)
PYTHONPATH=. SUDO_PASS=your_password \
python3 evaluation/run_experiment.py \
    --scenario all --runs 20 --yes \
    > logs/rerun.log 2>&1
```

> **Note:** The experiment runner automatically skips runs that already have
> valid results and only retries failed or missing runs.

### Reproduce figures only (from processed data)

```bash
python3 docs/create_figures.py
# Output: docs/figures/*.png (300 DPI, IEEE standard)
```

---

## Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| **MAPE** | (1/k)Σ\|nᵢ/n − pᵢ'\|/pᵢ' × 100% | Distributional accuracy |
| **τ** | First flow where MAPE sustained < 5% | Convergence onset |
| **JFI_c** | (Σfᵢ/cᵢ)²/(k·Σ(fᵢ/cᵢ)²) | Capacity-normalized fairness |
| **CDE** | Mean MAPE over all post-change flows | Cumulative error |

---

## Citation

If you use this code or data in your research, please cite:

```bibtex
@article{Elyas2026,
  author  = {Elyas, Ananda Hadi and Adriman, Ramzi and
             Syahrial, Syahrial and Arif, Teuku Yuliar},
  title   = {{Post-Reconfiguration Convergence in SDN Load Balancing:
              A Comparative Empirical Study}},
  journal = {{[Target Journal]}},
  year    = {2026},
  note    = {Under review}
}
```

---

## Dataset

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19186281.svg)](https://doi.org/10.5281/zenodo.19186281)

Experimental data (219 runs × per-flow metrics) available on Zenodo:

> **DOI:** `10.5281/zenodo.19186281`
> **URL:** https://doi.org/10.5281/zenodo.19186281
> **License:** CC BY 4.0

---

## Related Work

This repository is part of a research program on adaptive SDN scheduling:

- **This study:** Empirical characterisation of weight-change convergence behaviour
- **Follow-up (in progress):** PPO-SL-QoS — RL-based convergence acceleration with QoS priority ordering

---

## Troubleshooting

**`Permission denied` when reading result files:**

This is the most common issue. The traffic generator runs under `sudo`, creating
result CSV files owned by `root`. When analysis scripts run as a normal user,
reading those files fails with `Permission denied`.

The experiment runner now automatically fixes this after each run (`chown`),
but if it persists after a crash, fix it manually:
```bash
sudo chown -R $USER:$USER results/ logs/
```

**Experiment fails after a few runs / port 6653 conflict:**
```bash
# Full cleanup (pass your sudo password)
sudo pkill -9 -f ryu-manager
sudo pkill -f iperf3
sudo mn --clean
sleep 3
# Verify port is free (should return nothing)
sudo ss -tlnp | grep 6653
# Fix file ownership
sudo chown -R $USER:$USER results/ logs/
```

**`pip install mininet` causes ImportError:**
```
Do NOT install mininet via pip. Mininet must come from the system package.
The codebase already adds /usr/lib/python3/dist-packages to sys.path automatically.
Fix: pip uninstall mininet  (inside venv if accidentally installed)
```

**Mininet dirty state after crash:**
```bash
sudo mn -c && sudo pkill -f iperf3 && sudo pkill -f ryu-manager
sudo chown -R $USER:$USER results/ logs/
```

**`No module named 'config'`:**
```bash
export PYTHONPATH=$(pwd)
```

**Ryu eventlet error:**
```bash
venv/bin/pip install "eventlet==0.30.2"
```

---

## License

This project is licensed under the MIT License.

---

## Authors

| # | Name | Affiliation | Email |
|---|------|-------------|-------|
| # | Name | Affiliation | ORCID |
|---|------|-------------|-------|
| 1 | **Ananda Hadi Elyas** | Doctoral Program of Engineering, Universitas Syiah Kuala | [0000-0001-8468-5411](https://orcid.org/0000-0001-8468-5411) |
| 2 | Ramzi Adriman | Dept. ECE, Universitas Syiah Kuala | [0000-0002-2301-3627](https://orcid.org/0000-0002-2301-3627) |
| 3 | Syahrial Syahrial | Dept. ECE, Universitas Dharmawangsa | [0000-0002-1436-4468](https://orcid.org/0000-0002-1436-4468) |
| 4 | Teuku Yuliar Arif | Dept. ECE, Universitas Syiah Kuala | [0000-0002-8923-6778](https://orcid.org/0000-0002-8923-6778) |
