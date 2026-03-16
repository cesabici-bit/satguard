"""Tests for TLE parser.

Oracle L2: CelesTrak TLE format spec — https://celestrak.org/columns/v04n03/
"""

import pytest

from satguard.catalog.tle import _validate_checksum, parse_tle, parse_tle_lines

# ISS TLE fixture (real data from CelesTrak)
ISS_3LE = """\
ISS (ZARYA)
1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9992
2 25544  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441079"""


class TestParseTLE:
    """L1: Unit tests for TLE parsing."""

    def test_parse_iss_norad_id(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.norad_id == 25544

    def test_parse_iss_name(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.name == "ISS (ZARYA)"

    def test_parse_iss_inclination(self) -> None:
        # SOURCE: CelesTrak TLE format spec — inclination field columns 9-16 of line 2
        tle = parse_tle(ISS_3LE)
        assert tle.inclination == pytest.approx(51.6416, abs=1e-4)

    def test_parse_iss_eccentricity(self) -> None:
        # SOURCE: CelesTrak TLE format spec — eccentricity is implicit decimal in cols 27-33
        tle = parse_tle(ISS_3LE)
        assert tle.eccentricity == pytest.approx(0.0006703, abs=1e-7)

    def test_parse_iss_mean_motion(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.mean_motion == pytest.approx(15.49560867, abs=1e-6)

    def test_parse_iss_raan(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.raan == pytest.approx(14.5021, abs=1e-4)

    def test_parse_iss_arg_perigee(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.arg_perigee == pytest.approx(38.8378, abs=1e-4)

    def test_parse_iss_bstar(self) -> None:
        # SOURCE: CelesTrak — B* drag term, implicit decimal with exponent
        tle = parse_tle(ISS_3LE)
        assert tle.bstar == pytest.approx(0.37340e-3, rel=1e-3)

    def test_parse_iss_epoch(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.epoch_year == 24
        assert tle.epoch_day == pytest.approx(45.51749023)

    def test_epoch_datetime(self) -> None:
        """L2: Verify epoch conversion against known date.
        # SOURCE: CelesTrak — epoch year 24 day 45.517 = 2024-02-14 ~12:25 UTC
        """
        tle = parse_tle(ISS_3LE)
        dt = tle.epoch_datetime
        assert dt.year == 2024
        assert dt.month == 2
        assert dt.day == 14

    def test_parse_two_line_format(self) -> None:
        """Parse 2-line format (no name line)."""
        lines = ISS_3LE.strip().splitlines()
        two_line = f"{lines[1]}\n{lines[2]}"
        tle = parse_tle(two_line)
        assert tle.norad_id == 25544
        assert tle.name == "UNKNOWN"

    def test_classification(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.classification == "U"

    def test_intl_designator(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.intl_designator == "98067A"

    def test_revolution_number(self) -> None:
        tle = parse_tle(ISS_3LE)
        assert tle.revolution_number == 44107  # cols 64-68 of line2: 44107


class TestChecksum:
    """L2: Checksum validation per CelesTrak spec."""

    def test_valid_checksum_line1(self) -> None:
        # SOURCE: CelesTrak checksum algorithm — sum digits + '-' counts as 1, mod 10
        line1 = "1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9992"
        assert _validate_checksum(line1) is True

    def test_valid_checksum_line2(self) -> None:
        line2 = "2 25544  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441079"
        assert _validate_checksum(line2) is True

    def test_invalid_checksum(self) -> None:
        # Modify last digit to make checksum invalid
        line1 = "1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9995"
        assert _validate_checksum(line1) is False


class TestParseErrors:
    """Error handling for malformed TLEs."""

    def test_wrong_line_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            parse_tle_lines("TEST", "1 25544", "2 25544")

    def test_wrong_line_number(self) -> None:
        lines = ISS_3LE.strip().splitlines()
        with pytest.raises(ValueError, match="start with"):
            parse_tle_lines("TEST", lines[2], lines[1])  # swapped

    def test_norad_id_mismatch(self) -> None:
        line1 = "1 25544U 98067A   24045.51749023  .00020825  00000+0  37340-3 0  9993"
        line2 = "2 99999  51.6416  14.5021 0006703  38.8378  76.2277 15.49560867441075"
        with pytest.raises(ValueError, match="mismatch|checksum"):
            parse_tle_lines("TEST", line1, line2)

    def test_empty_input(self) -> None:
        with pytest.raises(ValueError, match="Expected"):
            parse_tle("")

    def test_single_line(self) -> None:
        with pytest.raises(ValueError, match="Expected"):
            parse_tle("just one line")
