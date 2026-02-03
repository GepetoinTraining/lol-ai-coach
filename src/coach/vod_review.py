"""
VOD Review System

Provides a Socratic coaching experience by guiding players through
reviewing their deaths with targeted questions.

The coach asks questions that help players discover WHY they died,
rather than telling them what they did wrong.
"""

from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime

import anthropic

from ..db import get_database
from ..db.repositories import VODMomentRepository, DeathRepository, PatternRepository
from ..analysis.pattern_detector import MapZone, GamePhase, PatternKey, is_river_zone
from ..logging_config import get_logger

logger = get_logger(__name__)


# Socratic questions mapped to patterns
PATTERN_QUESTIONS = {
    PatternKey.RIVER_DEATH_NO_WARD.value: [
        "What information did you have about where their jungler was?",
        "Before you walked into river, what did you check on the minimap?",
        "If you were their jungler, where would you be right now?",
    ],
    PatternKey.DIES_WHEN_AHEAD.value: [
        "When you're winning lane, what changes about how your opponent should play?",
        "What did being ahead allow you to do that you couldn't do when even?",
        "If you're up 500 gold, what's the risk-reward of this fight?",
    ],
    PatternKey.EARLY_DEATH_REPEAT.value: [
        "What's different about this time in the game that makes it dangerous?",
        "What information do you have about the enemy jungler's pathing at this point?",
        "At this game time, what should your priority be?",
    ],
    PatternKey.CAUGHT_SIDELANE.value: [
        "Before you started pushing this wave, what did you check on the map?",
        "How many enemies were showing on the map when you pushed up?",
        "What's the risk of pushing this wave vs. staying with your team?",
    ],
    PatternKey.TOWER_DIVE_FAIL.value: [
        "What made you think this dive would work?",
        "How many tower shots did you calculate you could take?",
        "What was the enemy's health and cooldowns when you committed?",
    ],
    PatternKey.OVEREXTEND_NO_VISION.value: [
        "What parts of the map were dark when you pushed forward?",
        "Where was your ward coverage at this moment?",
        "If you couldn't see 3 enemies, where do you assume they are?",
    ],
    PatternKey.FACECHECK.value: [
        "What could you have done to check that brush safely?",
        "What ability or ward could have given you information first?",
        "Knowing that brush was unwarded, what made you walk into it?",
    ],
}

# Default questions for deaths without a specific pattern
DEFAULT_QUESTIONS = [
    "Looking at the minimap 10 seconds before this death, what information did you have?",
    "What were you trying to accomplish when this happened?",
    "If you could replay this moment, what would you do differently?",
    "What information did you NOT have that would have changed your decision?",
]


@dataclass
class ReviewMoment:
    """A moment ready for VOD review."""
    moment_id: int
    death_id: int
    match_id: str
    timestamp_seconds: int
    timestamp_formatted: str  # e.g., "6:42"

    # Context
    context: str  # e.g., "You died to Lee Sin in river"
    map_zone: str
    had_ward: bool
    gold_diff: int
    player_champion: str
    killer_champion: str

    # Pattern info
    pattern_key: Optional[str]
    pattern_description: Optional[str]

    # Coaching
    things_to_notice: list[str]
    socratic_question: str


class VODReviewManager:
    """
    Manages the VOD review flow for a player.

    Guides players through reviewing deaths with Socratic questions
    that help them discover insights themselves.
    """

    def __init__(self):
        self.claude = anthropic.Anthropic()
        self._db = None
        self._death_repo = None
        self._moment_repo = None
        self._pattern_repo = None

    async def _init_repos(self):
        """Lazy initialize database repositories."""
        if self._db is None:
            self._db = await get_database()
            self._death_repo = DeathRepository(self._db)
            self._moment_repo = VODMomentRepository(self._db)
            self._pattern_repo = PatternRepository(self._db)

    async def get_reviewable_deaths(
        self,
        player_id: int,
        limit: int = 5
    ) -> list[ReviewMoment]:
        """
        Get deaths worth reviewing for a player.

        Prioritizes:
        1. Deaths matching active patterns
        2. Recent deaths over old ones
        3. Deaths with clear learning potential
        """
        await self._init_repos()

        # Get active patterns
        active_patterns = await self._pattern_repo.get_active(player_id)
        pattern_keys = [p["pattern_key"] for p in active_patterns]

        # Get unreviewed moments first (already created VOD moments)
        existing_moments = await self._moment_repo.get_unreviewed(player_id, limit)

        if existing_moments:
            return [self._moment_to_review_moment(m, active_patterns) for m in existing_moments]

        # No existing moments - create some from recent deaths
        deaths = await self._death_repo.get_for_player(player_id, limit=50)

        if not deaths:
            return []

        # Score and rank deaths
        scored_deaths = []
        for death in deaths:
            score = self._score_death_for_review(death, pattern_keys)
            if score > 0:
                scored_deaths.append((death, score))

        # Sort by score descending
        scored_deaths.sort(key=lambda x: x[1], reverse=True)

        # Create VOD moments for top deaths
        moments = []
        for death, _ in scored_deaths[:limit]:
            pattern = self._find_matching_pattern(death, active_patterns)
            pattern_id = pattern["id"] if pattern else None

            # Generate the Socratic question
            question = self._generate_socratic_question(death, pattern)

            # Create VOD moment in database
            moment_id = await self._moment_repo.create(
                death_id=death["id"],
                player_id=player_id,
                pattern_id=pattern_id,
                coach_question=question
            )

            # Build ReviewMoment
            moment = self._death_to_review_moment(
                death, moment_id, pattern, question
            )
            moments.append(moment)

        return moments

    def _score_death_for_review(
        self,
        death: dict,
        active_pattern_keys: list[str]
    ) -> int:
        """
        Score a death for review priority.

        Higher score = more worth reviewing.
        """
        score = 0

        # Pattern match bonus
        if self._death_matches_any_pattern(death, active_pattern_keys):
            score += 10

        # No ward = preventable death
        if not death.get("had_ward_nearby"):
            score += 5

        # Early deaths are good learning opportunities
        if death.get("game_phase") == "early":
            score += 3

        # Deaths while ahead indicate decision issues
        if death.get("gold_diff", 0) > 500:
            score += 4

        # Solo kills = clear 1v1 mistake
        if death.get("death_type") == "solo_kill":
            score += 2

        # Ganks without vision = preventable
        if death.get("death_type") == "gank" and not death.get("had_ward_nearby"):
            score += 3

        return score

    def _death_matches_any_pattern(
        self,
        death: dict,
        pattern_keys: list[str]
    ) -> bool:
        """Check if a death matches any active pattern."""
        zone = death.get("map_zone", "")

        if PatternKey.RIVER_DEATH_NO_WARD.value in pattern_keys:
            if zone.startswith("river") and not death.get("had_ward_nearby"):
                return True

        if PatternKey.DIES_WHEN_AHEAD.value in pattern_keys:
            if death.get("gold_diff", 0) > 500:
                return True

        if PatternKey.EARLY_DEATH_REPEAT.value in pattern_keys:
            if death.get("game_phase") == "early":
                return True

        if PatternKey.CAUGHT_SIDELANE.value in pattern_keys:
            if zone in ("top_lane", "bot_lane") and death.get("game_phase") != "early":
                return True

        return False

    def _find_matching_pattern(
        self,
        death: dict,
        patterns: list[dict]
    ) -> Optional[dict]:
        """Find the pattern that best matches this death."""
        zone = death.get("map_zone", "")

        for pattern in patterns:
            key = pattern.get("pattern_key")

            if key == PatternKey.RIVER_DEATH_NO_WARD.value:
                if zone.startswith("river") and not death.get("had_ward_nearby"):
                    return pattern

            if key == PatternKey.DIES_WHEN_AHEAD.value:
                if death.get("gold_diff", 0) > 500:
                    return pattern

            if key == PatternKey.EARLY_DEATH_REPEAT.value:
                if death.get("game_phase") == "early":
                    return pattern

            if key == PatternKey.CAUGHT_SIDELANE.value:
                if zone in ("top_lane", "bot_lane") and death.get("game_phase") != "early":
                    return pattern

        return None

    def _generate_socratic_question(
        self,
        death: dict,
        pattern: Optional[dict]
    ) -> str:
        """Generate a Socratic question for this death."""
        if pattern:
            pattern_key = pattern.get("pattern_key")
            questions = PATTERN_QUESTIONS.get(pattern_key, DEFAULT_QUESTIONS)
            return questions[0]  # Use first question for now

        # Generate based on death context
        if not death.get("had_ward_nearby"):
            return "What parts of the map were dark when this happened?"

        if death.get("gold_diff", 0) > 500:
            return "You were ahead - what made you take this risk?"

        if death.get("death_type") == "gank":
            return "Where was the enemy jungler before this happened?"

        return DEFAULT_QUESTIONS[0]

    def _generate_things_to_notice(self, death: dict) -> list[str]:
        """Generate list of things player should look for in VOD."""
        notices = []

        if not death.get("had_ward_nearby"):
            notices.append("Check minimap - did you have vision of their jungler?")

        if death.get("gold_diff", 0) > 500:
            notices.append("You were ahead - what made you take this fight?")

        zone = death.get("map_zone", "")
        if zone.startswith("river"):
            notices.append("Look at wave state - was your wave pushing or crashing?")

        if death.get("death_type") == "gank":
            notices.append("Count enemy champions visible on map 10 seconds before")

        if death.get("death_type") == "solo_kill":
            notices.append("Check both health bars and cooldowns before the fight")

        if not notices:
            notices.append("Watch for the moment you committed to this position")

        return notices

    def _generate_death_context(self, death: dict) -> str:
        """Generate human-readable context for the death."""
        killer = death.get("killer_champion", "Unknown")
        zone = death.get("map_zone", "unknown").replace("_", " ")
        phase = death.get("game_phase", "unknown")

        context = f"You died to {killer} in {zone} during {phase} game"

        if death.get("gold_diff", 0) > 500:
            context += " (while ahead)"

        if not death.get("had_ward_nearby"):
            context += " (no ward nearby)"

        return context

    def _death_to_review_moment(
        self,
        death: dict,
        moment_id: int,
        pattern: Optional[dict],
        question: str
    ) -> ReviewMoment:
        """Convert a death dict to a ReviewMoment."""
        timestamp_ms = death.get("game_timestamp_ms", 0)
        timestamp_sec = timestamp_ms // 1000
        minutes = timestamp_sec // 60
        seconds = timestamp_sec % 60

        return ReviewMoment(
            moment_id=moment_id,
            death_id=death["id"],
            match_id=death.get("match_id", "unknown"),
            timestamp_seconds=timestamp_sec,
            timestamp_formatted=f"{minutes}:{seconds:02d}",
            context=self._generate_death_context(death),
            map_zone=death.get("map_zone", "unknown"),
            had_ward=death.get("had_ward_nearby", False),
            gold_diff=death.get("gold_diff", 0),
            player_champion=death.get("player_champion", "Unknown"),
            killer_champion=death.get("killer_champion", "Unknown"),
            pattern_key=pattern.get("pattern_key") if pattern else None,
            pattern_description=pattern.get("description") if pattern else None,
            things_to_notice=self._generate_things_to_notice(death),
            socratic_question=question,
        )

    def _moment_to_review_moment(
        self,
        moment: dict,
        patterns: list[dict]
    ) -> ReviewMoment:
        """Convert a VOD moment from DB to ReviewMoment."""
        timestamp_ms = moment.get("game_timestamp_ms", 0)
        timestamp_sec = timestamp_ms // 1000
        minutes = timestamp_sec // 60
        seconds = timestamp_sec % 60

        # Find pattern if exists
        pattern = None
        if moment.get("pattern_key"):
            pattern = next(
                (p for p in patterns if p.get("pattern_key") == moment.get("pattern_key")),
                None
            )

        death_dict = {
            "id": moment.get("death_id"),
            "map_zone": moment.get("map_zone"),
            "had_ward_nearby": moment.get("had_ward_nearby"),
            "gold_diff": moment.get("gold_diff"),
            "player_champion": moment.get("player_champion"),
            "killer_champion": moment.get("killer_champion"),
            "game_phase": "unknown",  # Not stored in join query
        }

        return ReviewMoment(
            moment_id=moment["id"],
            death_id=moment.get("death_id"),
            match_id=moment.get("match_id", "unknown"),
            timestamp_seconds=timestamp_sec,
            timestamp_formatted=f"{minutes}:{seconds:02d}",
            context=self._generate_death_context(death_dict),
            map_zone=moment.get("map_zone", "unknown"),
            had_ward=moment.get("had_ward_nearby", False),
            gold_diff=moment.get("gold_diff", 0),
            player_champion=moment.get("player_champion", "Unknown"),
            killer_champion=moment.get("killer_champion", "Unknown"),
            pattern_key=moment.get("pattern_key"),
            pattern_description=moment.get("pattern_description"),
            things_to_notice=self._generate_things_to_notice(death_dict),
            socratic_question=moment.get("coach_question") or DEFAULT_QUESTIONS[0],
        )

    async def start_review(
        self,
        player_id: int,
        moment: ReviewMoment
    ) -> dict[str, Any]:
        """
        Start a VOD review session for a specific moment.

        Returns context for the user to review.
        """
        await self._init_repos()

        # Mark as started
        await self._moment_repo.start_review(moment.moment_id)

        return {
            "moment_id": moment.moment_id,
            "timestamp": moment.timestamp_formatted,
            "context": moment.context,
            "things_to_notice": moment.things_to_notice,
            "initial_question": moment.socratic_question,
            "instruction": (
                f"Go to {moment.timestamp_formatted} in your replay and watch what happens. "
                f"{moment.socratic_question}"
            ),
        }

    async def record_player_response(
        self,
        moment_id: int,
        response: str
    ) -> str:
        """
        Record player's response and generate follow-up.

        Args:
            moment_id: ID of the VOD moment
            response: What the player said

        Returns:
            Next question or insight from coach
        """
        await self._init_repos()

        # Get moment details
        moment = await self._moment_repo.get_by_id(moment_id)
        if not moment:
            return "I couldn't find that review moment. Let's start fresh."

        # Store response
        await self._moment_repo.record_player_response(
            moment_id=moment_id,
            response=response,
            analysis=None  # Will be filled in by follow-up
        )

        # Generate Socratic follow-up via Claude
        follow_up = await self._generate_follow_up_question(
            response,
            moment.get("coach_question", ""),
            moment.get("map_zone", ""),
            moment.get("killer_champion", "")
        )

        return follow_up

    async def _generate_follow_up_question(
        self,
        player_response: str,
        original_question: str,
        map_zone: str,
        killer_champion: str
    ) -> str:
        """Use Claude to generate a Socratic follow-up question."""
        prompt = f"""You are a League of Legends coach having a Socratic coaching conversation.

The player just watched a replay of their death (they died to {killer_champion} in {map_zone.replace('_', ' ')}).

You asked: "{original_question}"

They responded: "{player_response}"

Generate ONE follow-up question that:
1. Acknowledges what they said
2. Pushes them to think deeper about the root cause
3. Helps them discover the lesson themselves (don't tell them the answer)
4. Stays focused on what THEY could control

Keep it SHORT (1-2 sentences). Be warm but focused.
Don't lecture. Don't give advice. Just ask a question."""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception as e:
            logger.exception(f"Error generating follow-up: {e}")
            return "What do you think you could have done differently in that moment?"

    async def check_for_breakthrough(
        self,
        moment_id: int,
        player_statement: str
    ) -> dict[str, Any]:
        """
        Check if the player had a coaching breakthrough.

        A breakthrough is when they articulate the core lesson themselves.

        Returns:
            {
                'breakthrough': bool,
                'insight': str or None,
                'celebration': str or None
            }
        """
        await self._init_repos()

        prompt = f"""You are evaluating if a League player had a coaching "breakthrough" -
a moment where they understood the root cause of their mistake.

Player statement: "{player_statement}"

A breakthrough is when they:
1. Identify a SPECIFIC, ACTIONABLE insight (not just "I should have warded")
2. Connect the mistake to a broader principle they can apply
3. Show they understand WHY, not just WHAT went wrong

Respond in JSON format:
{{
    "is_breakthrough": true or false,
    "insight_quality": "none" or "partial" or "full",
    "core_insight": "What they realized (or null if no breakthrough)",
    "celebration": "Short encouraging message if breakthrough (or null)"
}}

Be strict - only mark as breakthrough if they show real understanding."""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            # Parse JSON response
            import json
            result_text = response.content[0].text.strip()

            # Handle potential markdown code blocks
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()

            result = json.loads(result_text)

            # Record breakthrough if detected
            if result.get("is_breakthrough"):
                await self._moment_repo.record_breakthrough(
                    moment_id=moment_id,
                    insight=result.get("core_insight", "")
                )
            else:
                # Mark review as complete even without breakthrough
                await self._moment_repo.complete_review(moment_id)

            return {
                "breakthrough": result.get("is_breakthrough", False),
                "insight": result.get("core_insight"),
                "celebration": result.get("celebration"),
            }

        except Exception as e:
            logger.exception(f"Error checking breakthrough: {e}")
            return {
                "breakthrough": False,
                "insight": None,
                "celebration": None,
            }

    async def complete_review(self, moment_id: int) -> None:
        """Mark a review as complete without breakthrough."""
        await self._init_repos()
        await self._moment_repo.complete_review(moment_id)

    async def get_review_stats(self, player_id: int) -> dict[str, int]:
        """Get VOD review statistics for a player."""
        await self._init_repos()

        breakthroughs = await self._moment_repo.count_breakthroughs(player_id)

        return {
            "breakthroughs": breakthroughs,
        }
