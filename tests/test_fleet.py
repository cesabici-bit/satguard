"""Tests for fleet parsing, batch screening, and PDF report generation (v0.5).

Covers:
    - S1: Fleet YAML parser (valid, invalid, edge cases)
    - S2: Batch screening (with mock catalog)
    - S3: PDF report generation
    - S4: CLI fleet command
"""

from __future__ import annotations

import asyncio
import textwrap
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from satguard.fleet.parser import FleetConfig, FleetThresholds, load_fleet
from satguard.screen.screener import ConjunctionEvent

# ============================================================
# S1: Fleet Parser Tests
# ============================================================


class TestFleetParser:
    """L1: Unit tests for fleet YAML parser."""

    def test_parse_valid_fleet(self, tmp_path: Path) -> None:
        """Parse a well-formed fleet.yaml with all fields."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text(textwrap.dedent("""\
            name: TestConstellation
            thresholds:
              pc: 1.0e-5
              miss_km: 25.0
              days: 5
            objects:
              - 25544
              - 48274
              - 53239
        """))

        config = load_fleet(fleet_file)
        assert config.name == "TestConstellation"
        assert config.objects == [25544, 48274, 53239]
        assert config.thresholds.pc == 1e-5
        assert config.thresholds.miss_km == 25.0
        assert config.thresholds.days == 5

    def test_parse_minimal_fleet(self, tmp_path: Path) -> None:
        """Parse fleet.yaml with only required fields (defaults for thresholds)."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text(textwrap.dedent("""\
            name: MinimalFleet
            objects:
              - 25544
        """))

        config = load_fleet(fleet_file)
        assert config.name == "MinimalFleet"
        assert config.objects == [25544]
        # Defaults
        assert config.thresholds.pc == 1e-6
        assert config.thresholds.miss_km == 50.0
        assert config.thresholds.days == 3

    def test_parse_missing_file(self, tmp_path: Path) -> None:
        """Raise FileNotFoundError for non-existent file."""
        with pytest.raises(FileNotFoundError, match="not found"):
            load_fleet(tmp_path / "nonexistent.yaml")

    def test_parse_invalid_yaml(self, tmp_path: Path) -> None:
        """Raise ValueError for invalid YAML syntax."""
        fleet_file = tmp_path / "bad.yaml"
        fleet_file.write_text("name: [unclosed bracket")

        with pytest.raises(ValueError, match="Invalid YAML"):
            load_fleet(fleet_file)

    def test_parse_missing_name(self, tmp_path: Path) -> None:
        """Raise ValueError when 'name' is missing."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("objects:\n  - 25544\n")

        with pytest.raises(ValueError, match="name"):
            load_fleet(fleet_file)

    def test_parse_missing_objects(self, tmp_path: Path) -> None:
        """Raise ValueError when 'objects' is missing."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("name: Test\n")

        with pytest.raises(ValueError, match="objects"):
            load_fleet(fleet_file)

    def test_parse_empty_objects(self, tmp_path: Path) -> None:
        """Raise ValueError when 'objects' is empty list."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("name: Test\nobjects: []\n")

        with pytest.raises(ValueError, match="objects"):
            load_fleet(fleet_file)

    def test_parse_invalid_norad_id(self, tmp_path: Path) -> None:
        """Raise ValueError for non-integer NORAD ID."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("name: Test\nobjects:\n  - abc\n")

        with pytest.raises(ValueError, match="positive integer"):
            load_fleet(fleet_file)

    def test_parse_negative_norad_id(self, tmp_path: Path) -> None:
        """Raise ValueError for negative NORAD ID."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("name: Test\nobjects:\n  - -1\n")

        with pytest.raises(ValueError, match="positive integer"):
            load_fleet(fleet_file)

    def test_parse_invalid_threshold_pc(self, tmp_path: Path) -> None:
        """Raise ValueError for non-positive Pc threshold."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text(textwrap.dedent("""\
            name: Test
            thresholds:
              pc: -1
            objects:
              - 25544
        """))

        with pytest.raises(ValueError, match="pc"):
            load_fleet(fleet_file)

    def test_parse_not_a_mapping(self, tmp_path: Path) -> None:
        """Raise ValueError when YAML root is not a dict."""
        fleet_file = tmp_path / "fleet.yaml"
        fleet_file.write_text("- just\n- a\n- list\n")

        with pytest.raises(ValueError, match="mapping"):
            load_fleet(fleet_file)

    def test_fleet_thresholds_defaults(self) -> None:
        """FleetThresholds defaults are sensible."""
        t = FleetThresholds()
        assert t.pc == 1e-6
        assert t.miss_km == 50.0
        assert t.days == 3


# ============================================================
# S2: Batch Screening Tests
# ============================================================


def _make_mock_conjunction(
    norad_primary: int = 25544,
    norad_secondary: int = 99999,
    miss_km: float = 1.0,
    vrel: float = 10.0,
    tca_offset_hours: float = 0.0,
) -> ConjunctionEvent:
    """Create a mock ConjunctionEvent."""
    tca = datetime(2026, 3, 20, 12, 0, 0, tzinfo=UTC) + timedelta(hours=tca_offset_hours)
    return ConjunctionEvent(
        tca=tca,
        miss_distance_km=miss_km,
        r_primary=np.array([7000.0, 0.0, 0.0]),
        v_primary=np.array([0.0, 7.5, 0.0]),
        r_secondary=np.array([7000.0 + miss_km, 0.0, 0.0]),
        v_secondary=np.array([0.0, -7.5, 0.0]),
        norad_id_primary=norad_primary,
        norad_id_secondary=norad_secondary,
        relative_velocity_km_s=vrel,
    )


class TestBatchScreening:
    """L1: Unit tests for batch screening logic."""

    def test_score_event_returns_pc(self) -> None:
        """_score_event computes a valid Pc for a conjunction."""
        from satguard.fleet.batch import _score_event

        event = _make_mock_conjunction(miss_km=1.0)
        result = _score_event(event)
        assert result is not None
        assert 0 < result.pc <= 1.0
        assert result.event is event

    def test_score_event_closer_has_higher_pc(self) -> None:
        """Closer approaches should yield higher Pc.

        # SOURCE: Foster 1992 — Pc monotonically decreases with miss distance
        # for fixed covariance. A 0.1 km miss should have Pc > 1.0 km miss.
        """
        from satguard.fleet.batch import _score_event

        close = _score_event(_make_mock_conjunction(miss_km=0.1))
        far = _score_event(_make_mock_conjunction(miss_km=5.0))
        assert close is not None and far is not None
        assert close.pc > far.pc

    def test_pair_key_canonical(self) -> None:
        """_pair_key always returns (smaller, larger)."""
        from satguard.fleet.batch import _pair_key

        assert _pair_key(999, 100) == (100, 999)
        assert _pair_key(100, 999) == (100, 999)

    def test_screen_fleet_unfetchable_objects(self) -> None:
        """Fleet with unfetchable TLEs produces no results."""
        from satguard.fleet.batch import screen_fleet

        config = FleetConfig(
            name="Ghost",
            objects=[99999999],
            thresholds=FleetThresholds(pc=0, miss_km=100, days=1),
        )

        # Mock catalog with no TLEs (object not in catalog)
        mock_catalog = MagicMock()
        mock_catalog.__len__ = MagicMock(return_value=0)
        mock_catalog.tles = []

        results = asyncio.run(screen_fleet(config, catalog=mock_catalog))
        assert results == []


# ============================================================
# S3: PDF Report Tests
# ============================================================


class TestPdfReport:
    """L1: Unit tests for PDF report generation."""

    def _make_scored_conjunctions(self, n: int = 5) -> list:
        from satguard.fleet.batch import ScoredConjunction

        results = []
        for i in range(n):
            event = _make_mock_conjunction(
                norad_secondary=40000 + i,
                miss_km=float(i + 1) * 0.5,
                tca_offset_hours=float(i),
            )
            # Approximate Pc (decreasing with distance)
            pc = 1e-3 / (i + 1)
            results.append(ScoredConjunction(event=event, pc=pc))
        return results

    def test_generate_report_creates_file(self, tmp_path: Path) -> None:
        """generate_report produces a non-empty PDF file."""
        from satguard.report.pdf import generate_report

        fleet = FleetConfig(name="TestFleet", objects=[25544, 48274])
        conjunctions = self._make_scored_conjunctions(5)
        out = tmp_path / "test_report.pdf"

        result = generate_report(fleet, conjunctions, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 1000  # At least 1KB

    def test_generate_report_has_multiple_pages(self, tmp_path: Path) -> None:
        """PDF report with conjunctions has multiple pages (cover + content)."""
        from satguard.report.pdf import generate_report

        fleet = FleetConfig(name="Starlink-Test", objects=[25544])
        conjunctions = self._make_scored_conjunctions(5)
        out = tmp_path / "test.pdf"

        generate_report(fleet, conjunctions, out)
        content = out.read_bytes()
        # fpdf2 writes /Count N for total pages — with cover+summary+table+plots+cdm
        # we expect at least 4 pages
        assert out.stat().st_size > 5000
        # Check PDF structure: multiple page objects
        page_count = content.count(b"/Type /Page\n")
        assert page_count >= 4, f"Expected >=4 pages, got {page_count}"

    def test_generate_report_no_conjunctions(self, tmp_path: Path) -> None:
        """Report generates successfully even with zero conjunctions."""
        from satguard.report.pdf import generate_report

        fleet = FleetConfig(name="EmptyFleet", objects=[25544])
        out = tmp_path / "empty.pdf"

        generate_report(fleet, [], out)
        assert out.exists()
        assert out.stat().st_size > 500

    def test_generate_report_creates_parent_dirs(self, tmp_path: Path) -> None:
        """Report creates parent directories if they don't exist."""
        from satguard.report.pdf import generate_report

        fleet = FleetConfig(name="Test", objects=[25544])
        out = tmp_path / "subdir" / "nested" / "report.pdf"

        generate_report(fleet, self._make_scored_conjunctions(1), out)
        assert out.exists()

    def test_generate_report_with_many_conjunctions(self, tmp_path: Path) -> None:
        """Report handles 50+ conjunctions (table pagination)."""
        from satguard.report.pdf import generate_report

        fleet = FleetConfig(name="LargeFleet", objects=[25544])
        conjunctions = self._make_scored_conjunctions(60)
        out = tmp_path / "large.pdf"

        generate_report(fleet, conjunctions, out)
        assert out.exists()
        assert out.stat().st_size > 5000


# ============================================================
# S4: CLI Fleet Command Tests
# ============================================================


class TestFleetCLI:
    """L1: CLI integration tests for fleet command."""

    def test_fleet_group_exists(self) -> None:
        """'fleet' command group is registered."""
        from click.testing import CliRunner

        from satguard.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["fleet", "--help"])
        assert result.exit_code == 0
        assert "screen" in result.output

    def test_fleet_screen_help(self) -> None:
        """'fleet screen --help' shows expected options."""
        from click.testing import CliRunner

        from satguard.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["fleet", "screen", "--help"])
        assert result.exit_code == 0
        assert "--fleet" in result.output
        assert "--output" in result.output
        assert "--no-pdf" in result.output

    def test_fleet_screen_missing_file(self) -> None:
        """'fleet screen' with non-existent file shows error."""
        from click.testing import CliRunner

        from satguard.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["fleet", "screen", "--fleet", "/nonexistent/fleet.yaml"])
        assert result.exit_code != 0


# ============================================================
# L2: Domain Sanity Tests
# ============================================================


class TestDomainSanity:
    """L2: Domain-level sanity checks for fleet screening."""

    def test_score_event_pc_matches_alfano_isotropic(self) -> None:
        """_score_event Pc matches Alfano 2005 analytical formula for isotropic case.

        # SOURCE: Alfano 2005, "Numerical Implementation of Spherical Object
        # Collision Probability", Table 1 & Eq. 3.
        # For isotropic 2D covariance (sigma_x = sigma_y = sigma), the Pc has
        # a closed-form: Pc = 1 - exp(-R^2 / (2*sigma^2))
        # where R = hard_body_radius, sigma = combined position uncertainty.
        #
        # With default LEO covariance (1 km per axis, so combined sigma^2 = 2 km^2
        # projected to encounter plane) and miss_distance ≈ 0 km, HBR = 0.02 km:
        #   Pc_max ≈ R^2/(2*sigma^2) = 0.02^2 / (2*2) = 1e-4 (small-R approx)
        #
        # Our _score_event uses default_covariance("LEO") + project_to_encounter_plane.
        # At miss=0.01 km, Pc should be near the maximum (~1e-4 order of magnitude).
        # At miss=5 km (several sigma), Pc should drop below 1e-6.
        """
        from satguard.fleet.batch import _score_event

        # Near-zero miss: Pc should be in [1e-5, 2e-4] range
        close_event = _make_mock_conjunction(miss_km=0.01)
        close_scored = _score_event(close_event)
        assert close_scored is not None
        assert 1e-5 < close_scored.pc < 2e-4, (
            f"Near-zero miss Pc={close_scored.pc:.2e} outside expected [1e-5, 2e-4]"
        )

        # Large miss (several sigma): Pc should be negligible (< 1e-6)
        far_event = _make_mock_conjunction(miss_km=5.0)
        far_scored = _score_event(far_event)
        assert far_scored is not None
        assert far_scored.pc < 1e-6, (
            f"5 km miss Pc={far_scored.pc:.2e} should be < 1e-6"
        )

    def test_foster_pc_monotonic_with_miss_distance(self) -> None:
        """L1: Pc decreases as miss distance increases (property test)."""
        from satguard.fleet.batch import _score_event

        pcs = []
        for miss_km in [0.01, 0.1, 0.5, 1.0, 5.0, 10.0]:
            scored = _score_event(_make_mock_conjunction(miss_km=miss_km))
            assert scored is not None
            pcs.append(scored.pc)

        for i in range(len(pcs) - 1):
            assert pcs[i] >= pcs[i + 1], (
                f"Pc not monotonic: Pc[{i}]={pcs[i]:.2e} < Pc[{i+1}]={pcs[i+1]:.2e}"
            )
