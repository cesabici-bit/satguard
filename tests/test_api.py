"""Tests for the SatGuard FastAPI endpoints.

Uses mocked catalog data to avoid network calls.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from satguard.api.app import app, classify_orbit, orbital_params_from_tle
from satguard.api.cache import TTLCache, cache
from satguard.catalog.tle import TLE

# Synthetic TLE data for testing (realistic format)
# SOURCE: CelesTrak TLE format spec — https://celestrak.org/columns/v04n03/
MOCK_TLES = [
    TLE(
        name="ISS (ZARYA)",
        line1="1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9025",
        line2="2 25544  51.6400 100.0000 0007417  50.0000 310.0000 15.49560000400001",
        norad_id=25544,
        classification="U",
        intl_designator="98067A",
        epoch_year=24,
        epoch_day=1.5,
        mean_motion_dot=0.00016717,
        mean_motion_ddot=0.0,
        bstar=1.027e-4,
        element_set_type=0,
        element_number=902,
        inclination=51.64,
        raan=100.0,
        eccentricity=0.0007417,
        arg_perigee=50.0,
        mean_anomaly=310.0,
        mean_motion=15.4956,
        revolution_number=40000,
    ),
    TLE(
        name="STARLINK-1234",
        line1="1 44700U 19074A   24001.50000000  .00001234  00000-0  12345-4 0  9995",
        line2="2 44700  53.0500 200.0000 0001234 100.0000 260.0000 15.06000000200003",
        norad_id=44700,
        classification="U",
        intl_designator="19074A",
        epoch_year=24,
        epoch_day=1.5,
        mean_motion_dot=0.00001234,
        mean_motion_ddot=0.0,
        bstar=1.2345e-5,
        element_set_type=0,
        element_number=999,
        inclination=53.05,
        raan=200.0,
        eccentricity=0.0001234,
        arg_perigee=100.0,
        mean_anomaly=260.0,
        mean_motion=15.06,
        revolution_number=20000,
    ),
    TLE(
        name="GPS BIIR-2",
        line1="1 24876U 97035A   24001.50000000  .00000001  00000-0  00000+0 0  9997",
        line2="2 24876  55.5000 300.0000 0050000 200.0000 160.0000  2.00560000100005",
        norad_id=24876,
        classification="U",
        intl_designator="97035A",
        epoch_year=24,
        epoch_day=1.5,
        mean_motion_dot=0.00000001,
        mean_motion_ddot=0.0,
        bstar=0.0,
        element_set_type=0,
        element_number=999,
        inclination=55.5,
        raan=300.0,
        eccentricity=0.005,
        arg_perigee=200.0,
        mean_anomaly=160.0,
        mean_motion=2.0056,
        revolution_number=10000,
    ),
    TLE(
        name="VANGUARD 1",
        line1="1 00005U 58002B   24001.50000000  .00000001  00000-0  00000+0 0  9991",
        line2="2 00005  34.2500  50.0000 1845000 100.0000 260.0000  5.50000000100003",
        norad_id=5,
        classification="U",
        intl_designator="58002B",
        epoch_year=24,
        epoch_day=1.5,
        mean_motion_dot=0.00000001,
        mean_motion_ddot=0.0,
        bstar=0.0,
        element_set_type=0,
        element_number=999,
        inclination=34.25,
        raan=50.0,
        eccentricity=0.1845,
        arg_perigee=100.0,
        mean_anomaly=260.0,
        mean_motion=5.5,
        revolution_number=10000,
    ),
    TLE(
        name="GEO-SAT",
        line1="1 99999U 20001A   24001.50000000  .00000000  00000-0  00000+0 0  9993",
        line2="2 99999   0.0500  90.0000 0002000 270.0000  90.0000  1.00270000 50005",
        norad_id=99999,
        classification="U",
        intl_designator="20001A",
        epoch_year=24,
        epoch_day=1.5,
        mean_motion_dot=0.0,
        mean_motion_ddot=0.0,
        bstar=0.0,
        element_set_type=0,
        element_number=999,
        inclination=0.05,
        raan=90.0,
        eccentricity=0.0002,
        arg_perigee=270.0,
        mean_anomaly=90.0,
        mean_motion=1.0027,
        revolution_number=5000,
    ),
]


class MockCatalog:
    def __init__(self, tles: list[TLE]) -> None:
        self.tles = tles
        self._by_norad = {t.norad_id: t for t in tles}

    def __len__(self) -> int:
        return len(self.tles)

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.tles)

    def get_by_norad(self, norad_id: int) -> TLE | None:
        return self._by_norad.get(norad_id)


def _mock_catalog_entries() -> list[dict]:
    """Build expected catalog response from mock TLEs."""
    entries = []
    for tle in MOCK_TLES:
        params = orbital_params_from_tle(tle)
        entries.append({
            "norad_id": tle.norad_id,
            "name": tle.name,
            "line1": tle.line1,
            "line2": tle.line2,
            "object_type": classify_orbit(tle.mean_motion),
            "inclination_deg": round(tle.inclination, 4),
            "eccentricity": round(tle.eccentricity, 7),
            "raan_deg": round(tle.raan, 4),
            "arg_perigee_deg": round(tle.arg_perigee, 4),
            "mean_anomaly_deg": round(tle.mean_anomaly, 4),
            "mean_motion_rev_day": round(tle.mean_motion, 8),
            "bstar": tle.bstar,
            "epoch": tle.epoch_datetime.isoformat(),
            "intl_designator": tle.intl_designator,
            **params,
        })
    return entries


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear API cache before each test."""
    cache.clear()


@pytest.fixture
def client() -> TestClient:
    """Create FastAPI test client with mocked catalog."""
    return TestClient(app)


# --- classify_orbit tests ---


def test_classify_orbit_leo() -> None:
    """ISS mean_motion ~15.5 → LEO."""
    assert classify_orbit(15.5) == "LEO"
    assert classify_orbit(11.26) == "LEO"


def test_classify_orbit_meo() -> None:
    """GPS mean_motion ~2.0 → MEO."""
    assert classify_orbit(2.0) == "MEO"
    assert classify_orbit(1.8) == "MEO"
    assert classify_orbit(2.2) == "MEO"


def test_classify_orbit_geo() -> None:
    """GEO mean_motion ~1.0 → GEO."""
    assert classify_orbit(1.0) == "GEO"
    assert classify_orbit(0.9) == "GEO"
    assert classify_orbit(1.1) == "GEO"


def test_classify_orbit_other() -> None:
    """Vanguard 1 mean_motion ~5.5 → OTHER (HEO)."""
    assert classify_orbit(5.5) == "OTHER"
    assert classify_orbit(1.5) == "OTHER"


# --- orbital_params_from_tle tests ---


def test_orbital_params_iss() -> None:
    """ISS: period ~93 min, alt ~400 km.

    SOURCE: NASA ISS Fact Sheet — period 92.68 min, altitude ~408 km
    """
    iss = MOCK_TLES[0]
    params = orbital_params_from_tle(iss)
    assert 90.0 < params["period_min"] < 96.0
    assert 350.0 < params["perigee_alt_km"] < 450.0
    assert 350.0 < params["apogee_alt_km"] < 450.0


def test_orbital_params_geo() -> None:
    """GEO: period ~1436 min (~24h), alt ~35786 km.

    SOURCE: Vallado "Fundamentals of Astrodynamics" 5th Ed — GEO altitude 35786 km
    """
    geo = MOCK_TLES[4]
    params = orbital_params_from_tle(geo)
    assert 1430.0 < params["period_min"] < 1445.0
    assert 35000.0 < params["apogee_alt_km"] < 37000.0


# --- API endpoint tests ---


class TestCatalogEndpoint:
    """Tests for GET /api/catalog."""

    def test_catalog_returns_entries(self, client: TestClient) -> None:
        """Catalog endpoint returns list of satellite entries."""
        # Pre-populate cache to avoid real network call
        cache.set("catalog", _mock_catalog_entries(), 3600)

        resp = client.get("/api/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5

    def test_catalog_entry_fields(self, client: TestClient) -> None:
        """Each catalog entry has required fields."""
        cache.set("catalog", _mock_catalog_entries(), 3600)

        resp = client.get("/api/catalog")
        entry = resp.json()[0]
        assert "norad_id" in entry
        assert "name" in entry
        assert "line1" in entry
        assert "line2" in entry
        assert "object_type" in entry
        assert entry["object_type"] in ("LEO", "MEO", "GEO", "OTHER")

    def test_catalog_orbit_classification(self, client: TestClient) -> None:
        """Orbit types are classified correctly."""
        cache.set("catalog", _mock_catalog_entries(), 3600)

        resp = client.get("/api/catalog")
        data = {e["norad_id"]: e["object_type"] for e in resp.json()}
        assert data[25544] == "LEO"  # ISS
        assert data[24876] == "MEO"  # GPS
        assert data[99999] == "GEO"  # GEO-SAT
        assert data[5] == "OTHER"  # Vanguard (HEO)


class TestObjectDetailEndpoint:
    """Tests for GET /api/objects/{id}."""

    def test_object_found(self, client: TestClient) -> None:
        """Returns detail for a known object."""
        cache.set("catalog", _mock_catalog_entries(), 3600)
        cache.set("catalog_by_id", {e["norad_id"]: e for e in _mock_catalog_entries()}, 3600)

        resp = client.get("/api/objects/25544")
        assert resp.status_code == 200
        data = resp.json()
        assert data["norad_id"] == 25544
        assert data["name"] == "ISS (ZARYA)"
        assert "inclination_deg" in data
        assert "period_min" in data
        assert "apogee_alt_km" in data

    def test_object_not_found(self, client: TestClient) -> None:
        """Returns 404 for unknown NORAD ID."""
        cache.set("catalog", _mock_catalog_entries(), 3600)
        cache.set("catalog_by_id", {e["norad_id"]: e for e in _mock_catalog_entries()}, 3600)

        resp = client.get("/api/objects/11111")
        assert resp.status_code == 404


class TestConjunctionsEndpoint:
    """Tests for GET /api/conjunctions."""

    def test_conjunctions_cached(self, client: TestClient) -> None:
        """Returns cached conjunctions."""
        mock_conjs = [
            {
                "norad_id_primary": 25544,
                "norad_id_secondary": 44700,
                "tca": "2024-01-02T12:00:00",
                "miss_distance_km": 1.234,
                "relative_velocity_km_s": 14.5,
                "pc": 1.23e-6,
            }
        ]
        cache.set("conjunctions", mock_conjs, 600)

        resp = client.get("/api/conjunctions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["norad_id_primary"] == 25544

    def test_conjunctions_fields(self, client: TestClient) -> None:
        """Conjunction entries have required fields."""
        mock_conjs = [
            {
                "norad_id_primary": 25544,
                "norad_id_secondary": 44700,
                "tca": "2024-01-02T12:00:00",
                "miss_distance_km": 1.234,
                "relative_velocity_km_s": 14.5,
                "pc": 1.23e-6,
            }
        ]
        cache.set("conjunctions", mock_conjs, 600)

        resp = client.get("/api/conjunctions")
        conj = resp.json()[0]
        assert "tca" in conj
        assert "miss_distance_km" in conj
        assert "pc" in conj


class TestCache:
    """Tests for the TTL cache."""

    def test_cache_get_set(self) -> None:
        c = TTLCache()
        c.set("key", "value", 60)
        assert c.get("key") == "value"

    def test_cache_miss(self) -> None:
        c = TTLCache()
        assert c.get("nonexistent") is None

    def test_cache_clear(self) -> None:
        c = TTLCache()
        c.set("key", "value", 60)
        c.clear()
        assert c.get("key") is None
