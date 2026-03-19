"""SatGuard — Open-source conjunction assessment pipeline."""

__version__ = "0.5.1"

from satguard.alert.rules import AlertConfig, load_config, should_alert
from satguard.alert.webhook import send_alert
from satguard.assess.alfano import alfano_pc
from satguard.assess.chan import chan_pc
from satguard.assess.foster import foster_pc
from satguard.catalog.celestrak import Catalog, fetch_catalog, fetch_tle_by_norad
from satguard.catalog.tle import TLE, parse_tle
from satguard.cdm.writer import write_cdm
from satguard.covariance.realism import (
    CovarianceAssessment,
    CovarianceMatrix,
    assess_covariance,
    default_covariance,
    scale_covariance,
)
from satguard.fleet.batch import screen_fleet
from satguard.screen.vectorized import ScoredConjunction
from satguard.fleet.parser import FleetConfig, FleetThresholds, load_fleet
from satguard.history.evolution import PcTrend, TrendDirection, pc_trend, time_to_threshold
from satguard.history.store import ConjunctionHistory, HistoryStore, PcSnapshot
from satguard.propagate.sgp4 import StateVector, propagate_batch, propagate_single
from satguard.report.pdf import generate_report
from satguard.screen.screener import ConjunctionEvent, screen

__all__ = [
    # Catalog
    "Catalog",
    "TLE",
    "parse_tle",
    "fetch_catalog",
    "fetch_tle_by_norad",
    # Propagation
    "StateVector",
    "propagate_single",
    "propagate_batch",
    # Screening
    "ConjunctionEvent",
    "screen",
    # Collision probability
    "foster_pc",
    "chan_pc",
    "alfano_pc",
    # Covariance
    "CovarianceMatrix",
    "CovarianceAssessment",
    "default_covariance",
    "assess_covariance",
    "scale_covariance",
    # CDM
    "write_cdm",
    # Fleet (v0.5)
    "FleetConfig",
    "FleetThresholds",
    "load_fleet",
    "screen_fleet",
    "ScoredConjunction",
    # Report (v0.5)
    "generate_report",
    # History (v0.2)
    "PcSnapshot",
    "ConjunctionHistory",
    "HistoryStore",
    "PcTrend",
    "TrendDirection",
    "pc_trend",
    "time_to_threshold",
    # Alert (v0.2)
    "AlertConfig",
    "load_config",
    "should_alert",
    "send_alert",
]
