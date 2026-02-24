"""CLI entry point for the self-optimization system.

Usage:
    python src/__main__.py idle-check
    python src/__main__.py daily-review
    python src/__main__.py run-daemon [--interval 7200] [--review-hour 23]
    python src/__main__.py status
    python src/__main__.py intervention [--agent loopy-0]
    python src/__main__.py gateway-watchdog [--port 3000]
    python src/__main__.py cost-audit
    python src/__main__.py cost-apply [--strategy balanced]
    python src/__main__.py cost-baseline
    python src/__main__.py cost-status
    python src/__main__.py cost-govern
    python src/__main__.py self-eval [--no-services]
    python src/__main__.py self-heal
    python src/__main__.py self-discover
    python src/__main__.py marketing-eval [--markdown]
    python src/__main__.py marketing-discover
    python src/__main__.py marketing-score
    python src/__main__.py marketing-status
    python src/__main__.py marketing-metrics --content-id ID --impressions N ...
    python src/__main__.py marketing-publish --content-id ID --url URL [--date DATE]
    python src/__main__.py marketing-recommend
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

    # cost-audit
    subparsers.add_parser("cost-audit", help="Audit OpenClaw config for cost waste")

    # cost-apply
    cost_apply_parser = subparsers.add_parser(
        "cost-apply", help="Generate and apply optimized config"
    )
    cost_apply_parser.add_argument(
        "--strategy",
        choices=["aggressive", "balanced", "conservative"],
        default="balanced",
        help="Optimization strategy (default: balanced)",
    )
    cost_apply_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show patch without applying",
    )

    # cost-baseline
    subparsers.add_parser("cost-baseline", help="Record current state as cost baseline")

    # cost-status
    subparsers.add_parser("cost-status", help="Show cost governance status vs baseline")

    # cost-govern
    subparsers.add_parser("cost-govern", help="Run cost governor cycle (audit + compare + alert)")

    # gateway-watchdog
    gw_parser = subparsers.add_parser(
        "gateway-watchdog", help="Check gateway health and restart if down"
    )
    gw_parser.add_argument(
        "--port", type=int, default=0, help="Gateway port (default: from config)"
    )
    gw_parser.add_argument("--token", default="", help="Gateway auth token (default: from config)")

    # self-eval
    self_eval_parser = subparsers.add_parser(
        "self-eval", help="Run full self-evaluation (lint + types + tests + services)"
    )
    self_eval_parser.add_argument(
        "--no-services",
        action="store_true",
        help="Skip service health checks (for CI environments)",
    )
    self_eval_parser.add_argument(
        "--markdown", action="store_true", help="Output markdown report instead of JSON"
    )

    # self-heal
    subparsers.add_parser(
        "self-heal", help="Auto-fix lint/format issues and repair corrupted state"
    )

    # self-discover
    subparsers.add_parser(
        "self-discover", help="Discover services, repos, and config drift"
    )

    # ── Marketing eval commands ──────────────────────────────────────

    # marketing-eval
    mkt_eval_parser = subparsers.add_parser(
        "marketing-eval", help="Full marketing content evaluation"
    )
    mkt_eval_parser.add_argument(
        "--markdown", action="store_true", help="Output markdown report instead of JSON"
    )

    # marketing-discover
    subparsers.add_parser(
        "marketing-discover", help="Scan marketing/ for content items"
    )

    # marketing-score
    subparsers.add_parser(
        "marketing-score", help="Score all marketing content"
    )

    # marketing-status
    subparsers.add_parser(
        "marketing-status", help="Show content inventory (published vs draft)"
    )

    # marketing-metrics
    mkt_metrics_parser = subparsers.add_parser(
        "marketing-metrics", help="Update metrics for a content item"
    )
    mkt_metrics_parser.add_argument("--content-id", required=True, help="Content ID to update")
    mkt_metrics_parser.add_argument("--impressions", type=int, default=None)
    mkt_metrics_parser.add_argument("--engagements", type=int, default=None)
    mkt_metrics_parser.add_argument("--clicks", type=int, default=None)
    mkt_metrics_parser.add_argument("--conversions", type=int, default=None)

    # marketing-publish
    mkt_publish_parser = subparsers.add_parser(
        "marketing-publish", help="Mark content as published"
    )
    mkt_publish_parser.add_argument("--content-id", required=True, help="Content ID to publish")
    mkt_publish_parser.add_argument("--url", required=True, help="Published URL")
    mkt_publish_parser.add_argument("--date", default="", help="Publish date (ISO format)")

    # marketing-recommend
    subparsers.add_parser(
        "marketing-recommend", help="Generate improvement recommendations"
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

    elif args.command == "cost-audit":
        from cost_governor import CostGovernor  # noqa: E402

        gov = CostGovernor(
            workspace_dir=args.workspace_dir or "",
            state_dir=args.state_dir or "",
        )
        result = gov.audit()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "cost-apply":
        from cost_governor import CostGovernor  # noqa: E402

        gov = CostGovernor(
            workspace_dir=args.workspace_dir or "",
            state_dir=args.state_dir or "",
        )
        optimized = gov.generate_optimized_config(strategy=args.strategy)
        print(json.dumps(optimized, indent=2, default=str))

        if not args.dry_run:
            confirm = input("\nApply this config? [y/N] ").strip().lower()
            if confirm == "y":
                apply_result = gov.apply_config(optimized["patch"])
                print(json.dumps(apply_result, indent=2, default=str))
            else:
                print("Skipped.")

    elif args.command == "cost-baseline":
        from cost_governor import CostGovernor  # noqa: E402

        gov = CostGovernor(
            workspace_dir=args.workspace_dir or "",
            state_dir=args.state_dir or "",
        )
        baseline = gov.record_baseline(label="manual")
        print(json.dumps(baseline, indent=2, default=str))

    elif args.command == "cost-status":
        from cost_governor import CostGovernor  # noqa: E402

        gov = CostGovernor(
            workspace_dir=args.workspace_dir or "",
            state_dir=args.state_dir or "",
        )
        result = gov.status()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "cost-govern":
        from cost_governor import CostGovernor  # noqa: E402

        gov = CostGovernor(
            workspace_dir=args.workspace_dir or "",
            state_dir=args.state_dir or "",
        )
        result = gov.run_governor()
        print(json.dumps(result, indent=2, default=str))
        if result.get("status") == "needs_attention":
            sys.exit(1)

    elif args.command == "self-eval":
        from self_eval import SelfEvalEngine  # noqa: E402

        engine = SelfEvalEngine(state_dir=args.state_dir or "")
        report = engine.run_full_eval(include_services=not args.no_services)
        if args.markdown:
            print(engine.generate_markdown_report(report))
        else:
            print(json.dumps(report, indent=2, default=str))
        if report.get("grade") in ("D", "F"):
            sys.exit(1)

    elif args.command == "self-heal":
        from self_eval import SelfEvalEngine  # noqa: E402

        engine = SelfEvalEngine(state_dir=args.state_dir or "")
        print("Healing lint issues...")
        lint_result = engine.heal_lint()
        print(json.dumps(lint_result, indent=2, default=str))
        print("\nHealing formatting...")
        fmt_result = engine.heal_format()
        print(json.dumps(fmt_result, indent=2, default=str))
        print("\nRepairing corrupted state files...")
        state_result = engine.heal_state()
        print(json.dumps(state_result, indent=2, default=str))

    elif args.command == "self-discover":
        from self_eval import SelfEvalEngine  # noqa: E402

        engine = SelfEvalEngine(
            state_dir=args.state_dir or "",
            workspace_dir=args.workspace_dir or "",
        )
        discovery: dict[str, object] = {
            "services": engine.discover_services(),
            "repos": engine.discover_repos(),
            "config_drift": engine.discover_config_drift(),
        }
        print(json.dumps(discovery, indent=2, default=str))

    # ── Marketing eval commands ──────────────────────────────────────

    elif args.command == "marketing-eval":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        report = mkt.run_full_eval()
        if args.markdown:
            print(mkt.generate_markdown_report(report))
        else:
            print(json.dumps(report, indent=2, default=str))
        if report.get("grade") in ("D", "F"):
            sys.exit(1)

    elif args.command == "marketing-discover":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        result = mkt.discover_content()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "marketing-score":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        mkt.discover_content()
        result = mkt.score_all()
        print(json.dumps(result, indent=2, default=str))

    elif args.command == "marketing-status":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        result = mkt.discover_content()
        status = {
            "total": result["total"],
            "published": result["published"],
            "draft": result["draft"],
            "content": [
                {
                    "id": c["content_id"],
                    "title": c["title"],
                    "status": c["status"],
                    "channel": c["channel"],
                    "type": c["content_type"],
                }
                for c in result["content"]
            ],
        }
        print(json.dumps(status, indent=2, default=str))

    elif args.command == "marketing-metrics":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        mkt.discover_content()
        metrics: dict[str, int] = {}
        if args.impressions is not None:
            metrics["impressions"] = args.impressions
        if args.engagements is not None:
            metrics["engagements"] = args.engagements
        if args.clicks is not None:
            metrics["clicks"] = args.clicks
        if args.conversions is not None:
            metrics["conversions"] = args.conversions
        result = mkt.update_metrics(args.content_id, metrics)
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)

    elif args.command == "marketing-publish":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        mkt.discover_content()
        result = mkt.set_published(args.content_id, args.url, args.date)
        print(json.dumps(result, indent=2, default=str))
        if not result.get("success"):
            sys.exit(1)

    elif args.command == "marketing-recommend":
        from marketing_eval import MarketingEvalEngine  # noqa: E402

        mkt = MarketingEvalEngine(state_dir=args.state_dir or "")
        mkt.discover_content()
        recs = mkt.generate_recommendations()
        print(json.dumps(recs, indent=2, default=str))


if __name__ == "__main__":
    main()
