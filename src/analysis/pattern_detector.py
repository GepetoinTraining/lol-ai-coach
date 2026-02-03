"""
Pattern Detection System

Extracts deaths with full context from Riot API match data and
detects recurring patterns across games.

The system identifies patterns like:
- River deaths without ward coverage
- Dying while ahead in lane
- Repeated early game deaths
- Getting caught while side-laning
- Facechecking into unwarded areas
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from collections import defaultdict
import math

from ..logging_config import get_logger

logger = get_logger(__name__)


class GamePhase(Enum):
    """Game phases based on time."""
    EARLY = "early"    # 0-10 minutes
    MID = "mid"        # 10-20 minutes
    LATE = "late"      # 20+ minutes


class MapZone(Enum):
    """Map zones for death location classification."""
    # Lanes
    TOP_LANE = "top_lane"
    MID_LANE = "mid_lane"
    BOT_LANE = "bot_lane"

    # River
    RIVER_TOP = "river_top"       # Top side river (baron pit area)
    RIVER_BOT = "river_bot"       # Bot side river (dragon pit area)
    RIVER_MID = "river_mid"       # Mid river (around mid lane)

    # Jungle quadrants
    JUNGLE_TOP_BLUE = "jungle_top_blue"   # Blue side top jungle
    JUNGLE_BOT_BLUE = "jungle_bot_blue"   # Blue side bot jungle
    JUNGLE_TOP_RED = "jungle_top_red"     # Red side top jungle
    JUNGLE_BOT_RED = "jungle_bot_red"     # Red side bot jungle

    # Base areas
    BASE_BLUE = "base_blue"
    BASE_RED = "base_red"

    # Unknown
    UNKNOWN = "unknown"


class DeathType(Enum):
    """Classification of how the death occurred."""
    GANK = "gank"              # Killed by 2+ enemies with jungler
    SOLO_KILL = "solo_kill"   # 1v1 death
    TEAMFIGHT = "teamfight"   # Multiple allies nearby
    CAUGHT = "caught"         # Alone, outnumbered
    TOWER_DIVE = "tower_dive" # Died under tower
    UNKNOWN = "unknown"


class PatternKey(Enum):
    """Detectable pattern types."""
    RIVER_DEATH_NO_WARD = "river_death_no_ward"
    DIES_WHEN_AHEAD = "dies_when_ahead"
    EARLY_DEATH_REPEAT = "early_death_repeat"
    TOWER_DIVE_FAIL = "tower_dive_fail"
    CAUGHT_SIDELANE = "caught_sidelane"
    FACECHECK = "facecheck"
    OVEREXTEND_NO_VISION = "overextend_no_vision"
    DIES_TO_SAME_CHAMP = "dies_to_same_champ"


@dataclass
class DeathContext:
    """Rich context for a single death event."""
    # Match info
    match_id: str
    game_timestamp_ms: int
    game_phase: GamePhase

    # Position
    position_x: int
    position_y: int
    map_zone: MapZone

    # Kill context
    killer_champion: str
    killer_participant_id: int
    assisting_champions: list[str] = field(default_factory=list)

    # Player state at death
    had_ward_nearby: bool = False
    gold_diff: int = 0      # Player gold - opponent gold
    cs_diff: int = 0        # Player CS - opponent CS
    level_diff: int = 0     # Player level - opponent level
    player_gold: int = 0
    player_champion: str = ""

    # Classification
    death_type: DeathType = DeathType.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "match_id": self.match_id,
            "game_timestamp_ms": self.game_timestamp_ms,
            "game_phase": self.game_phase.value,
            "position_x": self.position_x,
            "position_y": self.position_y,
            "map_zone": self.map_zone.value,
            "killer_champion": self.killer_champion,
            "killer_participant_id": self.killer_participant_id,
            "assisting_champions": self.assisting_champions,
            "had_ward_nearby": self.had_ward_nearby,
            "gold_diff": self.gold_diff,
            "cs_diff": self.cs_diff,
            "level_diff": self.level_diff,
            "player_gold": self.player_gold,
            "player_champion": self.player_champion,
            "death_type": self.death_type.value,
        }


# ============================================================
# Map Zone Detection
# ============================================================

# Riot map coordinates are approximately 0-15000 for both axes
# Blue base is bottom-left (~500, 500)
# Red base is top-right (~14500, 14500)

# Key landmarks (approximate):
# - Baron pit: (5000, 10500)
# - Dragon pit: (9500, 4500)
# - Mid lane: diagonal from (3000, 3000) to (12000, 12000)
# - River: diagonal band from (2000, 13000) to (13000, 2000)

def determine_map_zone(x: int, y: int) -> MapZone:
    """
    Convert Riot coordinates to map zone.

    The map is roughly 15000x15000 units.
    Blue base is bottom-left, Red base is top-right.
    """
    if x is None or y is None:
        return MapZone.UNKNOWN

    # Base areas (corners)
    if x < 2000 and y < 2000:
        return MapZone.BASE_BLUE
    if x > 13000 and y > 13000:
        return MapZone.BASE_RED

    # River detection (diagonal band)
    # River runs roughly where x + y is around 14000-16000
    river_value = x + y
    if 11000 < river_value < 19000:
        # It's in or near the river
        # Check which part of river
        if y > 10000 or x < 5000:
            return MapZone.RIVER_TOP  # Baron side
        elif y < 5000 or x > 10000:
            return MapZone.RIVER_BOT  # Dragon side
        else:
            return MapZone.RIVER_MID

    # Lane detection
    # Top lane: top-left edge (low x, high y)
    if x < 4000 and y > 11000:
        return MapZone.TOP_LANE
    if x < 2500 and y > 8000:
        return MapZone.TOP_LANE

    # Bot lane: bottom-right edge (high x, low y)
    if x > 11000 and y < 4000:
        return MapZone.BOT_LANE
    if x > 8000 and y < 2500:
        return MapZone.BOT_LANE

    # Mid lane: diagonal through center
    mid_diff = abs(x - y)
    if mid_diff < 3000 and 4000 < x < 11000 and 4000 < y < 11000:
        return MapZone.MID_LANE

    # Jungle quadrants
    center_x, center_y = 7500, 7500

    if x < center_x:
        # Blue side jungle
        if y > center_y:
            return MapZone.JUNGLE_TOP_BLUE
        else:
            return MapZone.JUNGLE_BOT_BLUE
    else:
        # Red side jungle
        if y > center_y:
            return MapZone.JUNGLE_TOP_RED
        else:
            return MapZone.JUNGLE_BOT_RED


def determine_game_phase(timestamp_ms: int) -> GamePhase:
    """Determine game phase from timestamp in milliseconds."""
    minutes = timestamp_ms / 60000

    if minutes < 10:
        return GamePhase.EARLY
    elif minutes < 20:
        return GamePhase.MID
    else:
        return GamePhase.LATE


def is_river_zone(zone: MapZone) -> bool:
    """Check if a zone is in the river."""
    return zone in (MapZone.RIVER_TOP, MapZone.RIVER_BOT, MapZone.RIVER_MID)


def is_sidelane(zone: MapZone) -> bool:
    """Check if a zone is a side lane."""
    return zone in (MapZone.TOP_LANE, MapZone.BOT_LANE)


# ============================================================
# Death Extraction
# ============================================================

def extract_deaths_from_match(
    match_data: dict,
    timeline_data: dict,
    puuid: str
) -> list[DeathContext]:
    """
    Extract all deaths for a player from match timeline with full context.

    Args:
        match_data: Full match data from Riot API
        timeline_data: Timeline data from Riot API (match_data["timeline"])
        puuid: Player's PUUID

    Returns:
        List of DeathContext objects with rich context
    """
    deaths = []

    # Find participant info
    info = match_data.get("info", {})
    participants = info.get("participants", [])

    participant = None
    participant_id = None
    for p in participants:
        if p.get("puuid") == puuid:
            participant = p
            participant_id = p.get("participantId")
            break

    if not participant or not participant_id:
        logger.warning(f"Player not found in match data for PUUID: {puuid[:8]}...")
        return deaths

    player_champion = participant.get("championName", "Unknown")
    player_role = participant.get("teamPosition", "UNKNOWN")

    # Find lane opponent (same role on opposite team)
    player_team_id = participant.get("teamId", 100)
    opponent_team_id = 200 if player_team_id == 100 else 100
    lane_opponent = None
    lane_opponent_id = None

    for p in participants:
        if p.get("teamId") == opponent_team_id and p.get("teamPosition") == player_role:
            lane_opponent = p
            lane_opponent_id = p.get("participantId")
            break

    # Build champion lookup
    champion_by_id = {}
    for p in participants:
        champion_by_id[p.get("participantId")] = p.get("championName", "Unknown")

    # Process timeline frames
    timeline_info = timeline_data.get("info", {})
    frames = timeline_info.get("frames", [])

    # Track ward placements for ward proximity check
    ward_events = []

    # First pass: collect ward placements
    for frame in frames:
        for event in frame.get("events", []):
            if event.get("type") == "WARD_PLACED" and event.get("creatorId") == participant_id:
                ward_events.append({
                    "timestamp": event.get("timestamp", 0),
                    "position": event.get("position", {}),
                })

    # Second pass: extract deaths
    for frame in frames:
        frame_timestamp = frame.get("timestamp", 0)
        participant_frames = frame.get("participantFrames", {})

        for event in frame.get("events", []):
            if event.get("type") != "CHAMPION_KILL":
                continue

            if event.get("victimId") != participant_id:
                continue

            # This is a death of our player
            timestamp = event.get("timestamp", frame_timestamp)
            position = event.get("position", {})
            pos_x = position.get("x", 0)
            pos_y = position.get("y", 0)

            killer_id = event.get("killerId", 0)
            assisting_ids = event.get("assistingParticipantIds", [])

            # Get killer and assisting champion names
            killer_champion = champion_by_id.get(killer_id, "Unknown")
            assisting_champions = [champion_by_id.get(aid, "Unknown") for aid in assisting_ids]

            # Get player state from participant frames
            player_frame = participant_frames.get(str(participant_id), {})
            player_gold = player_frame.get("totalGold", 0)
            player_cs = player_frame.get("minionsKilled", 0) + player_frame.get("jungleMinionsKilled", 0)
            player_level = player_frame.get("level", 1)

            # Get opponent state for comparison
            gold_diff = 0
            cs_diff = 0
            level_diff = 0

            if lane_opponent_id:
                opponent_frame = participant_frames.get(str(lane_opponent_id), {})
                opponent_gold = opponent_frame.get("totalGold", 0)
                opponent_cs = opponent_frame.get("minionsKilled", 0) + opponent_frame.get("jungleMinionsKilled", 0)
                opponent_level = opponent_frame.get("level", 1)

                gold_diff = player_gold - opponent_gold
                cs_diff = player_cs - opponent_cs
                level_diff = player_level - opponent_level

            # Check for ward nearby
            had_ward = _check_ward_nearby(
                ward_events, timestamp, pos_x, pos_y,
                lookback_ms=30000, radius=1500
            )

            # Classify death type
            death_type = _classify_death_type(
                killer_id=killer_id,
                assisting_ids=assisting_ids,
                position=(pos_x, pos_y),
                participants=participants,
                participant_frames=participant_frames,
                player_team_id=player_team_id
            )

            # Determine zone and phase
            map_zone = determine_map_zone(pos_x, pos_y)
            game_phase = determine_game_phase(timestamp)

            death = DeathContext(
                match_id=match_data.get("metadata", {}).get("matchId", "unknown"),
                game_timestamp_ms=timestamp,
                game_phase=game_phase,
                position_x=pos_x,
                position_y=pos_y,
                map_zone=map_zone,
                killer_champion=killer_champion,
                killer_participant_id=killer_id,
                assisting_champions=assisting_champions,
                had_ward_nearby=had_ward,
                gold_diff=gold_diff,
                cs_diff=cs_diff,
                level_diff=level_diff,
                player_gold=player_gold,
                player_champion=player_champion,
                death_type=death_type,
            )

            deaths.append(death)
            logger.debug(
                f"Extracted death at {timestamp}ms: {killer_champion} killed {player_champion} "
                f"in {map_zone.value} ({death_type.value})"
            )

    logger.info(f"Extracted {len(deaths)} deaths from match")
    return deaths


def _check_ward_nearby(
    ward_events: list[dict],
    death_timestamp: int,
    death_x: int,
    death_y: int,
    lookback_ms: int = 30000,
    radius: int = 1500
) -> bool:
    """
    Check if the player had a ward nearby before death.

    Args:
        ward_events: List of ward placement events
        death_timestamp: When the death occurred (ms)
        death_x, death_y: Death position
        lookback_ms: How far back to look for wards
        radius: How close the ward needs to be

    Returns:
        True if a ward was placed nearby recently
    """
    for ward in ward_events:
        ward_time = ward.get("timestamp", 0)
        ward_pos = ward.get("position", {})
        ward_x = ward_pos.get("x", 0)
        ward_y = ward_pos.get("y", 0)

        # Check if ward was placed within lookback window
        time_diff = death_timestamp - ward_time
        if not (0 < time_diff < lookback_ms):
            continue

        # Check distance
        distance = math.sqrt((death_x - ward_x) ** 2 + (death_y - ward_y) ** 2)
        if distance < radius:
            return True

    return False


def _classify_death_type(
    killer_id: int,
    assisting_ids: list[int],
    position: tuple[int, int],
    participants: list[dict],
    participant_frames: dict,
    player_team_id: int
) -> DeathType:
    """
    Classify the type of death based on context.

    Args:
        killer_id: ID of the killer
        assisting_ids: IDs of players who assisted
        position: (x, y) of death
        participants: All participants in the match
        participant_frames: Frame data for all participants
        player_team_id: Team ID of the player who died

    Returns:
        DeathType classification
    """
    total_enemies_involved = 1 + len(assisting_ids)  # Killer + assists

    # Tower dive detection (near enemy tower)
    # TODO: Add tower position checking if needed

    # Check if it was a gank (jungler involved)
    enemy_team_id = 200 if player_team_id == 100 else 100
    jungler_ids = []
    for p in participants:
        if p.get("teamId") == enemy_team_id and p.get("teamPosition") == "JUNGLE":
            jungler_ids.append(p.get("participantId"))

    jungler_involved = killer_id in jungler_ids or any(aid in jungler_ids for aid in assisting_ids)

    if total_enemies_involved >= 2 and jungler_involved:
        return DeathType.GANK

    if total_enemies_involved == 1:
        return DeathType.SOLO_KILL

    if total_enemies_involved >= 3:
        return DeathType.TEAMFIGHT

    # 2 enemies, no jungler = likely caught
    return DeathType.CAUGHT


# ============================================================
# Pattern Detection
# ============================================================

def detect_patterns(
    deaths: list[DeathContext],
    existing_patterns: list[dict],
    min_occurrences: int = 2
) -> list[dict]:
    """
    Analyze deaths to detect recurring patterns.

    Args:
        deaths: List of death contexts from recent matches
        existing_patterns: Current patterns from database
        min_occurrences: Minimum occurrences to detect a pattern

    Returns:
        List of pattern updates (new patterns or updated existing ones)
    """
    pattern_updates = []

    if not deaths:
        return pattern_updates

    # Pattern: River deaths without ward
    river_deaths_no_ward = [
        d for d in deaths
        if is_river_zone(d.map_zone) and not d.had_ward_nearby
    ]
    if len(river_deaths_no_ward) >= min_occurrences:
        pattern_updates.append({
            "pattern_key": PatternKey.RIVER_DEATH_NO_WARD.value,
            "pattern_category": "vision",
            "description": f"Died in river {len(river_deaths_no_ward)} times without ward coverage",
            "occurrences": len(river_deaths_no_ward),
            "sample_death_ids": [d.match_id for d in river_deaths_no_ward[:5]],
        })

    # Pattern: Dying when ahead
    deaths_when_ahead = [
        d for d in deaths
        if d.gold_diff > 500 or d.cs_diff > 15
    ]
    if len(deaths_when_ahead) >= min_occurrences:
        pattern_updates.append({
            "pattern_key": PatternKey.DIES_WHEN_AHEAD.value,
            "pattern_category": "trading",
            "description": f"Died {len(deaths_when_ahead)} times while ahead in lane",
            "occurrences": len(deaths_when_ahead),
            "sample_death_ids": [d.match_id for d in deaths_when_ahead[:5]],
        })

    # Pattern: Early death repeat (same time window)
    early_deaths = [d for d in deaths if d.game_phase == GamePhase.EARLY]
    time_clusters = _cluster_by_time(early_deaths, window_ms=120000)
    for cluster in time_clusters:
        if len(cluster) >= min_occurrences:
            avg_time_ms = sum(d.game_timestamp_ms for d in cluster) // len(cluster)
            avg_time_min = avg_time_ms // 60000
            pattern_updates.append({
                "pattern_key": PatternKey.EARLY_DEATH_REPEAT.value,
                "pattern_category": "positioning",
                "description": f"Consistently dying around {avg_time_min} minutes into the game",
                "occurrences": len(cluster),
                "sample_death_ids": [d.match_id for d in cluster[:5]],
            })

    # Pattern: Caught in sidelane (mid/late game)
    sidelane_deaths = [
        d for d in deaths
        if is_sidelane(d.map_zone)
        and d.game_phase in (GamePhase.MID, GamePhase.LATE)
        and d.death_type == DeathType.CAUGHT
    ]
    if len(sidelane_deaths) >= min_occurrences:
        pattern_updates.append({
            "pattern_key": PatternKey.CAUGHT_SIDELANE.value,
            "pattern_category": "macro",
            "description": f"Got caught while sidelaning {len(sidelane_deaths)} times",
            "occurrences": len(sidelane_deaths),
            "sample_death_ids": [d.match_id for d in sidelane_deaths[:5]],
        })

    # Pattern: Tower dive fails
    tower_dive_deaths = [d for d in deaths if d.death_type == DeathType.TOWER_DIVE]
    if len(tower_dive_deaths) >= min_occurrences:
        pattern_updates.append({
            "pattern_key": PatternKey.TOWER_DIVE_FAIL.value,
            "pattern_category": "trading",
            "description": f"Died to tower dive {len(tower_dive_deaths)} times",
            "occurrences": len(tower_dive_deaths),
            "sample_death_ids": [d.match_id for d in tower_dive_deaths[:5]],
        })

    # Pattern: Overextending without vision (not river specific)
    overextend_deaths = [
        d for d in deaths
        if not d.had_ward_nearby
        and d.death_type in (DeathType.GANK, DeathType.CAUGHT)
    ]
    if len(overextend_deaths) >= min_occurrences:
        pattern_updates.append({
            "pattern_key": PatternKey.OVEREXTEND_NO_VISION.value,
            "pattern_category": "vision",
            "description": f"Overextended without vision {len(overextend_deaths)} times",
            "occurrences": len(overextend_deaths),
            "sample_death_ids": [d.match_id for d in overextend_deaths[:5]],
        })

    # Pattern: Dies to same champion repeatedly
    killer_counts = defaultdict(list)
    for d in deaths:
        killer_counts[d.killer_champion].append(d)

    for killer, killer_deaths in killer_counts.items():
        if len(killer_deaths) >= 3:  # Higher threshold for same-champion pattern
            pattern_updates.append({
                "pattern_key": PatternKey.DIES_TO_SAME_CHAMP.value,
                "pattern_category": "matchup",
                "description": f"Died to {killer} {len(killer_deaths)} times",
                "occurrences": len(killer_deaths),
                "sample_death_ids": [d.match_id for d in killer_deaths[:5]],
            })

    logger.info(f"Detected {len(pattern_updates)} patterns from {len(deaths)} deaths")
    return pattern_updates


def _cluster_by_time(
    deaths: list[DeathContext],
    window_ms: int = 120000
) -> list[list[DeathContext]]:
    """
    Cluster deaths that occurred within window_ms of each other.

    Uses a simple sliding window approach.
    """
    if not deaths:
        return []

    # Sort by timestamp
    sorted_deaths = sorted(deaths, key=lambda d: d.game_timestamp_ms)

    clusters = []
    current_cluster = [sorted_deaths[0]]

    for death in sorted_deaths[1:]:
        # Check if this death is within window of last death in cluster
        last_death = current_cluster[-1]
        if death.game_timestamp_ms - last_death.game_timestamp_ms <= window_ms:
            current_cluster.append(death)
        else:
            # Start new cluster
            if len(current_cluster) > 1:
                clusters.append(current_cluster)
            current_cluster = [death]

    # Don't forget the last cluster
    if len(current_cluster) > 1:
        clusters.append(current_cluster)

    return clusters


def _cluster_by_position(
    deaths: list[DeathContext],
    radius: int = 1000
) -> list[list[DeathContext]]:
    """
    Cluster deaths that occurred within radius units of each other.

    Uses a simple greedy clustering approach.
    """
    if not deaths:
        return []

    clusters = []
    used = set()

    for i, death in enumerate(deaths):
        if i in used:
            continue

        cluster = [death]
        used.add(i)

        for j, other in enumerate(deaths):
            if j in used:
                continue

            distance = math.sqrt(
                (death.position_x - other.position_x) ** 2 +
                (death.position_y - other.position_y) ** 2
            )

            if distance <= radius:
                cluster.append(other)
                used.add(j)

        if len(cluster) > 1:
            clusters.append(cluster)

    return clusters


# ============================================================
# Pattern Status Management
# ============================================================

def check_pattern_status(
    pattern: dict,
    recent_deaths: list[DeathContext],
    games_since_pattern: int
) -> str:
    """
    Check if a pattern is still active, improving, or broken.

    Args:
        pattern: Pattern dict from database
        recent_deaths: Deaths from the most recent game
        games_since_pattern: Number of games since pattern was last triggered

    Returns:
        'active', 'improving', or 'broken'
    """
    pattern_key = pattern.get("pattern_key")

    # Check if pattern was triggered in the most recent game
    triggered = _pattern_triggered_in_deaths(pattern_key, recent_deaths)

    if triggered:
        return "active"

    # Check improvement based on games since last occurrence
    if games_since_pattern >= 5:
        return "broken"
    elif games_since_pattern >= 3:
        return "improving"
    else:
        return "active"


def _pattern_triggered_in_deaths(
    pattern_key: str,
    deaths: list[DeathContext]
) -> bool:
    """Check if a specific pattern was triggered in the given deaths."""
    if not deaths:
        return False

    if pattern_key == PatternKey.RIVER_DEATH_NO_WARD.value:
        return any(is_river_zone(d.map_zone) and not d.had_ward_nearby for d in deaths)

    if pattern_key == PatternKey.DIES_WHEN_AHEAD.value:
        return any(d.gold_diff > 500 or d.cs_diff > 15 for d in deaths)

    if pattern_key == PatternKey.EARLY_DEATH_REPEAT.value:
        return any(d.game_phase == GamePhase.EARLY for d in deaths)

    if pattern_key == PatternKey.CAUGHT_SIDELANE.value:
        return any(
            is_sidelane(d.map_zone)
            and d.game_phase in (GamePhase.MID, GamePhase.LATE)
            and d.death_type == DeathType.CAUGHT
            for d in deaths
        )

    if pattern_key == PatternKey.TOWER_DIVE_FAIL.value:
        return any(d.death_type == DeathType.TOWER_DIVE for d in deaths)

    if pattern_key == PatternKey.OVEREXTEND_NO_VISION.value:
        return any(
            not d.had_ward_nearby
            and d.death_type in (DeathType.GANK, DeathType.CAUGHT)
            for d in deaths
        )

    return False


def get_priority_pattern(patterns: list[dict]) -> Optional[dict]:
    """
    Get the highest priority pattern for coaching focus.

    Priority = (occurrences * recency_weight) / (games_since_last + 1)

    Most frequent + most recent = highest priority.
    """
    if not patterns:
        return None

    def priority_score(p: dict) -> float:
        occurrences = p.get("occurrences", 1)
        games_since = p.get("games_since_last", 0)
        # More recent patterns get higher weight
        return occurrences / (games_since + 1)

    # Filter to only active patterns
    active_patterns = [p for p in patterns if p.get("status") == "active"]

    if not active_patterns:
        return None

    return max(active_patterns, key=priority_score)
