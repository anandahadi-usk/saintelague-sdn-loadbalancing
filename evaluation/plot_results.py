#!/usr/bin/env python3
# evaluation/plot_results.py
"""
Figure Generator — Publication-quality plots
Generates 4 key figures:
  Fig 1: MAPE trajectory post-change (S2 single change) — THE KEY FIGURE
  Fig 2: Recovery flows boxplot (S2 + S3)
  Fig 3: MAPE at checkpoints N=10,30,50,100,200 (S2 convergence table viz)
  Fig 4: CDE (cumulative distribution error) comparison across scenarios
"""
import os, sys, warnings
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.experiment_config import ALGORITHMS, SCENARIOS
from config.algo_config import ALGO_LABELS, ALGO_COLORS, ALGO_MARKERS

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
RESULTS_PROC = os.path.join(PROJECT_ROOT, "results", "processed")
FIGS_DIR     = os.path.join(PROJECT_ROOT, "docs", "figures")
os.makedirs(FIGS_DIR, exist_ok=True)

# Publication style
plt.rcParams.update({
    "font.family":       "serif",
    "font.size":         11,
    "axes.titlesize":    12,
    "axes.labelsize":    11,
    "xtick.labelsize":   10,
    "ytick.labelsize":   10,
    "legend.fontsize":   10,
    "figure.dpi":        300,
    "savefig.dpi":       300,
    "savefig.bbox":      "tight",
})

THRESHOLD = 5.0  # MAPE convergence threshold


# ─── Figure 1: MAPE Trajectory (S2 Single Change) ────────────────────────────
def fig_mape_trajectory(scenario="single_change", max_flows=150):
    """THE primary figure: MAPE vs post-change flows for all 4 algorithms."""
    fig, ax = plt.subplots(figsize=(8, 5))

    plotted = False
    for algo in ALGORITHMS:
        traj_path = os.path.join(RESULTS_PROC, f"mape_trajectory_{scenario}_{algo}.csv")
        if not os.path.exists(traj_path):
            print(f"  Missing trajectory: {traj_path}")
            continue
        df = pd.read_csv(traj_path)
        x  = df["post_change_flow"].values[:max_flows]
        y  = df["mape_mean"].values[:max_flows]
        e  = df["mape_std"].values[:max_flows]

        ax.plot(x, y,
                color=ALGO_COLORS[algo],
                marker=ALGO_MARKERS[algo],
                markevery=10, markersize=6,
                linewidth=2.0,
                label=ALGO_LABELS[algo])
        ax.fill_between(x, y - e, y + e,
                        color=ALGO_COLORS[algo], alpha=0.12)
        plotted = True

    if not plotted:
        ax.text(0.5, 0.5, "No trajectory data\n(run experiments first)",
                ha="center", va="center", transform=ax.transAxes, fontsize=12)

    # Convergence threshold line
    ax.axhline(THRESHOLD, color="black", linestyle="--", linewidth=1.5,
               label=f"Convergence threshold ({THRESHOLD}%)")

    ax.set_xlabel("Post-Change Flow Count")
    ax.set_ylabel("MAPE (%)")
    ax.set_title(f"MAPE Convergence Trajectory After Weight Change\n"
                 f"[{scenario.replace('_',' ').title()}]: weights [3,5,2]→[6,5,2]")
    ax.legend(loc="upper right")
    ax.set_xlim(0, max_flows)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)

    out = os.path.join(FIGS_DIR, f"fig1_mape_trajectory_{scenario}.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved: {out}")


# ─── Figure 2: Recovery Flows Boxplot ────────────────────────────────────────
def fig_recovery_boxplot():
    """Boxplot of recovery flows (flows to MAPE<5%) for S2 and S3."""
    scenarios_with_changes = ["single_change", "frequent_changes"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=False)

    for ax, scenario in zip(axes, scenarios_with_changes):
        conv_path = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
        if not os.path.exists(conv_path):
            ax.set_title(f"{scenario} (no data)")
            continue
        df = pd.read_csv(conv_path)
        col = "change1_recovery_flows"
        if col not in df.columns:
            ax.set_title(f"{scenario} (no change data)")
            continue

        data   = []
        labels = []
        for algo in ALGORITHMS:
            sub = df[df["algorithm"] == algo][col].replace(-1, np.nan).dropna()
            data.append(sub.values)
            labels.append(ALGO_LABELS[algo])

        bp = ax.boxplot(data, patch_artist=True,
                        medianprops={"color": "black", "linewidth": 2})
        for patch, algo in zip(bp["boxes"], ALGORITHMS):
            patch.set_facecolor(ALGO_COLORS[algo])
            patch.set_alpha(0.7)

        ax.set_xticks(range(1, len(ALGORITHMS) + 1))
        ax.set_xticklabels(labels, rotation=15, ha="right")
        ax.set_ylabel("Flows to MAPE < 5%")
        ax.set_title(f"{SCENARIOS[scenario]['label']}")
        ax.axhline(200, color="red", linestyle=":", linewidth=1.5,
                   label="Sim. limit (200)")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Recovery Flows: Number of Post-Change Flows to Reach MAPE < 5%",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    out = os.path.join(FIGS_DIR, "fig2_recovery_flows_boxplot.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved: {out}")


# ─── Figure 3: MAPE at Checkpoints (S2) ──────────────────────────────────────
def fig_mape_checkpoints(scenario="single_change"):
    """Bar chart of mean MAPE at N=10,30,50,100,200 post-change flows."""
    conv_path = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
    if not os.path.exists(conv_path):
        print(f"  Missing: {conv_path}")
        return
    df = pd.read_csv(conv_path)

    checkpoints = [10, 30, 50, 100, 200]
    cols = [f"change1_mape_at_n{n}" for n in checkpoints]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        print(f"  Missing columns: {missing}")
        return

    fig, ax = plt.subplots(figsize=(10, 5))
    x      = np.arange(len(checkpoints))
    width  = 0.18
    offset = np.linspace(-1.5, 1.5, 4) * width

    for i, algo in enumerate(ALGORITHMS):
        sub   = df[df["algorithm"] == algo]
        means = [sub[c].mean() for c in cols]
        errs  = [sub[c].std()  for c in cols]
        bars  = ax.bar(x + offset[i], means, width,
                       yerr=errs, capsize=3,
                       color=ALGO_COLORS[algo], alpha=0.8,
                       label=ALGO_LABELS[algo])

    ax.axhline(THRESHOLD, color="black", linestyle="--", linewidth=1.5,
               label=f"Convergence ({THRESHOLD}%)")
    ax.set_xticks(x)
    ax.set_xticklabels([f"N={n}" for n in checkpoints])
    ax.set_xlabel("Post-Change Flow Count")
    ax.set_ylabel("MAPE (%)")
    ax.set_title(f"MAPE at Convergence Checkpoints — {SCENARIOS[scenario]['label']}\n"
                 f"(mean ± std, {scenario.replace('_',' ')})")
    ax.legend(loc="upper right")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(FIGS_DIR, f"fig3_mape_checkpoints_{scenario}.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved: {out}")


# ─── Figure 4: CDE Comparison ────────────────────────────────────────────────
def fig_cde_comparison():
    """CDE (area under MAPE curve) for S2 and S3 — lower is better."""
    scenarios_with_changes = ["single_change", "frequent_changes"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))

    for ax, scenario in zip(axes, scenarios_with_changes):
        conv_path = os.path.join(RESULTS_PROC, f"convergence_{scenario}.csv")
        if not os.path.exists(conv_path):
            ax.set_title(f"{scenario} (no data)")
            continue
        df = pd.read_csv(conv_path)
        if "change1_cde" not in df.columns:
            ax.set_title(f"{scenario} (no CDE data)")
            continue

        means  = [df[df["algorithm"]==a]["change1_cde"].mean() for a in ALGORITHMS]
        stds   = [df[df["algorithm"]==a]["change1_cde"].std()  for a in ALGORITHMS]
        colors = [ALGO_COLORS[a] for a in ALGORITHMS]
        labels = [ALGO_LABELS[a] for a in ALGORITHMS]

        bars = ax.bar(labels, means, yerr=stds, capsize=4,
                      color=colors, alpha=0.8, edgecolor="black", linewidth=0.8)
        ax.set_ylabel("CDE (Mean MAPE over 200 post-change flows, %)")
        ax.set_title(f"{SCENARIOS[scenario]['label']}")
        ax.tick_params(axis="x", rotation=15)
        ax.set_ylim(bottom=0)
        ax.grid(True, alpha=0.3, axis="y")

        # Annotate bars
        for bar, m, s in zip(bars, means, stds):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + s + 0.3,
                    f"{m:.1f}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    fig.suptitle("Cumulative Distribution Error (CDE) — Lower is Better\n"
                 "(Area under MAPE curve / 200 post-change flows)",
                 fontsize=12, fontweight="bold")
    plt.tight_layout()
    out = os.path.join(FIGS_DIR, "fig4_cde_comparison.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved: {out}")


# ─── Figure 5: Steady-state MAPE (S1) ────────────────────────────────────────
def fig_steady_mape():
    """Steady-state end-MAPE — should show all algorithms equivalent."""
    conv_path = os.path.join(RESULTS_PROC, "convergence_steady.csv")
    if not os.path.exists(conv_path):
        print("  Missing steady convergence data")
        return
    df   = pd.read_csv(conv_path)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))

    for ax, metric, ylabel in [
        (axes[0], "end_mape",  "MAPE (%)"),
        (axes[1], "end_jfi_c", "JFI_c"),
    ]:
        if metric not in df.columns:
            continue
        data   = [df[df["algorithm"]==a][metric].dropna().values for a in ALGORITHMS]
        labels = [ALGO_LABELS[a] for a in ALGORITHMS]
        colors = [ALGO_COLORS[a] for a in ALGORITHMS]

        bp = ax.boxplot(data, patch_artist=True,
                        medianprops={"color":"black","linewidth":2})
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c); patch.set_alpha(0.7)
        ax.set_xticks(range(1, len(ALGORITHMS)+1))
        ax.set_xticklabels(labels, rotation=15, ha="right")
        ax.set_ylabel(ylabel)
        ax.set_title(f"S1 Steady-State — {ylabel}")
        ax.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Steady-State Performance (S1): All Algorithms Should Be Equivalent",
                 fontsize=12)
    plt.tight_layout()
    out = os.path.join(FIGS_DIR, "fig5_steady_state.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Figure Generator")
    parser.add_argument("--fig", default="all",
                        choices=["1","2","3","4","5","all"])
    args = parser.parse_args()

    print("Generating publication figures...")
    if args.fig in ("1","all"):
        fig_mape_trajectory("single_change")
        fig_mape_trajectory("frequent_changes")
    if args.fig in ("2","all"):
        fig_recovery_boxplot()
    if args.fig in ("3","all"):
        fig_mape_checkpoints("single_change")
        fig_mape_checkpoints("frequent_changes")
    if args.fig in ("4","all"):
        fig_cde_comparison()
    if args.fig in ("5","all"):
        fig_steady_mape()
    print("Done.")
