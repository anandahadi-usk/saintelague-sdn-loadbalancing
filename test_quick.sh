#!/bin/bash
# test_quick.sh — Quick validation of Sainte-Laguë SDN end-to-end pipeline
# Runs ONE experiment (saintelague, steady, run 1) with 30s duration.
# Expected: controller starts, Mininet runs, CSV produced.
#
# Usage:
#   sudo bash test_quick.sh
#   SUDO_PASS=your_sudo_password bash test_quick.sh

set -e

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$PROJECT/venv"
PYTHON=$VENV/bin/python3
RYU=$VENV/bin/ryu-manager
SUDO_PASS="${SUDO_PASS:-}"

# Require local venv — run setup.sh first if missing
if [[ ! -f "$RYU" ]]; then
    echo "ERROR: venv not found at $VENV"
    echo "Run first:  bash $PROJECT/setup.sh"
    exit 1
fi

if [[ -z "$SUDO_PASS" ]]; then
    echo "ERROR: SUDO_PASS not set."
    echo "Usage: SUDO_PASS=yourpassword bash test_quick.sh"
    exit 1
fi

echo "============================================"
echo " Quick Test — saintelague / steady / run1"
echo "============================================"

# Cleanup — kill by name AND by port (covers all Ryu startup methods)
echo "[1/5] Cleaning up..."
sudo pkill -9 -f ryu-manager 2>/dev/null || true
sudo fuser -k 6653/tcp 2>/dev/null || true
sudo pkill -f iperf3 2>/dev/null || true
sudo mn --clean 2>/dev/null || true
sleep 3

# Prepare output dir
RESULTS_DIR=$PROJECT/results/raw/steady_saintelague_run01
mkdir -p $RESULTS_DIR
LOG=$PROJECT/logs/test_quick.log
mkdir -p $PROJECT/logs
> $LOG

# Start Ryu
echo "[2/5] Starting Ryu controller..."
ALGO=saintelague RUN_ID=1 SCENARIO=steady RESULTS_DIR=$RESULTS_DIR \
PYTHONPATH=$PROJECT \
$RYU \
    $PROJECT/controller/main_controller.py \
    --ofp-tcp-listen-port 6653 \
    --wsapi-host 127.0.0.1 \
    --wsapi-port 8080 \
    >> $LOG 2>&1 &
RYU_PID=$!
echo "  Ryu PID: $RYU_PID"
sleep 5

# Check Ryu is running
if ! kill -0 $RYU_PID 2>/dev/null; then
    echo "ERROR: Ryu failed to start. Check $LOG"
    tail -20 $LOG
    exit 1
fi
echo "  Ryu running OK"

# Test REST API
echo "[3/5] Testing REST API..."
STATUS=$(curl -s http://127.0.0.1:8080/api/status 2>/dev/null || echo "")
if echo "$STATUS" | grep -q '"algorithm"'; then
    echo "  REST API OK: $STATUS" | head -1
else
    echo "  WARNING: REST API not ready yet (Ryu may still be initializing)"
fi

# Run traffic script
echo "[4/5] Running traffic (30s steady, saintelague)..."
echo "$SUDO_PASS" | sudo -S env PYTHONPATH=$PROJECT $PYTHON \
    $PROJECT/mn_traffic/traffic/steady_traffic.py \
    --duration 30 \
    --seed 42 \
    --algorithm saintelague \
    --run_id 1 \
    >> $LOG 2>&1
echo "  Traffic done"

# Check output
echo "[5/5] Checking output..."
CSV=$RESULTS_DIR/flow_decisions_steady_saintelague_run01.csv
if [ -f "$CSV" ]; then
    ROWS=$(wc -l < "$CSV")
    echo "  CSV found: $CSV"
    echo "  Rows (incl. header): $ROWS"
    echo "  First 5 rows:"
    head -5 "$CSV"
    echo ""
    echo "SUCCESS: Pipeline validated!"
else
    echo "ERROR: CSV not found at $CSV"
    echo "Controller log tail:"
    tail -30 $LOG
    kill $RYU_PID 2>/dev/null
    exit 1
fi

# Final cleanup — ensure port 6653 is free for next run
kill $RYU_PID 2>/dev/null || true
sudo fuser -k 6653/tcp 2>/dev/null || true
sudo pkill -f iperf3 2>/dev/null || true
sudo mn --clean 2>/dev/null || true

echo ""
echo "Log: $LOG"
echo "Results: $RESULTS_DIR"
echo "============================================"
