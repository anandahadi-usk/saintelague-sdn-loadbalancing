# config/algo_config.py
"""Algorithm-specific parameters."""

ALGO_LABELS = {
    "wrr":          "WRR",
    "iwrr":         "IWRR",
    "wlc":          "WLC",
    "saintelague":  "Sainte-Laguë",
}

ALGO_COLORS = {
    "wrr":          "#d62728",   # red
    "iwrr":         "#ff7f0e",   # orange
    "wlc":          "#2ca02c",   # green
    "saintelague":  "#1f77b4",   # blue
}

ALGO_MARKERS = {
    "wrr":          "s",   # square
    "iwrr":         "^",   # triangle
    "wlc":          "D",   # diamond
    "saintelague":  "o",   # circle
}
