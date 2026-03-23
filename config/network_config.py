# config/network_config.py
"""
Network topology configuration.
3-server heterogeneous SDN topology.
"""

# VIP (Virtual IP) — all clients send traffic here
VIP_IP   = "10.0.0.100"
VIP_MAC  = "00:00:00:00:01:00"

# Server definitions
SERVERS = [
    {"id": 1, "ip": "10.0.0.1",  "mac": "00:00:00:00:00:01", "capacity_mbps": 30, "weight": 3},
    {"id": 2, "ip": "10.0.0.2",  "mac": "00:00:00:00:00:02", "capacity_mbps": 50, "weight": 5},
    {"id": 3, "ip": "10.0.0.3",  "mac": "00:00:00:00:00:03", "capacity_mbps": 20, "weight": 2},
]

# Initial weights [w1, w2, w3]
INITIAL_WEIGHTS = [s["weight"] for s in SERVERS]  # [3, 5, 2]

# Client IP range — same subnet as servers (10.0.0.x)
# Clients: 10.0.0.10 – 10.0.0.19  (servers: 10.0.0.1-3, VIP: 10.0.0.100)
CLIENT_BASE  = "10.0.0."
CLIENT_START = 10       # first client: 10.0.0.10
NUM_CLIENTS  = 10

# OpenFlow
OF_PORT      = 6653
IDLE_TIMEOUT = 300   # Must exceed TCP SYN retry total (~127s); 300s = 5 min safe margin
HARD_TIMEOUT = 0     # 0 = no hard timeout; let idle_timeout control expiry

# Ryu REST API
RYU_REST_HOST = "127.0.0.1"
RYU_REST_PORT = 8080
