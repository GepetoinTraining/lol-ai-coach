"""
Analysis Module for LoL AI Coach

Provides:
- Death extraction from match timelines
- Pattern detection across games
- Map zone classification
- Game phase analysis
"""

from .pattern_detector import (
    GamePhase,
    MapZone,
    DeathType,
    PatternKey,
    DeathContext,
    extract_deaths_from_match,
    detect_patterns,
    check_pattern_status,
    get_priority_pattern,
    determine_map_zone,
    determine_game_phase,
)

__all__ = [
    "GamePhase",
    "MapZone",
    "DeathType",
    "PatternKey",
    "DeathContext",
    "extract_deaths_from_match",
    "detect_patterns",
    "check_pattern_status",
    "get_priority_pattern",
    "determine_map_zone",
    "determine_game_phase",
]
