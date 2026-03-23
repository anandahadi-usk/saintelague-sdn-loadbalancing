# mn_traffic/traffic/frequent_change_traffic.py
"""
S3: Frequent Weight Changes Traffic
4 weight changes every 30s: [3,5,2]→[6,5,2]→[3,5,2]→[3,8,2]→[3,5,2]
Tests compounding effect: WRR/IWRR never fully converge before next change.
Duration: 150s.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from mn_traffic.traffic.base_traffic import BaseTrafficGenerator, get_base_parser
from config.experiment_config import SCENARIOS
from mininet.log import info


class FrequentChangeTrafficGenerator(BaseTrafficGenerator):

    def __init__(self, duration, seed, algorithm, run_id):
        super().__init__(
            scenario="frequent_changes", duration=duration, seed=seed,
            algorithm=algorithm, run_id=run_id,
        )
        self.changes = SCENARIOS["frequent_changes"]["weight_changes"]

    def _run_traffic_pattern(self):
        info(f"[SL-SDN-S3] Starting | algo={self.algorithm} "
             f"run={self.run_id} dur={self.duration}s\n")
        info(f"[SL-SDN-S3] 4 weight changes at t=30,60,90,120s\n")

        FLOW_DUR = 4
        deadline = time.time() + self.duration

        # Schedule all weight change threads
        change_threads = []
        for change in self.changes:
            def make_change_t(t_delay, weights, label):
                def run():
                    time.sleep(t_delay)
                    if self.remaining() > 0:
                        self.trigger_weight_change(weights, label)
                        info(f"[SL-SDN-S3] ⚡ t={self.elapsed():.1f}s "
                             f"→ {weights}  label={label}\n")
                return run
            ct = threading.Thread(
                target=make_change_t(change["time"], change["weights_new"], change["label"]),
                daemon=True,
            )
            change_threads.append(ct)

        for ct in change_threads:
            ct.start()

        # Main traffic loop
        while time.time() < deadline:
            threads = []
            for client in self.client_hosts:
                remaining = deadline - time.time()
                flow_dur  = min(FLOW_DUR, remaining - 0.5)
                if flow_dur <= 0:
                    break

                def make_t(c, d):
                    def run():
                        self.send_flow(c, d, bandwidth="3M", protocol="tcp")
                    return run

                t = threading.Thread(target=make_t(client, flow_dur), daemon=True)
                threads.append(t)

            for t in threads:
                t.start()
            time.sleep(FLOW_DUR + 0.5)
            for t in threads:
                t.join(timeout=1.0)

        for ct in change_threads:
            ct.join(timeout=5.0)

        info(f"[SL-SDN-S3] Done.\n")


def main():
    parser = get_base_parser("S3 Frequent Weight Changes")
    args = parser.parse_args()
    gen = FrequentChangeTrafficGenerator(
        duration=args.duration, seed=args.seed,
        algorithm=args.algorithm, run_id=args.run_id,
    )
    gen.run()


if __name__ == "__main__":
    main()
