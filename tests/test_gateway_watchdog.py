"""Tests for gateway_watchdog module."""

import json
import os
import socket
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from gateway_watchdog import GatewayWatchdog


@pytest.fixture
def watchdog(tmp_path: object) -> GatewayWatchdog:
    """Create a watchdog with a temp state dir."""
    return GatewayWatchdog(
        port=31415,
        token="test-token",
        state_dir=str(tmp_path),
        max_retries=2,
        retry_delay=0,
        health_timeout=1,
    )


class TestCheckHealth:
    def test_healthy_gateway(self, watchdog: GatewayWatchdog) -> None:
        with patch("gateway_watchdog.socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health()
        assert health["healthy"] is True
        mock_sock.connect.assert_called_once_with(("127.0.0.1", 31415))
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
            mock_sock.connect.side_effect = socket.timeout("timed out")
            mock_sock_cls.return_value = mock_sock
            health = watchdog.check_health()
        assert health["healthy"] is False


class TestRestartGateway:
    def test_kickstart_succeeds(self, watchdog: GatewayWatchdog) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout="", stderr=""
            )
            result = watchdog.restart_gateway()
        assert result["success"] is True
        assert result["method"] == "kickstart"

    def test_fallback_to_bootout_bootstrap(self, watchdog: GatewayWatchdog) -> None:
        fail = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")
        success = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("subprocess.run", side_effect=[fail, success, success]):
            with patch("gateway_watchdog.time.sleep"):
                result = watchdog.restart_gateway()
        assert result["success"] is True
        assert result["method"] == "bootout+bootstrap"


class TestRunCheck:
    def test_healthy_no_restart(self, watchdog: GatewayWatchdog) -> None:
        with patch.object(
            watchdog,
            "check_health",
            return_value={"healthy": True, "port": 31415, "detail": "ok", "timestamp": "t"},
        ):
            result = watchdog.run_check()
        assert result["status"] == "healthy"
        assert result["action"] == "none"

    def test_unhealthy_then_recovered(self, watchdog: GatewayWatchdog) -> None:
        unhealthy = {"healthy": False, "port": 31415, "detail": "refused", "timestamp": "t"}
        healthy = {"healthy": True, "port": 31415, "detail": "ok", "timestamp": "t"}
        with patch.object(watchdog, "check_health", side_effect=[unhealthy, healthy]):
            with patch.object(
                watchdog,
                "restart_gateway",
                return_value={"method": "kickstart", "success": True, "output": "ok"},
            ):
                with patch("gateway_watchdog.time.sleep"):
                    result = watchdog.run_check()
        assert result["status"] == "recovered"
        assert result["action"] == "restarted"

    def test_unhealthy_all_retries_fail(self, watchdog: GatewayWatchdog) -> None:
        unhealthy = {"healthy": False, "port": 31415, "detail": "refused", "timestamp": "t"}
        with patch.object(watchdog, "check_health", return_value=unhealthy):
            with patch.object(
                watchdog,
                "restart_gateway",
                return_value={"method": "all_failed", "success": False, "output": "err"},
            ):
                with patch("gateway_watchdog.time.sleep"):
                    result = watchdog.run_check()
        assert result["status"] == "down"
        assert result["action"] == "escalate"
        assert result["total_attempts"] == 2


class TestStatePersistence:
    def test_state_saved_and_loaded(self, watchdog: GatewayWatchdog) -> None:
        with patch.object(
            watchdog,
            "check_health",
            return_value={"healthy": True, "port": 31415, "detail": "ok", "timestamp": "t"},
        ):
            watchdog.run_check()
        status = watchdog.get_status()
        assert status["total_checks"] == 1
        assert status["healthy"] == 1

    def test_history_capped_at_50(self, watchdog: GatewayWatchdog) -> None:
        with patch.object(
            watchdog,
            "check_health",
            return_value={"healthy": True, "port": 31415, "detail": "ok", "timestamp": "t"},
        ):
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


class TestLoadConfig:
    def test_loads_token_from_config(self, tmp_path: object) -> None:
        config = {"gateway": {"auth": {"token": "my-secret-token"}, "port": 31415}}
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

    def test_missing_config_returns_defaults(self, tmp_path: object) -> None:
        with patch(
            "gateway_watchdog.os.path.expanduser",
            return_value=os.path.join(str(tmp_path), "nonexistent.json"),
        ):
            wdog = GatewayWatchdog(state_dir=str(tmp_path))
        assert wdog.token == ""
        assert wdog.port == 31415
