# controller/main_controller.py
"""
Ryu Controller — Dynamic Weight Change Load Balancer
Supports 4 algorithms: WRR, IWRR, WLC, Sainte-Laguë

Launch example:
  ALGO=saintelague RUN_ID=1 SCENARIO=single_change RESULTS_DIR=/path/to/results \
  ryu-manager controller/main_controller.py --ofp-tcp-listen-port 6653 \
              --wsapi-host 127.0.0.1 --wsapi-port 8080

REST API:
  POST http://127.0.0.1:8080/api/weights
  Body: {"weights": [6, 5, 2], "label": "S1_upgrade"}
"""

import os
import sys
import csv
import time
import json
import threading
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp as tcp_pkt
from ryu.app.wsgi import ControllerBase, WSGIApplication, route, Response

from config.network_config import (
    VIP_IP, VIP_MAC, SERVERS, INITIAL_WEIGHTS,
    IDLE_TIMEOUT, HARD_TIMEOUT,
)

# ── Algorithm registry ──────────────────────────────────────────────────────
from controller.algorithms.wrr         import WRR
from controller.algorithms.iwrr        import IWRR
from controller.algorithms.wlc         import WLC
from controller.algorithms.saintelague import SainteLangue

ALGO_REGISTRY = {
    "wrr":         WRR,
    "iwrr":        IWRR,
    "wlc":         WLC,
    "saintelague": SainteLangue,
}

# ── Constants ────────────────────────────────────────────────────────────────
MAPE_IDEAL = [w / sum(INITIAL_WEIGHTS) for w in INITIAL_WEIGHTS]  # [0.3, 0.5, 0.2]

P5_APP_NAME = "p5_lb_controller"


def compute_mape(counts, weights):
    """Compute MAPE of current cumulative distribution vs proportional target."""
    total = sum(counts)
    if total == 0:
        return 0.0
    w_sum = sum(weights)
    ideal = [w / w_sum for w in weights]
    actual = [c / total for c in counts]
    errors = [abs(actual[i] - ideal[i]) / ideal[i] for i in range(len(weights)) if ideal[i] > 0]
    return (sum(errors) / len(errors)) * 100.0 if errors else 0.0


def compute_jfi_c(counts, weights):
    """Capacity-normalized Jain's Fairness Index."""
    phi = [counts[i] / weights[i] for i in range(len(weights)) if weights[i] > 0]
    if not phi or sum(phi) == 0:
        return 1.0
    return sum(phi) ** 2 / (len(phi) * sum(p ** 2 for p in phi))


class P5LoadBalancer(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS    = {"wsgi": WSGIApplication}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ── Config from environment ──────────────────────────────────────
        self.algo_name   = os.environ.get("ALGO",        "saintelague").lower()
        self.run_id      = int(os.environ.get("RUN_ID",   "1"))
        self.scenario    = os.environ.get("SCENARIO",    "steady")
        _default_results = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), '..')),
            "results", "raw", "default_run"
        )
        self.results_dir = os.environ.get("RESULTS_DIR", _default_results)

        os.makedirs(self.results_dir, exist_ok=True)

        # ── Algorithm instance ───────────────────────────────────────────
        AlgoClass = ALGO_REGISTRY.get(self.algo_name, SainteLangue)
        self.algo = AlgoClass(list(INITIAL_WEIGHTS))
        self.logger.info(f"[SL-SDN] Algorithm: {self.algo_name.upper()}  Run: {self.run_id}  Scenario: {self.scenario}")

        # ── State tracking ────────────────────────────────────────────────
        self._lock            = threading.Lock()
        self._weights         = list(INITIAL_WEIGHTS)
        self._cumulative      = [0, 0, 0]    # cumulative flows per server
        self._active_flows    = {}           # (src_ip, src_port) → server_idx
        self._src_ip_server   = {}           # src_ip → server_idx (session affinity)
        self._decision_num    = 0
        self._weight_changes  = []           # list of {time, weights, label, decision_num}
        self._last_change_dec = -1           # decision_num of last weight change
        self._start_time      = time.time()
        self._phase           = "pre_change" # current phase label

        # ── ARP table (server IP → MAC) ──────────────────────────────────
        self._server_macs  = {s["ip"]: s["mac"] for s in SERVERS}
        self._server_ips   = [s["ip"] for s in SERVERS]
        self._server_ids   = [s["id"] for s in SERVERS]

        # ── CSV logging ──────────────────────────────────────────────────
        fname = os.path.join(
            self.results_dir,
            f"flow_decisions_{self.scenario}_{self.algo_name}_run{self.run_id:02d}.csv"
        )
        self._csv_file = open(fname, "w", newline="")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "timestamp", "elapsed_s", "decision_num",
            "src_ip", "src_port", "proto",
            "selected_server",
            "weight_s1", "weight_s2", "weight_s3",
            "cumulative_s1", "cumulative_s2", "cumulative_s3",
            "mape", "jfi_c",
            "weight_change_event", "phase",
        ])
        self.logger.info(f"[SL-SDN] Logging to {fname}")

        # ── Flow timing CSV (flow_setup_ms per decision) ─────────────────
        tname = os.path.join(
            self.results_dir,
            f"flow_timing_{self.scenario}_{self.algo_name}_run{self.run_id:02d}.csv"
        )
        self._timing_csv_file = open(tname, "w", newline="")
        self._timing_csv_writer = csv.writer(self._timing_csv_file)
        self._timing_csv_writer.writerow([
            "decision_num", "packet_in_time", "flow_installed_time",
            "flow_setup_ms", "src_ip", "src_port", "selected_server",
        ])

        # ── Register REST API ────────────────────────────────────────────
        wsgi = kwargs["wsgi"]
        wsgi.register(P5WeightAPI, {P5_APP_NAME: self})

        # ── Datapath reference ───────────────────────────────────────────
        self._datapath = None

    # ════════════════════════════════════════════════════════════════════════
    # OpenFlow handlers
    # ════════════════════════════════════════════════════════════════════════

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def features_handler(self, ev):
        dp = ev.msg.datapath
        self._datapath = dp
        ofp = dp.ofproto; parser = dp.ofproto_parser

        # Table-miss: send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, 0, match, actions)
        self.logger.info(f"[SL-SDN] Switch connected: dpid={dp.id}")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp  = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        # ── ARP handling ─────────────────────────────────────────────────
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            self._handle_arp(dp, in_port, eth, arp_pkt)
            return

        # ── IPv4 / TCP handling ──────────────────────────────────────────
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt and ip_pkt.dst == VIP_IP:
            tcp_p = pkt.get_protocol(tcp_pkt.tcp)
            if tcp_p:
                self._handle_tcp(dp, in_port, eth, ip_pkt, tcp_p, msg)

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        """Update WLC active count when a flow expires."""
        msg = ev.msg
        match = msg.match
        src_ip   = match.get("ipv4_src")
        src_port = match.get("tcp_src")
        if src_ip and src_port:
            key = (src_ip, src_port)
            with self._lock:
                if key in self._active_flows:
                    srv_idx = self._active_flows.pop(key)
                    self.algo.flow_removed(srv_idx)
                    # Clear src_ip affinity when no more active flows from this IP
                    if not any(k[0] == src_ip for k in self._active_flows):
                        self._src_ip_server.pop(src_ip, None)

    # ════════════════════════════════════════════════════════════════════════
    # ARP proxy
    # ════════════════════════════════════════════════════════════════════════

    def _handle_arp(self, dp, in_port, eth, arp_pkt):
        """Reply to ARP requests for VIP with VIP_MAC."""
        if arp_pkt.opcode != arp.ARP_REQUEST:
            return
        if arp_pkt.dst_ip != VIP_IP:
            return

        ofp = dp.ofproto; parser = dp.ofproto_parser

        reply_pkt = packet.Packet()
        reply_pkt.add_protocol(ethernet.ethernet(
            ethertype=eth.ethertype,
            dst=eth.src, src=VIP_MAC,
        ))
        reply_pkt.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=VIP_MAC, src_ip=VIP_IP,
            dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip,
        ))
        reply_pkt.serialize()

        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(
            datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
            in_port=ofp.OFPP_CONTROLLER,
            actions=actions, data=reply_pkt.data,
        )
        dp.send_msg(out)

    # ════════════════════════════════════════════════════════════════════════
    # TCP flow routing
    # ════════════════════════════════════════════════════════════════════════

    def _handle_tcp(self, dp, in_port, eth, ip_pkt, tcp_p, msg):
        """Route new TCP flow to a server via the active algorithm."""
        src_ip     = ip_pkt.src
        src_port   = tcp_p.src_port
        key        = (src_ip, src_port)
        t_packet_in = time.time()   # precise packet-in timestamp

        with self._lock:
            # Skip duplicate (flow already installed)
            if key in self._active_flows:
                return

            # Session affinity: if this src_ip already has an active flow,
            # route all its connections to the same server.
            # This is required for iperf3 which opens 2 TCP connections
            # (control + data) to the same VIP — both must reach the same backend.
            if src_ip in self._src_ip_server:
                srv_idx = self._src_ip_server[src_ip]
            else:
                # Select server via algorithm
                active = [self.algo._active[i] if hasattr(self.algo, '_active') else 0
                          for i in range(3)]
                srv_idx = self.algo.select(active_connections=active)
                self._src_ip_server[src_ip] = srv_idx

            # Update state
            self._cumulative[srv_idx] += 1
            self._decision_num        += 1
            self._active_flows[key]    = srv_idx
            self.algo.flow_added(srv_idx)

            # Detect weight_change_event (first flow after weight change)
            wc_event = (self._decision_num == self._last_change_dec + 1 and
                        self._last_change_dec >= 0)

            # Compute metrics
            mape  = compute_mape(self._cumulative, self._weights)
            jfi_c = compute_jfi_c(self._cumulative, self._weights)
            ts    = time.time()
            elapsed = round(ts - self._start_time, 3)

            # Log (flow_setup_ms will be appended after _install_flow)
            self._csv_writer.writerow([
                round(ts, 3), elapsed, self._decision_num,
                src_ip, src_port, "tcp",
                srv_idx + 1,          # 1-based server ID
                self._weights[0], self._weights[1], self._weights[2],
                self._cumulative[0], self._cumulative[1], self._cumulative[2],
                round(mape, 4), round(jfi_c, 6),
                int(wc_event), self._phase,
            ])
            self._csv_file.flush()
            current_decision = self._decision_num

        # Install flow rule on switch and measure setup latency
        server = SERVERS[srv_idx]
        self._install_flow(dp, in_port, src_ip, src_port, server, msg)
        t_installed = time.time()
        flow_setup_ms = round((t_installed - t_packet_in) * 1000, 3)

        # Log flow setup latency to separate timing CSV
        if hasattr(self, '_timing_csv_writer') and self._timing_csv_writer:
            with self._lock:
                self._timing_csv_writer.writerow([
                    current_decision, round(t_packet_in, 6),
                    round(t_installed, 6), flow_setup_ms,
                    src_ip, src_port, srv_idx + 1,
                ])
                self._timing_csv_file.flush()

    def _install_flow(self, dp, in_port, src_ip, src_port, server, msg):
        """Install DNAT (forward) and SNAT (reverse) flow rules."""
        ofp = dp.ofproto; parser = dp.ofproto_parser

        # Determine exact switch port for this server (srv_id is 1-based, port = srv_id).
        # Topology order: srv1→port1, srv2→port2, srv3→port3, c1→port4, ...
        # Use specific output ports to avoid OFPP_NORMAL (broken in controller mode)
        # and OFPP_FLOOD (unreliable across OVS versions).
        server_port = server["id"]   # 1, 2, or 3
        client_port = in_port        # already known from packet_in

        # ── Forward: client → VIP → server (DNAT) ────────────────────────
        match_fwd = parser.OFPMatch(
            in_port=in_port,
            eth_type=0x0800,
            ip_proto=6,
            ipv4_src=src_ip,
            ipv4_dst=VIP_IP,
            tcp_src=src_port,
        )
        actions_fwd = [
            parser.OFPActionSetField(ipv4_dst=server["ip"]),
            parser.OFPActionSetField(eth_dst=server["mac"]),
            parser.OFPActionOutput(server_port),
        ]
        self._add_flow(
            dp, 10, match_fwd, actions_fwd,
            idle_timeout=IDLE_TIMEOUT,
            hard_timeout=HARD_TIMEOUT,
            flags=ofp.OFPFF_SEND_FLOW_REM,
        )

        # ── Reverse: server → client (SNAT: masquerade src as VIP) ───────
        match_rev = parser.OFPMatch(
            in_port=server_port,
            eth_type=0x0800,
            ip_proto=6,
            ipv4_src=server["ip"],
            ipv4_dst=src_ip,
            tcp_dst=src_port,
        )
        actions_rev = [
            parser.OFPActionSetField(ipv4_src=VIP_IP),
            parser.OFPActionSetField(eth_src=VIP_MAC),
            parser.OFPActionOutput(client_port),
        ]
        self._add_flow(
            dp, 10, match_rev, actions_rev,
            idle_timeout=IDLE_TIMEOUT,
            hard_timeout=HARD_TIMEOUT,
        )

        # Send buffered packet (forward)
        if msg.buffer_id != ofp.OFP_NO_BUFFER:
            out = parser.OFPPacketOut(
                datapath=dp, buffer_id=msg.buffer_id,
                in_port=in_port, actions=actions_fwd, data=None,
            )
        else:
            out = parser.OFPPacketOut(
                datapath=dp, buffer_id=ofp.OFP_NO_BUFFER,
                in_port=in_port, actions=actions_fwd, data=msg.data,
            )
        dp.send_msg(out)

    # ════════════════════════════════════════════════════════════════════════
    # Weight update (called from REST API)
    # ════════════════════════════════════════════════════════════════════════

    def apply_weight_change(self, new_weights, label=""):
        """
        Update algorithm weights. Records change timestamp and decision number.
        Thread-safe — called from WSGI thread.
        """
        with self._lock:
            old = list(self._weights)
            self._weights = list(new_weights)
            self.algo.update_weights(new_weights)
            self._last_change_dec = self._decision_num
            # Clear session affinity so next flow from each client is
            # re-assigned using updated weights. Without this, all clients
            # remain locked to their pre-change server → algo.select() is
            # never called again → distribution stays frozen at old ratio.
            self._src_ip_server.clear()
            ts = time.time()
            elapsed = round(ts - self._start_time, 3)

            # Update phase label
            change_num = len(self._weight_changes) + 1
            self._phase = f"post_change_{change_num}"

            record = {
                "change_num":    change_num,
                "elapsed_s":     elapsed,
                "decision_num":  self._decision_num,
                "weights_before": old,
                "weights_after":  list(new_weights),
                "label":         label,
                "mape_at_change": compute_mape(self._cumulative, new_weights),
            }
            self._weight_changes.append(record)

            self.logger.info(
                f"[SL-SDN] Weight change #{change_num} at t={elapsed:.1f}s "
                f"(flow #{self._decision_num}): {old} → {new_weights}  "
                f"MAPE={record['mape_at_change']:.2f}%  label={label}"
            )
        return record

    def get_status(self):
        """Return current controller status for REST API."""
        with self._lock:
            return {
                "algorithm":      self.algo_name,
                "run_id":         self.run_id,
                "scenario":       self.scenario,
                "elapsed_s":      round(time.time() - self._start_time, 1),
                "decision_num":   self._decision_num,
                "weights":        list(self._weights),
                "cumulative":     list(self._cumulative),
                "mape":           round(compute_mape(self._cumulative, self._weights), 4),
                "jfi_c":          round(compute_jfi_c(self._cumulative, self._weights), 6),
                "weight_changes": self._weight_changes,
                "phase":          self._phase,
            }

    def close(self):
        """Flush and close CSV files on shutdown."""
        for f in [self._csv_file, self._timing_csv_file]:
            try:
                f.flush()
                f.close()
            except Exception:
                pass
        super().close()

    # ════════════════════════════════════════════════════════════════════════
    # Helpers
    # ════════════════════════════════════════════════════════════════════════

    def _add_flow(self, dp, priority, match, actions,
                  idle_timeout=0, hard_timeout=0, flags=0):
        ofp = dp.ofproto; parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=dp, priority=priority,
            match=match, instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            flags=flags,
        )
        dp.send_msg(mod)


# ════════════════════════════════════════════════════════════════════════════
# REST API
# ════════════════════════════════════════════════════════════════════════════

class P5WeightAPI(ControllerBase):
    """Ryu WSGI REST API for weight updates."""

    def __init__(self, req, link, data, **config):
        super().__init__(req, link, data, **config)
        self.app: P5LoadBalancer = data[P5_APP_NAME]

    @route("p5_weights", "/api/weights", methods=["POST"])
    def update_weights(self, req, **kwargs):
        """
        POST /api/weights
        Body: {"weights": [6, 5, 2], "label": "S1_upgrade"}
        Returns: {"ok": true, "record": {...}}
        """
        try:
            body = req.json if req.content_type == "application/json" else json.loads(req.body)
            weights = [int(w) for w in body.get("weights", [])]
            label   = body.get("label", "")
            if len(weights) != 3 or any(w <= 0 for w in weights):
                raise ValueError(f"Invalid weights: {weights}")
            record = self.app.apply_weight_change(weights, label)
            body_str = json.dumps({"ok": True, "record": record})
        except Exception as e:
            body_str = json.dumps({"ok": False, "error": str(e)})
        return Response(content_type="application/json", body=body_str)

    @route("p5_status", "/api/status", methods=["GET"])
    def get_status(self, req, **kwargs):
        """GET /api/status — returns current controller state."""
        body_str = json.dumps(self.app.get_status())
        return Response(content_type="application/json", body=body_str)
