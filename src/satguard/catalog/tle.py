"""TLE (Two-Line Element) parser.

Parses NORAD TLE format into structured data.
Reference: CelesTrak TLE format spec — https://celestrak.org/columns/v04n03/
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class TLE:
    """Parsed Two-Line Element set."""

    name: str
    line1: str
    line2: str
    norad_id: int
    classification: str
    intl_designator: str
    epoch_year: int
    epoch_day: float
    mean_motion_dot: float
    mean_motion_ddot: float
    bstar: float
    element_set_type: int
    element_number: int
    inclination: float  # degrees
    raan: float  # degrees (Right Ascension of Ascending Node)
    eccentricity: float  # dimensionless
    arg_perigee: float  # degrees
    mean_anomaly: float  # degrees
    mean_motion: float  # rev/day
    revolution_number: int

    @property
    def epoch_datetime(self) -> datetime:
        """Convert TLE epoch (year + fractional day) to UTC datetime."""
        # TLE uses 2-digit year: 57-99 → 1957-1999, 00-56 → 2000-2056
        if self.epoch_year >= 57:
            full_year = 1957 + (self.epoch_year - 57)
        else:
            full_year = 2000 + self.epoch_year
        jan1 = datetime(full_year, 1, 1, tzinfo=UTC)
        # epoch_day is 1-based: day 1.0 = Jan 1 00:00:00
        from datetime import timedelta

        return jan1 + timedelta(days=self.epoch_day - 1.0)


def _validate_checksum(line: str) -> bool:
    """Validate TLE line checksum (last digit).

    SOURCE: CelesTrak — https://celestrak.org/columns/v04n03/
    Checksum = sum of all digits + 1 for each '-', mod 10.
    """
    expected = int(line[68])
    total = 0
    for ch in line[:68]:
        if ch.isdigit():
            total += int(ch)
        elif ch == "-":
            total += 1
    return (total % 10) == expected


def _parse_decimal_assumption(s: str) -> float:
    """Parse TLE implicit-decimal format like ' 12345-6' → 0.12345e-6."""
    s = s.strip()
    if not s or s == "00000+0" or s == "00000-0":
        return 0.0
    # Handle sign
    sign = 1.0
    if s[0] == "-":
        sign = -1.0
        s = s[1:]
    elif s[0] == "+":
        s = s[1:]
    # Find exponent
    exp_idx = -1
    for i in range(1, len(s)):
        if s[i] in "+-":
            exp_idx = i
            break
    if exp_idx == -1:
        return sign * float("0." + s)
    mantissa = float("0." + s[:exp_idx])
    exponent = int(s[exp_idx:])
    return sign * mantissa * (10.0**exponent)


def parse_tle_lines(name: str, line1: str, line2: str) -> TLE:
    """Parse TLE from three lines (name, line1, line2).

    Args:
        name: Object name (line 0 of 3LE format).
        line1: First line of TLE (starts with '1').
        line2: Second line of TLE (starts with '2').

    Raises:
        ValueError: If lines are malformed or checksums fail.
    """
    line1 = line1.rstrip()
    line2 = line2.rstrip()

    if len(line1) != 69:
        raise ValueError(f"Line 1 length {len(line1)}, expected 69")
    if len(line2) != 69:
        raise ValueError(f"Line 2 length {len(line2)}, expected 69")
    if line1[0] != "1":
        raise ValueError(f"Line 1 must start with '1', got '{line1[0]}'")
    if line2[0] != "2":
        raise ValueError(f"Line 2 must start with '2', got '{line2[0]}'")
    if not _validate_checksum(line1):
        raise ValueError("Line 1 checksum failed")
    if not _validate_checksum(line2):
        raise ValueError("Line 2 checksum failed")

    # Line 1 fields
    norad_id = int(line1[2:7])
    classification = line1[7]
    intl_designator = line1[9:17].strip()
    epoch_year = int(line1[18:20])
    epoch_day = float(line1[20:32])
    mean_motion_dot = float(line1[33:43])
    mean_motion_ddot = _parse_decimal_assumption(line1[44:52])
    bstar = _parse_decimal_assumption(line1[53:61])
    element_set_type = int(line1[62])
    element_number = int(line1[64:68])

    # Line 2 fields
    norad_id_2 = int(line2[2:7])
    if norad_id != norad_id_2:
        raise ValueError(f"NORAD ID mismatch: {norad_id} vs {norad_id_2}")

    inclination = float(line2[8:16])
    raan = float(line2[17:25])
    eccentricity = float("0." + line2[26:33].strip())
    arg_perigee = float(line2[34:42])
    mean_anomaly = float(line2[43:51])
    mean_motion = float(line2[52:63])
    revolution_number = int(line2[63:68])

    return TLE(
        name=name.strip(),
        line1=line1,
        line2=line2,
        norad_id=norad_id,
        classification=classification,
        intl_designator=intl_designator,
        epoch_year=epoch_year,
        epoch_day=epoch_day,
        mean_motion_dot=mean_motion_dot,
        mean_motion_ddot=mean_motion_ddot,
        bstar=bstar,
        element_set_type=element_set_type,
        element_number=element_number,
        inclination=inclination,
        raan=raan,
        eccentricity=eccentricity,
        arg_perigee=arg_perigee,
        mean_anomaly=mean_anomaly,
        mean_motion=mean_motion,
        revolution_number=revolution_number,
    )


def parse_tle(text: str) -> TLE:
    """Parse a TLE from a string containing 2 or 3 lines.

    Accepts both 2-line (no name) and 3-line (with name) formats.
    """
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) == 3:
        return parse_tle_lines(lines[0], lines[1], lines[2])
    elif len(lines) == 2:
        return parse_tle_lines("UNKNOWN", lines[0], lines[1])
    else:
        raise ValueError(f"Expected 2 or 3 lines, got {len(lines)}")
