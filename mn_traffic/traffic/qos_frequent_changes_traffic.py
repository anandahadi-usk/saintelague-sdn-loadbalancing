# mn_traffic/traffic/qos_frequent_changes_traffic.py
"""
S3 QoS Frequent Weight Changes Traffic.
4 WC events at t=30,60,90,120s. Sequential QoS measurement, phase-tagged.
Duration: 150s.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from mn_traffic.traffic.base_traffic import BaseTrafficGenerator, get_base_parser
from config.experiment_config import SCENARIOS
from mininet.log import info


class QoSFrequentChangesTrafficGenerator(BaseTrafficGenerator):

    def __init__(self, duration, seed, algorithm, run_id, results_dir=None):
        super().__init__(
            scenario="frequent_changes", duration=duration, seed=seed,
            algorithm=algorithm, run_id=run_id,
        )
        self.changes = SCENARIOS["frequent_changes"]["weight_changes"]
        self._results_dir = results_dir or os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'results', 'raw')),
            f'qos_frequent_changes_{algorithm}_run{run_id:02d}'
        )
        self._current_phase = "steady"
        self._wc_event = 0
        self._wc_count = 0
        self._phase_lock = threading.Lock()

    def _run_traffic_pattern(self):
        info(f"[SL-SDN-QoS-S3] Starting | algo={self.algorithm} run={self.run_id}\n")

        self._open_qos_csv(self._results_dir)

        FLOW_DUR = 5
        deadline = time.time() + self.duration
        all_threads = []

        change_threads = []
        for change in self.changes:
            def make_change_t(t_delay, weights, label):
                def run():
                    time.sleep(t_delay)
                    if self.remaining() > 0:
                        with self._phase_lock:
                            self._wc_count += 1
                            self._current_phase = f"post_change_{self._wc_count}"
                            self._wc_event = 1
                        self.trigger_weight_change(weights, label)
                        info(f"[SL-SDN-QoS-S3] WC#{self._wc_count} at t={self.elapsed():.1f}s → {weights}\n")
                        time.sleep(FLOW_DUR + 2)
                        with self._phase_lock:
                            self._wc_event = 0
                return run
            ct = threading.Thread(
                target=make_change_t(change["time"], change["weights_new"], change["label"]),
                daemon=True,
            )
            change_threads.append(ct)

        for ct in change_threads:
            ct.start()

        while time.time() < deadline:
            remaining = deadline - time.time()
            flow_dur  = min(FLOW_DUR, remaining - 1.0)
            if flow_dur <= 1.0:
                break

            with self._phase_lock:
                phase_snap = self._current_phase
                wc_snap    = self._wc_event

            round_threads = []

            def qos_round(c=self.client_hosts[0], d=flow_dur, ph=phase_snap, wc=wc_snap):
                self.send_flow_qos(c, d, bandwidth="3M", phase=ph, weight_change_event=wc)
            qt = threading.Thread(target=qos_round, daemon=True)
            round_threads.append(qt)

            for client in self.client_hosts[1:]:
                def tcp_round(c=client, d=flow_dur):
                    self.send_flow(c, d, bandwidth="3M", protocol="tcp")
                t = threading.Thread(target=tcp_round, daemon=True)
                round_threads.append(t)

            for t in round_threads:
                t.start()
                all_threads.append(t)

            time.sleep(FLOW_DUR + 3.0)
            for t in round_threads:
                t.join(timeout=5.0)

        for ct in change_threads:
            ct.join(timeout=5.0)
        for t in all_threads:
            if t.is_alive():
                t.join(timeout=8.0)

        info(f"[SL-SDN-QoS-S3] Done.\n")


def main():
    parser = get_base_parser("S3 QoS Frequent Changes")
    parser.add_argument("--results_dir", type=str, default=None)
    args = parser.parse_args()
    gen = QoSFrequentChangesTrafficGenerator(
        duration=args.duration, seed=args.seed,
        algorithm=args.algorithm, run_id=args.run_id,
        results_dir=args.results_dir,
    )
    gen.run()


if __name__ == "__main__":
    main()
