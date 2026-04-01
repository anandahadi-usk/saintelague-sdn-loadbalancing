#!/usr/bin/env python3
# evaluation/statistical_tests.py
"""
Statistical Tests
Pipeline: Shapiro-Wilk normality pre-test → Mann-Whitney U →
          Benjamini-Hochberg FDR correction → Cliff's delta effect size.

Primary metric: recovery_flows and CDE (convergence quality).
Secondary: end_mape, end_jfi_c.

Outputs:
  results/processed/statistical_results_{scenario}.csv  — per-scenario tests
  results/processed/statistical_results_all.csv         — combined (BH-FDR applied)
  results/processed/normality_tests.csv                 — Shapiro-Wilk results
"""
import os
import sys
import itertools
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.experiment_config import ALGORITHMS, SCENARIOS
from config.algo_config import ALGO_LABELS

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESULTS_PROC = os.path.join(PROJECT_ROOT, "results", "processed")


def run_normality_tests(scenarios: list) -> pd.DataFrame:
    """
    Shapiro-Wilk normality test for each algorithm × metric × scenario.
    Returns DataFrame saved to results/processed/normality_tests.csv.
    Justifies non-parametric Mann-Whitney U when H0 (normality) is rejected.
    """
    records = []
    for scenario in scenarios:
        conv_path = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
        if not os.path.exists(conv_path):
            continue
        df = pd.read_csv(conv_path)
        has_changes = bool(SCENARIOS[scenario]["weight_changes"])
        test_metrics = (
            ["change1_recovery_flows", "change1_cde", "end_mape"]
            if has_changes else ["end_mape"]
        )
        for metric in test_metrics:
            if metric not in df.columns:
                continue
            for algo in ALGORITHMS:
                x = df[df["algorithm"] == algo][metric].dropna().values
                if len(x) < 3:
                    continue
                try:
                    W, p_sw = stats.shapiro(x)
                except Exception:
                    W, p_sw = float("nan"), float("nan")
                records.append({
                    "scenario":          scenario,
                    "algorithm":         algo,
                    "metric":            metric,
                    "n":                 len(x),
                    "shapiro_W":         round(float(W),   4),
                    "shapiro_p":         round(float(p_sw), 6),
                    "normality_rejected": bool(p_sw < 0.05),
                })

    result_df = pd.DataFrame(records)
    if not result_df.empty:
        out_path = os.path.join(RESULTS_PROC, "normality_tests.csv")
        result_df.to_csv(out_path, index=False)
        n_rejected = result_df["normality_rejected"].sum()
        n_total    = len(result_df)
        print(f"\nShapiro-Wilk: {n_rejected}/{n_total} distributions reject normality "
              f"(W range {result_df['shapiro_W'].min():.3f}–"
              f"{result_df['shapiro_W'].max():.3f})")
        print(f"  → Non-parametric Mann-Whitney U is justified.")
        print(f"  Saved: {out_path}")
    return result_df


def cliff_delta(x, y):
    """Cliff's delta effect size between two samples."""
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return 0.0
    greater = sum(xi > yj for xi in x for yj in y)
    less    = sum(xi < yj for xi in x for yj in y)
    return (greater - less) / (n1 * n2)


def interpret_delta(d):
    """Classify effect size magnitude."""
    ad = abs(d)
    if   ad < 0.147: return "negligible"
    elif ad < 0.330: return "small"
    elif ad < 0.474: return "medium"
    else:            return "large"


def run_tests(scenario: str) -> pd.DataFrame:
    """Run all pairwise tests for a scenario. Returns results DataFrame."""
    conv_path = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
    if not os.path.exists(conv_path):
        print(f"  Missing: {conv_path}")
        return pd.DataFrame()

    df = pd.read_csv(conv_path)
    has_changes = bool(SCENARIOS[scenario]["weight_changes"])

    # Metrics to test
    metrics_steady = ["end_mape", "end_jfi_c"]
    metrics_change = ["change1_recovery_flows", "change1_recovery_time_s",
                      "change1_cde", "change1_mape_at_n50", "change1_mape_at_n100",
                      "change1_mape_at_n200", "end_mape"]

    test_metrics = metrics_change if has_changes else metrics_steady

    # Compare SL vs each baseline (primary), then all pairs
    pairs = []
    sl = "saintelague"
    baselines = [a for a in ALGORITHMS if a != sl]
    for b in baselines:
        pairs.append((sl, b))  # SL vs baseline
    # Also all other pairs
    for a1, a2 in itertools.combinations(ALGORITHMS, 2):
        if (a1, a2) not in pairs and (a2, a1) not in pairs:
            pairs.append((a1, a2))

    records = []
    for metric in test_metrics:
        if metric not in df.columns:
            continue
        for a1, a2 in pairs:
            x = df[df["algorithm"] == a1][metric].dropna().values
            y = df[df["algorithm"] == a2][metric].dropna().values
            if len(x) < 3 or len(y) < 3:
                continue
            try:
                stat, p = stats.mannwhitneyu(x, y, alternative="two-sided")
            except Exception:
                continue
            d     = cliff_delta(list(x), list(y))
            label = interpret_delta(d)

            records.append({
                "scenario":    scenario,
                "metric":      metric,
                "algo_1":      a1,
                "algo_2":      a2,
                "label_1":     ALGO_LABELS.get(a1, a1),
                "label_2":     ALGO_LABELS.get(a2, a2),
                "mean_1":      round(float(np.mean(x)), 4),
                "std_1":       round(float(np.std(x)),  4),
                "mean_2":      round(float(np.mean(y)), 4),
                "std_2":       round(float(np.std(y)),  4),
                "p_value_raw": round(float(p), 6),
                "p_value":     round(float(p), 6),   # updated below with BH-FDR
                "cliff_delta": round(float(d), 4),
                "effect_size": label,
                "significant": False,                 # updated below
                "n1":          len(x),
                "n2":          len(y),
            })

    if not records:
        return pd.DataFrame()

    # ── Benjamini-Hochberg FDR correction across all comparisons ──────────────
    raw_pvals = [r["p_value_raw"] for r in records]
    reject, pvals_adj, _, _ = multipletests(raw_pvals, method="fdr_bh", alpha=0.05)
    for i, rec in enumerate(records):
        rec["p_value"]    = round(float(pvals_adj[i]), 6)
        rec["significant"] = bool(reject[i])

    result_df = pd.DataFrame(records)
    # Drop helper column — keep only BH-FDR adjusted p_value
    result_df = result_df.drop(columns=["p_value_raw"])

    out_path = os.path.join(RESULTS_PROC, f"statistical_results_{scenario}.csv")
    result_df.to_csv(out_path, index=False)
    print(f"Saved: {out_path}  ({len(result_df)} comparisons, "
          f"{result_df['significant'].sum()} significant after BH-FDR)")

    # Print SL vs baselines for primary metrics
    sl_results = result_df[result_df["algo_1"] == "saintelague"]
    if not sl_results.empty:
        print(f"\n  Sainte-Laguë vs baselines ({scenario}):")
        for _, row in sl_results.iterrows():
            sig_mark = "* " if row["significant"] else "  "
            print(f"  {sig_mark}{row['metric']:35s} vs {row['label_2']:15s} "
                  f"p_adj={row['p_value']:.4f}  δ={row['cliff_delta']:+.3f} "
                  f"({row['effect_size']})")

    return result_df


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Statistical Tests")
    parser.add_argument("--scenario", default="all",
                        choices=list(SCENARIOS.keys()) + ["all"])
    args = parser.parse_args()

    scenarios = list(SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]

    # Step 1: Shapiro-Wilk normality pre-test
    print("=" * 60)
    print("Step 1: Shapiro-Wilk Normality Pre-Test")
    print("=" * 60)
    run_normality_tests(scenarios)

    # Step 2: Mann-Whitney U + BH-FDR + Cliff's delta
    print("\n" + "=" * 60)
    print("Step 2: Mann-Whitney U + BH-FDR + Cliff's delta")
    print("=" * 60)
    all_results = []
    for scenario in scenarios:
        print(f"\nRunning tests for: {scenario}")
        df = run_tests(scenario)
        if not df.empty:
            all_results.append(df)

    if all_results:
        combined = pd.concat(all_results, ignore_index=True)
        out = os.path.join(RESULTS_PROC, "statistical_results_all.csv")
        combined.to_csv(out, index=False)
        sig = combined[combined["significant"]]
        print(f"\nTotal: {len(combined)} comparisons, "
              f"{len(sig)} significant (p<0.05)")
        # Show SL advantages
        sl_sig = sig[sig["algo_1"] == "saintelague"]
        print(f"SL significant advantages: {len(sl_sig)}")
        for _, row in sl_sig.iterrows():
            direction = "LOWER" if row["cliff_delta"] < 0 else "HIGHER"
            print(f"  {row['scenario']}/{row['metric']}: "
                  f"SL {direction} than {row['label_2']}  "
                  f"p={row['p_value']:.4f}  δ={row['cliff_delta']:+.3f}")


if __name__ == "__main__":
    main()
