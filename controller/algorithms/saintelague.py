# controller/algorithms/saintelague.py
"""
Sainte-Laguë (SL) Algorithm
Per-decision optimal proportional allocation.
Selects server i maximizing:
    Q(i) = weight[i] / (2 * cumulative_count[i] + 1)

KEY PROPERTY: cumulative_count[i] is PRESERVED across weight changes.
When weights update, quotients are immediately recomputed using existing
counts — the algorithm begins correcting distributional imbalance from
the very next flow decision, without any sequence rebuild.

Convergence after weight change [3,5,2]→[6,5,2] from n=[33,55,22]:
  Q(S1) = 6/(2×33+1) = 0.0896  ← highest → SL routes next flow here
  Q(S2) = 5/(2×55+1) = 0.0450
  Q(S3) = 2/(2×22+1) = 0.0444
Result: MAPE < 5% within ~27 flows. IWRR requires >200 flows.

Reference: Chen (2024) IEICE Trans. Fundam. E107-A(3):284-292
"""
import threading


class SainteLangue:
    """
    Sainte-Laguë greedy divisor algorithm.
    Cumulative counts preserved across weight changes → fast convergence.
    This is the structural advantage over WRR/IWRR.
    """

    name = "Sainte-Laguë"

    def __init__(self, weights):
        self._lock    = threading.Lock()
        self._weights = list(weights)
        self._counts  = [0] * len(weights)   # cumulative, NEVER reset

    def select(self, active_connections=None):
        """
        Select server maximizing Q(i) = w(i) / (2*n(i) + 1).
        Increments count for selected server.
        Returns server index (0-based).
        """
        with self._lock:
            quotients = [
                self._weights[i] / (2 * self._counts[i] + 1)
                for i in range(len(self._weights))
            ]
            best = quotients.index(max(quotients))
            self._counts[best] += 1
            return best

    def update_weights(self, new_weights):
        """
        Update weights — counts PRESERVED (no rebuild, no reset).
        Quotients immediately recomputed at next select() call.
        This is why SL converges 3-7× faster than IWRR after weight changes.
        """
        with self._lock:
            self._weights = list(new_weights)
            # ← counts NOT reset — structural convergence advantage

    def flow_added(self, server_idx):
        pass  # counts already incremented in select()

    def flow_removed(self, server_idx):
        pass  # SL uses cumulative counts, not active connections

    def get_state(self):
        with self._lock:
            total = sum(self._counts)
            return {
                "weights": list(self._weights),
                "counts":  list(self._counts),
                "total":   total,
                "quotients": [
                    self._weights[i] / (2 * self._counts[i] + 1)
                    for i in range(len(self._weights))
                ],
                "distribution": [
                    c / total if total > 0 else 0
                    for c in self._counts
                ],
            }

    def reset_counts(self):
        """Reset cumulative counts (only for testing/new experiment)."""
        with self._lock:
            self._counts = [0] * len(self._weights)
