"""CelesTrak catalog ingest.

Fetches TLE data from CelesTrak's public API.
Reference: https://celestrak.org/NORAD/elements/
"""

from __future__ import annotations

import httpx

from satguard.catalog.tle import TLE, parse_tle_lines

CELESTRAK_BASE = "https://celestrak.org"
GP_URL = f"{CELESTRAK_BASE}/NORAD/elements/gp.php"


class Catalog:
    """Collection of TLEs with lookup capabilities."""

    def __init__(self, tles: list[TLE]) -> None:
        self.tles = tles
        self._by_norad: dict[int, TLE] = {t.norad_id: t for t in tles}

    def __len__(self) -> int:
        return len(self.tles)

    def get_by_norad(self, norad_id: int) -> TLE | None:
        return self._by_norad.get(norad_id)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.tles)


def parse_3le_text(text: str) -> list[TLE]:
    """Parse a multi-object 3LE text into a list of TLEs."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    tles: list[TLE] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            # 2-line format (no name)
            tles.append(parse_tle_lines("UNKNOWN", lines[i], lines[i + 1]))
            i += 2
        elif (
            i + 2 < len(lines)
            and lines[i + 1].startswith("1 ")
            and lines[i + 2].startswith("2 ")
        ):
            # 3-line format
            tles.append(parse_tle_lines(lines[i], lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1  # skip unknown line
    return tles


async def fetch_tle_by_norad(norad_id: int) -> TLE:
    """Fetch a single TLE by NORAD catalog number from CelesTrak.

    Args:
        norad_id: NORAD catalog number (e.g., 25544 for ISS).

    Returns:
        Parsed TLE.

    Raises:
        ValueError: If TLE not found.
        httpx.HTTPStatusError: On HTTP errors.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(GP_URL, params={"CATNR": norad_id, "FORMAT": "3le"})
        resp.raise_for_status()
        text = resp.text.strip()
        if not text or "No GP data found" in text:
            raise ValueError(f"No TLE found for NORAD ID {norad_id}")
        tles = parse_3le_text(text)
        if not tles:
            raise ValueError(f"Failed to parse TLE for NORAD ID {norad_id}")
        return tles[0]


async def fetch_catalog(group: str = "active") -> Catalog:
    """Fetch a catalog group from CelesTrak.

    Args:
        group: Catalog group name (e.g., 'active', 'stations', 'visual').

    Returns:
        Catalog with all TLEs in the group.
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(GP_URL, params={"GROUP": group, "FORMAT": "3le"})
        resp.raise_for_status()
        tles = parse_3le_text(resp.text)
        return Catalog(tles)
