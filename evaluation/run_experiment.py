#!/usr/bin/env python3
# evaluation/run_experiment.py
"""
Experiment Runner
Runs all combinations of: scenarios × algorithms × runs
Uses sudo with SUDO_PASS env var.

Usage:
  cd /path/to/saintelague-sdn-loadbalancing
  PYTHONPATH=$(pwd) SUDO_PASS=yourpassword \
  nohup venv/bin/python3 evaluation/run_experiment.py \
    --scenario all --runs 20 --yes > logs/experiment.log 2>&1 &

  # Or single run:
  PYTHONPATH=$(pwd) SUDO_PASS=yourpassword \
  venv/bin/python3 evaluation/run_experiment.py \
    --scenario single_change --algo saintelague --runs 5
"""
import os
import sys
import time
import subprocess
import argparse
import signal
import shutil
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.experiment_config import ALGORITHMS, SCENARIOS

# ── Paths ────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Venv must be at project root — run setup.sh to create it
VENV_PYTHON  = os.path.join(PROJECT_ROOT, 'venv', 'bin', 'python3')
RYU_BIN      = os.path.join(PROJECT_ROOT, 'venv', 'bin', 'ryu-manager')

if not os.path.exists(VENV_PYTHON) or not os.path.exists(RYU_BIN):
    print(f"ERROR: venv not found at {PROJECT_ROOT}/venv/")
    print(f"Run first:  bash {PROJECT_ROOT}/setup.sh")
    sys.exit(1)
RESULTS_BASE = os.path.join(PROJECT_ROOT, 'results', 'raw')
LOGS_DIR     = os.path.join(PROJECT_ROOT, 'logs')

TRAFFIC_SCRIPTS = {
    "steady":           "mn_traffic/traffic/qos_steady_traffic.py",
    "single_change":    "mn_traffic/traffic/qos_single_change_traffic.py",
    "frequent_changes": "mn_traffic/traffic/qos_frequent_changes_traffic.py",
}

SCENARIO_DURATIONS = {
    "steady":           90,
    "single_change":    120,
    "frequent_changes": 150,
}


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def kill_existing():
    """Kill any leftover ryu-manager or mininet processes."""
    os.system("sudo pkill -f ryu-manager 2>/dev/null")
    os.system("sudo pkill -f iperf3 2>/dev/null")
    os.system("sudo mn --clean 2>/dev/null")
    time.sleep(2)


def run_single(scenario: str, algo: str, run_id: int, seed: int,
               sudo_pass: str) -> bool:
    """
    Run one experiment: start Ryu, run traffic, collect results.
    Returns True on success.
    """
    results_dir = os.path.join(RESULTS_BASE, f"{scenario}_{algo}_run{run_id:02d}")
    os.makedirs(results_dir, exist_ok=True)

    duration = SCENARIO_DURATIONS[scenario]
    log_file = os.path.join(LOGS_DIR, f"{scenario}_{algo}_run{run_id:02d}.log")

    log(f"Starting: scenario={scenario} algo={algo} run={run_id}")

    # ── Start Ryu controller ─────────────────────────────────────────────
    ryu_env = os.environ.copy()
    ryu_env.update({
        "ALGO":        algo,
        "RUN_ID":      str(run_id),
        "SCENARIO":    scenario,
        "RESULTS_DIR": results_dir,
        "PYTHONPATH":  PROJECT_ROOT,
    })
    ryu_cmd = [
        RYU_BIN,
        os.path.join(PROJECT_ROOT, "controller", "main_controller.py"),
        "--ofp-tcp-listen-port", "6653",
        "--wsapi-host", "127.0.0.1",
        "--wsapi-port", "8080",
        "--verbose",
    ]

    ryu_log = open(log_file, "w")
    ryu_proc = subprocess.Popen(
        ryu_cmd, env=ryu_env,
        stdout=ryu_log, stderr=subprocess.STDOUT,
    )

    # Wait for Ryu to be ready
    time.sleep(4)
    if ryu_proc.poll() is not None:
        log(f"ERROR: Ryu exited early for {scenario}/{algo}/run{run_id}")
        ryu_log.close()
        return False

    # ── Run traffic script (as sudo) ─────────────────────────────────────
    # Use "sudo -S env PYTHONPATH=..." to ensure PYTHONPATH reaches python3
    # (sudo strips env vars by default; -E may be blocked by sudoers)
    traffic_script = os.path.join(PROJECT_ROOT, TRAFFIC_SCRIPTS[scenario])
    traffic_cmd = [
        "sudo", "-S",
        "env", f"PYTHONPATH={PROJECT_ROOT}",
        sys.executable,
        traffic_script,
        "--duration",  str(duration),
        "--seed",      str(seed),
        "--algorithm", algo,
        "--run_id",    str(run_id),
        "--scenario",  scenario,
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = PROJECT_ROOT

    traffic_log = open(log_file, "a")
    traffic_proc = subprocess.Popen(
        traffic_cmd, env=env,
        stdin=subprocess.PIPE,
        stdout=traffic_log, stderr=subprocess.STDOUT,
    )
    if sudo_pass:
        traffic_proc.stdin.write(f"{sudo_pass}\n".encode())
        traffic_proc.stdin.flush()

    timeout = duration + 60  # generous timeout
    try:
        traffic_proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT: {scenario}/{algo}/run{run_id}")
        traffic_proc.kill()

    # ── Cleanup ──────────────────────────────────────────────────────────
    ryu_proc.terminate()
    try:
        ryu_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        ryu_proc.kill()

    ryu_log.close()
    traffic_log.close()

    kill_existing()

    # ── Verify output ────────────────────────────────────────────────────
    csv_file = os.path.join(
        results_dir,
        f"flow_decisions_{scenario}_{algo}_run{run_id:02d}.csv"
    )
    if os.path.exists(csv_file) and os.path.getsize(csv_file) > 200:
        import csv
        with open(csv_file) as f:
            rows = list(csv.reader(f))
        n_decisions = len(rows) - 1  # minus header
        log(f"OK: {scenario}/{algo}/run{run_id} — {n_decisions} flow decisions")
        return True
    else:
        log(f"WARN: {scenario}/{algo}/run{run_id} — CSV missing or empty")
        return False


def main():
    parser = argparse.ArgumentParser(description="Experiment Runner")
    parser.add_argument("--scenario", default="all",
                        choices=list(SCENARIOS.keys()) + ["all"])
    parser.add_argument("--algo", default="all",
                        choices=ALGORITHMS + ["all"])
    parser.add_argument("--runs",  type=int, default=20)
    parser.add_argument("--seed",  type=int, default=42)
    parser.add_argument("--yes",   action="store_true",
                        help="Skip confirmation prompt")
    args = parser.parse_args()

    sudo_pass = os.environ.get("SUDO_PASS", "")

    # Determine scenarios and algos to run
    scenarios = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    algos     = ALGORITHMS if args.algo == "all" else [args.algo]

    # Calculate total runs
    # S1: 15 runs (override if --runs given)
    run_counts = {
        "steady":           min(args.runs, SCENARIOS["steady"]["runs"]),
        "single_change":    args.runs,
        "frequent_changes": args.runs,
    }

    total = sum(run_counts[s] * len(algos) for s in scenarios)
    est_min = sum(
        run_counts[s] * len(algos) * (SCENARIO_DURATIONS[s] + 30) / 60
        for s in scenarios
    )

    log(f"Experiment Runner")
    log(f"Scenarios: {scenarios}")
    log(f"Algorithms: {algos}")
    log(f"Runs: {[run_counts[s] for s in scenarios]}")
    log(f"Total runs: {total}")
    log(f"Est. time: {est_min:.0f} minutes ({est_min/60:.1f} hours)")

    if not args.yes:
        ans = input("Proceed? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return

    os.makedirs(RESULTS_BASE, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)

    kill_existing()

    success = fail = 0
    start_time = time.time()

    for scenario in scenarios:
        n_runs = run_counts[scenario]
        for algo in algos:
            for run_id in range(1, n_runs + 1):
                seed = args.seed + run_id
                ok = run_single(scenario, algo, run_id, seed, sudo_pass)
                if ok:
                    success += 1
                else:
                    fail += 1
                    log(f"FAILED: {scenario}/{algo}/run{run_id} — retrying once")
                    time.sleep(5)
                    kill_existing()
                    ok2 = run_single(scenario, algo, run_id, seed + 100, sudo_pass)
                    if ok2:
                        success += 1
                        fail -= 1

    elapsed_min = (time.time() - start_time) / 60
    log(f"\n{'='*60}")
    log(f"DONE: {success} success, {fail} failed, {elapsed_min:.1f} min total")


if __name__ == "__main__":
    main()
