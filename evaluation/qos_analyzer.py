#!/usr/bin/env python3
"""
P5 QoS Analyzer
Aggregates per-run QoS metrics from:
  - results/raw/qos_*/qos_metrics_*.csv    → latency, jitter, loss, throughput
  - results/raw/qos_*/flow_timing_*.csv    → flow_setup_ms
  - results/raw/qos_*/flow_decisions_*.csv → MAPE, JFI_c (distributional)

Outputs to results/processed/:
  - qos_summary.csv             — per-algorithm per-scenario summary
  - qos_prepost_comparison.csv  — QoS before vs after weight change (S2, S3)
  - qos_flow_timing.csv         — flow setup latency statistics

Usage:
  PYTHONPATH=$(pwd) venv/bin/python3 evaluation/qos_analyzer.py
"""
import os
import sys
import csv
import glob
import statistics
import math
from collections import defaultdict

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW  = os.path.join(BASE, "results", "raw")
OUT  = os.path.join(BASE, "results", "processed")
os.makedirs(OUT, exist_ok=True)

ALGOS     = ["saintelague", "wrr", "iwrr", "wlc"]
ALGO_LABELS = {"saintelague": "Sainte-Lague", "wrr": "WRR", "iwrr": "IWRR", "wlc": "WLC"}
SCENARIOS = ["steady", "single_change", "frequent_changes"]


def safe_mean(lst):
    lst = [x for x in lst if x is not None and not math.isnan(x)]
    return statistics.mean(lst) if lst else 0.0

def safe_std(lst):
    lst = [x for x in lst if x is not None and not math.isnan(x)]
    return statistics.stdev(lst) if len(lst) > 1 else 0.0

def safe_median(lst):
    lst = [x for x in lst if x is not None and not math.isnan(x)]
    return statistics.median(lst) if lst else 0.0

def percentile(lst, p):
    lst = sorted([x for x in lst if x is not None and not math.isnan(x)])
    if not lst:
        return 0.0
    k = (len(lst) - 1) * p / 100
    f = int(k)
    c = f + 1
    if c >= len(lst):
        return lst[-1]
    return lst[f] + (k - f) * (lst[c] - lst[f])


def load_qos_csv(path):
    """Load qos_metrics CSV, return list of dicts."""
    rows = []
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "seq":             int(row["seq"]),
                        "elapsed_s":       float(row["elapsed_s"]),
                        "throughput_mbps": float(row["throughput_mbps"]),
                        "latency_avg_ms":  float(row["latency_avg_ms"]),
                        "latency_min_ms":  float(row["latency_min_ms"]),
                        "latency_max_ms":  float(row["latency_max_ms"]),
                        "latency_mdev_ms": float(row["latency_mdev_ms"]),
                        "jitter_ms":       float(row["jitter_ms"]),
                        "packet_loss_pct": float(row["packet_loss_pct"]),
                        "retransmits":     int(row["retransmits"]),
                        "phase":           row["phase"],
                        "weight_change_event": int(row["weight_change_event"]),
                    })
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return rows


def load_timing_csv(path):
    """Load flow_timing CSV, return list of dicts."""
    rows = []
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "decision_num":   int(row["decision_num"]),
                        "flow_setup_ms":  float(row["flow_setup_ms"]),
                        "selected_server": int(row["selected_server"]),
                    })
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return rows


def load_flow_decisions_csv(path):
    """Load flow_decisions CSV, return list of dicts."""
    rows = []
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                try:
                    rows.append({
                        "elapsed_s":    float(row["elapsed_s"]),
                        "decision_num": int(row["decision_num"]),
                        "selected_server": int(row["selected_server"]),
                        "mape":         float(row["mape"]),
                        "jfi_c":        float(row["jfi_c"]),
                        "wc_event":     int(row["weight_change_event"]),
                        "phase":        row["phase"],
                    })
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return rows


def analyze_qos_run(results_dir, scenario, algo, run_id):
    """Analyze one QoS run, return summary dict."""
    prefix = f"qos_metrics_{scenario}_{algo}_run{run_id:02d}"
    timing_prefix = f"flow_timing_{scenario}_{algo}_run{run_id:02d}"
    flow_prefix = f"flow_decisions_{scenario}_{algo}_run{run_id:02d}"

    qos_files = glob.glob(os.path.join(results_dir, f"{prefix}*.csv"))
    timing_files = glob.glob(os.path.join(results_dir, f"{timing_prefix}*.csv"))
    flow_files = glob.glob(os.path.join(results_dir, f"{flow_prefix}*.csv"))

    qos_rows = load_qos_csv(qos_files[0]) if qos_files else []
    timing_rows = load_timing_csv(timing_files[0]) if timing_files else []
    flow_rows = load_flow_decisions_csv(flow_files[0]) if flow_files else []

    result = {
        "scenario": scenario, "algo": algo,
        "algo_label": ALGO_LABELS.get(algo, algo),
        "run_id": run_id,
        "n_qos_flows": len(qos_rows),
        "n_decisions": len(flow_rows),
        "n_timing": len(timing_rows),
    }

    # ── QoS metrics from iperf3 + ping ─────────────────────────────────
    if qos_rows:
        tput = [r["throughput_mbps"] for r in qos_rows]
        lat  = [r["latency_avg_ms"]  for r in qos_rows if r["latency_avg_ms"] > 0]
        jit  = [r["jitter_ms"]       for r in qos_rows if r["jitter_ms"] >= 0]
        loss = [r["packet_loss_pct"] for r in qos_rows]
        mdev = [r["latency_mdev_ms"] for r in qos_rows if r["latency_mdev_ms"] > 0]

        result.update({
            "throughput_mean":   safe_mean(tput),
            "throughput_std":    safe_std(tput),
            "throughput_min":    min(tput) if tput else 0,
            "throughput_max":    max(tput) if tput else 0,
            "latency_mean_ms":   safe_mean(lat),
            "latency_std_ms":    safe_std(lat),
            "latency_p50_ms":    safe_median(lat),
            "latency_p95_ms":    percentile(lat, 95),
            "latency_p99_ms":    percentile(lat, 99),
            "jitter_mean_ms":    safe_mean(jit),
            "jitter_std_ms":     safe_std(jit),
            "jitter_p95_ms":     percentile(jit, 95),
            "packet_loss_mean":  safe_mean(loss),
            "packet_loss_max":   max(loss) if loss else 0,
            "latency_mdev_mean": safe_mean(mdev),  # ping mdev ≈ jitter
        })

        # Pre/post weight change split (for S2, S3)
        pre  = [r for r in qos_rows if r["phase"] == "pre_change"]
        post = [r for r in qos_rows if r["phase"] == "post_change"]
        if pre and post:
            result["latency_pre_ms"]    = safe_mean([r["latency_avg_ms"] for r in pre if r["latency_avg_ms"] > 0])
            result["latency_post_ms"]   = safe_mean([r["latency_avg_ms"] for r in post if r["latency_avg_ms"] > 0])
            result["jitter_pre_ms"]     = safe_mean([r["jitter_ms"]      for r in pre])
            result["jitter_post_ms"]    = safe_mean([r["jitter_ms"]      for r in post])
            result["throughput_pre"]    = safe_mean([r["throughput_mbps"] for r in pre])
            result["throughput_post"]   = safe_mean([r["throughput_mbps"] for r in post])
            result["loss_pre_pct"]      = safe_mean([r["packet_loss_pct"] for r in pre])
            result["loss_post_pct"]     = safe_mean([r["packet_loss_pct"] for r in post])
        else:
            for k in ["latency_pre_ms", "latency_post_ms", "jitter_pre_ms", "jitter_post_ms",
                      "throughput_pre", "throughput_post", "loss_pre_pct", "loss_post_pct"]:
                result[k] = result.get("latency_mean_ms", 0) if "lat" in k else result.get("jitter_mean_ms", 0)
    else:
        for k in ["throughput_mean", "throughput_std", "throughput_min", "throughput_max",
                  "latency_mean_ms", "latency_std_ms", "latency_p50_ms", "latency_p95_ms",
                  "latency_p99_ms", "jitter_mean_ms", "jitter_std_ms", "jitter_p95_ms",
                  "packet_loss_mean", "packet_loss_max", "latency_mdev_mean",
                  "latency_pre_ms", "latency_post_ms", "jitter_pre_ms", "jitter_post_ms",
                  "throughput_pre", "throughput_post", "loss_pre_pct", "loss_post_pct"]:
            result[k] = 0.0

    # ── Flow setup latency ────────────────────────────────────────────
    if timing_rows:
        setup = [r["flow_setup_ms"] for r in timing_rows]
        result.update({
            "flow_setup_mean_ms": safe_mean(setup),
            "flow_setup_std_ms":  safe_std(setup),
            "flow_setup_p50_ms":  safe_median(setup),
            "flow_setup_p95_ms":  percentile(setup, 95),
            "flow_setup_p99_ms":  percentile(setup, 99),
            "flow_setup_max_ms":  max(setup) if setup else 0,
        })
    else:
        for k in ["flow_setup_mean_ms", "flow_setup_std_ms", "flow_setup_p50_ms",
                  "flow_setup_p95_ms", "flow_setup_p99_ms", "flow_setup_max_ms"]:
            result[k] = 0.0

    # ── Distributional metrics from flow_decisions ────────────────────
    if flow_rows:
        result["end_mape"]  = flow_rows[-1]["mape"]
        result["end_jfi_c"] = flow_rows[-1]["jfi_c"]
        result["n_flows"]   = flow_rows[-1]["decision_num"]
    else:
        result["end_mape"] = result["end_jfi_c"] = result["n_flows"] = 0

    return result


def aggregate_runs(run_results):
    """Given list of per-run dicts, compute mean±std across runs."""
    if not run_results:
        return {}
    keys = [k for k in run_results[0] if isinstance(run_results[0][k], (int, float))]
    out = {
        "scenario":   run_results[0]["scenario"],
        "algo":       run_results[0]["algo"],
        "algo_label": run_results[0]["algo_label"],
        "n_runs":     len(run_results),
    }
    for k in keys:
        vals = [r[k] for r in run_results if k in r]
        out[f"{k}_mean"] = safe_mean(vals)
        out[f"{k}_std"]  = safe_std(vals)
    return out


def main():
    print("=" * 60)
    print("P5 QoS Analyzer")
    print("=" * 60)

    all_run_results = []
    summary_rows = []

    for sc in SCENARIOS:
        for algo in ALGOS:
            # Find all QoS run directories for this (scenario, algo)
            pattern = os.path.join(RAW, f"qos_{sc}_{algo}_run*")
            run_dirs = sorted(glob.glob(pattern))

            if not run_dirs:
                print(f"  [SKIP] No QoS data found for {sc}/{algo}")
                continue

            print(f"\n  {sc} / {algo}: {len(run_dirs)} run(s)")
            run_results = []
            for d in run_dirs:
                run_id = int(d.split("run")[-1])
                r = analyze_qos_run(d, sc, algo, run_id)
                run_results.append(r)
                all_run_results.append(r)
                print(f"    run{run_id:02d}: tput={r['throughput_mean']:.3f} Mbps, "
                      f"lat={r['latency_mean_ms']:.2f} ms, "
                      f"jitter={r['jitter_mean_ms']:.4f} ms, "
                      f"loss={r['packet_loss_mean']:.4f}%, "
                      f"setup={r['flow_setup_mean_ms']:.2f} ms")

            agg = aggregate_runs(run_results)
            summary_rows.append(agg)

    # ── Write per-run QoS CSV ──────────────────────────────────────────
    if all_run_results:
        run_fields = list(all_run_results[0].keys())
        with open(os.path.join(OUT, "qos_per_run.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=run_fields)
            w.writeheader()
            w.writerows(all_run_results)
        print(f"\n  Saved: results/processed/qos_per_run.csv ({len(all_run_results)} rows)")

    # ── Write aggregated QoS summary CSV ─────────────────────────────
    if summary_rows:
        sum_fields = list(summary_rows[0].keys())
        with open(os.path.join(OUT, "qos_summary.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=sum_fields)
            w.writeheader()
            w.writerows(summary_rows)
        print(f"  Saved: results/processed/qos_summary.csv ({len(summary_rows)} rows)")

    # ── Print summary table ────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"{'Scenario':<20} {'Algorithm':<14} {'Tput(Mbps)':<14} {'Latency(ms)':<14} "
          f"{'Jitter(ms)':<12} {'Loss(%)':<10} {'Setup(ms)':<10}")
    print("-" * 80)
    for r in summary_rows:
        print(f"{r['scenario']:<20} {r['algo_label']:<14} "
              f"{r.get('throughput_mean_mean', 0):.3f}±{r.get('throughput_mean_std', 0):.3f}  "
              f"{r.get('latency_mean_ms_mean', 0):.2f}±{r.get('latency_mean_ms_std', 0):.2f}  "
              f"{r.get('jitter_mean_ms_mean', 0):.4f}±{r.get('jitter_mean_ms_std', 0):.4f}  "
              f"{r.get('packet_loss_mean_mean', 0):.4f}  "
              f"{r.get('flow_setup_mean_ms_mean', 0):.2f}")
    print("=" * 80)

    if not all_run_results:
        print("\nNo QoS data found. Run qos_experiment_runner.py first.")
        print("Command:")
        print("  PYTHONPATH=$(pwd) SUDO_PASS=admin venv/bin/python3 "
              "evaluation/qos_experiment_runner.py --scenario all --runs 5 --yes")


if __name__ == "__main__":
    main()
