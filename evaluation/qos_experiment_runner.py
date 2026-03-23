#!/usr/bin/env python3
"""
QoS Experiment Runner
Runs focused QoS experiments (5 runs × 4 algorithms × 3 scenarios = 60 total).
Collects: throughput, latency, jitter, packet loss, flow_setup_ms.

Usage:
  PYTHONPATH=$(pwd) SUDO_PASS=your_sudo_password venv/bin/python3 evaluation/qos_experiment_runner.py \
      --scenario all --runs 5 --yes
"""
import os
import sys
import time
import subprocess
import argparse
import signal
import shutil

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE)

ALGOS     = ["saintelague", "wrr", "iwrr", "wlc"]
SCENARIOS = {
    # duration extended so each 8s/round yields at least 8-10 QoS measurements
    "steady":           {"duration": 100, "traffic": "qos_steady_traffic",            "runs": 5},
    "single_change":    {"duration": 140, "traffic": "qos_single_change_traffic",     "runs": 5},
    "frequent_changes": {"duration": 165, "traffic": "qos_frequent_changes_traffic",  "runs": 5},
}
RESULTS_BASE = os.path.join(BASE, "results", "raw")
LOGS_DIR     = os.path.join(BASE, "logs", "qos")
VENV_PYTHON  = os.path.join(BASE, "venv", "bin", "python3")
RYU_MANAGER  = os.path.join(BASE, "venv", "bin", "ryu-manager")

os.makedirs(LOGS_DIR, exist_ok=True)


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def kill_existing():
    os.system("pkill -9 -f ryu-manager 2>/dev/null; sleep 1")
    os.system("sudo mn --clean 2>/dev/null; sleep 1")


def start_controller(algo: str, run_id: int, scenario: str, results_dir: str,
                     sudo_pass: str) -> subprocess.Popen:
    env = os.environ.copy()
    env.update({
        "ALGO":        algo,
        "RUN_ID":      str(run_id),
        "SCENARIO":    scenario,
        "RESULTS_DIR": results_dir,
        "PYTHONPATH":  BASE,
    })
    log_file = os.path.join(LOGS_DIR, f"ctrl_{scenario}_{algo}_run{run_id:02d}.log")
    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            [RYU_MANAGER,
             "controller/main_controller.py",
             "--ofp-tcp-listen-port", "6653",
             "--wsapi-host", "127.0.0.1",
             "--wsapi-port", "8080"],
            env=env, cwd=BASE,
            stdout=lf, stderr=lf,
        )
    time.sleep(5)  # wait for Ryu to start
    return proc


def run_traffic(algo: str, run_id: int, scenario: str, results_dir: str,
                duration: int, traffic_module: str, sudo_pass: str) -> bool:
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE

    log_file = os.path.join(LOGS_DIR, f"traffic_{scenario}_{algo}_run{run_id:02d}.log")

    cmd = [
        "sudo", "-S",
        VENV_PYTHON, "-m",
        f"mn_traffic.traffic.{traffic_module}",
        "--algorithm", algo,
        "--run_id",    str(run_id),
        "--scenario",  scenario,
        "--duration",  str(duration),
        "--seed",      str(run_id * 100 + 7),
        "--results_dir", results_dir,
    ]
    with open(log_file, "w") as lf:
        proc = subprocess.Popen(
            cmd, env=env, cwd=BASE,
            stdin=subprocess.PIPE, stdout=lf, stderr=lf,
        )
        try:
            proc.communicate(input=(sudo_pass + "\n").encode(),
                             timeout=duration + 60)
        except subprocess.TimeoutExpired:
            proc.kill()
            log(f"  [TIMEOUT] {scenario} {algo} run{run_id:02d}")
            return False
    return proc.returncode == 0


def run_one(scenario: str, algo: str, run_id: int, cfg: dict, sudo_pass: str) -> bool:
    results_dir = os.path.join(RESULTS_BASE, f"qos_{scenario}_{algo}_run{run_id:02d}")
    os.makedirs(results_dir, exist_ok=True)

    log(f"  Starting QoS run: {scenario} / {algo} / run{run_id:02d}")

    # Clean up
    kill_existing()
    time.sleep(2)

    # Start controller
    ctrl = start_controller(algo, run_id, scenario, results_dir, sudo_pass)
    try:
        ok = run_traffic(algo, run_id, scenario, results_dir,
                         cfg["duration"], cfg["traffic"], sudo_pass)
    finally:
        ctrl.terminate()
        try:
            ctrl.wait(timeout=5)
        except subprocess.TimeoutExpired:
            ctrl.kill()

    time.sleep(2)
    kill_existing()

    if ok:
        # Check for QoS CSV output
        qos_files = [f for f in os.listdir(results_dir) if f.startswith("qos_metrics")]
        flow_files = [f for f in os.listdir(results_dir) if f.startswith("flow_timing")]
        log(f"  [OK] QoS CSV: {len(qos_files)} file(s), flow_timing: {len(flow_files)} file(s)")
    else:
        log(f"  [FAIL] {scenario} {algo} run{run_id:02d}")

    return ok


def main():
    parser = argparse.ArgumentParser(description="QoS Experiment Runner")
    parser.add_argument("--scenario", default="all",
                        choices=["all", "steady", "single_change", "frequent_changes"])
    parser.add_argument("--algo", default="all")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    sudo_pass = os.environ.get("SUDO_PASS", "")
    if not sudo_pass:
        print("ERROR: Set SUDO_PASS environment variable.")
        sys.exit(1)

    scenarios = [args.scenario] if args.scenario != "all" else list(SCENARIOS.keys())
    algos     = [args.algo]     if args.algo     != "all" else ALGOS

    total = sum(args.runs for _ in scenarios for _ in algos)
    log(f"QoS Experiment Runner")
    log(f"Scenarios: {scenarios}")
    log(f"Algorithms: {algos}")
    log(f"Runs per combo: {args.runs}")
    log(f"Total runs: {total}")
    log(f"Est. time: ~{total * 3.5 / 60:.1f} hours")

    if not args.yes:
        confirm = input("Start? [y/N] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

    done = 0
    failed = 0
    t_start = time.time()

    for sc in scenarios:
        cfg = SCENARIOS[sc].copy()
        cfg["runs"] = args.runs
        for algo in algos:
            for run_id in range(1, args.runs + 1):
                ok = run_one(sc, algo, run_id, cfg, sudo_pass)
                done += 1
                if not ok:
                    failed += 1
                elapsed_min = (time.time() - t_start) / 60
                log(f"Progress: {done}/{total} ({done/total*100:.0f}%) | "
                    f"elapsed={elapsed_min:.1f}m | failed={failed}")

    log(f"\nQoS experiments complete: {done - failed}/{done} successful")
    log(f"Results in: {RESULTS_BASE}/qos_*/")


if __name__ == "__main__":
    main()
