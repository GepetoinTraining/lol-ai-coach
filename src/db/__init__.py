"""
Database Module for LoL AI Coach

Provides async SQLite database access for:
- Player tracking
- Death context storage
- Pattern detection and tracking
- Mission persistence
- VOD review moments
- Coaching session continuity
"""

from .database import Database, get_database, close_database
from .repositories import (
    PlayerRepository,
    MatchRepository,
    DeathRepository,
    PatternRepository,
    MissionRepository,
    VODMomentRepository,
    SessionRepository,
)

__all__ = [
    "Database",
    "get_database",
    "close_database",
    "PlayerRepository",
    "MatchRepository",
    "DeathRepository",
    "PatternRepository",
    "MissionRepository",
    "VODMomentRepository",
    "SessionRepository",
]
