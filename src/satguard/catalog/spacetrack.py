"""Space-Track.org catalog ingest.

Fetches TLE data from Space-Track.org REST API (requires credentials).
Reference: https://www.space-track.org/documentation
"""

from __future__ import annotations

import os

import httpx

from satguard.catalog.celestrak import Catalog, parse_3le_text
from satguard.catalog.tle import TLE

SPACETRACK_BASE = "https://www.space-track.org"
LOGIN_URL = f"{SPACETRACK_BASE}/ajaxauth/login"


class SpaceTrackClient:
    """Client for Space-Track.org REST API.

    Credentials are read from environment variables:
      - SPACETRACK_USER
      - SPACETRACK_PASSWORD
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.username = username or os.environ.get("SPACETRACK_USER", "")
        self.password = password or os.environ.get("SPACETRACK_PASSWORD", "")
        if not self.username or not self.password:
            raise ValueError(
                "Space-Track credentials required. Set SPACETRACK_USER and "
                "SPACETRACK_PASSWORD environment variables."
            )
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create authenticated HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
            resp = await self._client.post(
                LOGIN_URL,
                data={
                    "identity": self.username,
                    "password": self.password,
                },
            )
            resp.raise_for_status()
        return self._client

    async def fetch_tle(self, norad_id: int) -> TLE:
        """Fetch latest TLE for a single object.

        Args:
            norad_id: NORAD catalog number.

        Returns:
            Parsed TLE.
        """
        client = await self._get_client()
        url = (
            f"{SPACETRACK_BASE}/basicspacedata/query/class/tle_latest"
            f"/NORAD_CAT_ID/{norad_id}/ORDINAL/1/format/3le"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            raise ValueError(f"No TLE found for NORAD ID {norad_id}")
        tles = parse_3le_text(text)
        if not tles:
            raise ValueError(f"Failed to parse TLE for NORAD ID {norad_id}")
        return tles[0]

    async def fetch_catalog(self, epoch: str = ">now-30") -> Catalog:
        """Fetch catalog of recent TLEs.

        Args:
            epoch: Epoch filter (e.g., '>now-30' for last 30 days).

        Returns:
            Catalog with TLEs.
        """
        client = await self._get_client()
        url = (
            f"{SPACETRACK_BASE}/basicspacedata/query/class/tle_latest"
            f"/EPOCH/{epoch}/ORDINAL/1/format/3le"
        )
        resp = await client.get(url)
        resp.raise_for_status()
        tles = parse_3le_text(resp.text)
        return Catalog(tles)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
