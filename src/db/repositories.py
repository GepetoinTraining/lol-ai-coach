"""
Repository Classes for Database Access

Each repository handles CRUD operations for a specific domain entity.
"""

import json
from datetime import datetime
from typing import Optional, Any

from .database import Database
from ..logging_config import get_logger

logger = get_logger(__name__)


class PlayerRepository:
    """Repository for player data."""

    def __init__(self, db: Database):
        self.db = db

    async def get_or_create(
        self,
        discord_id: int,
        riot_id: str,
        platform: str = "br1"
    ) -> dict[str, Any]:
        """Get existing player or create new one."""
        player = await self.get_by_discord_id(discord_id)

        if player:
            return player

        player_id = await self.db.insert(
            """
            INSERT INTO players (discord_id, riot_id, platform)
            VALUES (?, ?, ?)
            """,
            (discord_id, riot_id, platform)
        )

        logger.info(f"Created new player: discord_id={discord_id}, riot_id={riot_id}")

        return await self.get_by_id(player_id)

    async def get_by_id(self, player_id: int) -> Optional[dict[str, Any]]:
        """Get player by database ID."""
        return await self.db.fetch_one(
            "SELECT * FROM players WHERE id = ?",
            (player_id,)
        )

    async def get_by_discord_id(self, discord_id: int) -> Optional[dict[str, Any]]:
        """Get player by Discord ID."""
        return await self.db.fetch_one(
            "SELECT * FROM players WHERE discord_id = ?",
            (discord_id,)
        )

    async def get_by_puuid(self, puuid: str) -> Optional[dict[str, Any]]:
        """Get player by Riot PUUID."""
        return await self.db.fetch_one(
            "SELECT * FROM players WHERE puuid = ?",
            (puuid,)
        )

    async def update_puuid(self, player_id: int, puuid: str) -> None:
        """Update player's PUUID after Riot API lookup."""
        await self.db.execute(
            "UPDATE players SET puuid = ? WHERE id = ?",
            (puuid, player_id)
        )


class MatchRepository:
    """Repository for match data."""

    def __init__(self, db: Database):
        self.db = db

    async def get_or_create(
        self,
        match_id: str,
        player_id: int,
        champion: str,
        role: str,
        win: bool,
        kills: int,
        deaths: int,
        assists: int,
        cs: int,
        vision_score: int,
        game_duration_sec: int,
        played_at: Optional[datetime] = None
    ) -> dict[str, Any]:
        """Get existing match or create new one."""
        existing = await self.get_by_match_id(match_id)

        if existing:
            return existing

        db_id = await self.db.insert(
            """
            INSERT INTO matches (
                match_id, player_id, champion, role, win,
                kills, deaths, assists, cs, vision_score,
                game_duration_sec, played_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                match_id, player_id, champion, role, win,
                kills, deaths, assists, cs, vision_score,
                game_duration_sec, played_at
            )
        )

        return await self.get_by_id(db_id)

    async def get_by_id(self, match_db_id: int) -> Optional[dict[str, Any]]:
        """Get match by database ID."""
        return await self.db.fetch_one(
            "SELECT * FROM matches WHERE id = ?",
            (match_db_id,)
        )

    async def get_by_match_id(self, match_id: str) -> Optional[dict[str, Any]]:
        """Get match by Riot match ID."""
        return await self.db.fetch_one(
            "SELECT * FROM matches WHERE match_id = ?",
            (match_id,)
        )

    async def get_recent_for_player(
        self,
        player_id: int,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get recent matches for a player."""
        return await self.db.fetch_all(
            """
            SELECT * FROM matches
            WHERE player_id = ?
            ORDER BY played_at DESC
            LIMIT ?
            """,
            (player_id, limit)
        )

    async def count_since_match(
        self,
        player_id: int,
        match_id: int
    ) -> int:
        """Count matches played since a specific match."""
        result = await self.db.fetch_one(
            """
            SELECT COUNT(*) as count FROM matches
            WHERE player_id = ? AND id > ?
            """,
            (player_id, match_id)
        )
        return result["count"] if result else 0


class DeathRepository:
    """Repository for death events."""

    def __init__(self, db: Database):
        self.db = db

    async def insert(self, death_data: dict[str, Any]) -> int:
        """Insert a new death record."""
        assisting_champions = death_data.get("assisting_champions", [])
        if isinstance(assisting_champions, list):
            assisting_champions = json.dumps(assisting_champions)

        return await self.db.insert(
            """
            INSERT INTO deaths (
                match_db_id, player_id, game_timestamp_ms, game_phase,
                position_x, position_y, map_zone,
                killer_champion, killer_participant_id, assisting_champions,
                had_ward_nearby, gold_diff, cs_diff, level_diff,
                player_gold, player_champion, death_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                death_data["match_db_id"],
                death_data["player_id"],
                death_data["game_timestamp_ms"],
                death_data["game_phase"],
                death_data.get("position_x"),
                death_data.get("position_y"),
                death_data.get("map_zone"),
                death_data.get("killer_champion"),
                death_data.get("killer_participant_id"),
                assisting_champions,
                death_data.get("had_ward_nearby", False),
                death_data.get("gold_diff", 0),
                death_data.get("cs_diff", 0),
                death_data.get("level_diff", 0),
                death_data.get("player_gold", 0),
                death_data.get("player_champion"),
                death_data.get("death_type", "unknown")
            )
        )

    async def get_for_player(
        self,
        player_id: int,
        limit: int = 100,
        game_phase: Optional[str] = None,
        map_zone: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Get deaths for a player with optional filters."""
        query = "SELECT * FROM deaths WHERE player_id = ?"
        params = [player_id]

        if game_phase:
            query += " AND game_phase = ?"
            params.append(game_phase)

        if map_zone:
            query += " AND map_zone = ?"
            params.append(map_zone)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        deaths = await self.db.fetch_all(query, tuple(params))

        # Parse JSON fields
        for death in deaths:
            if death.get("assisting_champions"):
                death["assisting_champions"] = json.loads(death["assisting_champions"])

        return deaths

    async def get_for_match(self, match_db_id: int) -> list[dict[str, Any]]:
        """Get all deaths from a specific match."""
        deaths = await self.db.fetch_all(
            """
            SELECT * FROM deaths
            WHERE match_db_id = ?
            ORDER BY game_timestamp_ms
            """,
            (match_db_id,)
        )

        for death in deaths:
            if death.get("assisting_champions"):
                death["assisting_champions"] = json.loads(death["assisting_champions"])

        return deaths

    async def get_recent_by_zone(
        self,
        player_id: int,
        map_zone: str,
        days: int = 30
    ) -> list[dict[str, Any]]:
        """Get deaths in a specific zone from recent games."""
        return await self.db.fetch_all(
            """
            SELECT d.*, m.played_at FROM deaths d
            JOIN matches m ON d.match_db_id = m.id
            WHERE d.player_id = ?
                AND d.map_zone = ?
                AND m.played_at >= datetime('now', ?)
            ORDER BY m.played_at DESC
            """,
            (player_id, map_zone, f"-{days} days")
        )

    async def get_by_id(self, death_id: int) -> Optional[dict[str, Any]]:
        """Get a death by ID."""
        death = await self.db.fetch_one(
            "SELECT * FROM deaths WHERE id = ?",
            (death_id,)
        )

        if death and death.get("assisting_champions"):
            death["assisting_champions"] = json.loads(death["assisting_champions"])

        return death


class PatternRepository:
    """Repository for detected patterns."""

    def __init__(self, db: Database):
        self.db = db

    async def upsert(
        self,
        player_id: int,
        pattern_key: str,
        pattern_data: dict[str, Any]
    ) -> int:
        """Insert or update a pattern."""
        existing = await self.get_by_key(player_id, pattern_key)

        sample_death_ids = pattern_data.get("sample_death_ids", [])
        if isinstance(sample_death_ids, list):
            sample_death_ids = json.dumps(sample_death_ids)

        if existing:
            # Update existing pattern
            await self.db.execute(
                """
                UPDATE patterns SET
                    occurrences = ?,
                    description = ?,
                    last_seen_at = CURRENT_TIMESTAMP,
                    last_match_id = ?,
                    games_since_last = 0,
                    status = ?,
                    sample_death_ids = ?
                WHERE id = ?
                """,
                (
                    pattern_data.get("occurrences", existing["occurrences"]),
                    pattern_data.get("description", existing["description"]),
                    pattern_data.get("last_match_id"),
                    pattern_data.get("status", "active"),
                    sample_death_ids,
                    existing["id"]
                )
            )
            return existing["id"]
        else:
            # Insert new pattern
            return await self.db.insert(
                """
                INSERT INTO patterns (
                    player_id, pattern_key, pattern_category, description,
                    occurrences, last_match_id, sample_death_ids
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    player_id,
                    pattern_key,
                    pattern_data.get("pattern_category", "general"),
                    pattern_data["description"],
                    pattern_data.get("occurrences", 1),
                    pattern_data.get("last_match_id"),
                    sample_death_ids
                )
            )

    async def get_by_key(
        self,
        player_id: int,
        pattern_key: str
    ) -> Optional[dict[str, Any]]:
        """Get a pattern by player and key."""
        pattern = await self.db.fetch_one(
            "SELECT * FROM patterns WHERE player_id = ? AND pattern_key = ?",
            (player_id, pattern_key)
        )

        if pattern and pattern.get("sample_death_ids"):
            pattern["sample_death_ids"] = json.loads(pattern["sample_death_ids"])

        return pattern

    async def get_active(self, player_id: int) -> list[dict[str, Any]]:
        """Get all active patterns for a player."""
        patterns = await self.db.fetch_all(
            """
            SELECT * FROM patterns
            WHERE player_id = ? AND status IN ('active', 'improving')
            ORDER BY occurrences DESC
            """,
            (player_id,)
        )

        for pattern in patterns:
            if pattern.get("sample_death_ids"):
                pattern["sample_death_ids"] = json.loads(pattern["sample_death_ids"])

        return patterns

    async def get_priority(self, player_id: int) -> Optional[dict[str, Any]]:
        """
        Get the highest priority pattern for coaching focus.

        Priority = occurrences / (games_since_last + 1)
        Most frequent AND most recent = highest priority
        """
        pattern = await self.db.fetch_one(
            """
            SELECT *,
                (occurrences * 1.0 / (games_since_last + 1)) as priority_score
            FROM patterns
            WHERE player_id = ? AND status = 'active'
            ORDER BY priority_score DESC
            LIMIT 1
            """,
            (player_id,)
        )

        if pattern and pattern.get("sample_death_ids"):
            pattern["sample_death_ids"] = json.loads(pattern["sample_death_ids"])

        return pattern

    async def update_status(
        self,
        pattern_id: int,
        status: str,
        games_since_last: int
    ) -> None:
        """Update pattern status after match analysis."""
        await self.db.execute(
            """
            UPDATE patterns SET
                status = ?,
                games_since_last = ?,
                improvement_streak = CASE
                    WHEN ? > 0 THEN improvement_streak + 1
                    ELSE 0
                END
            WHERE id = ?
            """,
            (status, games_since_last, games_since_last, pattern_id)
        )

    async def increment_games_since(self, player_id: int) -> None:
        """Increment games_since_last for all patterns after a match."""
        await self.db.execute(
            """
            UPDATE patterns SET games_since_last = games_since_last + 1
            WHERE player_id = ?
            """,
            (player_id,)
        )

    async def get_all(self, player_id: int) -> list[dict[str, Any]]:
        """Get all patterns for a player."""
        patterns = await self.db.fetch_all(
            "SELECT * FROM patterns WHERE player_id = ? ORDER BY last_seen_at DESC",
            (player_id,)
        )

        for pattern in patterns:
            if pattern.get("sample_death_ids"):
                pattern["sample_death_ids"] = json.loads(pattern["sample_death_ids"])

        return patterns


class MissionRepository:
    """Repository for missions."""

    def __init__(self, db: Database):
        self.db = db

    async def create(self, mission_data: dict[str, Any]) -> int:
        """Create a new mission."""
        tips = mission_data.get("tips", [])
        if isinstance(tips, list):
            tips = json.dumps(tips)

        return await self.db.insert(
            """
            INSERT INTO missions (
                player_id, pattern_id, description, focus_area,
                success_criteria, tips, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                mission_data["player_id"],
                mission_data.get("pattern_id"),
                mission_data["description"],
                mission_data["focus_area"],
                mission_data.get("success_criteria"),
                tips
            )
        )

    async def get_active(self, player_id: int) -> Optional[dict[str, Any]]:
        """Get the active mission for a player."""
        mission = await self.db.fetch_one(
            """
            SELECT * FROM missions
            WHERE player_id = ? AND status = 'active'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (player_id,)
        )

        if mission and mission.get("tips"):
            mission["tips"] = json.loads(mission["tips"])

        return mission

    async def get_by_id(self, mission_id: int) -> Optional[dict[str, Any]]:
        """Get a mission by ID."""
        mission = await self.db.fetch_one(
            "SELECT * FROM missions WHERE id = ?",
            (mission_id,)
        )

        if mission and mission.get("tips"):
            mission["tips"] = json.loads(mission["tips"])

        return mission

    async def complete(self, mission_id: int, notes: Optional[str] = None) -> None:
        """Mark a mission as completed."""
        await self.db.execute(
            """
            UPDATE missions SET
                status = 'completed',
                completed_at = CURRENT_TIMESTAMP,
                result_notes = ?
            WHERE id = ?
            """,
            (notes, mission_id)
        )

    async def fail(self, mission_id: int, notes: Optional[str] = None) -> None:
        """Mark a mission as failed."""
        await self.db.execute(
            """
            UPDATE missions SET
                status = 'failed',
                completed_at = CURRENT_TIMESTAMP,
                result_notes = ?
            WHERE id = ?
            """,
            (notes, mission_id)
        )

    async def skip(self, mission_id: int) -> None:
        """Mark a mission as skipped."""
        await self.db.execute(
            "UPDATE missions SET status = 'skipped' WHERE id = ?",
            (mission_id,)
        )

    async def get_history(
        self,
        player_id: int,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get mission history for a player."""
        missions = await self.db.fetch_all(
            """
            SELECT * FROM missions
            WHERE player_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (player_id, limit)
        )

        for mission in missions:
            if mission.get("tips"):
                mission["tips"] = json.loads(mission["tips"])

        return missions

    async def count_completed(self, player_id: int) -> int:
        """Count completed missions for a player."""
        result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM missions WHERE player_id = ? AND status = 'completed'",
            (player_id,)
        )
        return result["count"] if result else 0

    async def count_for_pattern(
        self,
        player_id: int,
        pattern_id: int
    ) -> dict[str, int]:
        """Count missions for a specific pattern."""
        result = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
            FROM missions
            WHERE player_id = ? AND pattern_id = ?
            """,
            (player_id, pattern_id)
        )
        return {
            "total": result["total"] if result else 0,
            "completed": result["completed"] if result else 0
        }


class VODMomentRepository:
    """Repository for VOD review moments."""

    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        death_id: int,
        player_id: int,
        pattern_id: Optional[int] = None,
        coach_question: Optional[str] = None
    ) -> int:
        """Create a new VOD moment for review."""
        return await self.db.insert(
            """
            INSERT INTO vod_moments (death_id, player_id, pattern_id, coach_question)
            VALUES (?, ?, ?, ?)
            """,
            (death_id, player_id, pattern_id, coach_question)
        )

    async def get_unreviewed(
        self,
        player_id: int,
        limit: int = 5
    ) -> list[dict[str, Any]]:
        """Get unreviewed VOD moments for a player."""
        return await self.db.fetch_all(
            """
            SELECT vm.*, d.game_timestamp_ms, d.map_zone, d.killer_champion,
                   d.had_ward_nearby, d.gold_diff, d.player_champion,
                   m.match_id, p.pattern_key, p.description as pattern_description
            FROM vod_moments vm
            JOIN deaths d ON vm.death_id = d.id
            JOIN matches m ON d.match_db_id = m.id
            LEFT JOIN patterns p ON vm.pattern_id = p.id
            WHERE vm.player_id = ? AND vm.reviewed = FALSE
            ORDER BY vm.created_at DESC
            LIMIT ?
            """,
            (player_id, limit)
        )

    async def get_by_id(self, moment_id: int) -> Optional[dict[str, Any]]:
        """Get a VOD moment by ID."""
        return await self.db.fetch_one(
            """
            SELECT vm.*, d.game_timestamp_ms, d.map_zone, d.killer_champion,
                   d.had_ward_nearby, d.gold_diff, d.player_champion,
                   m.match_id
            FROM vod_moments vm
            JOIN deaths d ON vm.death_id = d.id
            JOIN matches m ON d.match_db_id = m.id
            WHERE vm.id = ?
            """,
            (moment_id,)
        )

    async def start_review(self, moment_id: int) -> None:
        """Mark a moment as being reviewed."""
        await self.db.execute(
            "UPDATE vod_moments SET review_started_at = CURRENT_TIMESTAMP WHERE id = ?",
            (moment_id,)
        )

    async def record_player_response(
        self,
        moment_id: int,
        response: str,
        analysis: Optional[str] = None
    ) -> None:
        """Store what the player said during review."""
        await self.db.execute(
            """
            UPDATE vod_moments SET
                player_response = ?,
                player_analysis = ?
            WHERE id = ?
            """,
            (response, analysis, moment_id)
        )

    async def record_coach_insight(
        self,
        moment_id: int,
        insight: str
    ) -> None:
        """Store the coach's insight."""
        await self.db.execute(
            "UPDATE vod_moments SET coach_insight = ? WHERE id = ?",
            (insight, moment_id)
        )

    async def record_breakthrough(
        self,
        moment_id: int,
        insight: str
    ) -> None:
        """Record a coaching breakthrough."""
        await self.db.execute(
            """
            UPDATE vod_moments SET
                had_breakthrough = TRUE,
                breakthrough_insight = ?,
                reviewed = TRUE,
                review_completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (insight, moment_id)
        )

    async def complete_review(self, moment_id: int) -> None:
        """Mark a review as complete."""
        await self.db.execute(
            """
            UPDATE vod_moments SET
                reviewed = TRUE,
                review_completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (moment_id,)
        )

    async def count_breakthroughs(self, player_id: int) -> int:
        """Count breakthroughs for a player."""
        result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM vod_moments WHERE player_id = ? AND had_breakthrough = TRUE",
            (player_id,)
        )
        return result["count"] if result else 0


class SessionRepository:
    """Repository for coaching sessions."""

    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        player_id: int,
        focus_area: Optional[str] = None,
        matches_analyzed: int = 0
    ) -> int:
        """Create a new coaching session."""
        return await self.db.insert(
            """
            INSERT INTO coaching_sessions (player_id, focus_area, matches_analyzed)
            VALUES (?, ?, ?)
            """,
            (player_id, focus_area, matches_analyzed)
        )

    async def get_last(self, player_id: int) -> Optional[dict[str, Any]]:
        """Get the most recent session for a player."""
        session = await self.db.fetch_one(
            """
            SELECT * FROM coaching_sessions
            WHERE player_id = ?
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (player_id,)
        )

        if session:
            if session.get("patterns_discussed"):
                session["patterns_discussed"] = json.loads(session["patterns_discussed"])
            if session.get("insights"):
                session["insights"] = json.loads(session["insights"])

        return session

    async def end_session(
        self,
        session_id: int,
        patterns_discussed: Optional[list[str]] = None,
        insights: Optional[list[str]] = None
    ) -> None:
        """End a session with summary."""
        patterns_json = json.dumps(patterns_discussed) if patterns_discussed else None
        insights_json = json.dumps(insights) if insights else None

        await self.db.execute(
            """
            UPDATE coaching_sessions SET
                ended_at = CURRENT_TIMESTAMP,
                patterns_discussed = ?,
                insights = ?
            WHERE id = ?
            """,
            (patterns_json, insights_json, session_id)
        )

    async def update_opener(self, session_id: int, opener: str) -> None:
        """Store the session opener that was generated."""
        await self.db.execute(
            "UPDATE coaching_sessions SET opener_generated = ? WHERE id = ?",
            (opener, session_id)
        )

    async def count_for_player(self, player_id: int) -> int:
        """Count total sessions for a player."""
        result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM coaching_sessions WHERE player_id = ?",
            (player_id,)
        )
        return result["count"] if result else 0
