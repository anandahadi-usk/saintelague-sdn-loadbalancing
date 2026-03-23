# controller/algorithms/wrr.py
"""
Weighted Round Robin (WRR)
Classic cyclic schedule: builds a W-slot sequence [0,0,0,1,1,1,1,1,2,2]
for weights [3,5,2]. Cycles through it indefinitely.

Weight change: rebuilds sequence from scratch, resets position to 0.
This causes slow convergence because pre-change distribution is discarded.
"""
import threading


class WRR:
    """
    WRR builds a precomputed sequence of length W=Σwᵢ.
    For weights [3,5,2]: sequence = [0,0,0,1,1,1,1,1,2,2] (10 slots).
    Flows are assigned by cycling through this sequence.
    On weight change: sequence rebuilt, position reset → convergence is slow.
    """

    name = "WRR"

    def __init__(self, weights):
        self._lock    = threading.Lock()
        self._weights = list(weights)
        self._pos     = 0
        self._sequence = []
        self._build_sequence()

    def _build_sequence(self):
        """Build cyclic W-slot sequence. Call under lock."""
        seq = []
        for i, w in enumerate(self._weights):
            seq.extend([i] * int(w))
        self._sequence = seq
        self._pos      = 0   # reset position — discards history

    def select(self, active_connections=None):
        """Select next server. Returns server index (0-based)."""
        with self._lock:
            if not self._sequence:
                return 0
            server = self._sequence[self._pos]
            self._pos = (self._pos + 1) % len(self._sequence)
            return server

    def update_weights(self, new_weights):
        """Update weights — REBUILDS sequence and resets position."""
        with self._lock:
            self._weights = list(new_weights)
            self._build_sequence()   # ← slow convergence source

    def flow_added(self, server_idx):
        pass  # WRR doesn't track active connections

    def flow_removed(self, server_idx):
        pass

    def get_state(self):
        with self._lock:
            return {
                "weights":  list(self._weights),
                "pos":      self._pos,
                "seq_len":  len(self._sequence),
            }
