"""
Player Memory Module

Persistent storage for player profiles using markdown files.
Acts as the coach's "memory" of each player - their rank, goals,
progress, and coaching history.

Each player gets their own .md file that the coach can read and update.

Now integrates with database for:
- Pattern tracking and progress
- Session continuity with opener generation
- Rich coaching context for AI prompts
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass, field

from ..logging_config import get_logger
from ..db import get_database
from ..db.repositories import (
    PlayerRepository,
    PatternRepository,
    SessionRepository,
    MissionRepository,
)

logger = get_logger(__name__)

# Default storage location
MEMORY_DIR = Path(os.getenv("COACH_MEMORY_DIR", "./data/players"))


@dataclass
class PlayerProfile:
    """Player profile data structure"""
    # Identity
    discord_id: int
    discord_name: str
    riot_id: str
    platform: str

    # Rank tracking
    current_rank: str = "Unranked"
    target_rank: str = "Gold IV"
    peak_rank: str = "Unranked"

    # Goals
    current_goal: str = "Improve overall gameplay"
    short_term_goals: list[str] = field(default_factory=list)
    long_term_goals: list[str] = field(default_factory=list)

    # Progress tracking
    missions_completed: int = 0
    missions_failed: int = 0
    sessions_count: int = 0

    # Coaching insights
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)

    # History
    coaching_notes: list[str] = field(default_factory=list)
    milestones: list[str] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    last_session: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.last_session:
            self.last_session = datetime.now().isoformat()


class PlayerMemory:
    """
    Manages player profile storage as markdown files.

    Each player has a file like: data/players/123456789.md
    The markdown format makes it easy to:
    - Read/edit manually if needed
    - Include in Claude prompts as context
    - Track history over time
    """

    def __init__(self, memory_dir: Optional[Path] = None):
        self.memory_dir = memory_dir or MEMORY_DIR
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"PlayerMemory initialized at {self.memory_dir}")

    def _get_profile_path(self, discord_id: int) -> Path:
        """Get the path to a player's profile file"""
        return self.memory_dir / f"{discord_id}.md"

    def profile_exists(self, discord_id: int) -> bool:
        """Check if a player profile exists"""
        return self._get_profile_path(discord_id).exists()

    def load_profile(self, discord_id: int) -> Optional[PlayerProfile]:
        """Load a player profile from markdown file"""
        path = self._get_profile_path(discord_id)

        if not path.exists():
            return None

        try:
            content = path.read_text(encoding="utf-8")
            return self._parse_markdown(discord_id, content)
        except Exception as e:
            logger.exception(f"Error loading profile {discord_id}: {e}")
            return None

    def save_profile(self, profile: PlayerProfile) -> bool:
        """Save a player profile to markdown file"""
        path = self._get_profile_path(profile.discord_id)

        try:
            content = self._generate_markdown(profile)
            path.write_text(content, encoding="utf-8")
            logger.info(f"Saved profile for {profile.discord_id}")
            return True
        except Exception as e:
            logger.exception(f"Error saving profile {profile.discord_id}: {e}")
            return False

    def create_profile(
        self,
        discord_id: int,
        discord_name: str,
        riot_id: str,
        platform: str,
        current_rank: str = "Unranked",
        target_rank: str = "Gold IV"
    ) -> PlayerProfile:
        """Create a new player profile"""
        profile = PlayerProfile(
            discord_id=discord_id,
            discord_name=discord_name,
            riot_id=riot_id,
            platform=platform,
            current_rank=current_rank,
            target_rank=target_rank,
            peak_rank=current_rank,
        )
        self.save_profile(profile)
        return profile

    def get_or_create_profile(
        self,
        discord_id: int,
        discord_name: str,
        riot_id: str,
        platform: str
    ) -> PlayerProfile:
        """Get existing profile or create new one"""
        profile = self.load_profile(discord_id)
        if profile:
            # Update last session
            profile.last_session = datetime.now().isoformat()
            profile.sessions_count += 1
            self.save_profile(profile)
            return profile
        return self.create_profile(discord_id, discord_name, riot_id, platform)

    def update_rank(self, discord_id: int, new_rank: str) -> bool:
        """Update player's current rank"""
        profile = self.load_profile(discord_id)
        if not profile:
            return False

        old_rank = profile.current_rank
        profile.current_rank = new_rank

        # Check if this is a new peak
        if self._rank_value(new_rank) > self._rank_value(profile.peak_rank):
            profile.peak_rank = new_rank
            profile.milestones.append(
                f"[{datetime.now().strftime('%Y-%m-%d')}] New peak rank: {new_rank}!"
            )

        # Add to notes if rank changed
        if old_rank != new_rank:
            profile.coaching_notes.append(
                f"[{datetime.now().strftime('%Y-%m-%d')}] Rank changed: {old_rank} → {new_rank}"
            )

        return self.save_profile(profile)

    def set_goal(self, discord_id: int, goal: str, goal_type: str = "current") -> bool:
        """Set player's goal"""
        profile = self.load_profile(discord_id)
        if not profile:
            return False

        if goal_type == "current":
            profile.current_goal = goal
        elif goal_type == "short":
            if goal not in profile.short_term_goals:
                profile.short_term_goals.append(goal)
        elif goal_type == "long":
            if goal not in profile.long_term_goals:
                profile.long_term_goals.append(goal)
        elif goal_type == "target_rank":
            profile.target_rank = goal

        return self.save_profile(profile)

    def add_coaching_note(self, discord_id: int, note: str) -> bool:
        """Add a coaching note to player's history"""
        profile = self.load_profile(discord_id)
        if not profile:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        profile.coaching_notes.append(f"[{timestamp}] {note}")

        # Keep only last 50 notes
        if len(profile.coaching_notes) > 50:
            profile.coaching_notes = profile.coaching_notes[-50:]

        return self.save_profile(profile)

    def add_pattern(self, discord_id: int, pattern: str) -> bool:
        """Add a discovered pattern/weakness"""
        profile = self.load_profile(discord_id)
        if not profile:
            return False

        if pattern not in profile.patterns:
            profile.patterns.append(pattern)

        return self.save_profile(profile)

    def record_mission(self, discord_id: int, completed: bool) -> bool:
        """Record mission completion/failure"""
        profile = self.load_profile(discord_id)
        if not profile:
            return False

        if completed:
            profile.missions_completed += 1
        else:
            profile.missions_failed += 1

        return self.save_profile(profile)

    def get_context_for_coach(self, discord_id: int) -> str:
        """Get the full markdown content for use in Claude prompts"""
        path = self._get_profile_path(discord_id)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _generate_markdown(self, profile: PlayerProfile) -> str:
        """Generate markdown content from profile"""

        strengths = "\n".join(f"- {s}" for s in profile.strengths) or "- Not yet identified"
        weaknesses = "\n".join(f"- {w}" for w in profile.weaknesses) or "- Not yet identified"
        patterns = "\n".join(f"- {p}" for p in profile.patterns) or "- Not yet identified"
        short_goals = "\n".join(f"- {g}" for g in profile.short_term_goals) or "- None set"
        long_goals = "\n".join(f"- {g}" for g in profile.long_term_goals) or "- None set"
        notes = "\n".join(profile.coaching_notes[-20:]) or "No notes yet"  # Last 20 notes
        milestones = "\n".join(f"- {m}" for m in profile.milestones) or "- None yet"

        return f"""# Player Profile: {profile.discord_name}

## Identity
- **Discord ID:** {profile.discord_id}
- **Riot ID:** {profile.riot_id}
- **Platform:** {profile.platform}
- **First Session:** {profile.created_at[:10]}
- **Last Session:** {profile.last_session[:10]}
- **Total Sessions:** {profile.sessions_count}

## Rank
- **Current Rank:** {profile.current_rank}
- **Target Rank:** {profile.target_rank}
- **Peak Rank:** {profile.peak_rank}

## Goals
### Current Focus
{profile.current_goal}

### Short-term Goals
{short_goals}

### Long-term Goals
{long_goals}

## Progress
- **Missions Completed:** {profile.missions_completed}
- **Missions Failed:** {profile.missions_failed}
- **Success Rate:** {self._calc_success_rate(profile)}%

## Coach's Assessment

### Strengths
{strengths}

### Weaknesses
{weaknesses}

### Patterns Noticed
{patterns}

## Milestones
{milestones}

## Coaching Notes
{notes}

---
*Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""

    def _parse_markdown(self, discord_id: int, content: str) -> PlayerProfile:
        """Parse markdown content into profile"""
        profile = PlayerProfile(
            discord_id=discord_id,
            discord_name="Unknown",
            riot_id="Unknown#NA1",
            platform="na1"
        )

        # Helper to extract value after **Label:**
        def extract(pattern: str, default: str = "") -> str:
            match = re.search(pattern, content)
            return match.group(1).strip() if match else default

        # Helper to extract list items under a header
        def extract_list(header: str) -> list[str]:
            pattern = rf"### {header}\n((?:- .+\n?)+)"
            match = re.search(pattern, content)
            if match:
                items = re.findall(r"- (.+)", match.group(1))
                return [i for i in items if i and i != "Not yet identified" and i != "None set" and i != "None yet"]
            return []

        # Parse identity
        profile.discord_name = extract(r"\*\*Discord ID:\*\* (\d+)", str(discord_id))
        profile.riot_id = extract(r"\*\*Riot ID:\*\* (.+)")
        profile.platform = extract(r"\*\*Platform:\*\* (.+)")
        profile.created_at = extract(r"\*\*First Session:\*\* (.+)")
        profile.last_session = extract(r"\*\*Last Session:\*\* (.+)")
        profile.sessions_count = int(extract(r"\*\*Total Sessions:\*\* (\d+)", "0"))

        # Parse rank
        profile.current_rank = extract(r"\*\*Current Rank:\*\* (.+)", "Unranked")
        profile.target_rank = extract(r"\*\*Target Rank:\*\* (.+)", "Gold IV")
        profile.peak_rank = extract(r"\*\*Peak Rank:\*\* (.+)", "Unranked")

        # Parse goals
        goal_match = re.search(r"### Current Focus\n(.+?)(?=\n###|\n##|$)", content, re.DOTALL)
        if goal_match:
            profile.current_goal = goal_match.group(1).strip()

        profile.short_term_goals = extract_list("Short-term Goals")
        profile.long_term_goals = extract_list("Long-term Goals")

        # Parse progress
        profile.missions_completed = int(extract(r"\*\*Missions Completed:\*\* (\d+)", "0"))
        profile.missions_failed = int(extract(r"\*\*Missions Failed:\*\* (\d+)", "0"))

        # Parse assessment
        profile.strengths = extract_list("Strengths")
        profile.weaknesses = extract_list("Weaknesses")
        profile.patterns = extract_list("Patterns Noticed")

        # Parse milestones
        milestones_match = re.search(r"## Milestones\n((?:- .+\n?)+)", content)
        if milestones_match:
            profile.milestones = re.findall(r"- (.+)", milestones_match.group(1))
            profile.milestones = [m for m in profile.milestones if m != "None yet"]

        # Parse coaching notes
        notes_match = re.search(r"## Coaching Notes\n(.+?)(?=\n---|$)", content, re.DOTALL)
        if notes_match:
            notes_text = notes_match.group(1).strip()
            if notes_text != "No notes yet":
                profile.coaching_notes = [n.strip() for n in notes_text.split("\n") if n.strip()]

        return profile

    def _calc_success_rate(self, profile: PlayerProfile) -> int:
        """Calculate mission success rate"""
        total = profile.missions_completed + profile.missions_failed
        if total == 0:
            return 0
        return int((profile.missions_completed / total) * 100)

    def _rank_value(self, rank: str) -> int:
        """Convert rank string to numeric value for comparison"""
        ranks = {
            "Iron IV": 1, "Iron III": 2, "Iron II": 3, "Iron I": 4,
            "Bronze IV": 5, "Bronze III": 6, "Bronze II": 7, "Bronze I": 8,
            "Silver IV": 9, "Silver III": 10, "Silver II": 11, "Silver I": 12,
            "Gold IV": 13, "Gold III": 14, "Gold II": 15, "Gold I": 16,
            "Platinum IV": 17, "Platinum III": 18, "Platinum II": 19, "Platinum I": 20,
            "Emerald IV": 21, "Emerald III": 22, "Emerald II": 23, "Emerald I": 24,
            "Diamond IV": 25, "Diamond III": 26, "Diamond II": 27, "Diamond I": 28,
            "Master": 29, "Grandmaster": 30, "Challenger": 31,
        }
        return ranks.get(rank, 0)

    # ============================================================
    # Database-Backed Coaching Context
    # ============================================================

    async def get_coaching_context(self, discord_id: int) -> dict[str, Any]:
        """
        Get full coaching context for AI prompts.

        Combines:
        - Markdown profile (goals, notes)
        - Active patterns from DB
        - Pattern progress
        - Last session insights
        - Generated session opener

        Args:
            discord_id: Discord user ID

        Returns:
            {
                'profile': PlayerProfile,
                'active_patterns': [...],
                'pattern_progress': {...},
                'last_session': {...},
                'session_opener': str
            }
        """
        # Load markdown profile
        profile = self.load_profile(discord_id)
        if not profile:
            return {"profile": None}

        # Get DB context
        try:
            db = await get_database()
            player_repo = PlayerRepository(db)
            pattern_repo = PatternRepository(db)
            session_repo = SessionRepository(db)
            mission_repo = MissionRepository(db)

            player = await player_repo.get_by_discord_id(discord_id)
            if not player:
                return {"profile": profile}

            player_id = player["id"]

            # Get active patterns
            active_patterns = await pattern_repo.get_active(player_id)

            # Calculate progress for each pattern
            pattern_progress = {}
            for pattern in active_patterns:
                pattern_progress[pattern["pattern_key"]] = {
                    "occurrences": pattern.get("occurrences", 0),
                    "status": pattern.get("status", "active"),
                    "improvement_streak": pattern.get("improvement_streak", 0),
                    "games_since_last": pattern.get("games_since_last", 0),
                }

            # Get last session
            last_session = await session_repo.get_last(player_id)

            # Generate session opener
            session_opener = await self._generate_session_opener(
                profile, active_patterns, last_session
            )

            return {
                "profile": profile,
                "active_patterns": active_patterns,
                "pattern_progress": pattern_progress,
                "last_session": last_session,
                "session_opener": session_opener,
            }

        except Exception as e:
            logger.exception(f"Error getting coaching context: {e}")
            return {"profile": profile}

    async def _generate_session_opener(
        self,
        profile: PlayerProfile,
        active_patterns: list[dict],
        last_session: Optional[dict]
    ) -> str:
        """
        Generate personalized session opener based on continuity.

        Examples:
        - "Last time you said you'd focus on warding river. You've played 2 games since - let's see how it went!"
        - "Welcome back! Your early deaths have decreased - nice progress!"
        - "Good to see you again. You mentioned wanting to work on your CS - want to continue with that?"
        """
        opener_parts = []

        # Reference last session if exists
        if last_session:
            try:
                last_started = last_session.get("started_at")
                if last_started:
                    if isinstance(last_started, str):
                        last_date = datetime.fromisoformat(last_started.replace("Z", "+00:00"))
                    else:
                        last_date = last_started

                    days_since = (datetime.now() - last_date.replace(tzinfo=None)).days

                    if days_since < 7:
                        focus = last_session.get("focus_area", "")
                        if focus:
                            opener_parts.append(
                                f"Welcome back! Last time we talked about {focus}."
                            )
            except Exception as e:
                logger.warning(f"Could not parse last session date: {e}")

        # Highlight pattern progress
        improving_patterns = [p for p in active_patterns if p.get("status") == "improving"]
        if improving_patterns:
            pattern = improving_patterns[0]
            pattern_name = pattern.get("pattern_key", "").replace("_", " ")
            streak = pattern.get("improvement_streak", 0)
            if streak > 0:
                opener_parts.append(
                    f"Your {pattern_name} has been improving - "
                    f"{streak} games without triggering!"
                )

        # Reference broken patterns (successes!)
        broken_patterns = [p for p in active_patterns if p.get("status") == "broken"]
        if broken_patterns:
            pattern = broken_patterns[0]
            pattern_name = pattern.get("pattern_key", "").replace("_", " ")
            opener_parts.append(
                f"Great news: You've broken the {pattern_name} pattern! "
                f"It hasn't shown up in your recent games."
            )

        # Reference player goals
        if profile.current_goal and profile.current_goal != "Improve overall gameplay":
            opener_parts.append(f"Still working towards: {profile.current_goal}")

        # Default opener if nothing else
        if not opener_parts:
            if profile.sessions_count > 1:
                opener_parts.append("Good to see you again! Ready for some coaching?")
            else:
                opener_parts.append("Let's take a look at your gameplay!")

        return " ".join(opener_parts)

    async def record_session(
        self,
        discord_id: int,
        focus_area: str,
        patterns_discussed: Optional[list[str]] = None,
        insights: Optional[list[str]] = None,
        matches_analyzed: int = 0
    ) -> Optional[int]:
        """
        Record a coaching session for continuity.

        Args:
            discord_id: Discord user ID
            focus_area: What the session focused on
            patterns_discussed: Pattern keys that were discussed
            insights: Insights generated during the session
            matches_analyzed: Number of matches analyzed

        Returns:
            Session ID or None if failed
        """
        try:
            db = await get_database()
            player_repo = PlayerRepository(db)
            session_repo = SessionRepository(db)

            player = await player_repo.get_by_discord_id(discord_id)
            if not player:
                return None

            session_id = await session_repo.create(
                player_id=player["id"],
                focus_area=focus_area,
                matches_analyzed=matches_analyzed
            )

            # If we have patterns/insights to record, end the session immediately
            # with that info (for simple use cases)
            if patterns_discussed or insights:
                await session_repo.end_session(
                    session_id=session_id,
                    patterns_discussed=patterns_discussed,
                    insights=insights
                )

            logger.info(f"Recorded session {session_id} for discord_id={discord_id}")
            return session_id

        except Exception as e:
            logger.exception(f"Error recording session: {e}")
            return None

    async def get_pattern_summary(self, discord_id: int) -> str:
        """
        Get a summary of the player's patterns for display.

        Returns a formatted string suitable for Discord embeds.
        """
        try:
            db = await get_database()
            player_repo = PlayerRepository(db)
            pattern_repo = PatternRepository(db)

            player = await player_repo.get_by_discord_id(discord_id)
            if not player:
                return "No patterns tracked yet."

            patterns = await pattern_repo.get_all(player["id"])
            if not patterns:
                return "No patterns detected yet. Play some games!"

            lines = []
            for p in patterns[:5]:  # Top 5 patterns
                status_emoji = {
                    "active": "🔴",
                    "improving": "🟡",
                    "broken": "🟢",
                }.get(p.get("status"), "⚪")

                name = p.get("pattern_key", "").replace("_", " ").title()
                occurrences = p.get("occurrences", 0)
                status = p.get("status", "active")

                lines.append(f"{status_emoji} **{name}** ({occurrences}x) - {status}")

            return "\n".join(lines)

        except Exception as e:
            logger.exception(f"Error getting pattern summary: {e}")
            return "Could not load pattern summary."
