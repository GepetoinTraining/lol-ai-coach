"""
Mission Tracker for LoL AI Coach

Handles:
- Mission generation based on coaching analysis
- Pattern-linked mission generation
- Mission state tracking per user (with database persistence)
- Screenshot analysis for mission verification
- Progress tracking and tips
"""

import base64
from typing import Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import anthropic

from ..logging_config import get_logger
from ..config import get_config
from ..db import get_database
from ..db.repositories import MissionRepository, PatternRepository, PlayerRepository
from ..analysis.pattern_detector import PatternKey, DeathContext

if TYPE_CHECKING:
    from .bot import CoachBot

logger = get_logger(__name__)


# Pattern-specific mission templates
PATTERN_MISSION_TEMPLATES = {
    PatternKey.RIVER_DEATH_NO_WARD.value: {
        "name": "The Ward Guardian",
        "description": (
            "Your mission: Place a ward in river before making ANY aggressive play. "
            "If you don't see a ward, you don't fight. River is where junglers live - "
            "respect their territory."
        ),
        "success_criteria": "Zero deaths in river zones this game",
        "tips": [
            "Count to 3 after placing ward - if no one shows, THEN you can play aggressive",
            "If you don't know where their jungler is, assume they're in the closest bush",
        ],
        "focus_area": "vision",
    },
    PatternKey.DIES_WHEN_AHEAD.value: {
        "name": "The Patient Hunter",
        "description": (
            "You're winning lane, but then throwing leads. Your mission: When you're ahead, "
            "play SAFER, not more aggressive. Being ahead means you can farm safely - "
            "let THEM make mistakes coming to you."
        ),
        "success_criteria": "Don't die while ahead in gold (500+ lead)",
        "tips": [
            "Being ahead means they HAVE to fight you, so just farm",
            "A 500 gold lead grows to 1000 gold if you just don't die",
        ],
        "focus_area": "trading",
    },
    PatternKey.EARLY_DEATH_REPEAT.value: {
        "name": "The Slow Starter",
        "description": (
            "You're dying too early in games. Your mission: Survive the first 10 minutes. "
            "Early deaths snowball - the jungler you fed will come back for more. "
            "Play like a coward until you hit your power spike."
        ),
        "success_criteria": "Zero deaths before 10:00",
        "tips": [
            "If you don't have vision, you don't have permission to push",
            "Play like their jungler started on your side",
        ],
        "focus_area": "laning",
    },
    PatternKey.CAUGHT_SIDELANE.value: {
        "name": "The Map Reader",
        "description": (
            "You're getting caught while sidelaning. Your mission: Before pushing past river, "
            "count the enemies on the map. If you can't see 3+ enemies, you can't push. "
            "The wave isn't worth your life."
        ),
        "success_criteria": "Don't die while alone in a sidelane",
        "tips": [
            "Before pushing, ask: 'Where are the 3 enemies I can't see?'",
            "Deep wards save lives - ward their jungle, not yours",
        ],
        "focus_area": "macro",
    },
    PatternKey.TOWER_DIVE_FAIL.value: {
        "name": "The Tower Respecter",
        "description": (
            "Tower dives are killing you. Your mission: Don't dive unless you KNOW "
            "they can't survive the burst. Calculate tower shots. Watch their summoners. "
            "A failed dive is worse than no dive."
        ),
        "success_criteria": "Zero deaths under enemy tower",
        "tips": [
            "Count tower shots: Level 1-7 towers hurt, 8+ you can tank one",
            "Never dive if their CC is up",
        ],
        "focus_area": "trading",
    },
    PatternKey.OVEREXTEND_NO_VISION.value: {
        "name": "The Vision Hunter",
        "description": (
            "You're dying in the dark. Your mission: Ward before you walk. "
            "Every time you want to push forward, place a ward first. "
            "If you can't ward it, you can't walk there."
        ),
        "success_criteria": "Don't die in unwarded territory",
        "tips": [
            "Rule of thumb: 1 ward = 1 minute of safe play",
            "Control wards are an investment, not an expense",
        ],
        "focus_area": "vision",
    },
}


class MissionStatus(Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Mission:
    """A single coaching mission"""
    id: str
    description: str
    focus_area: str
    success_criteria: str
    tips: list[str]
    status: MissionStatus = MissionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    screenshot_analyses: list[dict] = field(default_factory=list)


@dataclass
class UserSession:
    """Coaching session for a user"""
    user_id: int
    analysis: str  # Initial coaching analysis
    focus: str  # What they want to work on
    missions: list[Mission] = field(default_factory=list)
    current_mission_idx: int = 0
    conversation_history: list[dict] = field(default_factory=list)

    @property
    def current_mission(self) -> Optional[Mission]:
        if 0 <= self.current_mission_idx < len(self.missions):
            return self.missions[self.current_mission_idx]
        return None


class MissionTracker:
    """
    Tracks missions and analyzes screenshots for mission verification.

    Uses Claude for:
    - Generating contextual missions
    - Analyzing screenshots to check progress
    - Providing tips based on game state

    Now supports:
    - Database persistence for missions
    - Pattern-linked mission generation
    - Mission verification against match data
    """

    def __init__(self, bot: "CoachBot"):
        self.bot = bot
        self.config = get_config()
        self.sessions: dict[int, UserSession] = {}  # In-memory cache

        # Initialize Claude client
        self.claude = anthropic.Anthropic()

        # Database repositories (initialized lazily)
        self._db = None
        self._mission_repo: Optional[MissionRepository] = None
        self._pattern_repo: Optional[PatternRepository] = None
        self._player_repo: Optional[PlayerRepository] = None

        logger.info("MissionTracker initialized")

    async def _init_repos(self):
        """Lazily initialize database repositories."""
        if self._db is None:
            self._db = await get_database()
            self._mission_repo = MissionRepository(self._db)
            self._pattern_repo = PatternRepository(self._db)
            self._player_repo = PlayerRepository(self._db)

    def get_session(self, user_id: int) -> Optional[UserSession]:
        """Get user's coaching session"""
        return self.sessions.get(user_id)

    def get_current_mission(self, user_id: int) -> Optional[dict]:
        """Get user's current mission as dict"""
        session = self.sessions.get(user_id)
        if session and session.current_mission:
            mission = session.current_mission
            return {
                "description": mission.description,
                "focus_area": mission.focus_area,
                "success_criteria": mission.success_criteria,
                "tips": mission.tips,
                "status": mission.status.value,
            }
        return None

    async def generate_mission(
        self,
        analysis: str,
        focus: str,
        user_id: int = 0
    ) -> str:
        """Generate a mission based on coaching analysis"""

        prompt = f"""You are an expert League of Legends coach with a creative, engaging personality.
Based on this player's analysis, create a FUN and MEMORABLE mission for them.

PLAYER ANALYSIS:
{analysis}

FOCUS AREA: {focus}

Your mission should:
- Feel like a real coach giving a challenge, not a robot
- Be specific to THEIR weaknesses (reference the analysis!)
- Be achievable in one game but still challenging
- Have a catchy name or theme if it fits
- Include why this matters for their improvement

You have creative freedom! Some ideas:
- "The Survivor" - Don't die before 10 minutes
- "Vision King" - Place 10 wards before 15 min
- "CS Machine" - Hit 7 CS/min this game
- "The Patient One" - Only fight when your jungler is nearby
- Or invent your own based on their specific issues!

Format:
🎯 **[Creative Mission Name]**
[2-3 sentences describing the mission and WHY it helps them]

✅ **Success:** [How they know they did it]

💡 **Pro tip:** [One actionable tip to help them succeed]

Keep the energy positive and coaching-focused. Make them WANT to do this!
"""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,  # More tokens for creative responses
                messages=[{"role": "user", "content": prompt}]
            )

            mission_text = response.content[0].text

            # Parse the creative response - more flexible parsing
            mission_desc = mission_text  # Keep the full creative text
            success_criteria = ""
            tips = []

            # Try to extract success criteria and tips if formatted
            lines = mission_text.split("\n")
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if "success" in line_lower and ":" in line:
                    # Get the part after the colon
                    success_criteria = line.split(":", 1)[-1].strip().strip("*")
                elif "tip" in line_lower and ":" in line:
                    tips.append(line.split(":", 1)[-1].strip().strip("*"))
                elif "pro tip" in line_lower and ":" in line:
                    tips.append(line.split(":", 1)[-1].strip().strip("*"))

            # Create mission object
            mission = Mission(
                id=f"mission_{user_id}_{datetime.now().timestamp()}",
                description=mission_text,  # Store the full creative response
                focus_area=focus,
                success_criteria=success_criteria or "Complete the mission objective",
                tips=tips or ["You got this!"],
            )

            # Create or update session
            if user_id not in self.sessions:
                self.sessions[user_id] = UserSession(
                    user_id=user_id,
                    analysis=analysis,
                    focus=focus,
                )

            self.sessions[user_id].missions.append(mission)
            self.sessions[user_id].current_mission_idx = len(self.sessions[user_id].missions) - 1

            # Log just the first line for brevity
            first_line = mission_text.split("\n")[0][:50]
            logger.info(f"Generated mission for user {user_id}: {first_line}...")

            return mission_text  # Return full creative response

        except Exception as e:
            logger.exception(f"Error generating mission: {e}")
            return "🎯 **The Survivor**\nYour mission: Don't die before 10 minutes. Show them you can play safe!\n\n✅ **Success:** Zero deaths before the 10:00 mark\n\n💡 **Pro tip:** If you don't have vision of the enemy jungler, play like they're in your bush!"

    async def generate_new_mission(self, user_id: int) -> str:
        """Generate a new mission for an existing session"""
        session = self.sessions.get(user_id)

        if not session:
            return "No active session. Start one with `/coach`!"

        # Mark current mission as skipped if not completed
        if session.current_mission and session.current_mission.status == MissionStatus.ACTIVE:
            session.current_mission.status = MissionStatus.SKIPPED
            # Record skipped mission in memory
            if self.bot.memory:
                self.bot.memory.record_mission(user_id, completed=False)

        # Generate new mission
        return await self.generate_mission(session.analysis, session.focus, user_id)

    async def complete_mission(self, user_id: int) -> dict:
        """Mark current mission as complete and generate next"""
        session = self.sessions.get(user_id)

        if not session or not session.current_mission:
            return {
                "success": False,
                "message": "No active mission to complete!"
            }

        # Mark as complete
        session.current_mission.status = MissionStatus.COMPLETED
        session.current_mission.completed_at = datetime.now()

        # Record completion in memory
        if self.bot.memory:
            self.bot.memory.record_mission(user_id, completed=True)
            self.bot.memory.add_coaching_note(
                user_id,
                f"Completed mission: {session.current_mission.description[:50]}..."
            )

        # Generate next mission
        next_mission = await self.generate_mission(
            session.analysis,
            session.focus,
            user_id
        )

        return {
            "success": True,
            "message": "Great job! Keep up the good work!",
            "next_mission": next_mission
        }

    async def analyze_screenshot(
        self,
        user_id: int,
        image_data: bytes
    ) -> dict:
        """Analyze a screenshot to check mission progress"""
        session = self.sessions.get(user_id)

        if not session:
            return {
                "analysis": "No active coaching session. Use `/coach` to start one!",
                "progress": False,
            }

        mission = session.current_mission
        mission_context = ""
        if mission:
            mission_context = f"""
CURRENT MISSION: {mission.description}
SUCCESS CRITERIA: {mission.success_criteria}
"""

        # Encode image for Claude Vision
        image_base64 = base64.b64encode(image_data).decode("utf-8")

        prompt = f"""Analyze this League of Legends screenshot.
{mission_context}

Provide:
1. GAME STATE: What's happening in the game (score, time, player position)
2. MISSION PROGRESS: Are they making progress on their mission? (Yes/No/Can't tell)
3. SPECIFIC FEEDBACK: One specific thing they're doing well or could improve
4. QUICK TIP: One actionable tip based on what you see

Keep responses SHORT - this goes in a game overlay!
"""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_base64,
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            analysis_text = response.content[0].text

            # Store analysis
            if mission:
                mission.screenshot_analyses.append({
                    "timestamp": datetime.now().isoformat(),
                    "analysis": analysis_text,
                })

            # Parse progress
            progress = "yes" in analysis_text.lower() and "progress" in analysis_text.lower()

            # Extract mission status
            mission_status = None
            if mission:
                if progress:
                    mission_status = "✅ Making progress!"
                else:
                    mission_status = f"📋 Keep working on: {mission.description}"

            # Extract tips
            tips = None
            if "TIP:" in analysis_text.upper():
                for line in analysis_text.split("\n"):
                    if "TIP:" in line.upper():
                        tips = line.split(":", 1)[-1].strip()
                        break

            return {
                "analysis": analysis_text,
                "progress": progress,
                "mission_status": mission_status,
                "tips": tips,
            }

        except Exception as e:
            logger.exception(f"Error analyzing screenshot: {e}")
            return {
                "analysis": f"Couldn't analyze screenshot: {e}",
                "progress": False,
            }

    async def get_contextual_tip(self, user_id: int, context: str) -> str:
        """Get a contextual coaching tip"""
        session = self.sessions.get(user_id)

        base_context = ""
        if session:
            base_context = f"""
Player is working on: {session.focus}
Current mission: {session.current_mission.description if session.current_mission else 'None'}
"""

        prompt = f"""Give a quick, actionable League of Legends coaching tip.
{base_context}
Player said: "{context}"

Respond with ONE short tip (1-2 sentences max). Be specific and practical.
"""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception as e:
            logger.exception(f"Error getting tip: {e}")
            return "Focus on farming safely and watch your minimap!"

    async def ask_coach(self, user_id: int, question: str) -> str:
        """Handle a general coaching question"""
        session = self.sessions.get(user_id)

        context = ""
        if session:
            context = f"""
PLAYER CONTEXT:
- Focus area: {session.focus}
- Current mission: {session.current_mission.description if session.current_mission else 'None'}

PREVIOUS ANALYSIS:
{session.analysis[:500]}...
"""
            # Add to conversation history
            session.conversation_history.append({
                "role": "user",
                "content": question
            })

        prompt = f"""You are a League of Legends coach. Answer this question concisely.
{context}

QUESTION: {question}

Keep your response SHORT (2-3 sentences) - this is shown in a game overlay.
Be specific and actionable.
"""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            answer = response.content[0].text.strip()

            if session:
                session.conversation_history.append({
                    "role": "assistant",
                    "content": answer
                })

            return answer

        except Exception as e:
            logger.exception(f"Error answering question: {e}")
            return "Sorry, I couldn't process that. Try asking again!"

    # ============================================================
    # Pattern-Linked Missions
    # ============================================================

    async def generate_mission_from_pattern(
        self,
        pattern: dict[str, Any],
        player_id: int,
        discord_id: int
    ) -> str:
        """
        Generate a mission specifically targeting a detected pattern.

        Uses predefined templates for known patterns with personalization.

        Args:
            pattern: Pattern dict from database
            player_id: Database player ID
            discord_id: Discord user ID for session tracking

        Returns:
            Mission description text
        """
        await self._init_repos()

        pattern_key = pattern.get("pattern_key")
        template = PATTERN_MISSION_TEMPLATES.get(pattern_key)

        if template:
            # Use template-based mission
            mission_text = self._format_pattern_mission(template, pattern)
            success_criteria = template["success_criteria"]
            tips = template["tips"]
            focus_area = template["focus_area"]
        else:
            # Generate custom mission via Claude for unknown patterns
            mission_text = await self._generate_custom_pattern_mission(pattern)
            success_criteria = "Complete the mission objective"
            tips = ["Focus on breaking this habit"]
            focus_area = pattern.get("pattern_category", "general")

        # Store in database
        mission_id = await self._mission_repo.create({
            "player_id": player_id,
            "pattern_id": pattern.get("id"),
            "description": mission_text,
            "focus_area": focus_area,
            "success_criteria": success_criteria,
            "tips": tips,
        })

        # Also update in-memory session
        mission = Mission(
            id=str(mission_id),
            description=mission_text,
            focus_area=focus_area,
            success_criteria=success_criteria,
            tips=tips,
        )

        if discord_id not in self.sessions:
            self.sessions[discord_id] = UserSession(
                user_id=discord_id,
                analysis="",
                focus=focus_area,
            )

        self.sessions[discord_id].missions.append(mission)
        self.sessions[discord_id].current_mission_idx = len(self.sessions[discord_id].missions) - 1

        logger.info(
            f"Generated pattern mission for player {player_id}: "
            f"{pattern_key} -> {template['name'] if template else 'custom'}"
        )

        return mission_text

    def _format_pattern_mission(
        self,
        template: dict[str, Any],
        pattern: dict[str, Any]
    ) -> str:
        """Format a pattern mission template with personalization."""
        occurrences = pattern.get("occurrences", 0)
        status = pattern.get("status", "active")

        # Build the mission text
        mission_text = f"🎯 **{template['name']}**\n\n"
        mission_text += template["description"]

        # Add pattern context
        if occurrences > 3:
            mission_text += f"\n\n📊 *This has happened {occurrences} times in your recent games.*"

        if status == "improving":
            mission_text += "\n\n✨ *You've been improving on this - keep it up!*"

        mission_text += f"\n\n✅ **Success:** {template['success_criteria']}"
        mission_text += f"\n\n💡 **Pro tip:** {template['tips'][0]}"

        return mission_text

    async def _generate_custom_pattern_mission(self, pattern: dict[str, Any]) -> str:
        """Generate a custom mission for patterns without templates."""
        pattern_key = pattern.get("pattern_key", "unknown")
        description = pattern.get("description", "a recurring issue")
        occurrences = pattern.get("occurrences", 0)

        prompt = f"""You are a League of Legends coach creating a mission to break a bad habit.

PATTERN: {pattern_key}
DESCRIPTION: {description}
OCCURRENCES: {occurrences} times in recent games

Create a FUN, MEMORABLE mission that:
1. Directly addresses this pattern
2. Is achievable in one game
3. Has a catchy name
4. Explains WHY this matters

Format:
🎯 **[Mission Name]**
[2-3 sentences describing the mission]

✅ **Success:** [Clear success criteria]

💡 **Pro tip:** [One actionable tip]
"""

        try:
            response = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text

        except Exception as e:
            logger.exception(f"Error generating custom pattern mission: {e}")
            return (
                f"🎯 **Break the Habit**\n\n"
                f"Focus on avoiding: {description}\n\n"
                f"✅ **Success:** Don't trigger this pattern this game\n\n"
                f"💡 **Pro tip:** Awareness is the first step to change!"
            )

    async def check_mission_against_match(
        self,
        mission_id: int,
        match_deaths: list[DeathContext]
    ) -> dict[str, Any]:
        """
        Check if a pattern-linked mission was completed in a match.

        Args:
            mission_id: Database ID of the mission
            match_deaths: Deaths from the match to evaluate

        Returns:
            {
                'completed': bool,
                'notes': str,
                'progress': str
            }
        """
        await self._init_repos()

        mission = await self._mission_repo.get_by_id(mission_id)
        if not mission:
            return {
                "completed": False,
                "notes": "Mission not found",
                "progress": "Unknown"
            }

        pattern_id = mission.get("pattern_id")
        if not pattern_id:
            # Not a pattern-linked mission, can't auto-check
            return {
                "completed": False,
                "notes": "Manual verification required",
                "progress": "Check your game stats"
            }

        pattern = await self._pattern_repo.get_by_key(
            mission.get("player_id"),
            ""  # Need to get by ID instead
        )

        # For now, look up pattern from mission
        # Check if pattern was triggered in this match
        pattern_triggered = self._check_pattern_in_deaths(
            mission.get("pattern_id"),
            match_deaths
        )

        if pattern_triggered:
            return {
                "completed": False,
                "notes": "Pattern was triggered in this game",
                "progress": "Keep trying! You'll break this habit."
            }
        else:
            # Mission completed!
            await self._mission_repo.complete(
                mission_id,
                notes="Pattern not triggered - mission success!"
            )
            return {
                "completed": True,
                "notes": "Pattern NOT triggered - great job!",
                "progress": "Mission complete! The pattern didn't show up this game."
            }

    def _check_pattern_in_deaths(
        self,
        pattern_id: int,
        deaths: list[DeathContext]
    ) -> bool:
        """Check if a pattern was triggered in the given deaths."""
        # This is a simplified check - in reality we'd look up the pattern
        # and check against specific criteria
        # For now, any death could trigger the pattern
        return len(deaths) > 0

    async def get_active_mission_from_db(self, discord_id: int) -> Optional[dict[str, Any]]:
        """Get active mission from database."""
        await self._init_repos()

        player = await self._player_repo.get_by_discord_id(discord_id)
        if not player:
            return None

        return await self._mission_repo.get_active(player["id"])

    async def get_mission_stats(self, discord_id: int) -> dict[str, int]:
        """Get mission statistics for a player."""
        await self._init_repos()

        player = await self._player_repo.get_by_discord_id(discord_id)
        if not player:
            return {"completed": 0, "total": 0}

        completed = await self._mission_repo.count_completed(player["id"])
        history = await self._mission_repo.get_history(player["id"])

        return {
            "completed": completed,
            "total": len(history),
        }
