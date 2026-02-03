"""
Mission Tracker for LoL AI Coach

Handles:
- Mission generation based on coaching analysis
- Mission state tracking per user
- Screenshot analysis for mission verification
- Progress tracking and tips
"""

import base64
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import anthropic

from ..logging_config import get_logger
from ..config import get_config

if TYPE_CHECKING:
    from .bot import CoachBot

logger = get_logger(__name__)


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
    """

    def __init__(self, bot: "CoachBot"):
        self.bot = bot
        self.config = get_config()
        self.sessions: dict[int, UserSession] = {}

        # Initialize Claude client
        self.claude = anthropic.Anthropic()

        logger.info("MissionTracker initialized")

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
