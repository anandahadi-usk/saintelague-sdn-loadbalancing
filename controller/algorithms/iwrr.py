# controller/algorithms/iwrr.py
"""
Interleaved Weighted Round Robin (IWRR)
Uses deficit scoring to produce a tighter interleaved sequence than WRR.
For each slot k of W total slots, selects server maximizing:
    score(i, k) = wᵢ·(k+1)/W − nᵢ

For weights [3,5,2] (W=10), produces: e.g. [1,0,1,2,1,0,1,1,0,1]
(server indices — actual sequence depends on weights).

Weight change: rebuilds sequence from scratch, resets position to 0.
Causes same slow convergence problem as WRR.

Reference: Tabatabaee, Le Boudec, Boyer (2021) IEICE Trans. Commun.
"""
import threading


class IWRR:
    """
    IWRR builds a deficit-scored interleaved sequence of length W=Σwᵢ.
    Per-cycle distribution is tighter than WRR (no consecutive bursts).
    On weight change: sequence rebuilt, position reset → slow convergence.
    """

    name = "IWRR"

    def __init__(self, weights):
        self._lock    = threading.Lock()
        self._weights = list(weights)
        self._sequence = []
        self._pos      = 0
        self._build_sequence()

    def _build_sequence(self):
        """
        Build interleaved W-slot sequence using deficit scoring.
        At slot k, selects server i maximizing: wᵢ·(k+1)/W − count_given_so_far[i]
        """
        W      = sum(self._weights)
        counts = [0] * len(self._weights)
        seq    = []

        for k in range(W):
            scores = [
                self._weights[i] * (k + 1) / W - counts[i]
                for i in range(len(self._weights))
            ]
            best = scores.index(max(scores))
            seq.append(best)
            counts[best] += 1

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
        pass

    def flow_removed(self, server_idx):
        pass

    def get_state(self):
        with self._lock:
            return {
                "weights":  list(self._weights),
                "pos":      self._pos,
                "seq_len":  len(self._sequence),
                "sequence": list(self._sequence),
            }
