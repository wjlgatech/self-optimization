"""CLI entry point for the self-optimization system.

Usage:
    python src/__main__.py idle-check
    python src/__main__.py daily-review
    python src/__main__.py run-daemon [--interval 7200] [--review-hour 23]
    python src/__main__.py status
    python src/__main__.py intervention [--agent loopy-0]
    python src/__main__.py gateway-watchdog [--port 31415]
"""

import argparse
import json
import logging
import os
import sys

# Ensure src/ is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import SelfOptimizationOrchestrator  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Self-optimization system for OpenClaw agents")
    parser.add_argument(
        "--state-dir",
        default="",
        help="State persistence directory (default: ~/.openclaw/workspace/self-optimization/state)",
    )
    parser.add_argument(
        "--workspace-dir",
        default="",
        help="Workspace directory to scan (default: ~/.openclaw/workspace)",
    )
    parser.add_argument(
        "--agent-id",
        default="loopy-0",
        help="Agent identifier (default: loopy-0)",
    )
    parser.add_argument(
        "--config-path",
        default="",
        help="Path to monitoring config.yaml (default: auto-detect)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # idle-check
    subparsers.add_parser("idle-check", help="Run a single idle check")

    # daily-review
    subparsers.add_parser("daily-review", help="Run a full daily review")

    # run-daemon
    daemon_parser = subparsers.add_parser("run-daemon", help="Run as a daemon")
    daemon_parser.add_argument(
        "--interval", type=int, default=7200, help="Idle check interval in seconds"
    )
    daemon_parser.add_argument(
        "--review-hour", type=int, default=23, help="Hour to run daily review (0-23)"
    )

    # status
    subparsers.add_parser("status", help="Show current system status")

    # intervention
    intervention_parser = subparsers.add_parser(
        "intervention", help="Check intervention tier for an agent"
    )
    intervention_parser.add_argument(
        "--agent", default="", help="Agent to check (default: current agent)"
    )

    # gateway-watchdog
    gw_parser = subparsers.add_parser(
        "gateway-watchdog", help="Check gateway health and restart if down"
    )
    gw_parser.add_argument(
        "--port", type=int, default=0, help="Gateway port (default: from config)"
    )
    gw_parser.add_argument(
        "--token", default="", help="Gateway auth token (default: from config)"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create orchestrator
    orch = SelfOptimizationOrchestrator(
        state_dir=args.state_dir,
        workspace_dir=args.workspace_dir,
        agent_id=args.agent_id,
        config_path=args.config_path,
    )

    if args.command == "idle-check":
        result = orch.idle_check()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "daily-review":
        result = orch.daily_review()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "run-daemon":
        try:
            orch.run_daemon(idle_interval=args.interval, review_hour=args.review_hour)
        except KeyboardInterrupt:
            orch.stop_daemon()
            print("\nDaemon stopped.")

    elif args.command == "status":
        result = orch.status()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "intervention":
        agent = args.agent if args.agent else ""
        result = orch.get_intervention_tier(agent)
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "gateway-watchdog":
        from gateway_watchdog import GatewayWatchdog  # noqa: E402

        kwargs: dict[str, object] = {"state_dir": args.state_dir or ""}
        if args.port:
            kwargs["port"] = args.port
        if args.token:
            kwargs["token"] = args.token
        watchdog = GatewayWatchdog(**kwargs)  # type: ignore[arg-type]
        result = watchdog.run_check()
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") == "down":
            sys.exit(2)


if __name__ == "__main__":
    main()
