# mn_traffic/traffic/base_traffic.py
"""
Base traffic generator.
Manages Mininet hosts, iperf3 flows, REST API weight change calls.
"""
import os
import sys
import time
import json
import subprocess
import threading
import argparse
import random
import csv
import statistics

# Mininet is system-installed
sys.path.insert(0, '/usr/lib/python3/dist-packages')

from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.link import TCLink

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
from config.network_config import (
    VIP_IP, VIP_MAC, SERVERS, CLIENT_BASE, CLIENT_START, NUM_CLIENTS,
    RYU_REST_HOST, RYU_REST_PORT, OF_PORT,
)
from config.experiment_config import SCENARIOS, CONVERGENCE_MAPE_THRESHOLD


class P5Topology(Topo):
    """Single switch, 3 servers, 10 clients topology."""

    def build(self, **opts):
        sw = self.addSwitch("s1", cls=OVSSwitch, protocols="OpenFlow13")

        # Servers
        for s in SERVERS:
            host = self.addHost(
                f"srv{s['id']}",
                ip=f"{s['ip']}/24",
                mac=s["mac"],
            )
            self.addLink(host, sw, bw=s["capacity_mbps"])

        # Clients: 10.0.0.10 – 10.0.0.19 (same subnet as servers)
        for i in range(1, NUM_CLIENTS + 1):
            host = self.addHost(
                f"c{i}",
                ip=f"{CLIENT_BASE}{CLIENT_START + i - 1}/24",
                mac=f"00:00:01:00:00:{i:02x}",
            )
            self.addLink(host, sw, bw=100)


class BaseTrafficGenerator:
    """
    Base class for traffic generators.
    Subclasses implement _run_traffic_pattern().
    """

    # iperf3 port pool — 13 ports to avoid collisions
    _PORT_POOL = list(range(5201, 5214))

    def __init__(self, scenario: str, duration: int, seed: int,
                 algorithm: str, run_id: int):
        self.scenario   = scenario
        self.duration   = duration
        self.seed       = seed
        self.algorithm  = algorithm
        self.run_id     = run_id
        self._start_time = None

        random.seed(seed)

        # Scenario config
        self.scenario_cfg = SCENARIOS[scenario]

        # Port pool management
        self._port_lock    = threading.Lock()
        self._used_ports   = set()
        self._port_counter = 0

        # Mininet objects (set during run())
        self.net            = None
        self.client_hosts   = []
        self.server_hosts   = []

        # QoS CSV logging (set during run())
        self._qos_csv_file   = None
        self._qos_csv_writer = None
        self._qos_lock       = threading.Lock()
        self._qos_seq        = 0   # per-flow QoS sequence number

    # ── Timing helpers ────────────────────────────────────────────────────

    def elapsed(self) -> float:
        return time.time() - self._start_time if self._start_time else 0.0

    def remaining(self) -> float:
        return max(0.0, self.duration - self.elapsed())

    # ── Port management ───────────────────────────────────────────────────

    def _get_port(self) -> int:
        with self._port_lock:
            p = self._PORT_POOL[self._port_counter % len(self._PORT_POOL)]
            self._port_counter += 1
            return p

    # ── REST API helpers ──────────────────────────────────────────────────

    def _api_url(self, path: str) -> str:
        return f"http://{RYU_REST_HOST}:{RYU_REST_PORT}{path}"

    def trigger_weight_change(self, new_weights: list, label: str = "") -> bool:
        """Send POST /api/weights to controller. Returns True on success."""
        payload = json.dumps({"weights": new_weights, "label": label}).encode()
        try:
            result = subprocess.run(
                ["curl", "-s", "-X", "POST",
                 "-H", "Content-Type: application/json",
                 "-d", payload.decode(),
                 self._api_url("/api/weights")],
                capture_output=True, text=True, timeout=5,
            )
            resp = json.loads(result.stdout)
            if resp.get("ok"):
                info(f"[SL-SDN] Weight change triggered: {new_weights}  label={label}\n")
                return True
            else:
                info(f"[SL-SDN] Weight change FAILED: {resp}\n")
                return False
        except Exception as e:
            info(f"[SL-SDN] Weight change error: {e}\n")
            return False

    def get_status(self) -> dict:
        """GET /api/status from controller."""
        try:
            result = subprocess.run(
                ["curl", "-s", self._api_url("/api/status")],
                capture_output=True, text=True, timeout=3,
            )
            return json.loads(result.stdout)
        except Exception:
            return {}

    # ── iperf3 flow ───────────────────────────────────────────────────────

    def send_flow(self, client_host, duration: float,
                  bandwidth: str = "3M", protocol: str = "tcp",
                  port: int = None) -> dict:
        """
        Send one iperf3 flow from client_host to VIP.
        Returns dict with {throughput_mbps, duration, error}.
        """
        if port is None:
            port = self._get_port()
        if duration <= 0:
            return {"throughput_mbps": 0.0, "error": "duration<=0"}

        # Start iperf3 server on a random server (controller will route)
        # Actually: server side is handled by Mininet server hosts
        # Client sends to VIP_IP — controller routes to a server
        proto_flag = "-u" if protocol == "udp" else ""
        cmd = (
            f"iperf3 -c {VIP_IP} -p {port} -t {duration:.1f} "
            f"-b {bandwidth} {proto_flag} -J 2>/dev/null"
        )
        try:
            out = client_host.cmd(cmd)
            data = json.loads(out)
            bps = data.get("end", {}).get("sum_received", {}).get("bits_per_second", 0)
            return {
                "throughput_mbps": round(bps / 1e6, 4),
                "duration":        duration,
                "error":           None,
            }
        except Exception as e:
            return {"throughput_mbps": 0.0, "duration": duration, "error": str(e)}

    def send_flow_qos(self, client_host, duration: float,
                     bandwidth: str = "3M", phase: str = "steady",
                     weight_change_event: int = 0, port: int = None) -> dict:
        """
        Send one iperf3 TCP flow to VIP (triggers controller routing + flow rule install).
        Collects QoS from iperf3 -J: throughput, RTT (latency), retransmits (loss proxy).
        Also measures jitter via separate ping sequence.
        Writes results to qos_metrics CSV.
        Returns dict with all QoS metrics.
        """
        if port is None:
            port = self._get_port()
        if duration <= 0:
            return {}

        # ── TCP flow to VIP: throughput + RTT (from TCP stack) + retransmits ─
        # Controller routes TCP → installs DNAT rule → iperf3 server on backend receives
        cmd_tcp = (
            f"iperf3 -c {VIP_IP} -p {port} -t {duration:.1f} "
            f"-b {bandwidth} -J 2>&1"
        )
        # ── Jitter: ping sequence to VIP (uses the installed flow rule path) ─
        # 10 packets at 0.2s = 2s total; mdev from ping = jitter proxy
        cmd_ping = f"ping -c 10 -i 0.2 -W 1 {VIP_IP} 2>&1"

        throughput_mbps = 0.0
        retransmits     = 0
        rtt_mean_ms     = 0.0
        rtt_min_ms      = 0.0
        rtt_max_ms      = 0.0
        lat_avg = lat_min = lat_max = lat_mdev = 0.0
        loss_pct = 0.0

        t0 = time.time()

        # Run TCP flow (this triggers controller routing decision)
        try:
            out = client_host.cmd(cmd_tcp)
            data = json.loads(out)
            end  = data.get("end", {})
            # Throughput from receiver side
            bps = end.get("sum_received", {}).get("bits_per_second", 0)
            throughput_mbps = round(bps / 1e6, 4)
            # Retransmits (packet loss proxy)
            retransmits = int(end.get("sum_sent", {}).get("retransmits", 0))
            total_pkts  = int(end.get("sum_sent", {}).get("bytes", 1)) // 1460 or 1
            loss_pct    = round(retransmits / max(total_pkts, 1) * 100, 4)
            # RTT from TCP stack (microseconds → ms)
            streams = end.get("streams", [{}])
            if streams:
                sender = streams[0].get("sender", {})
                rtt_mean_ms = round(sender.get("mean_rtt", 0) / 1000, 4)
                rtt_min_ms  = round(sender.get("min_rtt",  0) / 1000, 4)
                rtt_max_ms  = round(sender.get("max_rtt",  0) / 1000, 4)
            # iperf3 error field (e.g. "unable to connect to server")
            if data.get("error"):
                info(f"[SL-SDN-QoS] iperf3 error on {getattr(client_host,'name','?')}:{port} "
                     f"→ {data['error']}\n")
        except Exception as e:
            info(f"[SL-SDN-QoS] iperf3 parse error on {getattr(client_host,'name','?')}:{port} "
                 f"({e}) raw={repr(out[:200]) if 'out' in dir() else 'N/A'}\n")

        # Measure jitter/latency via ping (after flow rule is installed)
        try:
            out = client_host.cmd(cmd_ping)
            for line in out.splitlines():
                if "rtt" in line or "round-trip" in line:
                    parts = line.split("=")[-1].strip().split("/")
                    lat_min  = float(parts[0])
                    lat_avg  = float(parts[1])
                    lat_max  = float(parts[2].split()[0])
                    if len(parts) > 3:
                        lat_mdev = float(parts[3].split()[0])
                    break
            # Extract packet loss from ping output — only override iperf3-based
            # loss_pct if ping shows partial loss (<100%). 100% ping loss means
            # ICMP is unrouted (controller handles TCP only), not real TCP loss.
            for line in out.splitlines():
                if "packet loss" in line:
                    for token in line.split():
                        if "%" in token:
                            try:
                                ping_loss = float(token.replace("%", "").replace(",", ""))
                                if ping_loss < 100.0:
                                    loss_pct = ping_loss
                            except ValueError:
                                pass
                            break
        except Exception:
            pass

        # Use ping RTT if iperf3 TCP RTT not available
        if lat_avg > 0 and rtt_mean_ms == 0:
            rtt_mean_ms = lat_avg
            rtt_min_ms  = lat_min
            rtt_max_ms  = lat_max

        elapsed = round(time.time() - (self._start_time or t0), 3)

        # jitter_ms: mdev from ping (standard deviation of RTT = jitter proxy)
        jitter_ms = lat_mdev

        qos = {
            "elapsed_s":       elapsed,
            "client_id":       getattr(client_host, "name", "?"),
            "port":            port,
            "throughput_mbps": throughput_mbps,
            "latency_avg_ms":  lat_avg if lat_avg > 0 else rtt_mean_ms,
            "latency_min_ms":  lat_min if lat_min > 0 else rtt_min_ms,
            "latency_max_ms":  lat_max if lat_max > 0 else rtt_max_ms,
            "latency_mdev_ms": lat_mdev,
            "jitter_ms":       jitter_ms,
            "packet_loss_pct": loss_pct,
            "retransmits":     retransmits,
            "rtt_tcp_mean_ms": rtt_mean_ms,
            "phase":           phase,
            "weight_change_event": weight_change_event,
        }

        # Write to QoS CSV
        if self._qos_csv_writer is not None:
            with self._qos_lock:
                self._qos_seq += 1
                self._qos_csv_writer.writerow([
                    self._qos_seq, round(time.time(), 3), elapsed,
                    qos["client_id"], port,
                    throughput_mbps,
                    qos["latency_avg_ms"], lat_min, lat_max, lat_mdev,
                    jitter_ms, loss_pct, retransmits, rtt_mean_ms,
                    phase, weight_change_event,
                ])
                self._qos_csv_file.flush()

        return qos

    def measure_latency(self, client_host, count: int = 5) -> dict:
        """Ping VIP, return avg/min/max latency ms."""
        try:
            out = client_host.cmd(f"ping -c {count} -W 1 {VIP_IP} 2>/dev/null")
            for line in out.splitlines():
                if "rtt" in line or "round-trip" in line:
                    parts = line.split("=")[-1].strip().split("/")
                    return {
                        "latency_min": float(parts[0]),
                        "latency_avg": float(parts[1]),
                        "latency_max": float(parts[2].split()[0]),
                    }
        except Exception:
            pass
        return {"latency_min": 0.0, "latency_avg": 0.0, "latency_max": 0.0}

    # ── Mininet setup / teardown ──────────────────────────────────────────

    def _setup_network(self):
        """Build and start Mininet network."""
        setLogLevel("warning")
        topo = P5Topology()
        self.net = Mininet(
            topo=topo,
            controller=RemoteController("c0", ip="127.0.0.1", port=OF_PORT),
            switch=OVSSwitch,
            link=TCLink,
            autoSetMacs=False,
            autoStaticArp=False,
        )
        self.net.start()

        # Collect host references
        self.server_hosts = [self.net.get(f"srv{s['id']}") for s in SERVERS]
        self.client_hosts = [self.net.get(f"c{i}") for i in range(1, NUM_CLIENTS + 1)]

        # Static ARP for VIP on all clients — use actual VIP_MAC (unicast).
        # MUST NOT use broadcast (ff:ff:ff:ff:ff:ff): broadcast causes OVS to
        # flood the TCP SYN to all ports simultaneously, racing with SNAT rule
        # installation → SYN-ACK arrives before SNAT rule is ready → dropped.
        for client in self.client_hosts:
            client.cmd(f'arp -s {VIP_IP} {VIP_MAC}')

        # Static ARP on servers for all client IPs — servers must know client MACs
        # to send TCP SYN-ACK replies. Controller only handles ARP for VIP_IP;
        # non-VIP ARP requests are silently dropped → without this, SYN-ACK never sent.
        for srv in self.server_hosts:
            for client in self.client_hosts:
                srv.cmd(f'arp -s {client.IP()} {client.MAC()}')

        # Start iperf3 servers on each server host (no --one-off: keep running after each test)
        for srv in self.server_hosts:
            for port in self._PORT_POOL:
                srv.cmd(f"iperf3 -s -p {port} -D 2>/dev/null")

        # Allow time for controller to connect
        time.sleep(3)
        info(f"[SL-SDN] Network ready | algo={self.algorithm} run={self.run_id}\n")

    def _open_qos_csv(self, results_dir: str):
        """Open QoS metrics CSV for this run."""
        os.makedirs(results_dir, exist_ok=True)
        fname = os.path.join(
            results_dir,
            f"qos_metrics_{self.scenario}_{self.algorithm}_run{self.run_id:02d}.csv"
        )
        self._qos_csv_file = open(fname, "w", newline="")
        self._qos_csv_writer = csv.writer(self._qos_csv_file)
        self._qos_csv_writer.writerow([
            "seq", "timestamp", "elapsed_s",
            "client_id", "port",
            "throughput_mbps",
            "latency_avg_ms", "latency_min_ms", "latency_max_ms", "latency_mdev_ms",
            "jitter_ms", "packet_loss_pct", "retransmits", "rtt_tcp_mean_ms",
            "phase", "weight_change_event",
        ])

    def _close_qos_csv(self):
        if self._qos_csv_file:
            self._qos_csv_file.close()
            self._qos_csv_file   = None
            self._qos_csv_writer = None

    def _teardown_network(self):
        """Stop iperf3 servers and Mininet."""
        self._close_qos_csv()
        if self.net:
            for srv in self.server_hosts:
                srv.cmd("pkill -f iperf3 2>/dev/null")
            time.sleep(1)
            self.net.stop()

    # ── Main entry point ──────────────────────────────────────────────────

    def run(self):
        """Set up network, run traffic pattern, tear down."""
        self._setup_network()
        self._start_time = time.time()
        try:
            self._run_traffic_pattern()
        finally:
            self._teardown_network()

    def _run_traffic_pattern(self):
        """Override in subclass."""
        raise NotImplementedError


def get_base_parser(description: str = "Traffic Generator") -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--duration",  type=int,  default=90)
    p.add_argument("--seed",      type=int,  default=42)
    p.add_argument("--algorithm", type=str,  default="saintelague")
    p.add_argument("--run_id",    type=int,  default=1)
    p.add_argument("--scenario",  type=str,  default="steady")
    return p
