# config/experiment_config.py
"""
Experiment scenarios and weight change schedules for P5.

3 scenarios:
  S1: Steady-State       — no weight changes, validates baseline equivalence
  S2: Single Change      — one weight change at t=45s
  S3: Frequent Changes   — weight changes every 30s (compounding stress test)
"""

ALGORITHMS = ["wrr", "iwrr", "wlc", "saintelague"]

SCENARIOS = {
    # ── S1: Steady-State ──────────────────────────────────────────────────
    "steady": {
        "label":        "S1 Steady-State",
        "duration":     90,           # seconds
        "runs":         15,
        "weight_changes": [],         # no changes
        "traffic": {
            "rate_mbps":    3,        # per client
            "protocol":     "tcp",
            "flow_interval": 5,       # seconds between flow rounds
        },
        "description": "Baseline: all 4 algorithms should be equivalent. "
                       "Validates experimental setup.",
    },

    # ── S2: Single Weight Change ──────────────────────────────────────────
    "single_change": {
        "label":    "S2 Single Weight Change",
        "duration": 120,          # seconds
        "runs":     20,
        "weight_changes": [
            {
                "time":        45,            # seconds after experiment start
                "weights_new": [6, 5, 2],     # S1: 30→60 Mbps (capacity doubled)
                "label":       "S1_upgrade",
                "description": "Server S1 capacity doubles (30→60 Mbps). "
                               "New ideal ratio: 6:5:2 = 46.2%:38.5%:15.4%",
            },
        ],
        "traffic": {
            "rate_mbps":    3,
            "protocol":     "tcp",
            "flow_interval": 4,
        },
        "description": "S1 capacity doubles at t=45s. Measures convergence trajectory "
                       "and recovery time for each algorithm.",
    },

    # ── S3: Frequent Weight Changes ───────────────────────────────────────
    "frequent_changes": {
        "label":    "S3 Frequent Weight Changes",
        "duration": 150,          # seconds
        "runs":     20,
        "weight_changes": [
            {
                "time":        30,
                "weights_new": [6, 5, 2],
                "label":       "change_1",
                "description": "S1 upgrade: [3,5,2]→[6,5,2]",
            },
            {
                "time":        60,
                "weights_new": [3, 5, 2],
                "label":       "change_2",
                "description": "Revert: [6,5,2]→[3,5,2]",
            },
            {
                "time":        90,
                "weights_new": [3, 8, 2],
                "label":       "change_3",
                "description": "S2 upgrade: [3,5,2]→[3,8,2]",
            },
            {
                "time":        120,
                "weights_new": [3, 5, 2],
                "label":       "change_4",
                "description": "Revert: [3,8,2]→[3,5,2]",
            },
        ],
        "traffic": {
            "rate_mbps":    3,
            "protocol":     "tcp",
            "flow_interval": 4,
        },
        "description": "4 weight changes every 30s. Tests compounding effect: "
                       "WRR/IWRR never fully converge before next change.",
    },
}

# ── Statistical thresholds ────────────────────────────────────────────────
CONVERGENCE_MAPE_THRESHOLD = 5.0   # % — MAPE < this = converged
SIGNIFICANCE_ALPHA         = 0.05
