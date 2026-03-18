"""Webhook alert dispatcher.

Sends JSON POST to configured webhook URL (Slack, Discord, Teams, etc.).
Fire-and-forget: alert failure never blocks the pipeline.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from satguard.alert.rules import AlertConfig
from satguard.history.evolution import pc_trend
from satguard.history.store import ConjunctionHistory
from satguard.screen.screener import ConjunctionEvent

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_MAX_RETRIES = 1


async def send_alert(
    config: AlertConfig,
    event: ConjunctionEvent,
    pc: float,
    history: ConjunctionHistory | None = None,
) -> bool:
    """Send a webhook alert for a conjunction event.

    Args:
        config: Alert configuration with webhook URL.
        event: The conjunction event triggering the alert.
        pc: Computed collision probability (Foster method).
        history: Optional conjunction history for trend info.

    Returns:
        True if the webhook was delivered successfully, False otherwise.
    """
    trend_str = "UNKNOWN"
    previous_pc: float | None = None
    if history and len(history.snapshots) >= 1:
        trend_result = pc_trend(history)
        trend_str = trend_result.direction.value
        if len(history.snapshots) >= 2:
            previous_pc = history.snapshots[-1].pc_foster

    payload = {
        "tool": "satguard",
        "event": "conjunction_alert",
        "primary_norad": event.norad_id_primary,
        "secondary_norad": event.norad_id_secondary,
        "tca": event.tca.isoformat().replace("+00:00", "Z"),
        "miss_distance_km": round(event.miss_distance_km, 3),
        "pc_foster": pc,
        "trend": trend_str,
        "previous_pc": previous_pc,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "message": (
            f"Pc for NORAD {event.norad_id_primary} vs {event.norad_id_secondary} "
            f"= {pc:.2e} exceeds threshold {config.pc_threshold:.1e}"
        ),
    }

    for attempt in range(_MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
                resp = await client.post(config.webhook_url, json=payload)
                resp.raise_for_status()
                logger.info("Alert sent successfully to %s", config.webhook_url)
                return True
        except Exception as exc:
            if attempt < _MAX_RETRIES:
                logger.warning("Alert attempt %d failed: %s. Retrying...", attempt + 1, exc)
            else:
                logger.warning("Alert delivery failed after %d attempts: %s", attempt + 1, exc)

    return False
