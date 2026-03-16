"""CDM (Conjunction Data Message) writer in CCSDS KVN format.

Generates CDM v1.0 messages per CCSDS 508.0-B-1 standard.
Reference: https://public.ccsds.org/Pubs/508x0b1e2s.pdf
"""

from __future__ import annotations

from datetime import UTC, datetime

from satguard.screen.screener import ConjunctionEvent


def write_cdm(
    event: ConjunctionEvent,
    collision_probability: float,
    creation_date: datetime | None = None,
    originator: str = "SATGUARD",
    message_id: str = "AUTO",
) -> str:
    """Write a CDM in CCSDS KVN format.

    Args:
        event: Conjunction event data.
        collision_probability: Computed collision probability.
        creation_date: Message creation date (defaults to now UTC).
        originator: Originator of the message.
        message_id: Unique message identifier.

    Returns:
        CDM string in CCSDS 508.0-B-1 KVN format.

    Reference:
        CCSDS 508.0-B-1 Section 4 — mandatory fields for CDM.
    """
    if creation_date is None:
        creation_date = datetime.now(UTC)

    tca_str = _format_datetime(event.tca)
    creation_str = _format_datetime(creation_date)

    miss_distance_m = event.miss_distance_km * 1000.0

    lines = [
        "CCSDS_CDM_VERS                = 1.0",
        f"CREATION_DATE                 = {creation_str}",
        f"ORIGINATOR                    = {originator}",
        f"MESSAGE_ID                    = {message_id}",
        f"TCA                           = {tca_str}",
        f"MISS_DISTANCE                 = {miss_distance_m:.3f} [m]",
        f"RELATIVE_SPEED                = {event.relative_velocity_km_s * 1000.0:.3f} [m/s]",
        f"RELATIVE_POSITION_R           = {miss_distance_m:.3f} [m]",
        f"RELATIVE_VELOCITY_R           = {event.relative_velocity_km_s * 1000.0:.3f} [m/s]",
        f"COLLISION_PROBABILITY         = {collision_probability:.6e}",
        "COLLISION_PROBABILITY_METHOD  = FOSTER-1992",
        "",
        "OBJECT                        = OBJECT1",
        f"OBJECT_DESIGNATOR             = {event.norad_id_primary}",
        "CATALOG_NAME                  = SATCAT",
        "OBJECT_NAME                   = PRIMARY",
        "EPHEMERIS_NAME                = SGP4",
        f"X                             = {event.r_primary[0]:.6f} [km]",
        f"Y                             = {event.r_primary[1]:.6f} [km]",
        f"Z                             = {event.r_primary[2]:.6f} [km]",
        f"X_DOT                         = {event.v_primary[0]:.9f} [km/s]",
        f"Y_DOT                         = {event.v_primary[1]:.9f} [km/s]",
        f"Z_DOT                         = {event.v_primary[2]:.9f} [km/s]",
        "",
        "OBJECT                        = OBJECT2",
        f"OBJECT_DESIGNATOR             = {event.norad_id_secondary}",
        "CATALOG_NAME                  = SATCAT",
        "OBJECT_NAME                   = SECONDARY",
        "EPHEMERIS_NAME                = SGP4",
        f"X                             = {event.r_secondary[0]:.6f} [km]",
        f"Y                             = {event.r_secondary[1]:.6f} [km]",
        f"Z                             = {event.r_secondary[2]:.6f} [km]",
        f"X_DOT                         = {event.v_secondary[0]:.9f} [km/s]",
        f"Y_DOT                         = {event.v_secondary[1]:.9f} [km/s]",
        f"Z_DOT                         = {event.v_secondary[2]:.9f} [km/s]",
    ]

    return "\n".join(lines) + "\n"


def _format_datetime(dt: datetime) -> str:
    """Format datetime as CCSDS date string: YYYY-MM-DDTHH:MM:SS.SSS"""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}"
