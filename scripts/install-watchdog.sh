#!/bin/bash
# install-watchdog.sh — 1-click installer for OpenClaw gateway watchdog
#
# Usage:
#   bash scripts/install-watchdog.sh install    # deploy watchdog + cron
#   bash scripts/install-watchdog.sh uninstall  # remove cron + deployed scripts
#   bash scripts/install-watchdog.sh status     # show current state
#
# macOS sandbox blocks cron from reading ~/Documents/ and venv files, so this
# installer copies scripts to ~/.openclaw/scripts/ and uses system Python.

set -euo pipefail

# ---------- constants ----------
DEPLOY_DIR="$HOME/.openclaw/scripts"
CONFIG_FILE="$HOME/.openclaw/openclaw.json"
PLIST_PATH="$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist"
LOG_FILE="/tmp/openclaw-watchdog.log"
CRON_MARKER="# openclaw-gateway-watchdog"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_MODULE="$PROJECT_ROOT/src/gateway_watchdog.py"

# ---------- helpers ----------
info()  { printf "\033[32m✓\033[0m %s\n" "$1"; }
warn()  { printf "\033[33m!\033[0m %s\n" "$1"; }
error() { printf "\033[31m✗\033[0m %s\n" "$1" >&2; }
die()   { error "$1"; exit 1; }

# ---------- detect system python ----------
find_system_python() {
    for p in /usr/local/bin/python3 /usr/bin/python3 /opt/homebrew/bin/python3; do
        if [ -x "$p" ]; then
            echo "$p"
            return
        fi
    done
    die "No system Python3 found. Install Python 3 via Xcode CLT or Homebrew."
}

# ---------- read gateway port from config ----------
read_gateway_port() {
    if [ -f "$CONFIG_FILE" ]; then
        local port
        port=$("$SYSTEM_PYTHON" -c "
import json, sys
try:
    cfg = json.load(open('$CONFIG_FILE'))
    print(cfg.get('gateway', {}).get('port', 31415))
except Exception:
    print(31415)
" 2>/dev/null)
        echo "${port:-31415}"
    else
        echo "31415"
    fi
}

# ---------- detect node path from gateway plist ----------
detect_node_path() {
    if [ -f "$PLIST_PATH" ]; then
        local node_path
        node_path=$("$SYSTEM_PYTHON" -c "
import xml.etree.ElementTree as ET, sys
try:
    tree = ET.parse('$PLIST_PATH')
    elems = tree.findall('.//array/string')
    for e in elems:
        if e.text and '/node' in e.text and 'node_modules' not in e.text:
            print(e.text)
            sys.exit(0)
except Exception:
    pass
" 2>/dev/null)
        if [ -n "$node_path" ] && [ -x "$node_path" ]; then
            echo "$node_path"
            return
        fi
    fi

    # Fallback: latest nvm node
    local nvm_dir="${NVM_DIR:-$HOME/.nvm}"
    if [ -d "$nvm_dir/versions/node" ]; then
        local latest
        latest=$(ls -v "$nvm_dir/versions/node/" 2>/dev/null | tail -1)
        if [ -n "$latest" ] && [ -x "$nvm_dir/versions/node/$latest/bin/node" ]; then
            echo "$nvm_dir/versions/node/$latest/bin/node"
            return
        fi
    fi

    # Fallback: PATH
    which node 2>/dev/null || echo ""
}

# ---------- install ----------
do_install() {
    echo "Installing OpenClaw gateway watchdog..."
    echo ""

    # 1. Validate prerequisites
    [ -f "$SOURCE_MODULE" ] || die "Source module not found: $SOURCE_MODULE"
    SYSTEM_PYTHON="$(find_system_python)"
    info "System Python: $SYSTEM_PYTHON ($($SYSTEM_PYTHON --version 2>&1))"
    [ -f "$CONFIG_FILE" ] || die "OpenClaw config not found: $CONFIG_FILE"
    info "OpenClaw config: $CONFIG_FILE"

    # 2. Auto-detect gateway port
    local port
    port="$(read_gateway_port)"
    info "Gateway port: $port"

    # 3. Auto-detect node path (for PATH in cron)
    local node_path
    node_path="$(detect_node_path)"
    local node_dir=""
    if [ -n "$node_path" ]; then
        node_dir="$(dirname "$node_path")"
        info "Node binary: $node_path"
    else
        warn "Node binary not found — cron PATH may be incomplete"
    fi

    # 4. Copy gateway_watchdog.py to deploy dir
    mkdir -p "$DEPLOY_DIR"
    cp "$SOURCE_MODULE" "$DEPLOY_DIR/gateway_watchdog.py"
    info "Copied gateway_watchdog.py → $DEPLOY_DIR/"

    # 5. Generate run_watchdog.py (standalone runner)
    cat > "$DEPLOY_DIR/run_watchdog.py" << 'RUNNER_EOF'
#!/usr/bin/env python3
"""Standalone gateway watchdog runner for cron.

Imports gateway_watchdog from the same directory, runs a health check,
and prints/logs the result. No dependency on the full self-optimization system.
"""

import json
import logging
import sys
import os

# Add this script's directory to path for gateway_watchdog import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateway_watchdog import GatewayWatchdog

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

watchdog = GatewayWatchdog()
result = watchdog.run_check()
print(json.dumps(result, indent=2, default=str))

if result.get("status") == "down":
    sys.exit(2)
RUNNER_EOF
    chmod +x "$DEPLOY_DIR/run_watchdog.py"
    info "Generated run_watchdog.py → $DEPLOY_DIR/"

    # 6. Clean up stale watchdog_main.py leftover
    if [ -f "$DEPLOY_DIR/watchdog_main.py" ]; then
        rm -f "$DEPLOY_DIR/watchdog_main.py"
        info "Removed stale watchdog_main.py"
    fi

    # 7. Install crontab entry (idempotent)
    local cron_path="${node_dir:+$node_dir:}/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
    local cron_line="*/5 * * * * PATH=\"$cron_path\" $SYSTEM_PYTHON -u $DEPLOY_DIR/run_watchdog.py >> $LOG_FILE 2>&1 $CRON_MARKER"

    # Remove any existing watchdog entries, then add the new one
    local existing_cron
    existing_cron=$(crontab -l 2>/dev/null || true)
    local new_cron
    new_cron=$(echo "$existing_cron" | grep -v "openclaw-gateway-watchdog" | grep -v "run_watchdog\.py" | grep -v "gateway-watchdog" || true)
    # Remove trailing blank lines and add our entry
    new_cron=$(echo "$new_cron" | sed '/^$/d')
    if [ -n "$new_cron" ]; then
        new_cron="$new_cron"$'\n'"$cron_line"
    else
        new_cron="$cron_line"
    fi
    echo "$new_cron" | crontab -
    info "Installed crontab entry (every 5 minutes)"

    # 8. Health check
    echo ""
    echo "Verifying gateway is reachable on port $port..."
    if "$SYSTEM_PYTHON" -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(5)
try:
    s.connect(('127.0.0.1', $port))
    s.close()
    print('  Gateway is UP')
except Exception as e:
    print(f'  Gateway is DOWN ({e})')
    sys.exit(1)
" 2>/dev/null; then
        info "Health check passed"
    else
        warn "Gateway not reachable — watchdog will auto-restart it on next cron run"
    fi

    # 9. Summary
    echo ""
    echo "============================================"
    echo "  Gateway Watchdog Installed Successfully"
    echo "============================================"
    echo ""
    echo "  Deploy dir:   $DEPLOY_DIR"
    echo "  Python:       $SYSTEM_PYTHON"
    echo "  Gateway port: $port"
    echo "  Log file:     $LOG_FILE"
    echo "  Schedule:     every 5 minutes via cron"
    echo ""
    echo "  Helpful commands:"
    echo "    make watchdog-status       # show status"
    echo "    make uninstall-watchdog    # remove"
    echo "    tail -f $LOG_FILE   # watch logs"
    echo "    crontab -l | grep watchdog # verify cron"
    echo ""
}

# ---------- uninstall ----------
do_uninstall() {
    echo "Uninstalling OpenClaw gateway watchdog..."
    echo ""

    # Remove crontab entry
    local existing_cron
    existing_cron=$(crontab -l 2>/dev/null || true)
    if echo "$existing_cron" | grep -q "openclaw-gateway-watchdog\|run_watchdog\.py\|gateway-watchdog"; then
        local new_cron
        new_cron=$(echo "$existing_cron" | grep -v "openclaw-gateway-watchdog" | grep -v "run_watchdog\.py" | grep -v "gateway-watchdog" || true)
        new_cron=$(echo "$new_cron" | sed '/^$/d')
        if [ -n "$new_cron" ]; then
            echo "$new_cron" | crontab -
        else
            crontab -r 2>/dev/null || true
        fi
        info "Removed crontab entry"
    else
        warn "No watchdog crontab entry found"
    fi

    # Remove deployed scripts (preserve log)
    for f in gateway_watchdog.py run_watchdog.py watchdog_main.py; do
        if [ -f "$DEPLOY_DIR/$f" ]; then
            rm -f "$DEPLOY_DIR/$f"
            info "Removed $DEPLOY_DIR/$f"
        fi
    done

    # Clean __pycache__
    if [ -d "$DEPLOY_DIR/__pycache__" ]; then
        rm -rf "$DEPLOY_DIR/__pycache__"
        info "Removed $DEPLOY_DIR/__pycache__"
    fi

    echo ""
    info "Uninstall complete. Log file preserved at $LOG_FILE"
}

# ---------- status ----------
do_status() {
    echo "OpenClaw Gateway Watchdog Status"
    echo "================================"
    echo ""

    # Crontab
    echo "Crontab entry:"
    local cron_entry
    cron_entry=$(crontab -l 2>/dev/null | grep "run_watchdog\|gateway-watchdog\|openclaw-gateway-watchdog" || true)
    if [ -n "$cron_entry" ]; then
        echo "  $cron_entry"
    else
        echo "  (none)"
    fi
    echo ""

    # Deployed files
    echo "Deployed files:"
    for f in gateway_watchdog.py run_watchdog.py; do
        if [ -f "$DEPLOY_DIR/$f" ]; then
            echo "  $DEPLOY_DIR/$f  ($(wc -c < "$DEPLOY_DIR/$f" | tr -d ' ') bytes)"
        else
            echo "  $DEPLOY_DIR/$f  (missing)"
        fi
    done
    echo ""

    # Stale files
    if [ -f "$DEPLOY_DIR/watchdog_main.py" ]; then
        warn "Stale file: $DEPLOY_DIR/watchdog_main.py (run install to clean up)"
    fi

    # Recent log
    echo "Recent log ($LOG_FILE):"
    if [ -f "$LOG_FILE" ]; then
        tail -10 "$LOG_FILE" | sed 's/^/  /'
    else
        echo "  (no log file yet)"
    fi
    echo ""
}

# ---------- main ----------
SYSTEM_PYTHON="$(find_system_python)"

case "${1:-}" in
    install)   do_install ;;
    uninstall) do_uninstall ;;
    status)    do_status ;;
    *)
        echo "Usage: $0 {install|uninstall|status}"
        echo ""
        echo "  install    Deploy watchdog scripts and install cron job"
        echo "  uninstall  Remove cron job and deployed scripts"
        echo "  status     Show current watchdog status"
        exit 1
        ;;
esac
