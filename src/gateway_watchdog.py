"""Gateway watchdog: monitors OpenClaw services and restarts them if down.

Monitors multiple services (base gateway, enterprise gateway, Vite UI).
Uses TCP socket probes for health checks (works reliably in launchd/cron)
and launchctl for restarts (no dependency on openclaw CLI).
"""

import contextlib
import json
import logging
import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_PORT = 3000
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 10  # seconds between restart attempts
DEFAULT_HEALTH_TIMEOUT = 5  # seconds for TCP probe
LAUNCHD_LABEL = "ai.openclaw.gateway"
PLIST_PATH = "~/Library/LaunchAgents/ai.openclaw.gateway.plist"

# Well-known OpenClaw services
KNOWN_SERVICES: list[dict[str, Any]] = [
    {
        "name": "gateway",
        "port": 3000,
        "launchd_label": "ai.openclaw.gateway",
        "plist": "~/Library/LaunchAgents/ai.openclaw.gateway.plist",
        "description": "Base OpenClaw gateway",
        "critical": True,
    },
    {
        "name": "enterprise",
        "port": 18789,
        "launchd_label": "",
        "plist": "",
        "description": "Enterprise gateway (user-facing bot)",
        "critical": True,
    },
    {
        "name": "vite-ui",
        "port": 5173,
        "launchd_label": "",
        "plist": "",
        "description": "OpenClaw web UI (Vite dev server)",
        "critical": False,
    },
]


def probe_port(port: int, timeout: int = DEFAULT_HEALTH_TIMEOUT) -> dict[str, Any]:
    """Probe a TCP port and return health status."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(("127.0.0.1", port))
        sock.close()
        return {
            "healthy": True,
            "port": port,
            "detail": f"port {port} accepting connections",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except (TimeoutError, ConnectionRefusedError, OSError) as e:
        return {
            "healthy": False,
            "port": port,
            "detail": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class GatewayWatchdog:
    """Monitors OpenClaw services and restarts them when unhealthy."""

    def __init__(
        self,
        port: int = 0,
        token: str = "",
        state_dir: str = "",
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: int = DEFAULT_RETRY_DELAY,
        health_timeout: int = DEFAULT_HEALTH_TIMEOUT,
        services: list[dict[str, Any]] | None = None,
    ) -> None:
        config = self._load_openclaw_config()

        # Primary port (backward compat)
        if port:
            self.port = port
        else:
            self.port = int(config.get("gateway", {}).get("port", DEFAULT_PORT))

        self.token = token or self._load_token_from_config(config)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_timeout = health_timeout

        # Build service list
        if services is not None:
            self.services = services
        else:
            self.services = self._build_service_list(config)

        if not state_dir:
            state_dir = os.path.expanduser("~/.openclaw/workspace/self-optimization/state")
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self._state_file = os.path.join(state_dir, "gateway_watchdog.json")

    def _build_service_list(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Build monitored service list from config + well-known ports."""
        services: list[dict[str, Any]] = []

        # Base gateway — port from config
        gw_port = int(config.get("gateway", {}).get("port", DEFAULT_PORT))
        services.append({
            "name": "gateway",
            "port": gw_port,
            "launchd_label": LAUNCHD_LABEL,
            "plist": PLIST_PATH,
            "description": "Base OpenClaw gateway",
            "critical": True,
        })

        # Enterprise gateway — always monitor 18789
        services.append({
            "name": "enterprise",
            "port": 18789,
            "launchd_label": "",
            "plist": "",
            "description": "Enterprise gateway (user-facing bot)",
            "critical": True,
        })

        # Vite UI — non-critical
        services.append({
            "name": "vite-ui",
            "port": 5173,
            "launchd_label": "",
            "plist": "",
            "description": "OpenClaw web UI (Vite dev server)",
            "critical": False,
        })

        return services

    def _load_token_from_config(self, config: dict[str, Any] | None = None) -> str:
        """Load the gateway token from ~/.openclaw/openclaw.json."""
        if config is None:
            config = self._load_openclaw_config()
        token: str = config.get("gateway", {}).get("auth", {}).get("token", "")
        return token

    def _load_openclaw_config(self) -> dict[str, Any]:
        """Load ~/.openclaw/openclaw.json."""
        config_path = os.path.expanduser("~/.openclaw/openclaw.json")
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)  # type: ignore[no-any-return]
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Could not load openclaw config: %s", e)
            return {}

    def check_health(self, port: int = 0) -> dict[str, Any]:
        """Probe a single port's health via TCP socket connection."""
        return probe_port(port or self.port, self.health_timeout)

    def check_all_services(self) -> dict[str, dict[str, Any]]:
        """Probe all monitored services and return per-service health."""
        results: dict[str, dict[str, Any]] = {}
        for svc in self.services:
            health = probe_port(svc["port"], self.health_timeout)
            health["service_name"] = svc["name"]
            health["description"] = svc["description"]
            health["critical"] = svc.get("critical", False)
            results[svc["name"]] = health
        return results

    def restart_service(self, service: dict[str, Any]) -> dict[str, Any]:
        """Attempt to restart a service via launchctl."""
        label = service.get("launchd_label", "")
        plist = service.get("plist", "")
        name = service.get("name", "unknown")

        if not label:
            logger.warning(
                "No launchd_label for service %s — cannot auto-restart", name
            )
            return {
                "method": "no_launchd",
                "success": False,
                "output": f"Service '{name}' has no launchd_label configured. "
                "Manual restart required.",
            }

        logger.info("Attempting restart of %s via launchctl...", name)
        uid = os.getuid()
        target = f"gui/{uid}/{label}"
        plist_path = os.path.expanduser(plist) if plist else ""

        # Try kickstart -k (kill + restart in one command)
        try:
            result = subprocess.run(
                ["launchctl", "kickstart", "-k", target],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("launchctl kickstart succeeded for %s", name)
                return {
                    "method": "kickstart",
                    "success": True,
                    "output": result.stdout.strip() or "kicked",
                }
        except subprocess.TimeoutExpired:
            logger.warning("launchctl kickstart timed out for %s", name)

        # Fallback: bootout + bootstrap
        logger.warning("kickstart failed for %s, trying bootout+bootstrap", name)
        with contextlib.suppress(subprocess.TimeoutExpired):
            subprocess.run(
                ["launchctl", "bootout", target],
                capture_output=True,
                text=True,
                timeout=10,
            )

        time.sleep(2)

        if plist_path and os.path.isfile(plist_path):
            try:
                bootstrap = subprocess.run(
                    ["launchctl", "bootstrap", f"gui/{uid}", plist_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return {
                    "method": "bootout+bootstrap",
                    "success": bootstrap.returncode == 0,
                    "output": bootstrap.stdout.strip() or bootstrap.stderr.strip(),
                }
            except subprocess.TimeoutExpired:
                logger.warning("launchctl bootstrap timed out for %s", name)

        return {
            "method": "all_failed",
            "success": False,
            "output": f"plist exists: {bool(plist_path) and os.path.isfile(plist_path)}",
        }

    def restart_gateway(self) -> dict[str, Any]:
        """Attempt to restart the base gateway via launchctl (backward compat)."""
        base_svc = {
            "name": "gateway",
            "launchd_label": LAUNCHD_LABEL,
            "plist": PLIST_PATH,
        }
        return self.restart_service(base_svc)

    def run_check(self) -> dict[str, Any]:
        """Full watchdog cycle: check all services, restart if needed, verify.

        Returns a summary dict suitable for logging/cron output.
        """
        now = datetime.now(timezone.utc).isoformat()

        # Check all services
        service_results = self.check_all_services()
        all_healthy = all(r["healthy"] for r in service_results.values())

        if all_healthy:
            result: dict[str, Any] = {
                "status": "healthy",
                "timestamp": now,
                "services": service_results,
                "action": "none",
            }
            self._save_state(result)
            logger.info("All %d services healthy", len(service_results))
            return result

        # At least one service is down — attempt restarts
        down_services = [
            (name, health)
            for name, health in service_results.items()
            if not health["healthy"]
        ]

        restart_results: dict[str, dict[str, Any]] = {}
        for name, health in down_services:
            svc = next((s for s in self.services if s["name"] == name), None)
            if not svc:
                continue

            logger.warning(
                "%s unhealthy on port %d: %s",
                name, health["port"], health.get("detail"),
            )

            attempts: list[dict[str, Any]] = []
            recovered = False

            for attempt in range(1, self.max_retries + 1):
                logger.info(
                    "%s restart attempt %d/%d", name, attempt, self.max_retries
                )
                restart_result = self.restart_service(svc)
                attempts.append(restart_result)

                if restart_result["success"]:
                    time.sleep(5)
                    verify = probe_port(svc["port"], self.health_timeout)
                    if verify["healthy"]:
                        recovered = True
                        logger.info("%s recovered on attempt %d", name, attempt)
                        break
                    else:
                        logger.warning(
                            "%s restart succeeded but health check still failing",
                            name,
                        )
                elif restart_result.get("method") == "no_launchd":
                    # Can't auto-restart — don't retry
                    break

                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)

            restart_results[name] = {
                "recovered": recovered,
                "attempts": attempts,
                "total_attempts": len(attempts),
                "critical": svc.get("critical", False),
            }

            if not recovered:
                logger.error(
                    "%s failed to recover after %d attempts. Manual intervention needed.",
                    name,
                    len(attempts),
                )

        # Determine overall status
        any_critical_down = any(
            not r["recovered"] and r.get("critical", False)
            for r in restart_results.values()
        )
        all_recovered = all(r["recovered"] for r in restart_results.values())

        if all_recovered:
            overall = "recovered"
        elif any_critical_down:
            overall = "critical_down"
        else:
            overall = "degraded"

        result = {
            "status": overall,
            "timestamp": now,
            "services": service_results,
            "restart_results": restart_results,
            "action": "restarted" if all_recovered else "escalate",
        }
        self._save_state(result)
        return result

    def _save_state(self, result: dict[str, Any]) -> None:
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

    def _load_history(self) -> list[dict[str, Any]]:
        """Load check history from state file."""
        try:
            with open(self._state_file, encoding="utf-8") as f:
                state = json.load(f)
            history: list[dict[str, Any]] = state.get("history", [])
            return history
        except (OSError, json.JSONDecodeError):
            return []

    def get_status(self) -> dict[str, Any]:
        """Return the last watchdog state and summary stats."""
        try:
            with open(self._state_file, encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            state = {"last_check": None, "history": []}

        history = state.get("history", [])
        total = len(history)
        healthy_count = sum(1 for h in history if h.get("status") == "healthy")
        down_count = sum(
            1 for h in history if h.get("status") in ("down", "critical_down")
        )
        recovered_count = sum(1 for h in history if h.get("status") == "recovered")
        degraded_count = sum(1 for h in history if h.get("status") == "degraded")

        return {
            "last_check": state.get("last_check"),
            "total_checks": total,
            "healthy": healthy_count,
            "recovered": recovered_count,
            "down": down_count,
            "degraded": degraded_count,
            "uptime_pct": round(healthy_count / total * 100, 1) if total > 0 else 0.0,
            "monitored_services": [s["name"] for s in self.services],
        }
