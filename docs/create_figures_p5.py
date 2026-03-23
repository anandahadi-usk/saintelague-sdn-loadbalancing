#!/usr/bin/env python3
"""
P5 Publication Figures Generator — uses ACTUAL experiment results
IEEE Access Quality: 300 DPI, serif fonts, colorblind-safe palette
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import numpy as np
import os, csv, glob, statistics

# ── Paths ────────────────────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(BASE, 'docs', 'figures_p5')
RAW  = os.path.join(BASE, 'results', 'raw')
os.makedirs(OUT, exist_ok=True)

# ── IEEE Style ───────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.family':       'serif',
    'font.serif':        ['Times New Roman', 'DejaVu Serif', 'serif'],
    'font.size':         9,
    'axes.titlesize':    9,
    'axes.labelsize':    9,
    'xtick.labelsize':   8,
    'ytick.labelsize':   8,
    'legend.fontsize':   8,
    'legend.framealpha': 0.92,
    'axes.grid':         True,
    'grid.alpha':        0.3,
    'grid.linestyle':    '--',
    'axes.linewidth':    0.8,
    'lines.linewidth':   1.5,
    'patch.linewidth':   0.8,
})
DPI = 300

# ── Colorblind-safe palette ──────────────────────────────────────────────────
C = {'wrr': '#d62728', 'iwrr': '#ff7f0e', 'wlc': '#9467bd', 'sl': '#2ca02c'}
M = {'wrr': 'o', 'iwrr': 's', 'wlc': '^', 'sl': 'D'}
L = {'wrr': 'WRR', 'iwrr': 'IWRR', 'wlc': 'WLC', 'sl': 'Sainte-Lague'}

# ════════════════════════════════════════════════════════════════════════════
# Load actual trajectory data from raw CSVs
# ════════════════════════════════════════════════════════════════════════════
def load_traj_mean(scenario, algo):
    """Load per-run CSVs and return mean MAPE per flow index."""
    files = sorted(glob.glob(os.path.join(RAW, f'{scenario}_{algo}_run*', '*.csv')))
    all_runs = []
    for f in files:
        rows = list(csv.DictReader(open(f)))
        all_runs.append([float(r['mape']) for r in rows])
    n = min(len(r) for r in all_runs)
    return [statistics.mean(run[i] for run in all_runs) for i in range(n)]


print('Loading trajectory data from raw CSVs...')
ALGOS  = ['wrr', 'iwrr', 'wlc', 'saintelague']
ALGO_K = ['wrr', 'iwrr', 'wlc', 'sl']          # keys used in C / M / L dicts

S1 = {k: load_traj_mean('steady',           a) for k, a in zip(ALGO_K, ALGOS)}
S2 = {k: load_traj_mean('single_change',    a) for k, a in zip(ALGO_K, ALGOS)}
S3 = {k: load_traj_mean('frequent_changes', a) for k, a in zip(ALGO_K, ALGOS)}

# S2: WC at boundary between flow 20 and 21 (1-indexed)
# S3: WC1 before flow 1; WC2 at 10/11; WC3 at 20/21; WC4 at 30/31

# Summary metrics: (avg_mape_all_flows, final_mape)
def avg(lst): return statistics.mean(lst)

SUMMARY = {
    'S1 Steady': {
        k: (round(avg(S1[k]), 2), round(S1[k][-1], 2))
        for k in ALGO_K
    },
    'S2 Single\nChange': {
        k: (round(avg(S2[k]), 2), round(S2[k][-1], 2))
        for k in ALGO_K
    },
    'S3 Frequent\nChanges': {
        k: (round(avg(S3[k]), 2), round(S3[k][-1], 2))
        for k in ALGO_K
    },
}
print('Data loaded.')
print()


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 1 — Network Topology
# ════════════════════════════════════════════════════════════════════════════
def fig1_topology():
    fig, ax = plt.subplots(figsize=(7.5, 5.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(-0.6, 7.0)
    ax.axis('off')
    ax.set_facecolor('#fafafa')
    fig.patch.set_facecolor('#fafafa')

    def box(ax, x, y, w, h, color, text, fontsize=7.5, radius=0.25, tc='white'):
        r = FancyBboxPatch((x - w/2, y - h/2), w, h,
                            boxstyle=f'round,pad=0.05,rounding_size={radius}',
                            facecolor=color, edgecolor='#333333', lw=0.8, zorder=3)
        ax.add_patch(r)
        ax.text(x, y, text, ha='center', va='center', fontsize=fontsize,
                color=tc, fontweight='bold', zorder=4, linespacing=1.3)

    def arrow(ax, x1, y1, x2, y2, color='#555', lw=1.1, both=False):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='<->' if both else '->',
                                   color=color, lw=lw,
                                   connectionstyle='arc3,rad=0.0'), zorder=2)

    # Clients
    for i in range(5):
        y = 6.2 - i * 0.72
        box(ax, 1.0, y, 1.4, 0.50, '#1f77b4', f'c{i+1}\n10.0.0.{10+i}', fontsize=6.8)
        arrow(ax, 1.72, y, 2.85, 3.5, '#1f77b4', lw=0.9)
    y_dot = 6.2 - 5 * 0.72
    for dy in [-0.11, 0.0, 0.11]:
        ax.plot(1.0, y_dot + dy, 'o', markersize=2.2, color='#777', zorder=4)
    y_c10 = y_dot - 0.60
    box(ax, 1.0, y_c10, 1.4, 0.50, '#1f77b4', 'c10\n10.0.0.19', fontsize=6.8)
    arrow(ax, 1.72, y_c10, 2.85, 3.5, '#1f77b4', lw=0.9)

    # OVS Switch
    box(ax, 3.5, 3.5, 1.5, 0.75, '#333333',
        'OVS Switch\n(OpenFlow 1.3)', fontsize=7.5, radius=0.15)

    # Ryu Controller — REST API included in box text
    box(ax, 6.0, 5.7, 2.1, 1.00, '#8c564b',
        'Ryu Controller\nport 6653 | REST :8080\nDNAT / SNAT', fontsize=7.0, radius=0.2)
    # Control channel: straight dashed line
    ax.annotate('', xy=(4.95, 5.2), xytext=(4.25, 3.875),
                arrowprops=dict(arrowstyle='<->', color='#8c564b',
                                lw=1.1, linestyle='dashed',
                                connectionstyle='arc3,rad=0.0'), zorder=2)
    # OpenFlow label — left of line, white background
    ax.text(3.85, 4.65, 'OpenFlow\n(control)', ha='center', va='center',
            fontsize=6.5, color='#8c564b', style='italic', zorder=6,
            bbox=dict(boxstyle='round,pad=0.28', facecolor='white',
                      edgecolor='#ccc', lw=0.6, alpha=0.97))

    # VIP
    box(ax, 3.5, 1.9, 1.5, 0.56, '#e377c2',
        'VIP\n10.0.0.100', fontsize=7.5, radius=0.2, tc='white')
    arrow(ax, 3.5, 3.125, 3.5, 2.18, '#e377c2', lw=1.0, both=True)

    # Servers
    for name, ip, bw, w, color, y in [
        ('srv1', '10.0.0.1', '30 Mbps', 'w=3', '#2ca02c', 5.7),
        ('srv2', '10.0.0.2', '50 Mbps', 'w=5', '#2ca02c', 3.6),
        ('srv3', '10.0.0.3', '20 Mbps', 'w=2', '#2ca02c', 1.5),
    ]:
        box(ax, 8.4, y, 1.85, 0.85, color,
            f'{name}\n{ip}\n{bw}  {w}', fontsize=6.8, radius=0.2)
        arrow(ax, 4.25, 3.5, 7.475, y, '#555', lw=0.9, both=True)

    # Bottom annotation — left-centered, clear of servers
    ax.text(3.5, -0.25,
            'Initial weights: w = [3, 5, 2]  ->  ideal distribution: 30% : 50% : 20%\n'
            'Weight change event: [3,5,2] -> [6,5,2]  ->  new target: 46% : 38% : 15%',
            ha='center', va='center', fontsize=7.0, color='#333', style='italic',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fffde7',
                      edgecolor='#bbb', lw=0.7, zorder=5))

    fig.tight_layout(pad=0.6)
    path = f'{OUT}/fig1_topology.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor='#fafafa')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 2 — Algorithm Concept: WRR sequence rebuild vs SL count preservation
# ════════════════════════════════════════════════════════════════════════════
def fig2_concept():
    fig = plt.figure(figsize=(7.0, 5.0))
    fig.patch.set_facecolor('white')
    gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.60, wspace=0.35,
                           left=0.06, right=0.97, top=0.93, bottom=0.10)

    CC = {1: '#aec6e8', 2: '#ffc2a0', 3: '#c7e8a0'}
    CT = {1: 'S1', 2: 'S2', 3: 'S3'}

    def draw_seq(ax, seq, title, subtitle=''):
        ax.set_xlim(-0.5, len(seq) + 0.5)
        ax.set_ylim(-0.8, 2.0)
        ax.axis('off')
        ax.set_title(title, fontsize=8.5, fontweight='bold', pad=3)
        if subtitle:
            ax.text(len(seq)/2, 1.75, subtitle, ha='center', fontsize=7.0,
                    color='#555', style='italic')
        for i, s in enumerate(seq):
            r = plt.Rectangle((i+0.1, 0.1), 0.8, 0.8,
                               facecolor=CC.get(s, '#eee'), edgecolor='#666', lw=0.7, zorder=2)
            ax.add_patch(r)
            ax.text(i+0.5, 0.5, CT.get(s,''), ha='center', va='center',
                    fontsize=7.5, fontweight='bold', color='#333')
            ax.text(i+0.5, -0.4, str(i+1), ha='center', va='center',
                    fontsize=6.5, color='#777')
        ax.text(len(seq)/2, -0.72, 'Flow decision number',
                ha='center', va='center', fontsize=7.0, color='#555')

    # WRR pre-change
    draw_seq(fig.add_subplot(gs[0, 0]),
             [1,1,1,2,2,2,2,2,3,3], 'WRR — Pre-Change  W=[3,5,2]',
             'Cycle L=10: position moves 0->9->0->...')

    # WRR post-change
    ax1 = fig.add_subplot(gs[0, 1])
    seq_post = [1,1,1,1,1,1,2,2,2,2,2]
    ax1.set_xlim(-0.5, len(seq_post)+0.5); ax1.set_ylim(-0.8, 2.0); ax1.axis('off')
    ax1.set_title("WRR — Post-Change  W'=[6,5,2]", fontsize=8.5, fontweight='bold', pad=3)
    ax1.text(len(seq_post)/2, 1.75,
             "[!] Rebuild sequence L'=13, RESET pos=0, counts discarded",
             ha='center', fontsize=7.0, color='red', style='italic')
    for i, s in enumerate(seq_post):
        r = plt.Rectangle((i+0.1,0.1), 0.8, 0.8, facecolor=CC.get(s,'#eee'),
                           edgecolor='#666', lw=0.7, zorder=2)
        ax1.add_patch(r)
        ax1.text(i+0.5, 0.5, CT.get(s,''), ha='center', va='center',
                 fontsize=7.5, fontweight='bold', color='#333')
        ax1.text(i+0.5, -0.4, str(i+1), ha='center', va='center', fontsize=6.5, color='#777')
    ax1.text(len(seq_post)/2, -0.72, 'Post-change flow decision',
             ha='center', va='center', fontsize=7.0, color='#555')

    # SL pre-change
    ax2 = fig.add_subplot(gs[1, 0])
    sl_pre = [2,1,3,2,1,2,2,3,1,2]
    ax2.set_xlim(-0.5, len(sl_pre)+0.5); ax2.set_ylim(-0.8, 2.6); ax2.axis('off')
    ax2.set_title('Sainte-Lague — Pre-Change  W=[3,5,2]', fontsize=8.5, fontweight='bold', pad=3)
    ax2.text(len(sl_pre)/2, 2.35, 'Q(i) = w(i)/(2*n(i)+1), select argmax Q',
             ha='center', fontsize=7.0, color='#2ca02c', style='italic')
    counts = [0,0,0]
    for i, s in enumerate(sl_pre):
        counts[s-1] += 1
        r = plt.Rectangle((i+0.1,0.1), 0.8, 0.8, facecolor=CC.get(s,'#eee'),
                           edgecolor='#2ca02c', lw=0.9, zorder=2)
        ax2.add_patch(r)
        ax2.text(i+0.5, 0.5, CT.get(s,''), ha='center', va='center',
                 fontsize=7.5, fontweight='bold', color='#333')
        ax2.text(i+0.5, -0.4, str(i+1), ha='center', va='center', fontsize=6.5, color='#777')
    ax2.text(5.0, 1.25,
             f'n = [{counts[0]}, {counts[1]}, {counts[2]}]  (preserved at weight change)',
             ha='center', fontsize=7.2, color='#2ca02c',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#e8f5e9', edgecolor='#2ca02c', lw=0.8))
    ax2.text(len(sl_pre)/2, -0.72, 'Flow decision number',
             ha='center', va='center', fontsize=7.0, color='#555')

    # SL post-change
    ax3 = fig.add_subplot(gs[1, 1])
    sl_post = [1,1,1,1,1,1,1,2,1,3]
    ax3.set_xlim(-0.5, len(sl_post)+0.5); ax3.set_ylim(-0.8, 2.6); ax3.axis('off')
    ax3.set_title("Sainte-Lague — Post-Change  W'=[6,5,2]", fontsize=8.5, fontweight='bold', pad=3)
    ax3.text(len(sl_post)/2, 2.35,
             'n(i) preserved: [6,10,4] -> Q immediately compensates',
             ha='center', fontsize=7.0, color='#2ca02c', style='italic')
    n_wc = [6, 10, 4]; w_new = [6, 5, 2]
    q = [w_new[i]/(2*n_wc[i]+1) for i in range(3)]
    ax3.text(len(sl_post)/2, 1.55,
             f'Q at WC: S1={q[0]:.3f} <- max  S2={q[1]:.3f}  S3={q[2]:.3f}',
             ha='center', fontsize=7.0, color='#1565c0',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#e3f2fd', edgecolor='#1565c0', lw=0.8))
    for i, s in enumerate(sl_post):
        r = plt.Rectangle((i+0.1,0.1), 0.8, 0.8, facecolor=CC.get(s,'#eee'),
                           edgecolor='#2ca02c', lw=0.9, zorder=2)
        ax3.add_patch(r)
        ax3.text(i+0.5, 0.5, CT.get(s,''), ha='center', va='center',
                 fontsize=7.5, fontweight='bold', color='#333')
        ax3.text(i+0.5, -0.4, str(i+1), ha='center', va='center', fontsize=6.5, color='#777')
    ax3.text(len(sl_post)/2, -0.72, 'Post-change flow decision',
             ha='center', va='center', fontsize=7.0, color='#555')

    legend_items = [mpatches.Patch(facecolor=v, edgecolor='#666', label=f'Server {k}')
                    for k, v in CC.items()]
    fig.legend(handles=legend_items, loc='lower center', ncol=3,
               fontsize=8, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

    path = f'{OUT}/fig2_algorithm_concept.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 3 — S2 Full MAPE Trajectory (all 30 flows, WC at flow 20/21)
# ════════════════════════════════════════════════════════════════════════════
def fig3_s2_full():
    fig, ax = plt.subplots(figsize=(7.0, 4.2))

    flows  = list(range(1, len(S2['wrr']) + 1))  # 30 flows
    wc_x   = 20.5   # WC between flow 20 (pre) and 21 (post)

    for k in ['wrr', 'iwrr', 'wlc', 'sl']:
        ax.plot(flows, S2[k], color=C[k], marker=M[k],
                markersize=3.5, label=L[k], markevery=3, linewidth=1.4)

    ax.axvline(x=wc_x, color='#333', lw=1.3, linestyle='--', zorder=5)
    ax.text(wc_x + 0.3, 148, 'Weight Change\n[3,5,2]->[6,5,2]',
            fontsize=7.0, color='#333', va='top',
            bbox=dict(boxstyle='round,pad=0.25', facecolor='#fff9c4',
                      edgecolor='#999', lw=0.7, zorder=6))

    ax.axhline(y=5, color='#555', lw=0.9, linestyle=':', alpha=0.8)
    ax.text(1.5, 6.5, 'epsilon = 5%', fontsize=7.0, color='#555', style='italic')

    # Shade pre- and post-change regions
    ax.axvspan(0.5,  wc_x, alpha=0.04, color='steelblue')
    ax.axvspan(wc_x, len(flows)+0.5, alpha=0.06, color='orange')
    ax.text(10.5,  150, 'Pre-change',  ha='center', fontsize=7.0, color='steelblue', style='italic')
    ax.text(25.5, 150, 'Post-change', ha='center', fontsize=7.0, color='darkorange', style='italic')

    ax.set_xlabel('Flow Decision Number', fontsize=9)
    ax.set_ylabel('MAPE (%)', fontsize=9)
    ax.set_xlim(0.5, len(flows) + 0.5)
    ax.set_ylim(-3, 160)
    ax.set_xticks(range(1, len(flows)+1, 2))

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16),
              ncol=4, fontsize=8.5, framealpha=0.95, edgecolor='#ccc')
    fig.subplots_adjust(bottom=0.22)
    path = f'{OUT}/fig3_s2_full_trajectory.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 4 — S2 Post-Change Zoomed (flows 21–30, i.e., +1 to +10)
# ════════════════════════════════════════════════════════════════════════════
def fig4_postchange():
    fig, ax = plt.subplots(figsize=(7.0, 4.2))

    post_idx = 20   # WC at index 20 (0-based) = flow 21
    n_post   = len(S2['wrr']) - post_idx  # should be 10

    post_x      = list(range(1, n_post + 1))
    post_labels = [f'+{i}' for i in post_x]

    # Value offsets to avoid final-annotation overlap
    y_off = {'wrr': 3.5, 'iwrr': -4.5, 'wlc': 5.5, 'sl': -5.0}

    for k in ['wrr', 'iwrr', 'wlc', 'sl']:
        post = S2[k][post_idx:]
        ax.plot(post_x, post, color=C[k], marker=M[k],
                markersize=5, label=L[k], linewidth=1.8)
        ax.annotate(f'{post[-1]:.2f}%',
                    xy=(n_post, post[-1]),
                    xytext=(n_post + 0.15, post[-1] + y_off[k]),
                    fontsize=7.0, color=C[k], fontweight='bold', va='center')

    ax.axhline(y=5, color='#555', lw=1.0, linestyle=':', alpha=0.8)
    ax.text(0.15, 6.5, 'epsilon = 5% convergence threshold',
            fontsize=7.0, color='#555', style='italic')

    ax.fill_between(post_x, 0, 5, alpha=0.10, color='green')
    ax.text(5.0, 2.2, 'Convergence Zone', fontsize=7.5, color='#2ca02c',
            ha='center', style='italic', alpha=0.85)

    ax.set_xlabel('Flow Decision (post-weight-change)', fontsize=9)
    ax.set_ylabel('MAPE (%)', fontsize=9)
    ax.set_xlim(0.5, n_post + 1.0)
    ax.set_ylim(-1, 40)
    ax.set_xticks(post_x)
    ax.set_xticklabels(post_labels, fontsize=8)

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16),
              ncol=4, fontsize=8.5, framealpha=0.95, edgecolor='#ccc')
    fig.subplots_adjust(bottom=0.22)
    path = f'{OUT}/fig4_s2_postchange_detail.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 5 — Summary Bar Chart (Avg MAPE + Final MAPE, S1/S2/S3)
# ════════════════════════════════════════════════════════════════════════════
def fig5_summary():
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.8))

    scenarios = list(SUMMARY.keys())  # ['S1 Steady', 'S2 Single\nChange', 'S3 Frequent\nChanges']
    x     = np.arange(len(scenarios))
    width = 0.19

    for ax_idx, metric_idx in enumerate([0, 1]):
        ax = axes[ax_idx]
        for j, k in enumerate(ALGO_K):
            vals   = [SUMMARY[s][k][metric_idx] for s in scenarios]
            offset = (j - 1.5) * width
            bars   = ax.bar(x + offset, vals, width, color=C[k],
                            label=L[k], alpha=0.88, edgecolor='white', lw=0.5)
            for bar, v in zip(bars, vals):
                if v > 0.5:
                    ax.text(bar.get_x() + bar.get_width()/2,
                            bar.get_height() + 0.4,
                            f'{v:.1f}', ha='center', va='bottom',
                            fontsize=5.8, color='#333', rotation=90)

        ax.set_xticks(x)
        ax.set_xticklabels(scenarios, fontsize=8)
        ax.set_ylabel('MAPE (%)', fontsize=9)
        max_y = max(SUMMARY[s][k][metric_idx] for s in scenarios for k in ALGO_K)
        ax.set_ylim(0, max_y * 1.35)

        if metric_idx == 1:
            ax.axhline(y=5, color='#555', lw=0.9, linestyle=':', alpha=0.7)
            ax.text(2.4, max_y * 1.35 * 0.08, 'eps=5%', fontsize=7,
                    color='#555', style='italic')

        ax.set_title('(a) Average MAPE' if metric_idx == 0 else '(b) Final MAPE',
                     fontsize=9, pad=4, fontweight='bold')
        if ax_idx == 0:
            ax.legend(fontsize=7.5, loc='upper left', ncol=1, framealpha=0.9)

    fig.tight_layout(pad=0.8)
    path = f'{OUT}/fig5_summary_comparison.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 6 — S3 Frequent Changes Trajectory (40 flows, 4 WC events)
# ════════════════════════════════════════════════════════════════════════════
def fig6_s3():
    fig, ax = plt.subplots(figsize=(7.0, 4.2))

    flows = list(range(1, len(S3['wrr']) + 1))   # 40 flows
    # WC1 starts the experiment (before flow 1); WC2-4 between every 10 flows
    wc_bounds = [10.5, 20.5, 30.5]
    wc_labels = ['WC2', 'WC3', 'WC4']
    period_labels = ['WC1', 'WC2', 'WC3', 'WC4']
    period_centers = [5.5, 15.5, 25.5, 35.5]

    # Alternating background bands
    period_colors = ['#e3f2fd', '#fff3e0', '#e3f2fd', '#fff3e0']
    bounds = [0.5, 10.5, 20.5, 30.5, 40.5]
    for i in range(4):
        ax.axvspan(bounds[i], bounds[i+1], alpha=0.12, color=period_colors[i], zorder=0)
        ax.text(period_centers[i], 155, period_labels[i], ha='center',
                fontsize=7.5, color='#555', fontweight='bold')

    for i, wc in enumerate(wc_bounds):
        ax.axvline(x=wc, color='#444', lw=1.0, linestyle='--', alpha=0.8, zorder=5)

    for k in ['wrr', 'iwrr', 'wlc', 'sl']:
        ax.plot(flows, S3[k], color=C[k], marker=M[k],
                markersize=2.8, label=L[k], markevery=4,
                linewidth=1.4, alpha=0.90)

    ax.axhline(y=5, color='#555', lw=0.9, linestyle=':', alpha=0.7)
    ax.text(1.5, 6.5, 'epsilon = 5%', fontsize=7.0, color='#555', style='italic')

    # Final MAPE annotations at right edge — staggered
    y_off = {'wrr': 5, 'iwrr': 1, 'wlc': -5, 'sl': -9}
    for k in ['wrr', 'iwrr', 'wlc', 'sl']:
        fv = S3[k][-1]
        ax.annotate(f'{fv:.2f}%',
                    xy=(40, fv),
                    xytext=(40.3, fv + y_off[k]),
                    fontsize=6.8, color=C[k], fontweight='bold', va='center')

    ax.set_xlabel('Flow Decision Number', fontsize=9)
    ax.set_ylabel('MAPE (%)', fontsize=9)
    ax.set_xlim(0.5, 41.5)
    ax.set_ylim(-3, 165)
    ax.set_xticks(range(1, 41, 4))

    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.16),
              ncol=4, fontsize=8.5, framealpha=0.95, edgecolor='#ccc')
    fig.subplots_adjust(bottom=0.22)
    path = f'{OUT}/fig6_s3_trajectory.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 7 — Convergence Heatmap
# ════════════════════════════════════════════════════════════════════════════
def fig7_heatmap():
    fig, ax = plt.subplots(figsize=(6.5, 3.2))

    algo_labels = ['WRR', 'IWRR', 'WLC', 'Sainte-Lague']
    metrics     = ['S1\nAvg MAPE', 'S2\nAvg MAPE', 'S2\nFinal MAPE',
                   'S3\nAvg MAPE', 'S3\nFinal MAPE']

    # Use actual computed values
    sc = list(SUMMARY.keys())
    data = np.array([
        [SUMMARY[sc[0]][k][0], SUMMARY[sc[1]][k][0], SUMMARY[sc[1]][k][1],
         SUMMARY[sc[2]][k][0], SUMMARY[sc[2]][k][1]]
        for k in ALGO_K
    ])

    data_norm = np.zeros_like(data)
    for j in range(data.shape[1]):
        col = data[:, j]
        rng = col.max() - col.min()
        data_norm[:, j] = (col - col.min()) / (rng + 1e-9)

    im = ax.imshow(data_norm, cmap='RdYlGn_r', aspect='auto', vmin=0, vmax=1)
    ax.set_xticks(range(len(metrics)))
    ax.set_xticklabels(metrics, fontsize=8.0)
    ax.set_yticks(range(len(algo_labels)))
    ax.set_yticklabels(algo_labels, fontsize=8.5)

    for i in range(len(algo_labels)):
        for j in range(len(metrics)):
            norm = data_norm[i, j]
            tc   = 'white' if norm > 0.60 or norm < 0.20 else '#222'
            ax.text(j, i, f'{data[i,j]:.2f}%', ha='center', va='center',
                    fontsize=8.0, fontweight='bold', color=tc)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label('Normalized value\n(green = best)', fontsize=7.0)
    cbar.ax.tick_params(labelsize=7)

    fig.tight_layout(pad=0.8)
    path = f'{OUT}/fig7_heatmap_summary.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# FIGURE 8 — WRR Periodic Oscillation vs Sainte-Lague Convergence (S1 steady)
# ════════════════════════════════════════════════════════════════════════════
def fig8_wrr_oscillation():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 3.5))

    w_flows = list(range(1, len(S1['wrr']) + 1))   # 30
    s_flows = list(range(1, len(S1['sl'])  + 1))   # 30

    # ── WRR ─────────────────────────────────────────────────────────────────
    ax1.fill_between(w_flows, S1['wrr'], alpha=0.15, color=C['wrr'])
    ax1.plot(w_flows, S1['wrr'], color=C['wrr'], marker='o', markersize=3.5,
             linewidth=1.5, label='WRR (weights [3,5,2])')
    ax1.axhline(y=5, color='#555', lw=0.9, linestyle=':', alpha=0.7)

    # Cycle boundaries at 10, 20
    for bd in [10, 20]:
        ax1.axvline(x=bd, color=C['wrr'], lw=0.8, linestyle='--', alpha=0.5)
        ax1.text(bd, 153, 'Cycle\nend', ha='center', fontsize=6.0, color=C['wrr'], va='top')

    wrr_avg = avg(S1['wrr'])
    ax1.text(22, 90, f'Average:\n{wrr_avg:.2f}%', ha='center', fontsize=8,
             color=C['wrr'], fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#ffe0e0', edgecolor=C['wrr'], lw=0.8))
    ax1.text(2, 6.5, 'epsilon = 5%', fontsize=6.5, color='#555', style='italic')
    ax1.set_title('(a) WRR: Periodic Oscillation\nMAPE = 0% only at cycle end',
                  fontsize=8, pad=4)
    ax1.set_xlabel('Flow Decision', fontsize=8.5)
    ax1.set_ylabel('MAPE (%)', fontsize=8.5)
    ax1.set_xlim(0.5, 30.5)
    ax1.set_ylim(-3, 160)

    # ── Sainte-Lague ─────────────────────────────────────────────────────────
    ax2.fill_between(s_flows, S1['sl'], alpha=0.15, color=C['sl'])
    ax2.plot(s_flows, S1['sl'], color=C['sl'], marker='D', markersize=3.5,
             linewidth=1.5, label='Sainte-Lague')
    ax2.axhline(y=5, color='#555', lw=0.9, linestyle=':', alpha=0.7)

    sl_avg = avg(S1['sl'])
    ax2.text(22, 90, f'Average:\n{sl_avg:.2f}%', ha='center', fontsize=8,
             color=C['sl'], fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#e8f5e9', edgecolor=C['sl'], lw=0.8))
    ax2.text(2, 6.5, 'epsilon = 5%', fontsize=6.5, color='#555', style='italic')
    ax2.set_title('(b) Sainte-Lague: Monotonic Convergence\nMAPE < 5% achieved and maintained',
                  fontsize=8, pad=4)
    ax2.set_xlabel('Flow Decision', fontsize=8.5)
    ax2.set_ylabel('MAPE (%)', fontsize=8.5)
    ax2.set_xlim(0.5, 30.5)
    ax2.set_ylim(-3, 160)

    for ax in [ax1, ax2]:
        ax.grid(True, alpha=0.3, linestyle='--')

    fig.tight_layout(pad=0.8)
    path = f'{OUT}/fig8_oscillation_comparison.png'
    fig.savefig(path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f'Saved: {path}')


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('Generating P5 publication figures (300 DPI) — actual experiment data')
    print(f'Output: {OUT}')
    print()
    fig1_topology()
    fig2_concept()
    fig3_s2_full()
    fig4_postchange()
    fig5_summary()
    fig6_s3()
    fig7_heatmap()
    fig8_wrr_oscillation()
    print()
    print('All 8 figures saved.')
