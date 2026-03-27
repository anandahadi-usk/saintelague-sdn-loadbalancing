"""
generate_convergence_figure.py
Publication-quality figure addressing reviewer concern about sustained convergence.
Two-panel figure: (a) full MAPE trajectory, (b) post-crossing behavior.
Output: /home/nanda/Desktop/P5/docs/figures_p5/fig_sustained_convergence.png
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

# ---------------------------------------------------------------------------
# Font / style settings — IEEE-compatible, serif, no grid
# ---------------------------------------------------------------------------
rcParams["font.family"] = "serif"
rcParams["font.serif"] = ["Times New Roman", "DejaVu Serif", "Liberation Serif"]
rcParams["font.size"] = 10
rcParams["axes.titlesize"] = 10
rcParams["axes.labelsize"] = 10
rcParams["xtick.labelsize"] = 9
rcParams["ytick.labelsize"] = 9
rcParams["legend.fontsize"] = 9
rcParams["figure.dpi"] = 300
rcParams["axes.grid"] = False
rcParams["axes.spines.top"] = False
rcParams["axes.spines.right"] = False

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = str(Path(__file__).parent.parent / "results" / "processed")
OUT_DIR = str(Path(__file__).parent / "figures_p5")
OUT_FILE = os.path.join(OUT_DIR, "fig_sustained_convergence.png")
os.makedirs(OUT_DIR, exist_ok=True)

CSV_MAP = {
    "SL":   os.path.join(BASE, "mape_trajectory_single_change_saintelague.csv"),
    "WLC":  os.path.join(BASE, "mape_trajectory_single_change_wlc.csv"),
    "WRR":  os.path.join(BASE, "mape_trajectory_single_change_wrr.csv"),
    "IWRR": os.path.join(BASE, "mape_trajectory_single_change_iwrr.csv"),
}

# Colorblind-safe palette
COLORS = {
    "SL":   "#0072B2",   # blue
    "WRR":  "#E69F00",   # orange
    "IWRR": "#009E73",   # green
    "WLC":  "#D55E00",   # red
}
LINESTYLES = {
    "SL":   "-",
    "WRR":  "--",
    "IWRR": "-.",
    "WLC":  ":",
}

CONVERGENCE_THRESHOLD = 5.0   # %
SL_CROSSING_FLOW     = 94     # first flow where SL MAPE < 5 %
WLC_CROSSING_FLOW    = 29     # first flow where WLC MAPE < 5 %  (transient)
WLC_REDIVERGE_FLOW   = 44     # WLC re-exceeds 5 % here
WLC_FINAL_MAPE       = 50.47  # % at flow 200

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
data = {}
for alg, path in CSV_MAP.items():
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    data[alg] = df  # columns: post_change_flow, mape_mean, mape_std

# Clip to 0–180 for left panel (per spec)
def clip180(df):
    return df[df["post_change_flow"] <= 180].copy()

# ---------------------------------------------------------------------------
# Figure layout
# ---------------------------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
fig.subplots_adjust(left=0.06, right=0.98, top=0.90, bottom=0.12, wspace=0.28)

# ===========================================================================
# LEFT PANEL — Full Post-Change MAPE Trajectory (0–180 flows)
# ===========================================================================
ax = ax1

# Shaded "SL sustained" region
ax.axvspan(SL_CROSSING_FLOW, 180, color="#0072B2", alpha=0.08,
           label="SL sustained <5%")

# Horizontal convergence threshold line
ax.axhline(CONVERGENCE_THRESHOLD, color="black", linestyle="--", linewidth=1.0,
           zorder=3)
ax.text(182, CONVERGENCE_THRESHOLD + 0.8, r"$\varepsilon = 5\%$",
        fontsize=9, va="bottom", ha="left", color="black")

# Vertical line: SL convergence
ax.axvline(SL_CROSSING_FLOW, color=COLORS["SL"], linestyle=":", linewidth=1.2,
           zorder=3)
ax.text(SL_CROSSING_FLOW + 1, 38,
        r"SL: $\tau$=94 flows",
        fontsize=8, color=COLORS["SL"], va="center",
        rotation=90)

# Vertical line: WLC transient dip
ax.axvline(WLC_CROSSING_FLOW, color=COLORS["WLC"], linestyle=":", linewidth=1.2,
           zorder=3)
ax.text(WLC_CROSSING_FLOW - 2, 38,
        "WLC: transient",
        fontsize=8, color=COLORS["WLC"], va="center", ha="right",
        rotation=90)

# Plot all 4 algorithms
order = ["WLC", "WRR", "IWRR", "SL"]   # SL on top
for alg in order:
    df = clip180(data[alg])
    x = df["post_change_flow"].values
    y = df["mape_mean"].values
    s = df["mape_std"].values
    ax.plot(x, y, color=COLORS[alg], linestyle=LINESTYLES[alg],
            linewidth=1.6, label=alg, zorder=4)
    ax.fill_between(x, y - s, y + s, color=COLORS[alg], alpha=0.15, zorder=2)

# Annotate WLC endpoint
wlc_df = clip180(data["WLC"])
wlc_end_x = wlc_df["post_change_flow"].iloc[-1]
wlc_end_y = wlc_df["mape_mean"].iloc[-1]
ax.annotate(f"WLC: {wlc_end_y:.2f}%",
            xy=(wlc_end_x, wlc_end_y),
            xytext=(wlc_end_x - 45, wlc_end_y + 4),
            fontsize=8, color=COLORS["WLC"],
            arrowprops=dict(arrowstyle="->", color=COLORS["WLC"],
                            lw=0.8, connectionstyle="arc3,rad=-0.2"),
            zorder=6)

ax.set_xlim(0, 182)
ax.set_ylim(0, 55)
ax.set_xlabel("Post-Change Flows", fontsize=10)
ax.set_ylabel("MAPE (%)", fontsize=10)
ax.set_title("(a) Full Trajectory: Sustained vs. Transient Convergence",
             fontsize=10, pad=6)

# Legend — upper right, exclude the shaded patch from auto-legend
handles, labels = ax.get_legend_handles_labels()
# Build manual legend: algorithms first, then region
alg_handles = [h for h, l in zip(handles, labels) if l in COLORS]
alg_labels  = [l for l in labels if l in COLORS]
patch_sl = mpatches.Patch(color=COLORS["SL"], alpha=0.20, label="SL sustained <5%")
ax.legend(alg_handles + [patch_sl], alg_labels + ["SL sustained <5%"],
          loc="upper right", frameon=True, framealpha=0.85, edgecolor="gray",
          fontsize=9)

# ===========================================================================
# RIGHT PANEL — MAPE After First <5% Crossing
# ===========================================================================
ax = ax2

# Horizontal threshold
ax.axhline(CONVERGENCE_THRESHOLD, color="black", linestyle="--", linewidth=1.0,
           zorder=3)
ax.text(122, CONVERGENCE_THRESHOLD + 0.8, r"$\varepsilon = 5\%$",
        fontsize=9, va="bottom", ha="left", color="black")

# ---- SL: from index 93 (flow 94) onwards, re-index x from 0 ----
sl_df  = data["SL"]
sl_sub = sl_df[sl_df["post_change_flow"] >= SL_CROSSING_FLOW].copy()
sl_x   = np.arange(len(sl_sub))   # 0, 1, 2, …
sl_y   = sl_sub["mape_mean"].values
sl_s   = sl_sub["mape_std"].values

ax.plot(sl_x, sl_y, color=COLORS["SL"], linestyle=LINESTYLES["SL"],
        linewidth=1.8, label="SL", zorder=4)
ax.fill_between(sl_x, sl_y - sl_s, sl_y + sl_s,
                color=COLORS["SL"], alpha=0.15, zorder=2)

# ---- WLC: from index 28 (flow 29) onwards, re-index x from 0 ----
wlc_df  = data["WLC"]
wlc_sub = wlc_df[wlc_df["post_change_flow"] >= WLC_CROSSING_FLOW].copy()
wlc_x   = np.arange(len(wlc_sub))   # 0, 1, 2, …
wlc_y   = wlc_sub["mape_mean"].values
wlc_s   = wlc_sub["mape_std"].values

ax.plot(wlc_x, wlc_y, color=COLORS["WLC"], linestyle=LINESTYLES["WLC"],
        linewidth=1.8, label="WLC", zorder=4)
ax.fill_between(wlc_x, wlc_y - wlc_s, wlc_y + wlc_s,
                color=COLORS["WLC"], alpha=0.15, zorder=2)

# How many consecutive flows SL stays below 5%?
sl_consecutive = int(np.sum(sl_y < CONVERGENCE_THRESHOLD))
# WLC re-diverges after (WLC_REDIVERGE_FLOW - WLC_CROSSING_FLOW) flows
wlc_flows_until_rediverge = WLC_REDIVERGE_FLOW - WLC_CROSSING_FLOW  # 15

# Annotation: SL sustained
ax.annotate(
    f"SL: sustains ε<5%\nfor {sl_consecutive} consecutive flows",
    xy=(sl_consecutive // 2, sl_y[sl_consecutive // 2]),
    xytext=(40, 12),
    fontsize=8, color=COLORS["SL"],
    arrowprops=dict(arrowstyle="->", color=COLORS["SL"],
                    lw=0.8, connectionstyle="arc3,rad=0.3"),
    zorder=6,
)

# Annotation: WLC re-divergence
rediverge_idx = wlc_flows_until_rediverge  # index in wlc_x
ax.annotate(
    f"WLC: re-diverges in {wlc_flows_until_rediverge} flows\n→ {WLC_FINAL_MAPE:.2f}%",
    xy=(rediverge_idx, wlc_y[rediverge_idx]),
    xytext=(20, 35),
    fontsize=8, color=COLORS["WLC"],
    arrowprops=dict(arrowstyle="->", color=COLORS["WLC"],
                    lw=0.8, connectionstyle="arc3,rad=-0.3"),
    zorder=6,
)

ax.set_xlim(0, 120)
ax.set_ylim(0, 55)
ax.set_xlabel("Flows After First Sub-5% MAPE", fontsize=10)
ax.set_ylabel("MAPE (%)", fontsize=10)
ax.set_title("(b) Post-Crossing Behavior: Sustained vs. Re-divergence",
             fontsize=10, pad=6)
ax.legend(loc="upper right", frameon=True, framealpha=0.85,
          edgecolor="gray", fontsize=9)

# ===========================================================================
# Save
# ===========================================================================
fig.savefig(OUT_FILE, dpi=300, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {OUT_FILE}")
