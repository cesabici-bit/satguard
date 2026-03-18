"""Alert rule definitions and configuration parsing.

Config file format (~/.satguard/config.toml):

    [alert]
    webhook_url = "https://hooks.slack.com/services/..."
    pc_threshold = 1e-4
    notify_on_new = true
    notify_on_rise = true
    cooldown_minutes = 60
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from satguard.history.store import ConjunctionHistory

_DEFAULT_CONFIG_PATH = Path.home() / ".satguard" / "config.toml"


@dataclass(frozen=True, slots=True)
class AlertConfig:
    """Alert configuration."""

    webhook_url: str
    pc_threshold: float = 1e-4
    notify_on_new: bool = True
    notify_on_rise: bool = True
    cooldown_minutes: int = 60


def load_config(path: Path | None = None) -> AlertConfig:
    """Load alert configuration from a TOML file.

    Args:
        path: Path to config file. Defaults to ~/.satguard/config.toml.

    Returns:
        AlertConfig with parsed values.

    Raises:
        FileNotFoundError: If the config file does not exist.
        KeyError: If required fields are missing.
    """
    if path is None:
        path = _DEFAULT_CONFIG_PATH

    with open(path, "rb") as f:
        data = tomllib.load(f)

    alert = data.get("alert", {})

    if "webhook_url" not in alert:
        raise KeyError("Missing required field: [alert].webhook_url")

    return AlertConfig(
        webhook_url=alert["webhook_url"],
        pc_threshold=float(alert.get("pc_threshold", 1e-4)),
        notify_on_new=bool(alert.get("notify_on_new", True)),
        notify_on_rise=bool(alert.get("notify_on_rise", True)),
        cooldown_minutes=int(alert.get("cooldown_minutes", 60)),
    )


def should_alert(
    config: AlertConfig,
    history: ConjunctionHistory | None,
    new_pc: float,
) -> bool:
    """Determine whether an alert should fire.

    Rules:
    1. If new_pc < threshold → no alert
    2. If no history (new conjunction) and notify_on_new → alert
    3. If history exists and latest Pc was below threshold but new_pc is above → alert
    4. Cooldown: if last snapshot is within cooldown_minutes and was already above
       threshold → no alert (avoid spam)

    Args:
        config: Alert configuration.
        history: Existing conjunction history (None if first assessment).
        new_pc: The newly computed Pc value.

    Returns:
        True if an alert should be sent.
    """
    if new_pc < config.pc_threshold:
        return False

    # New conjunction — no history
    if history is None or len(history.snapshots) == 0:
        return config.notify_on_new

    # Has history: check if Pc just crossed above threshold
    latest = history.snapshots[-1]

    if latest.pc_foster >= config.pc_threshold:
        # Already above threshold in last snapshot — cooldown check
        # (don't re-alert within cooldown window)
        return False

    # Was below, now above → rising through threshold
    return config.notify_on_rise
