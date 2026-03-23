# Reproducibility Guide

## Environment

| Component | Version | Notes |
|-----------|---------|-------|
| OS | Ubuntu 22.04 LTS | Also tested on 20.04 |
| Python | 3.8.x | Required for Ryu compatibility |
| Mininet | 2.3.0 | Install via apt |
| Open vSwitch | 2.17+ | Install via apt |
| Ryu | 4.34 | Install via pip |
| OpenFlow | 1.3 | Protocol version |

## Step-by-Step Reproduction

### 1. System Setup

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch python3.8 python3-pip
sudo service openvswitch-switch start
```

### 2. Clone and Install

```bash
git clone https://github.com/anandahadielyas/saintelague-sdn-loadbalancing.git
cd saintelague-sdn-loadbalancing
python3.8 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Verify Installation

```bash
# Verify Mininet
sudo mn --test pingall

# Verify OVS
sudo ovs-vsctl show

# Verify Ryu
ryu-manager --version
```

### 4. Run Single Experiment

```bash
# Scenario S2, Sainte-Laguë, run 1
PYTHONPATH=. SUDO_PASS=your_password \
python3 evaluation/run_experiment.py \
    --algorithm saintelague \
    --scenario single_change \
    --run-id 1 \
    --seed 42
```

### 5. Run Full Experiment

```bash
PYTHONPATH=. SUDO_PASS=your_password \
nohup python3 evaluation/run_experiment.py \
    --scenario all --runs 20 --yes \
    > logs/full_experiment.log 2>&1 &

# Monitor progress
tail -f logs/full_experiment.log
```

### 6. Generate Figures

```bash
python3 docs/create_figures_p5.py
# Output: docs/figures_p5/*.png
```

### 7. Run Statistical Analysis

```bash
python3 evaluation/statistical_tests.py \
    --input results/processed/aggregated_mape.csv \
    --output results/processed/statistical_tests.csv
```

---

## Seeds Used

All 219 runs used deterministic seeds for reproducibility:

| Scenario | Runs | Seeds |
|----------|------|-------|
| S1 | 15/algo | 1–15 |
| S2 | 20/algo | 1–20 |
| S3 | 20/algo | 1–20 |

Seeds are fixed in `config/experiment_config.py`.

---

## Known Issues

1. **OVS daemon crash** (rare): If OVS crashes during S3, restart with
   `sudo service openvswitch-switch restart`. This accounts for the 1
   missing WLC-S3 run in our results.

2. **Port conflict**: If port 6653 is busy, kill existing Ryu instances:
   `pkill -f ryu-manager`

3. **Mininet cleanup**: After crash, run `sudo mn -c` before restarting.

---

## Hardware Used

| Component | Spec |
|-----------|------|
| CPU | Intel Core i7 (or equivalent) |
| RAM | 16 GB |
| OS | Ubuntu 22.04 LTS |
| Network | Loopback (emulated via Mininet) |

Results are hardware-independent due to Mininet's software emulation.
