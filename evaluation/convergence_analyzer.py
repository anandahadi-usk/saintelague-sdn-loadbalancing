#!/usr/bin/env python3
# evaluation/convergence_analyzer.py
"""
Convergence Analyzer
Reads flow_decisions CSV files and computes:
  1. MAPE trajectory (per flow, rolling over N-flow window)
  2. Recovery Time: flows and seconds to reach MAPE < threshold after weight change
  3. Cumulative Distribution Error (CDE): area under MAPE trajectory curve
  4. JFI_c trajectory

Outputs:
  - results/processed/convergence_{scenario}.csv  (per-run summary)
  - results/processed/mape_trajectory_{scenario}_{algo}.csv  (per-flow data)
"""
import os
import sys
import csv
import json
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.experiment_config import ALGORITHMS, SCENARIOS, CONVERGENCE_MAPE_THRESHOLD
from config.algo_config import ALGO_LABELS

PROJECT_ROOT   = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESULTS_RAW    = os.path.join(PROJECT_ROOT, "results", "raw")
RESULTS_PROC   = os.path.join(PROJECT_ROOT, "results", "processed")


def load_flow_decisions(scenario: str, algo: str, run_id: int) -> pd.DataFrame:
    """Load flow_decisions CSV for one run."""
    folder = os.path.join(RESULTS_RAW, f"{scenario}_{algo}_run{run_id:02d}")
    fname  = f"flow_decisions_{scenario}_{algo}_run{run_id:02d}.csv"
    fpath  = os.path.join(folder, fname)
    if not os.path.exists(fpath):
        return None
    try:
        df = pd.read_csv(fpath)
        df["elapsed_s"] = pd.to_numeric(df["elapsed_s"], errors="coerce")
        df["mape"]      = pd.to_numeric(df["mape"],      errors="coerce")
        df["jfi_c"]     = pd.to_numeric(df["jfi_c"],     errors="coerce")
        df["weight_change_event"] = df["weight_change_event"].astype(int)
        return df
    except Exception as e:
        print(f"  WARN: could not load {fpath}: {e}")
        return None


def find_weight_change_idx(df: pd.DataFrame) -> list:
    """Return list of row indices where weight_change_event==1 (first flow after change)."""
    return list(df.index[df["weight_change_event"] == 1])


def compute_recovery_metrics(df: pd.DataFrame, change_idx: int,
                              threshold: float = CONVERGENCE_MAPE_THRESHOLD) -> dict:
    """
    Compute recovery metrics after a weight change at change_idx.
    Returns:
      - recovery_flows: number of flows to reach MAPE < threshold (-1 if not reached)
      - recovery_time_s: seconds to reach MAPE < threshold (-1 if not reached)
      - mape_at_change: MAPE at the moment of weight change
      - mape_at_n50/n100/n200: MAPE after 50/100/200 post-change flows
      - cde: area under MAPE curve (flows 1..200 after change), normalized by 200
    """
    post = df.iloc[change_idx:].reset_index(drop=True)
    if len(post) == 0:
        return {}

    mape_at_change  = float(post.iloc[0]["mape"]) if len(post) > 0 else None
    t_change        = float(post.iloc[0]["elapsed_s"]) if len(post) > 0 else None

    # Recovery flows and time
    recovery_flows = -1
    recovery_time  = -1.0
    for i, row in post.iterrows():
        if row["mape"] < threshold:
            recovery_flows = i + 1  # 1-based
            recovery_time  = float(row["elapsed_s"]) - t_change if t_change else -1
            break

    # MAPE at checkpoints
    def mape_at_n(n):
        if len(post) > n - 1:
            return float(post.iloc[n - 1]["mape"])
        return float(post.iloc[-1]["mape"]) if len(post) > 0 else None

    # CDE: area under MAPE curve for first 200 post-change flows
    n_cde = min(200, len(post))
    cde   = float(np.trapz(post["mape"].iloc[:n_cde].values) / n_cde) if n_cde > 1 else None

    return {
        "mape_at_change":   round(mape_at_change, 4) if mape_at_change is not None else None,
        "recovery_flows":   recovery_flows,
        "recovery_time_s":  round(recovery_time, 2) if recovery_time >= 0 else -1,
        "mape_at_n10":      mape_at_n(10),
        "mape_at_n30":      mape_at_n(30),
        "mape_at_n50":      mape_at_n(50),
        "mape_at_n100":     mape_at_n(100),
        "mape_at_n200":     mape_at_n(200),
        "cde":              round(cde, 4) if cde is not None else None,
        "n_post_change":    len(post),
    }


def analyze_scenario(scenario: str, n_runs: int) -> pd.DataFrame:
    """Analyze all algorithms × runs for one scenario. Returns summary DataFrame."""
    os.makedirs(RESULTS_PROC, exist_ok=True)

    has_changes = len(SCENARIOS[scenario]["weight_changes"]) > 0
    records = []

    for algo in ALGORITHMS:
        label = ALGO_LABELS.get(algo, algo)
        for run_id in range(1, n_runs + 1):
            df = load_flow_decisions(scenario, algo, run_id)
            if df is None or len(df) == 0:
                continue

            n_flows  = len(df)
            end_mape = float(df.iloc[-1]["mape"])
            end_jfi  = float(df.iloc[-1]["jfi_c"])
            end_time = float(df.iloc[-1]["elapsed_s"])

            rec = {
                "scenario": scenario,
                "algorithm": algo,
                "algo_label": label,
                "run_id":  run_id,
                "n_flows": n_flows,
                "end_mape": round(end_mape, 4),
                "end_jfi_c": round(end_jfi, 6),
                "duration_s": round(end_time, 2),
            }

            if has_changes:
                change_indices = find_weight_change_idx(df)
                for ci, cidx in enumerate(change_indices):
                    metrics = compute_recovery_metrics(df, cidx)
                    for k, v in metrics.items():
                        rec[f"change{ci+1}_{k}"] = v

            records.append(rec)

    if not records:
        print(f"  No data for scenario={scenario}")
        return pd.DataFrame()

    result_df = pd.DataFrame(records)
    out_path  = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
    result_df.to_csv(out_path, index=False)
    print(f"Saved: {out_path}  ({len(result_df)} rows)")
    return result_df


def build_mape_trajectories(scenario: str, n_runs: int, max_post_flows: int = 200):
    """
    Build MAPE trajectory arrays for plotting.
    Returns dict: algo → np.array of shape (n_runs, max_post_flows) post-change MAPE.
    """
    if not SCENARIOS[scenario]["weight_changes"]:
        return {}

    trajectories = {algo: [] for algo in ALGORITHMS}

    for algo in ALGORITHMS:
        for run_id in range(1, n_runs + 1):
            df = load_flow_decisions(scenario, algo, run_id)
            if df is None:
                continue
            change_indices = find_weight_change_idx(df)
            if not change_indices:
                continue
            cidx = change_indices[0]  # first weight change
            post = df.iloc[cidx:]["mape"].values
            # Pad or trim to max_post_flows
            if len(post) >= max_post_flows:
                traj = post[:max_post_flows]
            else:
                traj = np.pad(post, (0, max_post_flows - len(post)),
                              mode="edge")
            trajectories[algo].append(traj)

    # Convert to numpy arrays
    result = {}
    for algo, trajs in trajectories.items():
        if trajs:
            result[algo] = np.array(trajs)  # shape (n_runs, max_post_flows)

    # Save trajectory CSV for each algo
    for algo, arr in result.items():
        mean = arr.mean(axis=0)
        std  = arr.std(axis=0)
        out_df = pd.DataFrame({
            "post_change_flow": range(1, max_post_flows + 1),
            "mape_mean": np.round(mean, 4),
            "mape_std":  np.round(std, 4),
        })
        out_path = os.path.join(RESULTS_PROC, f"mape_trajectory_{scenario}_{algo}.csv")
        out_df.to_csv(out_path, index=False)
        print(f"Saved trajectory: {out_path}")

    return result


def print_summary(df: pd.DataFrame, scenario: str):
    """Print a concise summary table."""
    if df.empty:
        return
    print(f"\n{'='*70}")
    print(f"  SCENARIO: {scenario.upper()}")
    print(f"{'='*70}")

    has_change = any("change1_recovery_flows" in c for c in df.columns)

    for algo in ALGORITHMS:
        sub = df[df["algorithm"] == algo]
        if sub.empty:
            continue
        label = ALGO_LABELS.get(algo, algo)
        n = len(sub)
        print(f"\n  [{label}] n={n} runs")
        print(f"    End MAPE:  {sub['end_mape'].mean():.3f} ± {sub['end_mape'].std():.3f} %")
        print(f"    End JFI_c: {sub['end_jfi_c'].mean():.4f} ± {sub['end_jfi_c'].std():.4f}")

        if has_change and "change1_recovery_flows" in sub.columns:
            rf = sub["change1_recovery_flows"]
            rt = sub["change1_recovery_time_s"]
            cde = sub.get("change1_cde", pd.Series([None]*n))
            converged = rf[rf > 0]
            print(f"    Recovery (change1):")
            print(f"      Flows to MAPE<5%: "
                  f"{converged.mean():.1f} ± {converged.std():.1f}"
                  f"  (converged: {len(converged)}/{n})")
            print(f"      Time to MAPE<5%:  "
                  f"{rt[rt>0].mean():.1f} ± {rt[rt>0].std():.1f} s")
            if "change1_cde" in sub.columns:
                print(f"      CDE (AUC/200):    "
                      f"{sub['change1_cde'].mean():.3f} ± {sub['change1_cde'].std():.3f}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Convergence Analyzer")
    parser.add_argument("--scenario", default="all",
                        choices=list(SCENARIOS.keys()) + ["all"])
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()

    scenarios = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    run_counts = {
        "steady":           15,
        "single_change":    args.runs,
        "frequent_changes": args.runs,
    }

    for scenario in scenarios:
        print(f"\nAnalyzing scenario: {scenario}")
        df = analyze_scenario(scenario, run_counts[scenario])
        print_summary(df, scenario)
        if SCENARIOS[scenario]["weight_changes"]:
            build_mape_trajectories(scenario, run_counts[scenario])


if __name__ == "__main__":
    main()
