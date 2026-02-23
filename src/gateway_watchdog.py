"""Gateway watchdog: monitors OpenClaw gateway health and restarts if down.

Uses a direct TCP socket probe for health checks (works reliably in launchd)
and launchctl for restarts (no dependency on openclaw CLI).
"""

import json
import logging
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_PORT = 31415
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10  # seconds between restart attempts
DEFAULT_HEALTH_TIMEOUT = 5  # seconds for TCP probe
LAUNCHD_LABEL = "ai.openclaw.gateway"
PLIST_PATH = "~/Library/LaunchAgents/ai.openclaw.gateway.plist"


class GatewayWatchdog:
    """Monitors OpenClaw gateway and restarts it when unhealthy."""

    def __init__(
        self,
        port: int = DEFAULT_PORT,
        token: str = "",
        state_dir: str = "",
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: int = DEFAULT_RETRY_DELAY,
        health_timeout: int = DEFAULT_HEALTH_TIMEOUT,
    ) -> None:
        self.port = port or self._load_port_from_config()
        self.token = token or self._load_token_from_config()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_timeout = health_timeout

        if not state_dir:
            state_dir = os.path.expanduser(
                "~/.openclaw/workspace/self-optimization/state"
            )
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self._state_file = os.path.join(state_dir, "gateway_watchdog.json")

    def _load_token_from_config(self) -> str:
        """Load the gateway token from ~/.openclaw/openclaw.json."""
        config = self._load_openclaw_config()
        return config.get("gateway", {}).get("auth", {}).get("token", "")

    def _load_port_from_config(self) -> int:
        """Load the gateway port from ~/.openclaw/openclaw.json."""
        config = self._load_openclaw_config()
        return int(config.get("gateway", {}).get("port", DEFAULT_PORT))

    def _load_openclaw_config(self) -> Dict[str, Any]:
        """Load ~/.openclaw/openclaw.json."""
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load openclaw config: %s", e)
            return {}

    def check_health(self) -> Dict[str, Any]:
        """Probe gateway health via TCP socket connection.

        Tries to connect to the gateway port. If the connection succeeds,
        the gateway process is listening and considered healthy.
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.health_timeout)
            sock.connect(("127.0.0.1", self.port))
            sock.close()
            healthy = True
            detail = f"port {self.port} accepting connections"
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            healthy = False
            detail = str(e)

        return {
            "healthy": healthy,
            "port": self.port,
            "detail": detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def restart_gateway(self) -> Dict[str, Any]:
        """Attempt to restart the gateway via launchctl (no openclaw CLI needed)."""
        logger.info("Attempting gateway restart via launchctl...")
        uid = os.getuid()
        target = f"gui/{uid}/{LAUNCHD_LABEL}"
        plist = os.path.expanduser(PLIST_PATH)

        # Try kickstart -k (kill + restart in one command)
        try:
            result = subprocess.run(
                ["launchctl", "kickstart", "-k", target],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("launchctl kickstart succeeded")
                return {
                    "method": "kickstart",
                    "success": True,
                    "output": result.stdout.strip() or "kicked",
                }
        except subprocess.TimeoutExpired:
            logger.warning("launchctl kickstart timed out")

        # Fallback: bootout + bootstrap
        logger.warning("kickstart failed, trying bootout+bootstrap")
        try:
            subprocess.run(
                ["launchctl", "bootout", target],
                capture_output=True, text=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass

        time.sleep(2)

        if os.path.isfile(plist):
            try:
                bootstrap = subprocess.run(
                    ["launchctl", "bootstrap", f"gui/{uid}", plist],
                    capture_output=True, text=True, timeout=10,
                )
                return {
                    "method": "bootout+bootstrap",
                    "success": bootstrap.returncode == 0,
                    "output": bootstrap.stdout.strip() or bootstrap.stderr.strip(),
                }
            except subprocess.TimeoutExpired:
                logger.warning("launchctl bootstrap timed out")

        return {
            "method": "all_failed",
            "success": False,
            "output": f"plist exists: {os.path.isfile(plist)}",
        }

    def run_check(self) -> Dict[str, Any]:
        """Full watchdog cycle: check health, restart if needed, verify recovery.

        Returns a summary dict suitable for logging/cron output.
        """
        now = datetime.now(timezone.utc).isoformat()
        health = self.check_health()

        if health["healthy"]:
            result: Dict[str, Any] = {
                "status": "healthy",
                "timestamp": now,
                "details": health,
                "action": "none",
            }
            self._save_state(result)
            logger.info("Gateway healthy on port %d", self.port)
            return result

        # Gateway is down — attempt restart with retries
        logger.warning("Gateway unhealthy on port %d: %s", self.port, health.get("detail"))
        attempts: List[Dict[str, Any]] = []
        recovered = False

        for attempt in range(1, self.max_retries + 1):
            logger.info("Restart attempt %d/%d", attempt, self.max_retries)
            restart_result = self.restart_gateway()
            attempts.append(restart_result)

            if restart_result["success"]:
                # Wait for gateway to become ready
                time.sleep(5)
                verify = self.check_health()
                if verify["healthy"]:
                    recovered = True
                    logger.info("Gateway recovered on attempt %d", attempt)
                    break
                else:
                    logger.warning("Restart succeeded but health check still failing")

            if attempt < self.max_retries:
                time.sleep(self.retry_delay)

        result = {
            "status": "recovered" if recovered else "down",
            "timestamp": now,
            "initial_health": health,
            "restart_attempts": attempts,
            "total_attempts": len(attempts),
            "action": "restarted" if recovered else "escalate",
        }
        self._save_state(result)

        if not recovered:
            logger.error(
                "Gateway failed to recover after %d attempts. Manual intervention needed.",
                self.max_retries,
            )

        return result

    def _save_state(self, result: Dict[str, Any]) -> None:
        """Persist the last watchdog result to state file."""
        history = self._load_history()
        history.append(result)
        history = history[-50:]

        state = {
            "last_check": result,
            "history": history,
        }
        try:
            tmp = self._state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            os.replace(tmp, self._state_file)
        except OSError as e:
            logger.warning("Failed to save watchdog state: %s", e)

    def _load_history(self) -> List[Dict[str, Any]]:
        """Load check history from state file."""
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            return state.get("history", [])
        except (OSError, json.JSONDecodeError):
            return []

    def get_status(self) -> Dict[str, Any]:
        """Return the last watchdog state and summary stats."""
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            state = {"last_check": None, "history": []}

        history = state.get("history", [])
        total = len(history)
        healthy_count = sum(1 for h in history if h.get("status") == "healthy")
        down_count = sum(1 for h in history if h.get("status") == "down")
        recovered_count = sum(1 for h in history if h.get("status") == "recovered")

        return {
            "last_check": state.get("last_check"),
            "total_checks": total,
            "healthy": healthy_count,
            "recovered": recovered_count,
            "down": down_count,
            "uptime_pct": round(healthy_count / total * 100, 1) if total > 0 else 0.0,
        }
