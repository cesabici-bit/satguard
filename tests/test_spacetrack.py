"""Tests for Space-Track.org ingest.

Oracle L2: Space-Track API docs — https://www.space-track.org/documentation
These tests use mocks (no real credentials needed).
"""

import pytest

from satguard.catalog.spacetrack import SpaceTrackClient


class TestSpaceTrackClient:
    """L1: Mock tests for Space-Track client."""

    def test_missing_credentials_raises(self) -> None:
        """# SOURCE: Space-Track API — requires authentication."""
        with pytest.raises(ValueError, match="credentials"):
            SpaceTrackClient(username="", password="")

    def test_init_with_credentials(self) -> None:
        client = SpaceTrackClient(username="test@example.com", password="secret")
        assert client.username == "test@example.com"

    @pytest.mark.network
    def test_real_fetch_iss(self) -> None:
        """Integration test — requires real credentials in env vars.
        Skip unless SPACETRACK_USER is set.
        """
        import asyncio
        import os

        if not os.environ.get("SPACETRACK_USER"):
            pytest.skip("SPACETRACK_USER not set")

        async def _run() -> None:
            client = SpaceTrackClient()
            try:
                tle = await client.fetch_tle(25544)
                assert tle.norad_id == 25544
            finally:
                await client.close()

        asyncio.run(_run())
