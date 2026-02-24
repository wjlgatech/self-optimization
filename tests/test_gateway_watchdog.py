"""Tests for gateway_watchdog module."""

import json
import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from gateway_watchdog import DEFAULT_PORT, GatewayWatchdog, probe_port


@pytest.fixture
def watchdog(tmp_path: object) -> GatewayWatchdog:
    """Create a watchdog with a temp state dir and explicit services."""
    return GatewayWatchdog(
        port=3000,
        token="test-token",
        state_dir=str(tmp_path),
        max_retries=2,
        retry_delay=0,
        health_timeout=1,
        services=[
            {
                "name": "gateway",
                "port": 3000,
                "launchd_label": "ai.openclaw.gateway",
                "plist": "~/Library/LaunchAgents/ai.openclaw.gateway.plist",
                "description": "Base gateway",
                "critical": True,
            },
        ],
    )


@pytest.fixture
def multi_service_watchdog(tmp_path: object) -> GatewayWatchdog:
    """Create a watchdog monitoring multiple services."""
    return GatewayWatchdog(
        port=3000,
        token="test-token",
        state_dir=str(tmp_path),
        max_retries=1,
        retry_delay=0,
        health_timeout=1,
        services=[
            {
                "name": "gateway",
                "port": 3000,
                "launchd_label": "ai.openclaw.gateway",
                "plist": "~/Library/LaunchAgents/ai.openclaw.gateway.plist",
                "description": "Base gateway",
                "critical": True,
            },
            {
                "name": "enterprise",
                "port": 18789,
                "launchd_label": "",
                "plist": "",
                "description": "Enterprise gateway",
                "critical": True,
            },
            {
                "name": "vite-ui",
                "port": 5173,
                "launchd_label": "",
                "plist": "",
                "description": "Vite UI",
                "critical": False,
            },
        ],
    )


class TestDefaultPort:
    def test_default_port_is_3000(self) -> None:
        assert DEFAULT_PORT == 3000


class TestProbePort:
    def test_healthy_port(self) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            result = probe_port(3000, timeout=1)
        assert result["healthy"] is True
        assert result["port"] == 3000
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 3000))

    def test_unhealthy_port(self) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_sock_cls.return_value = mock_sock
            result = probe_port(18789, timeout=1)
        assert result["healthy"] is False
        assert result["port"] == 18789


class TestCheckHealth:
    def test_healthy_gateway(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health()
        assert health["healthy"] is True
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 3000))
        mock_sock.close.assert_called_once()

    def test_unhealthy_connection_refused(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health()
        assert health["healthy"] is False
        assert "refused" in health["detail"]

    def test_unhealthy_timeout(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = TimeoutError("timed out")
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health()
        assert health["healthy"] is False

    def test_check_health_custom_port(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health(port=18789)
        assert health["healthy"] is True
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 18789))


class TestCheckAllServices:
    def test_all_healthy(self, multi_service_watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            results = multi_service_watchdog.check_all_services()
        assert len(results) == 3
        assert results["gateway"]["healthy"] is True
        assert results["enterprise"]["healthy"] is True
        assert results["vite-ui"]["healthy"] is True

    def test_enterprise_down(self, multi_service_watchdog: GatewayWatchdog) -> None:
        call_count = 0

        def mock_connect(addr: tuple[str, int]) -> None:
            nonlocal call_count
            call_count += 1
            # First call (gateway:3000) succeeds, second (enterprise:18789) fails
            if addr[1] == 18789:
                raise ConnectionRefusedError("refused")

        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = mock_connect
            mock_sock_cls.return_value = mock_sock
            results = multi_service_watchdog.check_all_services()

        assert results["gateway"]["healthy"] is True
        assert results["enterprise"]["healthy"] is False
        assert results["enterprise"]["critical"] is True
        assert results["vite-ui"]["healthy"] is True

    def test_service_names_and_metadata(
        self, multi_service_watchdog: GatewayWatchdog
    ) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            results = multi_service_watchdog.check_all_services()
        assert results["enterprise"]["service_name"] == "enterprise"
        assert results["enterprise"]["description"] == "Enterprise gateway"
        assert results["vite-ui"]["critical"] is False


class TestRestartService:
    def test_restart_with_launchd(self, watchdog: GatewayWatchdog) -> None:
        svc = {
            "name": "gateway",
            "launchd_label": "ai.openclaw.gateway",
            "plist": "~/Library/LaunchAgents/ai.openclaw.gateway.plist",
        }
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = watchdog.restart_service(svc)
        assert result["success"] is True
        assert result["method"] == "kickstart"

    def test_no_launchd_label(self, watchdog: GatewayWatchdog) -> None:
        svc = {"name": "enterprise", "launchd_label": "", "plist": ""}
        result = watchdog.restart_service(svc)
        assert result["success"] is False
        assert result["method"] == "no_launchd"
        assert "Manual restart required" in result["output"]

    def test_restart_gateway_backward_compat(self, watchdog: GatewayWatchdog) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = watchdog.restart_gateway()
        assert result["success"] is True

    def test_fallback_to_bootout_bootstrap(self, watchdog: GatewayWatchdog) -> None:
        svc = {
            "name": "gateway",
            "launchd_label": "ai.openclaw.gateway",
            "plist": "~/Library/LaunchAgents/ai.openclaw.gateway.plist",
        }
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")
        success = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with (
            patch("subprocess.run", side_effect=[fail, success, success]),
            patch("gateway_watchdog.time.sleep"),
        ):
            result = watchdog.restart_service(svc)
        assert result["success"] is True
        assert result["method"] == "bootout+bootstrap"


class TestRunCheck:
    def test_all_healthy_no_restart(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            result = watchdog.run_check()
        assert result["status"] == "healthy"
        assert result["action"] == "none"
        assert "services" in result

    def test_enterprise_down_no_launchd(
        self, multi_service_watchdog: GatewayWatchdog
    ) -> None:
        """Enterprise gateway down but no launchd → critical_down (can't auto-fix)."""

        def mock_connect(addr: tuple[str, int]) -> None:
            if addr[1] == 18789:
                raise ConnectionRefusedError("refused")

        with (
            patch("gateway_watchdog.socket.socket") as mock_sock_cls,
            patch("gateway_watchdog.time.sleep"),
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = mock_connect
            mock_sock_cls.return_value = mock_sock
            result = multi_service_watchdog.run_check()

        assert result["status"] == "critical_down"
        assert result["action"] == "escalate"
        assert "enterprise" in result["restart_results"]
        assert result["restart_results"]["enterprise"]["recovered"] is False

    def test_gateway_down_then_recovered(self, watchdog: GatewayWatchdog) -> None:
        call_count = 0

        def mock_connect(addr: tuple[str, int]) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # First probe (initial check)
                raise ConnectionRefusedError("refused")
            # Subsequent probes succeed (after restart)

        with (
            patch("gateway_watchdog.socket.socket") as mock_sock_cls,
            patch("subprocess.run") as mock_run,
            patch("gateway_watchdog.time.sleep"),
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = mock_connect
            mock_sock_cls.return_value = mock_sock
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = watchdog.run_check()

        assert result["status"] == "recovered"
        assert result["action"] == "restarted"

    def test_non_critical_down_is_degraded(self, tmp_path: object) -> None:
        """Non-critical service down → degraded, not critical_down."""
        wdog = GatewayWatchdog(
            port=3000,
            state_dir=str(tmp_path),
            max_retries=1,
            retry_delay=0,
            health_timeout=1,
            services=[
                {
                    "name": "vite-ui",
                    "port": 5173,
                    "launchd_label": "",
                    "plist": "",
                    "description": "Vite UI",
                    "critical": False,
                },
            ],
        )

        with (
            patch("gateway_watchdog.socket.socket") as mock_sock_cls,
            patch("gateway_watchdog.time.sleep"),
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_sock_cls.return_value = mock_sock
            result = wdog.run_check()

        assert result["status"] == "degraded"


class TestStatePersistence:
    def test_state_saved_and_loaded(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            watchdog.run_check()
        status = watchdog.get_status()
        assert status["total_checks"] == 1
        assert status["healthy"] == 1

    def test_history_capped_at_50(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            for _ in range(55):
                watchdog.run_check()
        status = watchdog.get_status()
        assert status["total_checks"] == 50

    def test_uptime_percentage(self, watchdog: GatewayWatchdog) -> None:
        history = [{"status": "healthy"} for _ in range(8)] + [
            {"status": "recovered"} for _ in range(2)
        ]
        state = {"last_check": history[-1], "history": history}
        with open(watchdog._state_file, "w") as f:
            json.dump(state, f)
        status = watchdog.get_status()
        assert status["uptime_pct"] == 80.0
        assert status["recovered"] == 2

    def test_monitored_services_in_status(
        self, multi_service_watchdog: GatewayWatchdog
    ) -> None:
        status = multi_service_watchdog.get_status()
        assert "gateway" in status["monitored_services"]
        assert "enterprise" in status["monitored_services"]
        assert "vite-ui" in status["monitored_services"]


class TestLoadConfig:
    def test_loads_token_from_config(self, tmp_path: object) -> None:
        config = {"gateway": {"auth": {"token": "my-secret-token"}, "port": 3000}}
        config_path = os.path.join(str(tmp_path), "openclaw.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
        with patch("gateway_watchdog.os.path.expanduser", return_value=config_path):
            wdog = GatewayWatchdog(state_dir=str(tmp_path))
        assert wdog.token == "my-secret-token"

    def test_loads_port_from_config(self, tmp_path: object) -> None:
        config = {"gateway": {"auth": {"token": ""}, "port": 9999}}
        config_path = os.path.join(str(tmp_path), "openclaw.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        orig_expand = os.path.expanduser

        def mock_expand(p: str) -> str:
            if "openclaw.json" in p or "openclaw/openclaw" in p:
                return config_path
            return orig_expand(p)

        with patch("gateway_watchdog.os.path.expanduser", side_effect=mock_expand):
            wdog = GatewayWatchdog(port=0, state_dir=str(tmp_path))
        assert wdog.port == 9999

    def test_missing_config_uses_default_port(self, tmp_path: object) -> None:
        with patch(
            "gateway_watchdog.os.path.expanduser",
            return_value=os.path.join(str(tmp_path), "nonexistent.json"),
        ):
            wdog = GatewayWatchdog(state_dir=str(tmp_path))
        assert wdog.token == ""
        assert wdog.port == 3000

    def test_auto_detects_enterprise_service(self, tmp_path: object) -> None:
        config = {"gateway": {"port": 3000}}
        config_path = os.path.join(str(tmp_path), "openclaw.json")
        with open(config_path, "w") as f:
            json.dump(config, f)
        with patch("gateway_watchdog.os.path.expanduser", return_value=config_path):
            wdog = GatewayWatchdog(state_dir=str(tmp_path))
        service_names = [s["name"] for s in wdog.services]
        assert "gateway" in service_names
        assert "enterprise" in service_names
        assert "vite-ui" in service_names
        # Enterprise should be on port 18789
        enterprise = next(s for s in wdog.services if s["name"] == "enterprise")
        assert enterprise["port"] == 18789
