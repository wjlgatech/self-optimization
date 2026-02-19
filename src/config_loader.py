"""Load monitoring config from performance-system/monitoring/config.yaml.

Uses stdlib only (no PyYAML dependency). Falls back to defaults if the
config file is missing or malformed.
"""

import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Defaults matching the config.yaml schema
DEFAULT_CONFIG: Dict[str, Any] = {
    "agents": ["loopy-0"],
    "monitoring_interval": "1h",
    "thresholds": {
        "goal_completion_rate": {"warning": 0.7, "critical": 0.5},
        "task_efficiency": {"warning": 0.65, "critical": 0.4},
    },
    "intervention_tiers": {
        "tier1": {"duration": "2 weeks", "actions": ["performance_review", "skill_assessment"]},
        "tier2": {
            "duration": "1 month",
            "actions": ["targeted_coaching", "personalized_learning_plan"],
        },
        "tier3": {
            "duration": "3 months",
            "actions": [
                "comprehensive_performance_rehabilitation",
                "external_skill_development_resources",
            ],
        },
    },
    "notification_channels": ["internal_dashboard", "periodic_report"],
}

# Agent name normalization: config.yaml uses "loopy"/"loopy1",
# the system uses "loopy-0"/"loopy-1"
_AGENT_NAME_MAP: Dict[str, str] = {
    "loopy": "loopy-0",
    "loopy1": "loopy-1",
}


def _normalize_agent_name(name: str) -> str:
    """Normalize agent name from config format to system format."""
    name = str(name).strip()
    return _AGENT_NAME_MAP.get(name, name)


def _extract_agents_from_text(text: str) -> List[str]:
    """Extract agent names from raw YAML text using regex."""
    agents_block = re.search(r"agents:\s*\n((?:\s+-\s+\S+\n?)+)", text)
    if not agents_block:
        return []
    return [
        _normalize_agent_name(m) for m in re.findall(r"-\s+(\S+)", agents_block.group(1))
    ]


def _extract_thresholds_from_text(text: str) -> Dict[str, Dict[str, float]]:
    """Extract threshold values from raw YAML text using regex."""
    thresholds: Dict[str, Dict[str, float]] = {}

    for metric in ("goal_completion_rate", "task_efficiency"):
        block_match = re.search(rf"{metric}:\s*\n((?:\s+\w+:\s+[\d.]+\n?)+)", text)
        if block_match:
            block = block_match.group(1)
            warning_m = re.search(r"warning_level:\s+([\d.]+)", block)
            critical_m = re.search(r"critical_level:\s+([\d.]+)", block)
            default_t = DEFAULT_CONFIG["thresholds"].get(metric, {})
            warn_val = (
                float(warning_m.group(1)) if warning_m else default_t.get("warning", 0.7)
            )
            crit_val = (
                float(critical_m.group(1)) if critical_m else default_t.get("critical", 0.5)
            )
            thresholds[metric] = {"warning": warn_val, "critical": crit_val}

    return thresholds


def _extract_intervention_tiers_from_text(text: str) -> Dict[str, Dict[str, Any]]:
    """Extract intervention tiers from raw YAML text."""
    tiers: Dict[str, Dict[str, Any]] = {}

    for tier_name in ("tier1", "tier2", "tier3"):
        tier_match = re.search(
            rf"{tier_name}:\s*\n\s+duration:\s+(.+)\n\s+actions:\s*\n((?:\s+-\s+\S+\n?)+)",
            text,
        )
        if tier_match:
            duration = tier_match.group(1).strip()
            actions = re.findall(r"-\s+(\S+)", tier_match.group(2))
            tiers[tier_name] = {"duration": duration, "actions": actions}

    return tiers


def _extract_notification_channels(text: str) -> List[str]:
    """Extract notification channels from raw YAML text."""
    block_match = re.search(r"notification_channels:\s*\n((?:\s+-\s+\S+\n?)+)", text)
    if not block_match:
        return []
    return re.findall(r"-\s+(\S+)", block_match.group(1))


def _extract_monitoring_interval(text: str) -> str:
    """Extract monitoring interval from raw YAML text."""
    match = re.search(r"interval:\s+(\S+)", text)
    return match.group(1) if match else DEFAULT_CONFIG["monitoring_interval"]


def _deep_copy_config(obj: Any) -> Any:
    """Simple deep copy for JSON-like structures."""
    if isinstance(obj, dict):
        return {k: _deep_copy_config(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy_config(item) for item in obj]
    return obj


def load_monitoring_config(config_path: str = "") -> Dict[str, Any]:
    """Load and normalize the monitoring config.

    Args:
        config_path: Path to config.yaml. If empty, tries the default location.

    Returns:
        Normalized config dict with keys: agents, thresholds, intervention_tiers,
        monitoring_interval, notification_channels.
    """
    if not config_path:
        config_path = os.path.expanduser(
            "~/.openclaw/workspace/performance-system/monitoring/config.yaml"
        )

    if not os.path.isfile(config_path):
        logger.info("Config not found at %s, using defaults", config_path)
        result: Dict[str, Any] = _deep_copy_config(DEFAULT_CONFIG)
        return result

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        logger.warning("Failed to read config: %s", e)
        fallback: Dict[str, Any] = _deep_copy_config(DEFAULT_CONFIG)
        return fallback

    config: Dict[str, Any] = {}

    # Agents
    agents = _extract_agents_from_text(text)
    config["agents"] = agents if agents else list(DEFAULT_CONFIG["agents"])

    # Monitoring interval
    config["monitoring_interval"] = _extract_monitoring_interval(text)

    # Thresholds
    thresholds = _extract_thresholds_from_text(text)
    config["thresholds"] = (
        thresholds if thresholds else _deep_copy_config(DEFAULT_CONFIG["thresholds"])
    )

    # Intervention tiers
    tiers = _extract_intervention_tiers_from_text(text)
    config["intervention_tiers"] = (
        tiers if tiers else _deep_copy_config(DEFAULT_CONFIG["intervention_tiers"])
    )

    # Notification channels
    channels = _extract_notification_channels(text)
    config["notification_channels"] = (
        channels if channels else list(DEFAULT_CONFIG["notification_channels"])
    )

    logger.info(
        "Loaded monitoring config: %d agents, %d thresholds",
        len(config["agents"]),
        len(config["thresholds"]),
    )
    return config
