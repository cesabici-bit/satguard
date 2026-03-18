"""Tests for alert rules and webhook dispatcher (v0.2).

L1: Config parsing, should_alert logic, mocked webhook delivery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from satguard.alert.rules import AlertConfig, load_config, should_alert
from satguard.alert.webhook import send_alert
from satguard.history.store import ConjunctionHistory, PcSnapshot
from satguard.screen.screener import ConjunctionEvent


def _make_config(**overrides: object) -> AlertConfig:
    defaults = {
        "webhook_url": "https://hooks.example.com/test",
        "pc_threshold": 1e-4,
        "notify_on_new": True,
        "notify_on_rise": True,
        "cooldown_minutes": 60,
    }
    defaults.update(overrides)
    return AlertConfig(**defaults)  # type: ignore[arg-type]


def _make_snapshot(pc: float = 1e-5) -> PcSnapshot:
    t = datetime(2026, 3, 18, 12, 0, 0, tzinfo=UTC)
    return PcSnapshot(
        timestamp=t, tca=t, miss_distance_km=5.0,
        pc_foster=pc, pc_chan=None,
        tle_epoch_primary=t, tle_epoch_secondary=t,
        covariance_source="default_LEO",
    )


def _make_history(pcs: list[float]) -> ConjunctionHistory:
    snaps = tuple(_make_snapshot(pc=pc) for pc in pcs)
    return ConjunctionHistory(
        norad_id_a=25544, norad_id_b=41335,
        tca_window_center=datetime(2026, 3, 20, 8, 0, 0, tzinfo=UTC),
        snapshots=snaps,
    )


def _make_event() -> ConjunctionEvent:
    t = datetime(2026, 3, 20, 8, 0, 0, tzinfo=UTC)
    return ConjunctionEvent(
        tca=t,
        miss_distance_km=0.5,
        r_primary=np.array([7000.0, 0.0, 0.0]),
        v_primary=np.array([0.0, 7.5, 0.0]),
        r_secondary=np.array([7000.5, 0.0, 0.0]),
        v_secondary=np.array([0.0, -7.5, 0.0]),
        norad_id_primary=25544,
        norad_id_secondary=41335,
        relative_velocity_km_s=15.0,
    )


class TestAlertConfig:
    """L1: Config parsing tests."""

    def test_load_config_from_file(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[alert]\nwebhook_url = "https://hooks.example.com/abc"\n'
            "pc_threshold = 1e-5\ncooldown_minutes = 30\n",
            encoding="utf-8",
        )
        config = load_config(config_path)
        assert config.webhook_url == "https://hooks.example.com/abc"
        assert config.pc_threshold == pytest.approx(1e-5)
        assert config.cooldown_minutes == 30

    def test_missing_webhook_url_raises(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        config_path = tmp_path / "config.toml"
        config_path.write_text("[alert]\npc_threshold = 1e-5\n", encoding="utf-8")
        with pytest.raises(KeyError, match="webhook_url"):
            load_config(config_path)

    def test_missing_file_raises(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.toml")

    def test_defaults_applied(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            '[alert]\nwebhook_url = "https://hooks.example.com/abc"\n',
            encoding="utf-8",
        )
        config = load_config(config_path)
        assert config.pc_threshold == pytest.approx(1e-4)
        assert config.notify_on_new is True
        assert config.cooldown_minutes == 60


class TestShouldAlert:
    """L1: Alert trigger logic."""

    def test_below_threshold_no_alert(self) -> None:
        config = _make_config(pc_threshold=1e-4)
        assert should_alert(config, None, new_pc=1e-6) is False

    def test_new_conjunction_above_threshold(self) -> None:
        config = _make_config(pc_threshold=1e-4, notify_on_new=True)
        assert should_alert(config, None, new_pc=5e-4) is True

    def test_new_conjunction_notify_disabled(self) -> None:
        config = _make_config(pc_threshold=1e-4, notify_on_new=False)
        assert should_alert(config, None, new_pc=5e-4) is False

    def test_rising_through_threshold(self) -> None:
        """Was below threshold, now above → alert."""
        config = _make_config(pc_threshold=1e-4, notify_on_rise=True)
        history = _make_history([1e-6, 5e-5])  # Both below threshold
        assert should_alert(config, history, new_pc=5e-4) is True

    def test_already_above_threshold_no_realert(self) -> None:
        """Was already above threshold → no re-alert (cooldown)."""
        config = _make_config(pc_threshold=1e-4)
        history = _make_history([5e-4])  # Already above
        assert should_alert(config, history, new_pc=6e-4) is False

    def test_empty_history_treated_as_new(self) -> None:
        history = _make_history([])
        config = _make_config(pc_threshold=1e-4, notify_on_new=True)
        assert should_alert(config, history, new_pc=5e-4) is True


class TestWebhookDispatcher:
    """L1: Mocked webhook delivery."""

    @pytest.mark.anyio
    async def test_successful_delivery(self) -> None:
        config = _make_config()
        event = _make_event()

        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        with patch("satguard.alert.webhook.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await send_alert(config, event, pc=5e-4)

        assert result is True
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        assert call_kwargs[0][0] == config.webhook_url
        payload = call_kwargs[1]["json"]
        assert payload["tool"] == "satguard"
        assert payload["primary_norad"] == 25544
        assert payload["pc_foster"] == 5e-4

    @pytest.mark.anyio
    async def test_failed_delivery_returns_false(self) -> None:
        config = _make_config()
        event = _make_event()

        with patch("satguard.alert.webhook.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            result = await send_alert(config, event, pc=5e-4)

        assert result is False
