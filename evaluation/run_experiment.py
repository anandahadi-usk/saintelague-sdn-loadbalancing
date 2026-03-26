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


def _sudo(cmd: str, sudo_pass: str = "") -> int:
    """
    Run a shell command with sudo, passing the password via stdin.
    Returns the exit code (0 = success). Suppresses stderr.
    """
    if sudo_pass:
        full = f"echo {sudo_pass!r} | sudo -S {cmd} 2>/dev/null"
    else:
        full = f"sudo {cmd} 2>/dev/null"
    return os.system(full)


def kill_existing(sudo_pass: str = ""):
    """
    Kill leftover processes and verify cleanup before next run.

    Steps:
      1. Kill ryu-manager, iperf3, and lingering traffic scripts (with password)
      2. Clean Mininet state via mn --clean
      3. Fix file ownership: chown results and logs back to current user
      4. Wait for port 6653 to be released (up to 10 s)

    Safe to call multiple times. Pass sudo_pass for reliable cleanup.
    """
    # Step 1: Kill by process name (catches ryu-manager binary)
    _sudo("pkill -f ryu-manager",    sudo_pass)
    _sudo("pkill -9 -f ryu-manager", sudo_pass)

    # Step 2: Kill by port number — most reliable, catches Ryu started as
    # "python3 /path/ryu-manager" where process name is just "python3"
    _sudo("fuser -k 6653/tcp 2>/dev/null || true", sudo_pass)

    # Step 3: Kill iperf3 and lingering traffic scripts
    _sudo("pkill -9 -f iperf3", sudo_pass)
    _sudo("pkill -f 'normal_traffic\\|bursty_traffic\\|flash_crowd\\|steady_traffic'",
          sudo_pass)

    # Step 4: Mininet cleanup
    _sudo("mn --clean", sudo_pass)
    time.sleep(2)

    # Step 5: Fix file ownership (sudo creates root-owned files)
    _current_user = os.getenv('USER') or os.getenv('LOGNAME') or \
                    subprocess.getoutput("id -un").strip() or "root"
    _sudo(f"chown -R {_current_user} {RESULTS_BASE}", sudo_pass)
    _sudo(f"chown -R {_current_user} {LOGS_DIR}",    sudo_pass)

    # Step 6: Verify port 6653 is actually free before returning
    import socket as _socket
    for _attempt in range(15):
        # First try fuser again if port still occupied
        if _attempt > 0 and _attempt % 3 == 0:
            _sudo("fuser -k 6653/tcp 2>/dev/null || true", sudo_pass)
        try:
            _s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            _s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            _s.bind(("127.0.0.1", 6653))
            _s.close()
            break   # port is free
        except OSError:
            time.sleep(1)
    else:
        log("WARN: Port 6653 may still be in use — proceeding anyway")


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

    # Wait for Ryu to be ready — poll until port 6653 is listening (up to 15 s)
    import socket as _sock
    ryu_ready = False
    for _ in range(15):
        time.sleep(1)
        if ryu_proc.poll() is not None:
            log(f"ERROR: Ryu exited early for {scenario}/{algo}/run{run_id}")
            ryu_log.close()
            return False
        try:
            with _sock.create_connection(("127.0.0.1", 6653), timeout=0.5):
                ryu_ready = True
                break
        except OSError:
            pass   # not ready yet

    if not ryu_ready:
        log(f"ERROR: Ryu not listening on port 6653 after 15s — {scenario}/{algo}/run{run_id}")
        ryu_proc.kill()
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
        # Traffic process runs as root (via sudo -S) so unprivileged kill()
        # raises PermissionError. Use sudo kill instead.
        try:
            traffic_proc.kill()
        except PermissionError:
            # Root process — must use sudo to kill it
            _sudo(f"kill -9 {traffic_proc.pid}", sudo_pass)
            try:
                traffic_proc.wait(timeout=5)
            except Exception:
                pass

    # ── Cleanup ──────────────────────────────────────────────────────────
    # Ryu runs without sudo so terminate() works directly
    try:
        ryu_proc.terminate()
        ryu_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            ryu_proc.kill()
        except Exception:
            _sudo(f"kill -9 {ryu_proc.pid}", sudo_pass)
    except Exception:
        pass

    try:
        ryu_log.close()
    except Exception:
        pass
    try:
        traffic_log.close()
    except Exception:
        pass

    kill_existing(sudo_pass)

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
        # Detailed diagnostic to help identify root cause
        if not os.path.exists(csv_file):
            log(f"WARN: {scenario}/{algo}/run{run_id} — CSV not found at {csv_file}")
            log(f"      Likely cause: Ryu failed to start (port conflict) or used wrong RESULTS_DIR")
            # Check if file landed in controller's fallback path
            _tmp_fallback = os.path.join(
                os.environ.get("TMPDIR", "/tmp"), "p5_results",
                f"flow_decisions_{scenario}_{algo}_run{run_id:02d}.csv")
            if os.path.exists(_tmp_fallback):
                log(f"      Found in fallback {_tmp_fallback} — RESULTS_DIR env not set correctly")
        else:
            size = os.path.getsize(csv_file)
            log(f"WARN: {scenario}/{algo}/run{run_id} — CSV empty ({size} bytes)")
            log(f"      Likely cause: Mininet did not connect to controller, or traffic crashed early")
            log(f"      Check log: {log_file}")
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

    kill_existing(sudo_pass)

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
                    kill_existing(sudo_pass)
                    ok2 = run_single(scenario, algo, run_id, seed + 100, sudo_pass)
                    if ok2:
                        success += 1
                        fail -= 1

    elapsed_min = (time.time() - start_time) / 60
    log(f"\n{'='*60}")
    log(f"DONE: {success} success, {fail} failed, {elapsed_min:.1f} min total")


if __name__ == "__main__":
    main()
