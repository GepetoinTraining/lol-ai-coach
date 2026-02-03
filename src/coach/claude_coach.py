"""
Claude AI Coach Client

Handles AI-powered coaching conversations and analysis using Anthropic's Claude API.
"""

import os
import json
from typing import Optional
from dataclasses import dataclass

import anthropic

from .knowledge import get_knowledge_context


SYSTEM_PROMPT = """You are an expert League of Legends coach with deep knowledge of:
- Laning fundamentals (wave management, trading, CSing)
- Macro play (rotations, objectives, map awareness)
- Champion-specific strategies
- Mental game and tilt management

Your role is to analyze player match data and provide personalized coaching.

## Your Coaching Style

1. **Be specific, not generic** - Reference exact games, timestamps, and situations
2. **Prioritize ruthlessly** - Focus on the top 2-3 issues, don't overwhelm
3. **Be encouraging but honest** - Celebrate improvements, but don't sugarcoat problems
4. **Give actionable advice** - Every issue should come with a concrete drill or focus area
5. **Adapt to rank** - Iron players need different advice than Diamond players

## Response Structure

When analyzing matches:
1. Start with a quick summary of what you noticed
2. Identify the MOST IMPORTANT issue to fix (not everything)
3. Give a specific example from their recent games
4. Provide a concrete exercise or focus area
5. End with an encouraging note or offer to dive deeper

## Rank-Appropriate Benchmarks

| Metric | Iron-Bronze | Silver-Gold | Platinum+ |
|--------|-------------|-------------|-----------|
| CS/min | 4-5 | 6-7 | 8+ |
| Vision Score/min | 0.5 | 0.8 | 1.0+ |
| Deaths pre-10 | 2+ is bad | 1+ is bad | Any is bad |

## Remember

- You're talking to a real person who wants to improve
- Gaming is supposed to be fun - keep the tone positive
- Small improvements compound over time
- Everyone has bad games - look for PATTERNS, not single instances"""


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


class CoachingClient:
    """
    AI Coaching client using Claude
    
    Usage:
        coach = CoachingClient()
        analysis = await coach.analyze_matches(summaries, player_info)
        response = await coach.chat(analysis, "How can I improve my CSing?")
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = "claude-sonnet-4-20250514"
    
    def analyze_matches(
        self,
        matches: list[MatchSummary],
        player_name: str,
        rank: Optional[str] = None,
        intent: Optional["PlayerIntent"] = None
    ) -> str:
        """
        Generate coaching analysis from match data
        
        Args:
            matches: List of MatchSummary objects
            player_name: Player's display name
            rank: Player's rank (e.g., "Gold II")
            intent: Optional PlayerIntent specifying what the player wants help with
        
        Returns:
            Coaching analysis as string
        """
        # Prepare match data for the prompt
        match_data = [m.to_dict() for m in matches]
        
        # Calculate aggregate stats
        total_games = len(matches)
        wins = sum(1 for m in matches if m.win)
        avg_cs_per_min = sum(m.cs_per_min for m in matches) / total_games if total_games > 0 else 0
        avg_vision = sum(m.vision_score for m in matches) / total_games if total_games > 0 else 0
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
Focus on:
1. The #1 thing they should work on
2. A specific example from their matches
3. A concrete exercise or drill
"""
            # Load general knowledge
            knowledge_context = get_knowledge_context("general", max_words=1000)
            if knowledge_context:
                knowledge_context = f"""
## Coaching Knowledge Base
{knowledge_context}
"""
        
        # Generate analysis
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"""Analyze this player's recent matches and provide coaching feedback.

{context}
{knowledge_context}
{intent_prompt}
Keep it conversational and encouraging."""
                }
            ]
        )
        
        return response.content[0].text
    
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
        """
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
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=messages
        )
        
        return response.content[0].text
    
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
        """
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

        response = self.client.messages.create(
            model=self.model,
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text


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
    
    console.print("\n[bold]🎮 LoL AI Coach - Test Run[/bold]\n")
    
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


if __name__ == "__main__":
    main()
