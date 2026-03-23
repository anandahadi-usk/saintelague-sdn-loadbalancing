#!/usr/bin/env python3
"""
P5 QoS Publication Figures (300 DPI, IEEE-standard)
Reads from results/processed/qos_*.csv and results/raw/qos_*/
Generates 6 figures in docs/figures_p5/:
  fig_qos1_throughput.png  — throughput comparison (bar + CI)
  fig_qos2_latency.png     — latency CDF per algorithm (all scenarios)
  fig_qos3_jitter.png      — jitter comparison (bar)
  fig_qos4_loss.png        — packet loss comparison
  fig_qos5_setup.png       — flow setup latency (bar + CDF)
  fig_qos6_prepost.png     — pre/post weight-change QoS delta (S2)

Usage:
  PYTHONPATH=$(pwd) venv/bin/python3 evaluation/plot_qos.py
"""
import os, sys, csv, glob, statistics, math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

BASE   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RAW    = os.path.join(BASE, "results", "raw")
PROC   = os.path.join(BASE, "results", "processed")
FIGDIR = os.path.join(BASE, "docs", "figures_p5")
os.makedirs(FIGDIR, exist_ok=True)

# ── Style ────────────────────────────────────────────────────────────────────
ALGO_KEYS   = ["saintelague", "wrr", "iwrr", "wlc"]
ALGO_LABELS = ["Sainte-Laguë", "WRR", "IWRR", "WLC"]
ALGO_COLORS = ["#1565C0", "#C62828", "#2E7D32", "#E65100"]
ALGO_MARKERS= ["o", "s", "^", "D"]
SCENARIOS   = ["steady", "single_change", "frequent_changes"]
SC_LABELS   = ["S1: Steady State", "S2: Single Change", "S3: Frequent Changes"]

plt.rcParams.update({
    "font.family":    "DejaVu Serif",
    "font.size":      10,
    "axes.titlesize": 10,
    "axes.labelsize": 10,
    "legend.fontsize": 8.5,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "lines.linewidth": 1.8,
    "axes.grid":      True,
    "grid.alpha":     0.3,
    "figure.dpi":     100,
})


def load_qos_summary():
    """Load qos_summary.csv → dict keyed by (scenario, algo)."""
    path = os.path.join(PROC, "qos_summary.csv")
    data = {}
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                k = (row["scenario"], row["algo"])
                data[k] = {kk: float(vv) if vv else 0.0
                           for kk, vv in row.items() if kk not in ("scenario","algo","algo_label")}
                data[k]["algo_label"] = row["algo_label"]
    except FileNotFoundError:
        print(f"  [WARN] {path} not found — using synthetic demo data for figure layout")
    return data


def load_per_run():
    """Load qos_per_run.csv → list of dicts."""
    path = os.path.join(PROC, "qos_per_run.csv")
    rows = []
    try:
        with open(path) as f:
            for row in csv.DictReader(f):
                d = {}
                for k, v in row.items():
                    try:
                        d[k] = float(v)
                    except ValueError:
                        d[k] = v
                rows.append(d)
    except FileNotFoundError:
        pass
    return rows


def load_flow_timing():
    """Load all flow_timing CSVs from raw QoS runs."""
    data = {k: [] for k in ALGO_KEYS}
    for algo in ALGO_KEYS:
        pattern = os.path.join(RAW, f"qos_*_{algo}_run*", f"flow_timing_*.csv")
        for fpath in glob.glob(pattern):
            try:
                with open(fpath) as f:
                    for row in csv.DictReader(f):
                        v = float(row["flow_setup_ms"])
                        if 0 < v < 500:  # filter outliers
                            data[algo].append(v)
            except Exception:
                pass
    return data


def load_qos_metrics_all():
    """Load all qos_metrics CSVs, grouped by (scenario, algo)."""
    data = {}
    for sc in SCENARIOS:
        for algo in ALGO_KEYS:
            key = (sc, algo)
            data[key] = []
            pattern = os.path.join(RAW, f"qos_{sc}_{algo}_run*", f"qos_metrics_*.csv")
            for fpath in glob.glob(pattern):
                try:
                    with open(fpath) as f:
                        for row in csv.DictReader(f):
                            data[key].append({
                                "latency_avg_ms":  float(row["latency_avg_ms"]),
                                "jitter_ms":       float(row["jitter_ms"]),
                                "throughput_mbps": float(row["throughput_mbps"]),
                                "packet_loss_pct": float(row["packet_loss_pct"]),
                                "phase":           row["phase"],
                            })
                except Exception:
                    pass
    return data


# ── Helpers ──────────────────────────────────────────────────────────────────
def safe_get(d, key, scenario, algo, default=0.0):
    return d.get((scenario, algo), {}).get(key, default)

def bar_group(ax, values, errors, labels, colors, ylabel, title, xtick_labels):
    x = np.arange(len(xtick_labels))
    w = 0.18
    for i, (algo_label, color) in enumerate(zip(labels, colors)):
        vals = [values[i][j] for j in range(len(xtick_labels))]
        errs = [errors[i][j] for j in range(len(xtick_labels))]
        ax.bar(x + (i - 1.5) * w, vals, w, yerr=errs,
               label=algo_label, color=color, capsize=3, alpha=0.85, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(xtick_labels, fontsize=8.5)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 1 — Throughput Comparison
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos1_throughput(summary, per_run):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=False)

    for si, (sc, sc_label) in enumerate(zip(SCENARIOS, SC_LABELS)):
        ax = axes[si]
        algo_means, algo_stds = [], []
        for algo in ALGO_KEYS:
            vals = [r["throughput_mean"] for r in per_run
                    if r.get("scenario") == sc and r.get("algo") == algo]
            algo_means.append(statistics.mean(vals) if vals else safe_get(summary, "throughput_mean_mean", sc, algo))
            algo_stds.append( statistics.stdev(vals) if len(vals) > 1 else 0.0)

        x = np.arange(len(ALGO_KEYS))
        bars = ax.bar(x, algo_means, yerr=algo_stds, color=ALGO_COLORS,
                      capsize=4, alpha=0.85, zorder=3, width=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(ALGO_LABELS, fontsize=8.5, rotation=20, ha="right")
        ax.set_title(sc_label, fontsize=9, pad=4)
        ax.set_ylabel("Throughput (Mbps)" if si == 0 else "")
        ax.yaxis.set_minor_locator(plt.MultipleLocator(0.1))

        # Annotate best
        best_i = int(np.argmax(algo_means))
        ax.annotate(f"{algo_means[best_i]:.3f}",
                    xy=(x[best_i], algo_means[best_i] + algo_stds[best_i] + 0.02),
                    ha="center", va="bottom", fontsize=8, fontweight="bold",
                    color=ALGO_COLORS[best_i])

    fig.suptitle("", y=1.0)
    # Shared legend below
    patches = [mpatches.Patch(color=c, label=l)
               for c, l in zip(ALGO_COLORS, ALGO_LABELS)]
    fig.legend(handles=patches, loc="lower center",
               bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    path = os.path.join(FIGDIR, "fig_qos1_throughput.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 2 — Latency CDF
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos2_latency_cdf(qos_all):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)

    for si, (sc, sc_label) in enumerate(zip(SCENARIOS, SC_LABELS)):
        ax = axes[si]
        for algo, label, color, marker in zip(ALGO_KEYS, ALGO_LABELS, ALGO_COLORS, ALGO_MARKERS):
            rows = qos_all.get((sc, algo), [])
            lats = sorted([r["latency_avg_ms"] for r in rows if r["latency_avg_ms"] > 0])
            if not lats:
                continue
            n = len(lats)
            cdf = [(i + 1) / n for i in range(n)]
            ax.plot(lats, cdf, color=color, label=label, linewidth=1.6, marker=marker,
                    markevery=max(1, n // 8), markersize=4)

        ax.set_xlabel("Latency (ms)")
        ax.set_ylabel("CDF" if si == 0 else "")
        ax.set_title(sc_label, fontsize=9, pad=4)
        ax.axvline(x=50, color="#666", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_xlim(left=0)

    # Shared legend
    handles = [plt.Line2D([0], [0], color=c, marker=m, linewidth=1.6, markersize=5, label=l)
               for c, m, l in zip(ALGO_COLORS, ALGO_MARKERS, ALGO_LABELS)]
    fig.legend(handles=handles, loc="lower center",
               bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    path = os.path.join(FIGDIR, "fig_qos2_latency_cdf.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 3 — Jitter Comparison
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos3_jitter(qos_all, per_run):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=False)

    for si, (sc, sc_label) in enumerate(zip(SCENARIOS, SC_LABELS)):
        ax = axes[si]
        algo_means, algo_stds = [], []
        for algo in ALGO_KEYS:
            vals = [r["jitter_mean_ms"] for r in per_run
                    if r.get("scenario") == sc and r.get("algo") == algo]
            rows = qos_all.get((sc, algo), [])
            raw_vals = [r["jitter_ms"] for r in rows if r["jitter_ms"] >= 0]
            if raw_vals:
                algo_means.append(statistics.mean(raw_vals))
                algo_stds.append( statistics.stdev(raw_vals) if len(raw_vals) > 1 else 0.0)
            elif vals:
                algo_means.append(statistics.mean(vals))
                algo_stds.append( 0.0)
            else:
                algo_means.append(0.0)
                algo_stds.append(0.0)

        x = np.arange(len(ALGO_KEYS))
        ax.bar(x, algo_means, yerr=algo_stds, color=ALGO_COLORS,
               capsize=4, alpha=0.85, zorder=3, width=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(ALGO_LABELS, fontsize=8.5, rotation=20, ha="right")
        ax.set_title(sc_label, fontsize=9, pad=4)
        ax.set_ylabel("Jitter (ms)" if si == 0 else "")

        # Annotate values
        for i, (m, e) in enumerate(zip(algo_means, algo_stds)):
            if m > 0:
                ax.text(x[i], m + e + max(algo_means)*0.02, f"{m:.3f}",
                        ha="center", va="bottom", fontsize=7.5, color=ALGO_COLORS[i])

    patches = [mpatches.Patch(color=c, label=l)
               for c, l in zip(ALGO_COLORS, ALGO_LABELS)]
    fig.legend(handles=patches, loc="lower center",
               bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    path = os.path.join(FIGDIR, "fig_qos3_jitter.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 4 — Packet Loss
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos4_loss(qos_all, per_run):
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=False)

    for si, (sc, sc_label) in enumerate(zip(SCENARIOS, SC_LABELS)):
        ax = axes[si]
        algo_means, algo_stds = [], []
        for algo in ALGO_KEYS:
            rows = qos_all.get((sc, algo), [])
            raw_vals = [r["packet_loss_pct"] for r in rows]
            if raw_vals:
                algo_means.append(statistics.mean(raw_vals))
                algo_stds.append( statistics.stdev(raw_vals) if len(raw_vals) > 1 else 0.0)
            else:
                algo_means.append(0.0)
                algo_stds.append(0.0)

        x = np.arange(len(ALGO_KEYS))
        bars = ax.bar(x, algo_means, yerr=algo_stds, color=ALGO_COLORS,
                      capsize=4, alpha=0.85, zorder=3, width=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(ALGO_LABELS, fontsize=8.5, rotation=20, ha="right")
        ax.set_title(sc_label, fontsize=9, pad=4)
        ax.set_ylabel("Packet Loss (%)" if si == 0 else "")
        ax.axhline(y=0, color="#333", linewidth=0.8)

        # If all zero, show note
        if max(algo_means, default=0) == 0.0:
            ax.text(0.5, 0.6, "0.000%\n(all algorithms)", ha="center", va="center",
                    transform=ax.transAxes, fontsize=9, color="#444",
                    bbox=dict(boxstyle="round,pad=0.3", fc="#f0f0f0", ec="#ccc"))

    patches = [mpatches.Patch(color=c, label=l)
               for c, l in zip(ALGO_COLORS, ALGO_LABELS)]
    fig.legend(handles=patches, loc="lower center",
               bbox_to_anchor=(0.5, -0.08), ncol=4, fontsize=9)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    path = os.path.join(FIGDIR, "fig_qos4_loss.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 5 — Flow Setup Latency (bar + CDF)
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos5_setup(timing_data):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    # Bar chart: mean ± std per algorithm
    means = [statistics.mean(timing_data[a]) if timing_data[a] else 0.0 for a in ALGO_KEYS]
    stds  = [statistics.stdev(timing_data[a]) if len(timing_data[a]) > 1 else 0.0 for a in ALGO_KEYS]
    x = np.arange(len(ALGO_KEYS))
    ax1.bar(x, means, yerr=stds, color=ALGO_COLORS, capsize=5, alpha=0.85, zorder=3, width=0.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(ALGO_LABELS, fontsize=9)
    ax1.set_ylabel("Flow Setup Latency (ms)")
    ax1.set_xlabel("Algorithm")
    for i, (m, s) in enumerate(zip(means, stds)):
        if m > 0:
            ax1.text(x[i], m + s + max(means)*0.02, f"{m:.2f} ms",
                    ha="center", va="bottom", fontsize=8, color=ALGO_COLORS[i])

    # CDF of setup latency per algorithm
    for algo, label, color, marker in zip(ALGO_KEYS, ALGO_LABELS, ALGO_COLORS, ALGO_MARKERS):
        vals = sorted(timing_data[algo])
        if not vals:
            continue
        n = len(vals)
        cdf = [(i + 1) / n for i in range(n)]
        ax2.plot(vals, cdf, color=color, label=label, linewidth=1.6,
                 marker=marker, markevery=max(1, n // 8), markersize=4)

    ax2.set_xlabel("Flow Setup Latency (ms)")
    ax2.set_ylabel("CDF")
    ax2.axvline(x=10, color="#666", linestyle="--", linewidth=0.8, alpha=0.6, label="10 ms ref.")
    ax2.set_xlim(left=0)
    ax2.legend(loc="lower right", fontsize=8.5)

    fig.tight_layout()
    path = os.path.join(FIGDIR, "fig_qos5_setup.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Fig QoS 6 — Pre/Post Weight-Change QoS Impact (S2)
# ══════════════════════════════════════════════════════════════════════════════
def fig_qos6_prepost(per_run, qos_all):
    """Show QoS change pre vs post weight change in S2."""
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    axes = axes.flatten()
    metrics = [
        ("latency_avg_ms", "Latency (ms)", "latency_pre_ms", "latency_post_ms"),
        ("jitter_ms",      "Jitter (ms)",  "jitter_pre_ms",  "jitter_post_ms"),
        ("throughput_mbps","Throughput (Mbps)", "throughput_pre", "throughput_post"),
        ("packet_loss_pct","Packet Loss (%)", "loss_pre_pct",  "loss_post_pct"),
    ]
    sc = "single_change"
    x  = np.arange(len(ALGO_KEYS))
    w  = 0.3

    for ai, (field, ylabel, pre_key, post_key) in enumerate(metrics):
        ax = axes[ai]
        pre_vals, post_vals = [], []
        for algo in ALGO_KEYS:
            rows = qos_all.get((sc, algo), [])
            pre_rows  = [r[field] for r in rows if r["phase"] == "pre_change"  and r[field] >= 0]
            post_rows = [r[field] for r in rows if r["phase"] == "post_change" and r[field] >= 0]
            pre_vals.append( statistics.mean(pre_rows)  if pre_rows  else 0.0)
            post_vals.append(statistics.mean(post_rows) if post_rows else 0.0)

        # Fallback to per_run summary if no phase data
        if all(v == 0.0 for v in pre_vals):
            for i, algo in enumerate(ALGO_KEYS):
                runs = [r for r in per_run if r.get("scenario") == sc and r.get("algo") == algo]
                pre_vals[i]  = statistics.mean([r[pre_key]  for r in runs]) if runs else 0.0
                post_vals[i] = statistics.mean([r[post_key] for r in runs]) if runs else 0.0

        bars_pre  = ax.bar(x - w/2, pre_vals,  w, label="Pre-WC",  color="#90CAF9", zorder=3, alpha=0.9)
        bars_post = ax.bar(x + w/2, post_vals, w, label="Post-WC", color="#1565C0", zorder=3, alpha=0.9)
        ax.set_xticks(x)
        ax.set_xticklabels(ALGO_LABELS, fontsize=8.5)
        ax.set_ylabel(ylabel)
        ax.set_title(f"S2: {ylabel} — Pre vs. Post Weight Change", fontsize=9, pad=4)

        # Delta annotations
        for i in range(len(ALGO_KEYS)):
            if pre_vals[i] > 0:
                delta_pct = (post_vals[i] - pre_vals[i]) / pre_vals[i] * 100
                color = "#C62828" if delta_pct > 0 else "#2E7D32"
                ax.text(x[i], max(pre_vals[i], post_vals[i]) + 0.01,
                        f"{delta_pct:+.1f}%", ha="center", va="bottom",
                        fontsize=7.5, color=color, fontweight="bold")

        ax.legend(fontsize=8)

    fig.suptitle("S2: QoS Metrics Before vs. After Weight Change [3,5,2]→[6,5,2]",
                 fontsize=11, y=1.01)
    fig.tight_layout()
    path = os.path.join(FIGDIR, "fig_qos6_prepost.png")
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("P5 QoS Plot Generator")
    print("=" * 60)

    summary    = load_qos_summary()
    per_run    = load_per_run()
    timing     = load_flow_timing()
    qos_all    = load_qos_metrics_all()

    if not summary and not per_run and not qos_all:
        print("\n[WARN] No QoS data found in results/processed/ or results/raw/qos_*/")
        print("Run qos_experiment_runner.py first, then qos_analyzer.py, then this script.")
        print("\nGenerating placeholder figure layout...")

    print("\nGenerating figures...")
    fig_qos1_throughput(summary, per_run)
    fig_qos2_latency_cdf(qos_all)
    fig_qos3_jitter(qos_all, per_run)
    fig_qos4_loss(qos_all, per_run)
    fig_qos5_setup(timing)
    fig_qos6_prepost(per_run, qos_all)

    print(f"\nAll QoS figures saved to: {FIGDIR}")
    print("Files: fig_qos1_throughput.png, fig_qos2_latency_cdf.png,")
    print("       fig_qos3_jitter.png, fig_qos4_loss.png,")
    print("       fig_qos5_setup.png, fig_qos6_prepost.png")


if __name__ == "__main__":
    main()
