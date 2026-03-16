"""Tests for CDM (Conjunction Data Message) writer.

Oracle L2: CCSDS 508.0-B-1 standard Section 4 — mandatory CDM fields.
"""

from datetime import UTC, datetime

import numpy as np

from satguard.cdm.writer import write_cdm
from satguard.screen.screener import ConjunctionEvent


def _make_event() -> ConjunctionEvent:
    return ConjunctionEvent(
        tca=datetime(2024, 6, 15, 12, 30, 0, tzinfo=UTC),
        miss_distance_km=0.5,
        r_primary=np.array([7000.0, 0.0, 0.0]),
        v_primary=np.array([0.0, 7.5, 0.0]),
        r_secondary=np.array([7000.5, 0.0, 0.0]),
        v_secondary=np.array([0.0, -7.5, 0.0]),
        norad_id_primary=25544,
        norad_id_secondary=34454,
        relative_velocity_km_s=15.0,
    )


class TestCDMWriter:
    """L1: CDM writer tests."""

    def test_contains_version(self) -> None:
        """# SOURCE: CCSDS 508.0-B-1 Section 4.2.1 — CCSDS_CDM_VERS mandatory."""
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "CCSDS_CDM_VERS" in cdm

    def test_contains_tca(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "TCA" in cdm

    def test_contains_miss_distance(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "MISS_DISTANCE" in cdm

    def test_contains_collision_probability(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "COLLISION_PROBABILITY" in cdm
        assert "1.230000e-05" in cdm

    def test_contains_both_objects(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "OBJECT1" in cdm
        assert "OBJECT2" in cdm

    def test_contains_object_designators(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "25544" in cdm
        assert "34454" in cdm

    def test_contains_state_vectors(self) -> None:
        cdm = write_cdm(_make_event(), 1.23e-5)
        assert "X_DOT" in cdm
        assert "Y_DOT" in cdm
        assert "Z_DOT" in cdm

    def test_contains_creation_date(self) -> None:
        cdm = write_cdm(_make_event(), 1.0e-6)
        assert "CREATION_DATE" in cdm

    def test_contains_originator(self) -> None:
        cdm = write_cdm(_make_event(), 1.0e-6)
        assert "ORIGINATOR" in cdm
        assert "SATGUARD" in cdm

    def test_miss_distance_in_meters(self) -> None:
        """CCSDS uses meters for miss distance."""
        event = _make_event()
        cdm = write_cdm(event, 1.0e-6)
        # 0.5 km = 500 m
        assert "500.000" in cdm

    def test_mandatory_fields_present(self) -> None:
        """# SOURCE: CCSDS 508.0-B-1 Section 4 — all mandatory fields."""
        cdm = write_cdm(_make_event(), 1.0e-6)
        mandatory = [
            "CCSDS_CDM_VERS",
            "CREATION_DATE",
            "ORIGINATOR",
            "MESSAGE_ID",
            "TCA",
            "MISS_DISTANCE",
            "COLLISION_PROBABILITY",
        ]
        for field in mandatory:
            assert field in cdm, f"Missing mandatory field: {field}"
