# mn_traffic/traffic/qos_steady_traffic.py
"""
S1 QoS Steady-State Traffic.
Sequential: one client at a time to avoid Mininet host.cmd() thread-safety issues.
Each round: QoS flow (iperf3 TCP + ping) on c1, then TCP routing flows on remaining clients.
Duration: 90s.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from mn_traffic.traffic.base_traffic import BaseTrafficGenerator, get_base_parser
from mininet.log import info


class QoSSteadyTrafficGenerator(BaseTrafficGenerator):

    def __init__(self, duration, seed, algorithm, run_id, results_dir=None):
        super().__init__(
            scenario="steady", duration=duration, seed=seed,
            algorithm=algorithm, run_id=run_id,
        )
        self._results_dir = results_dir or os.path.join(
            os.path.dirname(__file__), '../../results/raw',
            f'qos_steady_{algorithm}_run{run_id:02d}'
        )

    def _run_traffic_pattern(self):
        info(f"[P5-QoS-Steady] Starting | algo={self.algorithm} run={self.run_id}\n")

        self._open_qos_csv(self._results_dir)

        FLOW_DUR = 5
        deadline = time.time() + self.duration
        all_threads = []

        while time.time() < deadline:
            remaining = deadline - time.time()
            flow_dur  = min(FLOW_DUR, remaining - 1.0)
            if flow_dur <= 1.0:
                break

            round_threads = []

            # c1: QoS measurement flow (sequential — dedicated client, no overlap)
            def qos_round(c=self.client_hosts[0], d=flow_dur):
                self.send_flow_qos(c, d, bandwidth="3M",
                                   phase="steady", weight_change_event=0)
            qt = threading.Thread(target=qos_round, daemon=True)
            round_threads.append(qt)

            # c2..c10: TCP routing flows (parallel among themselves, different clients)
            for client in self.client_hosts[1:]:
                def tcp_round(c=client, d=flow_dur):
                    self.send_flow(c, d, bandwidth="3M", protocol="tcp")
                t = threading.Thread(target=tcp_round, daemon=True)
                round_threads.append(t)

            for t in round_threads:
                t.start()
                all_threads.append(t)

            # Wait for this round: iperf3(5s) + ping(2s) + buffer
            time.sleep(FLOW_DUR + 3.0)
            for t in round_threads:
                t.join(timeout=5.0)

        # Ensure all threads finished before teardown
        for t in all_threads:
            if t.is_alive():
                t.join(timeout=8.0)

        info(f"[P5-QoS-Steady] Done.\n")


def main():
    parser = get_base_parser("S1 QoS Steady-State")
    parser.add_argument("--results_dir", type=str, default=None)
    args = parser.parse_args()
    gen = QoSSteadyTrafficGenerator(
        duration=args.duration, seed=args.seed,
        algorithm=args.algorithm, run_id=args.run_id,
        results_dir=args.results_dir,
    )
    gen.run()


if __name__ == "__main__":
    main()
