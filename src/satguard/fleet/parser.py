"""Fleet YAML parser.

Parses a fleet.yaml file into a FleetConfig dataclass with validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class FleetThresholds:
    """Screening thresholds for a fleet."""

    pc: float = 1e-6
    """Minimum collision probability to report."""

    miss_km: float = 50.0
    """Maximum miss distance threshold for screening (km)."""

    days: int = 3
    """Screening window duration (days)."""


@dataclass(frozen=True, slots=True)
class FleetConfig:
    """Parsed fleet configuration from YAML."""

    name: str
    """Constellation/fleet name."""

    objects: list[int]
    """NORAD IDs of fleet objects."""

    thresholds: FleetThresholds = field(default_factory=FleetThresholds)
    """Screening thresholds."""


def load_fleet(path: Path) -> FleetConfig:
    """Parse a fleet YAML file.

    Expected format:
        name: Starlink-Shell1
        thresholds:
          pc: 1e-6
          miss_km: 50
          days: 3
        objects:
          - 25544
          - 48274
          - 53239

    Args:
        path: Path to fleet YAML file.

    Returns:
        Validated FleetConfig.

    Raises:
        FileNotFoundError: If file does not exist.
        ValueError: If YAML is malformed or invalid.
    """
    if not path.exists():
        raise FileNotFoundError(f"Fleet file not found: {path}")

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise ValueError(f"Fleet YAML must be a mapping, got {type(raw).__name__}")

    # Name
    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise ValueError("Fleet YAML must have a 'name' string field")

    # Objects
    objects_raw = raw.get("objects")
    if not objects_raw or not isinstance(objects_raw, list):
        raise ValueError("Fleet YAML must have an 'objects' list with at least 1 NORAD ID")

    objects: list[int] = []
    for i, obj in enumerate(objects_raw):
        if not isinstance(obj, int) or obj <= 0:
            raise ValueError(
                f"objects[{i}] must be a positive integer NORAD ID, got {obj!r}"
            )
        objects.append(obj)

    if len(objects) == 0:
        raise ValueError("Fleet must have at least 1 object")

    # Thresholds (optional, with defaults)
    thresholds = FleetThresholds()
    thresh_raw = raw.get("thresholds")
    if thresh_raw and isinstance(thresh_raw, dict):
        pc = thresh_raw.get("pc", thresholds.pc)
        miss_km = thresh_raw.get("miss_km", thresholds.miss_km)
        days = thresh_raw.get("days", thresholds.days)

        if not isinstance(pc, (int, float)) or pc <= 0:
            raise ValueError(f"thresholds.pc must be a positive number, got {pc!r}")
        if not isinstance(miss_km, (int, float)) or miss_km <= 0:
            raise ValueError(f"thresholds.miss_km must be positive, got {miss_km!r}")
        if not isinstance(days, int) or days <= 0:
            raise ValueError(f"thresholds.days must be a positive integer, got {days!r}")

        thresholds = FleetThresholds(pc=float(pc), miss_km=float(miss_km), days=days)

    return FleetConfig(name=name, objects=objects, thresholds=thresholds)
