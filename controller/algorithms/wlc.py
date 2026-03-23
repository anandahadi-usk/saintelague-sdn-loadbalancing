# controller/algorithms/wlc.py
"""
Weighted Least Connections (WLC)
Routes each new flow to the server with the lowest ratio:
    score(i) = active_connections[i] / weight[i]

Unlike WRR/IWRR, WLC reacts immediately to weight changes because
it uses the current weight in the ratio computation.
However, WLC optimizes ACTIVE connections (instantaneous), not
CUMULATIVE flow distribution (what MAPE measures).

Weight change behavior:
- No sequence to rebuild → immediate routing adjustment
- BUT: cumulative MAPE may still be elevated because historical
  assignments are not corrected — only future flows are affected.
- Active-connection count is preserved, weight ratio updated immediately.
"""
import threading


class WLC:
    """
    WLC selects the server minimizing active_connections[i] / weight[i].
    Adapts to weight changes immediately (no rebuild needed).
    Does not track cumulative flow counts — different fairness semantics.
    """

    name = "WLC"

    def __init__(self, weights):
        self._lock    = threading.Lock()
        self._weights = list(weights)
        self._active  = [0] * len(weights)   # active connections per server

    def select(self, active_connections=None):
        """
        Select server with lowest active/weight ratio.
        active_connections: optional override (list of int per server).
        Returns server index (0-based).
        """
        with self._lock:
            if active_connections is not None:
                # Use provided active connection counts (from flow table stats)
                active = active_connections
            else:
                active = self._active

            scores = [
                active[i] / max(self._weights[i], 1)
                for i in range(len(self._weights))
            ]
            return scores.index(min(scores))

    def update_weights(self, new_weights):
        """
        Update weights — immediate effect, no sequence rebuild.
        Active connections preserved — ratio recalculated at next select().
        """
        with self._lock:
            self._weights = list(new_weights)
            # No rebuild, no position reset — WLC adapts immediately

    def flow_added(self, server_idx):
        """Called when a new flow is installed to server_idx."""
        with self._lock:
            if 0 <= server_idx < len(self._active):
                self._active[server_idx] += 1

    def flow_removed(self, server_idx):
        """Called when a flow expires/is removed from server_idx."""
        with self._lock:
            if 0 <= server_idx < len(self._active):
                if self._active[server_idx] > 0:
                    self._active[server_idx] -= 1

    def get_state(self):
        with self._lock:
            return {
                "weights": list(self._weights),
                "active":  list(self._active),
                "scores":  [
                    self._active[i] / max(self._weights[i], 1)
                    for i in range(len(self._weights))
                ],
            }
