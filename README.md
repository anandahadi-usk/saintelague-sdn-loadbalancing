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

### Prerequisites

```bash
# System dependencies
sudo apt install python3.8 python3-pip mininet openvswitch-switch

# Ryu SDN controller
pip install ryu==4.34 eventlet==0.33.3 msgpack==1.0.7
```

### Python dependencies

```bash
git clone https://github.com/anandahadi-usk/saintelague-sdn-loadbalancing.git
cd saintelague-sdn-loadbalancing
pip install -r requirements.txt
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
PYTHONPATH=. SUDO_PASS=your_password \
nohup python3 evaluation/run_experiment.py \
    --scenario all --runs 20 --yes \
    > logs/full_experiment.log 2>&1 &
```

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
