# mn_traffic/traffic/steady_traffic.py
"""
S1: Steady-State Traffic
No weight changes. All clients send TCP flows at 3 Mbps.
Validates that all 4 algorithms are equivalent under stable conditions.
Duration: 90s. Flows: 5s each, all clients in parallel rounds.
"""
import sys, os, time, threading
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from mn_traffic.traffic.base_traffic import BaseTrafficGenerator, get_base_parser
from mininet.log import info


class SteadyTrafficGenerator(BaseTrafficGenerator):

    def __init__(self, duration, seed, algorithm, run_id):
        super().__init__(
            scenario="steady", duration=duration, seed=seed,
            algorithm=algorithm, run_id=run_id,
        )

    def _run_traffic_pattern(self):
        info(f"[SL-SDN-S1] Starting | algo={self.algorithm} run={self.run_id} dur={self.duration}s\n")
        FLOW_DUR = 5
        deadline = time.time() + self.duration

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

        info(f"[SL-SDN-S1] Done.\n")


def main():
    parser = get_base_parser("S1 Steady-State")
    args = parser.parse_args()
    gen = SteadyTrafficGenerator(
        duration=args.duration, seed=args.seed,
        algorithm=args.algorithm, run_id=args.run_id,
    )
    gen.run()


if __name__ == "__main__":
    main()
