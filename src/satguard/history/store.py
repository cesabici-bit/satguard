"""JSON-based persistence for Pc evolution tracking.

Each conjunction pair (norad_a, norad_b, tca_window) gets its own JSON file
under the history directory.  Files are human-readable and trivially testable.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

_TCA_WINDOW_HOURS = 1.0  # Snapshots within this window belong to same conjunction


@dataclass(frozen=True, slots=True)
class PcSnapshot:
    """Single Pc assessment at a point in time."""

    timestamp: datetime
    """When this assessment was performed (UTC)."""

    tca: datetime
    """Time of closest approach (UTC)."""

    miss_distance_km: float
    pc_foster: float
    pc_chan: float | None
    tle_epoch_primary: datetime
    tle_epoch_secondary: datetime
    covariance_source: str


@dataclass(frozen=True, slots=True)
class ConjunctionHistory:
    """Time series of Pc assessments for a conjunction pair."""

    norad_id_a: int
    norad_id_b: int
    tca_window_center: datetime
    snapshots: tuple[PcSnapshot, ...]


def _dt_to_str(dt: datetime) -> str:
    """Datetime → ISO 8601 with Z suffix (always UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _str_to_dt(s: str) -> datetime:
    """ISO 8601 string → timezone-aware datetime (UTC)."""
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _snapshot_to_dict(snap: PcSnapshot) -> dict:
    d = asdict(snap)
    for k in ("timestamp", "tca", "tle_epoch_primary", "tle_epoch_secondary"):
        d[k] = _dt_to_str(d[k])
    return d


def _dict_to_snapshot(d: dict) -> PcSnapshot:
    return PcSnapshot(
        timestamp=_str_to_dt(d["timestamp"]),
        tca=_str_to_dt(d["tca"]),
        miss_distance_km=d["miss_distance_km"],
        pc_foster=d["pc_foster"],
        pc_chan=d["pc_chan"],
        tle_epoch_primary=_str_to_dt(d["tle_epoch_primary"]),
        tle_epoch_secondary=_str_to_dt(d["tle_epoch_secondary"]),
        covariance_source=d["covariance_source"],
    )


def _conjunction_filename(norad_a: int, norad_b: int, tca: datetime) -> str:
    date_str = tca.strftime("%Y%m%d")
    return f"{norad_a}_{norad_b}_{date_str}.json"


class HistoryStore:
    """Read/write conjunction Pc history as JSON files."""

    def __init__(self, base_dir: Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path.home() / ".satguard" / "history"
        self.base_dir = base_dir

    def record(self, snapshot: PcSnapshot, norad_primary: int, norad_secondary: int) -> Path:
        """Append a snapshot to the appropriate conjunction history file.

        Returns the path to the history file.
        """
        norad_a = min(norad_primary, norad_secondary)
        norad_b = max(norad_primary, norad_secondary)
        fname = _conjunction_filename(norad_a, norad_b, snapshot.tca)
        fpath = self.base_dir / fname

        # Load existing or create new
        if fpath.exists():
            data = json.loads(fpath.read_text(encoding="utf-8"))
        else:
            data = {
                "norad_id_a": norad_a,
                "norad_id_b": norad_b,
                "tca_window_center": _dt_to_str(snapshot.tca),
                "snapshots": [],
            }

        # Deduplicate: skip if identical timestamp already exists
        new_ts = _dt_to_str(snapshot.timestamp)
        for existing in data["snapshots"]:
            if existing["timestamp"] == new_ts:
                return fpath

        data["snapshots"].append(_snapshot_to_dict(snapshot))
        # Sort by timestamp
        data["snapshots"].sort(key=lambda s: s["timestamp"])

        self.base_dir.mkdir(parents=True, exist_ok=True)
        fpath.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return fpath

    def load(
        self, norad_a: int, norad_b: int, tca_date: datetime,
    ) -> ConjunctionHistory | None:
        """Load conjunction history for a specific pair and TCA date."""
        a, b = min(norad_a, norad_b), max(norad_a, norad_b)
        fname = _conjunction_filename(a, b, tca_date)
        fpath = self.base_dir / fname

        if not fpath.exists():
            return None

        data = json.loads(fpath.read_text(encoding="utf-8"))
        snapshots = tuple(_dict_to_snapshot(s) for s in data["snapshots"])
        return ConjunctionHistory(
            norad_id_a=data["norad_id_a"],
            norad_id_b=data["norad_id_b"],
            tca_window_center=_str_to_dt(data["tca_window_center"]),
            snapshots=snapshots,
        )

    def list_conjunctions(self) -> list[tuple[int, int, str]]:
        """List all tracked conjunctions as (norad_a, norad_b, date_str)."""
        if not self.base_dir.exists():
            return []
        results = []
        for f in sorted(self.base_dir.glob("*.json")):
            parts = f.stem.split("_")
            if len(parts) == 3:
                results.append((int(parts[0]), int(parts[1]), parts[2]))
        return results
