#!/bin/bash
# ============================================================
# Setup Script
# Sainte-Laguë vs WRR/IWRR/WLC — SDN Load Balancing
#
# Supported: Ubuntu 20.04 / 22.04 / 24.04
#
# Usage:
#   bash setup.sh
#   bash setup.sh --dry-run     (check only, no install)
#   bash setup.sh --skip-apt    (skip apt installs, only create venv)
# ============================================================

set -euo pipefail

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*"; }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }
step() { echo -e "\n${BOLD}── $* ──${NC}"; }

# ── Arguments ────────────────────────────────────────────────────────────────
DRY_RUN=false
SKIP_APT=false
for arg in "$@"; do
    case $arg in
        --dry-run)  DRY_RUN=true  ;;
        --skip-apt) SKIP_APT=true ;;
        --help|-h)
            echo "Usage: bash setup.sh [--dry-run] [--skip-apt]"
            echo "  --dry-run   Check prerequisites only, install nothing"
            echo "  --skip-apt  Skip apt installs (assume system deps present)"
            exit 0
            ;;
    esac
done

# ── Project root ─────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

echo -e "${BOLD}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Sainte-Laguë SDN Load Balancing Setup                 ║"
echo "║  Project: $PROJECT_DIR"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

$DRY_RUN && warn "DRY-RUN mode — nothing will be installed"

# ────────────────────────────────────────────────────────────────────────────
# STEP 1: Check OS
# ────────────────────────────────────────────────────────────────────────────
step "1. Checking OS"
if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    info "OS: $PRETTY_NAME"
    if [[ "$ID" != "ubuntu" ]]; then
        warn "Tested on Ubuntu 20.04/22.04/24.04. Proceed with caution on $ID."
    fi
else
    warn "Cannot detect OS. Assuming Debian-based."
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 2: Check sudo
# ────────────────────────────────────────────────────────────────────────────
step "2. Checking sudo access"
if ! sudo -n true 2>/dev/null; then
    warn "sudo requires password. You'll be prompted during apt installs."
fi
ok "sudo available"

# ────────────────────────────────────────────────────────────────────────────
# STEP 3: System packages
# ────────────────────────────────────────────────────────────────────────────
step "3. System packages"

APT_PKGS=(
    "python3"
    "python3-pip"
    "python3-venv"
    "python3-dev"
    "mininet"
    "openvswitch-switch"
    "iperf3"
    "curl"
    "git"
    "build-essential"
    "libffi-dev"
    "libssl-dev"
)

MISSING_PKGS=()
for pkg in "${APT_PKGS[@]}"; do
    if dpkg -l "$pkg" &>/dev/null; then
        ok "  $pkg"
    else
        warn "  $pkg — NOT installed"
        MISSING_PKGS+=("$pkg")
    fi
done

if [[ ${#MISSING_PKGS[@]} -gt 0 ]]; then
    info "Missing packages: ${MISSING_PKGS[*]}"
    if $DRY_RUN; then
        warn "DRY-RUN: would install: sudo apt install -y ${MISSING_PKGS[*]}"
    elif $SKIP_APT; then
        warn "--skip-apt: skipping installation of ${MISSING_PKGS[*]}"
    else
        info "Installing missing packages..."
        sudo apt-get update -qq
        sudo apt-get install -y "${MISSING_PKGS[@]}"
        ok "System packages installed"
    fi
else
    ok "All system packages present"
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 4: Python version check
# ────────────────────────────────────────────────────────────────────────────
step "4. Python version"
PY_VER=$(python3 --version 2>&1)
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
info "Found: $PY_VER"
if [[ $PY_MINOR -lt 8 ]]; then
    err "Python 3.8+ required. Found 3.$PY_MINOR"
    exit 1
fi
ok "Python 3.$PY_MINOR >= 3.8"

# ────────────────────────────────────────────────────────────────────────────
# STEP 5: Create virtual environment
# ────────────────────────────────────────────────────────────────────────────
step "5. Virtual environment"

if [[ -d "$VENV_DIR" ]]; then
    if [[ -f "$VENV_DIR/bin/ryu-manager" ]]; then
        ok "venv already exists with ryu-manager — skipping creation"
        SKIP_VENV=true
    else
        warn "venv exists but ryu-manager missing — reinstalling packages"
        SKIP_VENV=false
    fi
else
    SKIP_VENV=false
fi

if ! $DRY_RUN && ! $SKIP_VENV; then
    info "Creating venv at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    ok "venv created"
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 6: Install Python packages into venv
# ────────────────────────────────────────────────────────────────────────────
step "6. Python packages (venv)"

REQ_FILE="$PROJECT_DIR/requirements.txt"

if $DRY_RUN; then
    warn "DRY-RUN: would install from $REQ_FILE"
elif $SKIP_VENV; then
    ok "Skipped (venv already has packages)"
else
    if [[ ! -f "$REQ_FILE" ]]; then
        err "requirements.txt not found at $REQ_FILE"
        exit 1
    fi
    info "Installing Python packages from requirements.txt (this may take 2-5 minutes)..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q

    # Python 3.12+ needs --no-build-isolation for ryu (distutils removed)
    PY_MINOR_LOCAL=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [[ $PY_MINOR_LOCAL -ge 12 ]]; then
        info "Python 3.$PY_MINOR_LOCAL detected — using --no-build-isolation for ryu"
        "$VENV_DIR/bin/pip" install -r "$REQ_FILE" --no-build-isolation -q
    else
        "$VENV_DIR/bin/pip" install -r "$REQ_FILE" -q
    fi
    ok "Python packages installed"
fi

# Verify ryu-manager
if ! $DRY_RUN; then
    if [[ -f "$VENV_DIR/bin/ryu-manager" ]]; then
        RYU_VER=$("$VENV_DIR/bin/ryu-manager" --version 2>&1 | head -1)
        ok "ryu-manager: $RYU_VER"
    else
        err "ryu-manager not found in venv. Install may have failed."
        err "Try manually: $VENV_DIR/bin/pip install ryu"
        exit 1
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 7: Mininet verification
# ────────────────────────────────────────────────────────────────────────────
step "7. Mininet verification"

if python3 -c "import mininet" 2>/dev/null; then
    MN_VER=$(python3 -c "import mininet; print(mininet.VERSION)" 2>/dev/null || echo "unknown")
    ok "Mininet importable (version: $MN_VER)"
elif [[ -d /usr/lib/python3/dist-packages/mininet ]]; then
    ok "Mininet found at /usr/lib/python3/dist-packages/mininet"
else
    err "Mininet not found! Install with: sudo apt install mininet"
    $DRY_RUN || exit 1
fi

# Check OVS
if command -v ovs-vsctl &>/dev/null; then
    OVS_VER=$(ovs-vsctl --version | head -1)
    ok "Open vSwitch: $OVS_VER"
else
    warn "ovs-vsctl not found. Install: sudo apt install openvswitch-switch"
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 8: iperf3 verification
# ────────────────────────────────────────────────────────────────────────────
step "8. iperf3"
if command -v iperf3 &>/dev/null; then
    IPERF_VER=$(iperf3 --version 2>&1 | head -1)
    ok "iperf3: $IPERF_VER"
else
    err "iperf3 not found! Install: sudo apt install iperf3"
    $DRY_RUN || exit 1
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 9: Create directory structure
# ────────────────────────────────────────────────────────────────────────────
step "9. Directory structure"
if ! $DRY_RUN; then
    mkdir -p "$PROJECT_DIR"/{results/{raw,processed},logs,docs/figures}
    ok "Directories created"
else
    info "Would create: results/raw, results/processed, logs, docs/figures"
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 10: Validate imports
# ────────────────────────────────────────────────────────────────────────────
step "10. Validating project imports"

if ! $DRY_RUN; then
    VALIDATE_OUT=$("$VENV_DIR/bin/python3" -c "
import sys
sys.path.insert(0, '$PROJECT_DIR')
sys.path.insert(0, '/usr/lib/python3/dist-packages')

# Config
from config.network_config import SERVERS, VIP_IP, INITIAL_WEIGHTS
from config.experiment_config import ALGORITHMS, SCENARIOS
from config.algo_config import ALGO_LABELS

# Algorithms
from controller.algorithms.wrr import WRR
from controller.algorithms.iwrr import IWRR
from controller.algorithms.wlc import WLC
from controller.algorithms.saintelague import SainteLangue

# Quick algorithm test
for cls in [WRR, IWRR, WLC, SainteLangue]:
    algo = cls([3,5,2])
    algo.select()
    algo.update_weights([6,5,2])
    algo.select()

# Verify SL convergence property
sl = SainteLangue([3,5,2])
[sl.select() for _ in range(110)]  # proportional pre-change
sl.update_weights([6,5,2])
assert sl._counts == [33, 55, 22], 'SL counts not preserved!'

print('ALL OK')
print('  INITIAL_WEIGHTS:', INITIAL_WEIGHTS)
print('  ALGORITHMS:', ALGORITHMS)
print('  SCENARIOS:', list(SCENARIOS.keys()))
" 2>&1)

    if echo "$VALIDATE_OUT" | grep -q "ALL OK"; then
        ok "Project imports validated"
        echo "$VALIDATE_OUT" | grep -v "ALL OK" | while IFS= read -r line; do
            info "  $line"
        done
    else
        err "Import validation failed:"
        echo "$VALIDATE_OUT"
        exit 1
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# STEP 11: Final check — venv usability
# ────────────────────────────────────────────────────────────────────────────
step "11. Final check"

if ! $DRY_RUN; then
    if [[ -f "$VENV_DIR/bin/ryu-manager" && -f "$VENV_DIR/bin/python3" ]]; then
        ok "venv/bin/ryu-manager   ✓"
        ok "venv/bin/python3       ✓"
    else
        err "venv incomplete — check pip output above"
        exit 1
    fi
fi

# ────────────────────────────────────────────────────────────────────────────
# Done
# ────────────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Setup complete!                                             ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

if ! $DRY_RUN; then
    echo -e "${BOLD}Next steps:${NC}"
    echo ""
    echo "  1. Quick test (validates end-to-end pipeline, ~60s):"
    echo "       SUDO_PASS=yourpassword bash $PROJECT_DIR/test_quick.sh"
    echo ""
    echo "  2. Full experiment (~10 hours, 220 runs):"
    echo "       cd $PROJECT_DIR"
    echo "       PYTHONPATH=\$(pwd) SUDO_PASS=yourpassword \\"
    echo "       nohup venv/bin/python3 evaluation/run_experiment.py \\"
    echo "         --scenario all --runs 20 --yes \\"
    echo "         > logs/full_experiment.log 2>&1 &"
    echo ""
    echo "  3. Monitor progress:"
    echo "       tail -f $PROJECT_DIR/logs/full_experiment.log"
    echo ""
    echo "  4. After experiment — analysis:"
    echo "       cd $PROJECT_DIR"
    echo "       PYTHONPATH=\$(pwd) venv/bin/python3 evaluation/convergence_analyzer.py"
    echo "       PYTHONPATH=\$(pwd) venv/bin/python3 evaluation/statistical_tests.py"
    echo "       PYTHONPATH=\$(pwd) venv/bin/python3 evaluation/plot_results.py"
    echo ""
    echo "  Venv: $VENV_DIR"
    echo "  Logs: $PROJECT_DIR/logs/"
    echo "  Results: $PROJECT_DIR/results/"
fi
