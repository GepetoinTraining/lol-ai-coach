"""
Claude AI Coach Client

Handles AI-powered coaching conversations and analysis using Anthropic's Claude API.
"""

import os
import json
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass

import anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .knowledge import get_knowledge_context
from ..logging_config import get_logger
from ..exceptions import ClaudeAPIError

if TYPE_CHECKING:
    from .intents import PlayerIntent

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are an expert League of Legends coach using the Socratic method.

Your role is NOT just to analyze - the data already shows the patterns.
Your role is to ASK QUESTIONS that help players discover WHY.

## Your Coaching Philosophy

1. **Ask questions, don't lecture** - Help players discover insights themselves
2. **"What were you thinking when..." not "You should have..."** - Guide reflection
3. **Acknowledge progress** - Celebrate improvements, no matter how small
4. **One pattern at a time** - Focus on the highest priority issue, not everything
5. **Connect to broader principles** - Help them see the "why" behind mistakes

## Socratic Style Examples

Instead of: "You need to ward more before fighting in river"
Ask: "What information did you have about the enemy jungler before this fight?"

Instead of: "You're dying too much when ahead"
Ask: "When you're winning lane, what changes about how your opponent should play?"

Instead of: "Your CS needs improvement"
Ask: "What do you think was stopping you from getting to the minions?"

## Response Structure

When analyzing matches:
1. Start with genuine, specific praise for what they're doing well
2. Identify ONE pattern to focus on (their priority pattern if provided)
3. Ask a Socratic question about it - don't tell them the answer
4. If they have context from previous sessions, reference their progress

When they respond:
1. Acknowledge their thinking
2. Ask a follow-up that goes deeper
3. If they're close to the insight, guide them there
4. If they discover it themselves, CELEBRATE

## Response Format

Keep responses SHORT (2-3 sentences for questions).
Use specific examples from their matches when asking questions.
Never say "you should" - instead ask "what do you think would happen if..."

## Rank-Appropriate Style

Iron-Silver: More direct questions, simpler concepts
Gold-Platinum: Deeper strategic questions about decision-making
Diamond+: Nuanced, assumption-challenging questions

## Remember

- You're talking to a real person who wants to improve
- Gaming is supposed to be fun - keep the energy positive
- The goal is THEIR insight, not your analysis
- Small "aha" moments are worth more than detailed breakdowns
- If they have a breakthrough, celebrate it genuinely"""


@dataclass
class MatchSummary:
    """Simplified match data for coaching analysis"""
    champion: str
    role: str
    win: bool
    kills: int
    deaths: int
    assists: int
    cs: int
    cs_per_min: float
    vision_score: int
    damage_dealt: int
    game_duration_min: int
    death_times: list[int]  # Timestamps of deaths in seconds

    def to_dict(self) -> dict:
        return {
            "champion": self.champion,
            "role": self.role,
            "win": self.win,
            "kda": f"{self.kills}/{self.deaths}/{self.assists}",
            "cs": self.cs,
            "cs_per_min": round(self.cs_per_min, 1),
            "vision_score": self.vision_score,
            "damage_dealt": self.damage_dealt,
            "game_duration_min": self.game_duration_min,
            "early_deaths": len([t for t in self.death_times if t < 600]),  # Deaths before 10 min
        }


def extract_match_summary(match_data: dict, puuid: str) -> MatchSummary:
    """Extract relevant coaching data from a match"""
    info = match_data["info"]

    # Find this player
    participant = None
    participant_id = None
    for i, p in enumerate(info["participants"]):
        if p["puuid"] == puuid:
            participant = p
            participant_id = p["participantId"]
            break

    if not participant:
        raise ValueError("Player not found in match")

    # Get death times from timeline if available
    death_times = []
    if "timeline" in match_data:
        for frame in match_data["timeline"]["info"]["frames"]:
            for event in frame.get("events", []):
                if event.get("type") == "CHAMPION_KILL" and event.get("victimId") == participant_id:
                    death_times.append(event["timestamp"] // 1000)  # Convert to seconds

    game_duration = info["gameDuration"]
    total_cs = participant["totalMinionsKilled"] + participant.get("neutralMinionsKilled", 0)

    return MatchSummary(
        champion=participant["championName"],
        role=participant.get("teamPosition", "UNKNOWN"),
        win=participant["win"],
        kills=participant["kills"],
        deaths=participant["deaths"],
        assists=participant["assists"],
        cs=total_cs,
        cs_per_min=total_cs / (game_duration / 60) if game_duration > 0 else 0,
        vision_score=participant["visionScore"],
        damage_dealt=participant["totalDamageDealtToChampions"],
        game_duration_min=game_duration // 60,
        death_times=death_times
    )


def _should_retry_claude_error(exception: BaseException) -> bool:
    """Determine if we should retry based on exception type"""
    if isinstance(exception, anthropic.RateLimitError):
        return True
    if isinstance(exception, anthropic.APIConnectionError):
        return True
    if isinstance(exception, anthropic.APIStatusError):
        # Retry on server errors and overloaded
        return exception.status_code in (500, 502, 503, 529)
    return False


class CoachingClient:
    """
    AI Coaching client using Claude

    Usage:
        coach = CoachingClient()
        analysis = coach.analyze_matches(summaries, player_info)
        response = coach.chat(analysis, "How can I improve my CSing?")
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")

        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

        logger.info(f"CoachingClient initialized with model: {self.model}")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
        )),
        reraise=True,
    )
    def _call_claude(
        self,
        messages: list[dict],
        max_tokens: int,
        operation: str = "api_call"
    ) -> str:
        """
        Make a Claude API call with retry logic and error handling.

        Args:
            messages: Message list for the API
            max_tokens: Maximum tokens in response
            operation: Name of the operation for logging

        Returns:
            Response text from Claude

        Raises:
            ClaudeAPIError: On API failures after retries exhausted
        """
        logger.debug(
            f"Calling Claude API for {operation}",
            extra={"model": self.model, "max_tokens": max_tokens, "message_count": len(messages)}
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=SYSTEM_PROMPT,
                messages=messages
            )

            logger.info(
                f"Claude API {operation} completed",
                extra={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "operation": operation,
                }
            )

            return response.content[0].text

        except anthropic.AuthenticationError as e:
            logger.error(f"Claude API authentication failed: {e}")
            raise ClaudeAPIError.authentication_failed()

        except anthropic.RateLimitError as e:
            logger.warning(f"Claude API rate limited: {e}")
            raise ClaudeAPIError.rate_limited()

        except anthropic.BadRequestError as e:
            logger.error(f"Claude API bad request: {e}")
            error_str = str(e).lower()
            if "context" in error_str or "token" in error_str:
                raise ClaudeAPIError.context_too_long()
            raise ClaudeAPIError.invalid_request(str(e))

        except anthropic.APIStatusError as e:
            logger.error(f"Claude API status error: {e.status_code} - {e}")
            if e.status_code == 529:
                raise ClaudeAPIError.overloaded()
            raise ClaudeAPIError(
                f"Claude API error (HTTP {e.status_code})",
                status_code=e.status_code
            )

        except anthropic.APIConnectionError as e:
            logger.error(f"Claude API connection failed: {e}")
            raise ClaudeAPIError.connection_failed()

        except anthropic.APITimeoutError as e:
            logger.error(f"Claude API timeout: {e}")
            raise ClaudeAPIError.timeout()

        except Exception as e:
            logger.exception(f"Unexpected error in Claude API call: {e}")
            raise ClaudeAPIError(f"Unexpected error: {str(e)}")

    def analyze_matches(
        self,
        matches: list[MatchSummary],
        player_name: str,
        rank: Optional[str] = None,
        intent: Optional["PlayerIntent"] = None,
        coaching_context: Optional[dict] = None
    ) -> str:
        """
        Generate coaching analysis from match data

        Args:
            matches: List of MatchSummary objects
            player_name: Player's display name
            rank: Player's rank (e.g., "Gold II")
            intent: Optional PlayerIntent specifying what the player wants help with
            coaching_context: Optional dict with active_patterns, session_opener, etc.

        Returns:
            Coaching analysis as string

        Raises:
            ClaudeAPIError: On API failures
        """
        logger.info(
            f"Starting match analysis",
            extra={
                "player_name": player_name[:10] + "...",
                "rank": rank,
                "match_count": len(matches),
                "intent": intent.intent.value if intent else None,
                "has_coaching_context": coaching_context is not None,
            }
        )

        # Prepare match data for the prompt
        match_data = [m.to_dict() for m in matches]

        # Calculate aggregate stats
        total_games = len(matches)
        if total_games == 0:
            logger.warning("No matches to analyze")
            return "I don't see any match data to analyze. Let's try fetching your recent games again!"

        wins = sum(1 for m in matches if m.win)
        avg_cs_per_min = sum(m.cs_per_min for m in matches) / total_games
        avg_vision = sum(m.vision_score for m in matches) / total_games
        total_early_deaths = sum(len([t for t in m.death_times if t < 600]) for m in matches)

        # Build context
        context = f"""
## Player Information
- Summoner: {player_name}
- Rank: {rank or "Unknown"}
- Matches Analyzed: {total_games}
- Win Rate: {wins}/{total_games} ({100*wins/total_games:.0f}%)

## Aggregate Stats
- Average CS/min: {avg_cs_per_min:.1f}
- Average Vision Score: {avg_vision:.1f}
- Total Early Deaths (pre-10min): {total_early_deaths} across {total_games} games

## Match Details
{json.dumps(match_data, indent=2)}
"""

        # Add pattern context if available
        pattern_context = ""
        session_opener = ""

        if coaching_context:
            active_patterns = coaching_context.get("active_patterns", [])
            if active_patterns:
                # Focus on the priority pattern
                priority_pattern = active_patterns[0]
                pattern_context = f"""
## Player's Active Pattern (FOCUS ON THIS)
The data shows a recurring pattern: {priority_pattern.get('description', 'Unknown pattern')}
- Pattern: {priority_pattern.get('pattern_key', 'unknown')}
- Status: {priority_pattern.get('status', 'active')}
- Occurrences: {priority_pattern.get('occurrences', 0)}
- Games since last: {priority_pattern.get('games_since_last', 0)}

Your job is to ask Socratic questions about THIS pattern.
Don't tell them what's wrong - ask questions that help them discover it.
If they're improving (status=improving), acknowledge the progress!
"""

            # Add session opener instruction
            opener = coaching_context.get("session_opener", "")
            if opener:
                session_opener = f"""
## Session Opener
Start your response with this personalized opener:
"{opener}"

Then transition into your coaching questions.
"""

        # Add intent context if specified
        intent_prompt = ""
        knowledge_context = ""

        if intent:
            intent_prompt = f"""
{intent.to_prompt_context()}

Focus your analysis specifically on what the player asked for help with.
"""
            # Load relevant knowledge for this intent
            knowledge_context = get_knowledge_context(intent.intent.value, max_words=1500)
            if knowledge_context:
                knowledge_context = f"""
## Coaching Knowledge Base (Core Theory)
Use these principles to inform your recommendations:

{knowledge_context}
"""
        else:
            intent_prompt = """
Remember: Use the Socratic method!
1. Start with genuine praise for something specific they did well
2. Ask ONE question about their priority pattern (or biggest issue)
3. Wait for their insight - don't give the answer

Example response format:
"[Session opener if provided]

I noticed you're playing a lot of [champion] - your [specific positive thing] is solid!

Looking at your deaths, I have a question: [Socratic question about their pattern]"
"""
            # Load general knowledge
            knowledge_context = get_knowledge_context("general", max_words=1000)
            if knowledge_context:
                knowledge_context = f"""
## Coaching Knowledge Base
{knowledge_context}
"""

        # Generate analysis
        messages = [
            {
                "role": "user",
                "content": f"""Analyze this player's recent matches and provide coaching feedback.

{context}
{pattern_context}
{session_opener}
{knowledge_context}
{intent_prompt}

IMPORTANT: Use the Socratic method. Ask questions, don't lecture.
Keep it conversational and encouraging."""
            }
        ]

        return self._call_claude(messages, max_tokens=1500, operation="analyze_matches")

    def chat(
        self,
        player_context: str,
        user_message: str,
        conversation_history: Optional[list[dict]] = None
    ) -> str:
        """
        Continue a coaching conversation

        Args:
            player_context: The initial analysis context
            user_message: User's new message
            conversation_history: Previous messages in the conversation

        Returns:
            Coach's response

        Raises:
            ClaudeAPIError: On API failures
        """
        logger.debug(
            "Processing chat message",
            extra={"history_length": len(conversation_history) if conversation_history else 0}
        )

        messages = []

        # Add initial context
        messages.append({
            "role": "user",
            "content": f"Here's my match analysis:\n\n{player_context}"
        })
        messages.append({
            "role": "assistant",
            "content": "I've reviewed your matches. What would you like to focus on?"
        })

        # Add conversation history
        if conversation_history:
            messages.extend(conversation_history)

        # Add new message
        messages.append({
            "role": "user",
            "content": user_message
        })

        return self._call_claude(messages, max_tokens=1000, operation="chat")

    def generate_exercise(
        self,
        weakness: str,
        rank: str,
        main_champions: list[str]
    ) -> str:
        """
        Generate a specific practice exercise

        Args:
            weakness: The identified weakness to address
            rank: Player's rank
            main_champions: Champions they play most

        Returns:
            Detailed exercise description

        Raises:
            ClaudeAPIError: On API failures
        """
        logger.info(
            "Generating exercise",
            extra={"weakness": weakness[:50], "rank": rank, "champion_count": len(main_champions)}
        )

        prompt = f"""Create a specific practice exercise for a {rank} player who struggles with:

{weakness}

They mainly play: {', '.join(main_champions)}

The exercise should be:
1. Specific and measurable
2. Doable in 3-5 games
3. Have clear success criteria
4. Include what to focus on and what to ignore

Format:
## Exercise: [Name]
**Goal:** [What they'll improve]
**Duration:** [How many games/time]
**Instructions:** [Step by step]
**Success Metric:** [How to know it's working]
**Common Mistakes:** [What to watch out for]"""

        messages = [{"role": "user", "content": prompt}]

        return self._call_claude(messages, max_tokens=800, operation="generate_exercise")


# ==================== CLI for testing ====================

def main():
    """Test the coaching client with sample data"""
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()

    # Sample match data
    sample_matches = [
        MatchSummary(
            champion="Jinx",
            role="BOTTOM",
            win=False,
            kills=3,
            deaths=8,
            assists=5,
            cs=156,
            cs_per_min=5.2,
            vision_score=12,
            damage_dealt=15000,
            game_duration_min=30,
            death_times=[180, 420, 540, 720, 900, 1100, 1400, 1650]  # 3 early deaths
        ),
        MatchSummary(
            champion="Caitlyn",
            role="BOTTOM",
            win=True,
            kills=7,
            deaths=4,
            assists=8,
            cs=198,
            cs_per_min=6.6,
            vision_score=18,
            damage_dealt=22000,
            game_duration_min=30,
            death_times=[380, 850, 1200, 1500]  # 1 early death
        ),
        MatchSummary(
            champion="Jinx",
            role="BOTTOM",
            win=False,
            kills=2,
            deaths=9,
            assists=3,
            cs=134,
            cs_per_min=4.8,
            vision_score=8,
            damage_dealt=12000,
            game_duration_min=28,
            death_times=[210, 380, 520, 680, 850, 1000, 1200, 1400, 1600]  # 4 early deaths
        ),
    ]

    console.print("\n[bold]LoL AI Coach - Test Run[/bold]\n")

    try:
        coach = CoachingClient()

        # Generate analysis
        console.print("[yellow]Analyzing matches...[/yellow]\n")

        analysis = coach.analyze_matches(
            matches=sample_matches,
            player_name="TestPlayer",
            rank="Silver II"
        )

        console.print(Markdown(analysis))

        # Test follow-up
        console.print("\n[yellow]Testing follow-up question...[/yellow]\n")

        follow_up = coach.chat(
            player_context=analysis,
            user_message="Can you give me a specific drill to work on my early game deaths?"
        )

        console.print(Markdown(follow_up))

    except ClaudeAPIError as e:
        console.print(f"\n[red]Claude API Error: {e.message}[/red]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")


if __name__ == "__main__":
    main()
