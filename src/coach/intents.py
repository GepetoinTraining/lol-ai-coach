"""
Player Intent System

Allows players to specify what they want coaching help with,
enabling focused and personalized coaching experiences.
"""

from dataclasses import dataclass
from typing import Optional
from enum import Enum


class CoachingIntent(Enum):
    """Available coaching focus areas"""
    
    LANING = "laning"
    MACRO = "macro"
    TEAMFIGHTING = "teamfighting"
    DYING_LESS = "dying_less"
    CLIMBING = "climbing"
    CHAMPION_SPECIFIC = "champion_specific"
    MENTAL = "mental"
    GENERAL = "general"


# Human-readable descriptions for each intent
INTENT_DESCRIPTIONS = {
    CoachingIntent.LANING: "Improve lane phase (CS, trading, wave management)",
    CoachingIntent.MACRO: "Improve macro decisions (rotations, objectives, map awareness)",
    CoachingIntent.TEAMFIGHTING: "Improve teamfighting (positioning, target selection, cooldown tracking)",
    CoachingIntent.DYING_LESS: "Reduce deaths and improve survivability",
    CoachingIntent.CLIMBING: "Focus on what's holding you back from climbing",
    CoachingIntent.CHAMPION_SPECIFIC: "Master a specific champion",
    CoachingIntent.MENTAL: "Improve mental game and reduce tilt",
    CoachingIntent.GENERAL: "Complete analysis covering all areas",
}


# Specific analysis focus for each intent
INTENT_ANALYSIS_FOCUS = {
    CoachingIntent.LANING: {
        "metrics": ["cs_at_10", "cs_at_15", "cs_diff_10", "deaths_pre_10", "xp_diff_10", "first_blood"],
        "timeline_events": ["kills", "deaths", "ward_placed", "item_purchased"],
        "phase_focus": "0-14 min (laning phase)",
        "key_patterns": [
            "CS consistency across games",
            "Early death timing and causes",
            "Trading patterns (damage dealt vs taken in lane)",
            "Recall timing",
            "Wave state before deaths"
        ]
    },
    CoachingIntent.MACRO: {
        "metrics": ["objective_participation", "roam_timing", "vision_score", "cs_mid_game"],
        "timeline_events": ["tower_kill", "dragon_kill", "baron_kill", "rift_herald"],
        "phase_focus": "14-35 min (mid to late game)",
        "key_patterns": [
            "Objective participation rate",
            "Rotation timing after lane phase",
            "Vision placement around objectives",
            "Death locations (lane vs jungle vs objective)",
            "CS maintenance during mid-game"
        ]
    },
    CoachingIntent.TEAMFIGHTING: {
        "metrics": ["damage_dealt", "damage_taken", "teamfight_deaths", "kp"],
        "timeline_events": ["champion_kill", "assist"],
        "phase_focus": "Major teamfights (typically 15+ min)",
        "key_patterns": [
            "Damage dealt vs damage taken ratio",
            "Death timing in teamfights (early focus vs cleanup)",
            "Positioning relative to carries",
            "Kill participation",
            "Ability usage patterns"
        ]
    },
    CoachingIntent.DYING_LESS: {
        "metrics": ["deaths", "deaths_per_game", "death_timing", "solo_deaths"],
        "timeline_events": ["death"],
        "phase_focus": "All phases - death analysis",
        "key_patterns": [
            "Death timing (before 10 min, mid-game, late)",
            "Solo deaths vs teamfight deaths",
            "Death locations on map",
            "Vision state before deaths",
            "Item state before deaths (did they recall before dying?)"
        ]
    },
    CoachingIntent.CLIMBING: {
        "metrics": ["win_rate", "kda", "cs_min", "vision_score", "damage_dealt"],
        "timeline_events": ["all"],
        "phase_focus": "What's most impactful for rank",
        "key_patterns": [
            "Win rate by champion",
            "Biggest weakness across all games",
            "Consistency issues",
            "Throw patterns (ahead early, lose late)",
            "Quick wins they can implement"
        ]
    },
    CoachingIntent.CHAMPION_SPECIFIC: {
        "metrics": ["all"],
        "timeline_events": ["all"],
        "phase_focus": "Champion-specific patterns",
        "key_patterns": [
            "Win rate on champion",
            "Matchup performance",
            "Power spike timing",
            "Combo execution (from damage patterns)",
            "Build path optimization"
        ]
    },
    CoachingIntent.MENTAL: {
        "metrics": ["loss_streaks", "tilt_indicators", "performance_after_loss"],
        "timeline_events": ["death", "chat_restricted"],
        "phase_focus": "Pattern across sessions",
        "key_patterns": [
            "Performance degradation in losing streaks",
            "Death patterns after falling behind",
            "Recovery rate after early deaths",
            "Session length and performance correlation",
            "Revenge queue patterns"
        ]
    },
    CoachingIntent.GENERAL: {
        "metrics": ["all"],
        "timeline_events": ["all"],
        "phase_focus": "All phases",
        "key_patterns": [
            "Top 3 weaknesses",
            "Top 3 strengths",
            "Immediate improvement opportunities",
            "Long-term development areas"
        ]
    }
}


@dataclass
class PlayerIntent:
    """Represents a player's coaching request with their specific intent"""
    
    intent: CoachingIntent
    champion_focus: Optional[str] = None  # For CHAMPION_SPECIFIC intent
    additional_context: Optional[str] = None  # Freeform player input
    
    @property
    def description(self) -> str:
        """Human-readable description of this intent"""
        base = INTENT_DESCRIPTIONS.get(self.intent, "General coaching")
        if self.intent == CoachingIntent.CHAMPION_SPECIFIC and self.champion_focus:
            return f"Master {self.champion_focus}"
        return base
    
    @property
    def analysis_focus(self) -> dict:
        """Get the analysis focus configuration for this intent"""
        return INTENT_ANALYSIS_FOCUS.get(self.intent, INTENT_ANALYSIS_FOCUS[CoachingIntent.GENERAL])
    
    def to_prompt_context(self) -> str:
        """Generate prompt context for the AI coach based on this intent"""
        focus = self.analysis_focus
        
        context = f"""
## Player's Coaching Goal
The player wants help with: **{self.description}**

## Analysis Focus
Focus your analysis on: {focus['phase_focus']}

Key patterns to look for:
{chr(10).join(f'- {pattern}' for pattern in focus['key_patterns'])}

Priority metrics: {', '.join(focus['metrics'][:5])}
"""
        
        if self.additional_context:
            context += f"""
## Additional Context from Player
"{self.additional_context}"
"""
        
        if self.champion_focus:
            context += f"""
## Champion Focus
Analyze performance specifically on: {self.champion_focus}
"""
        
        return context


def get_intent_menu() -> str:
    """Generate a menu of available intents for CLI display"""
    lines = ["What would you like coaching on?\n"]
    
    for i, intent in enumerate(CoachingIntent, 1):
        desc = INTENT_DESCRIPTIONS.get(intent, "")
        lines.append(f"  {i}. {intent.value:20s} - {desc}")
    
    return "\n".join(lines)


def parse_intent_choice(choice: str) -> Optional[CoachingIntent]:
    """Parse user input into a CoachingIntent"""
    choice = choice.strip().lower()
    
    # Try by number
    try:
        idx = int(choice) - 1
        intents = list(CoachingIntent)
        if 0 <= idx < len(intents):
            return intents[idx]
    except ValueError:
        pass
    
    # Try by name
    for intent in CoachingIntent:
        if intent.value == choice or intent.name.lower() == choice:
            return intent
    
    return None


# ==================== CLI Integration ====================

def prompt_for_intent() -> PlayerIntent:
    """Interactive CLI prompt for getting player's intent"""
    from rich.console import Console
    from rich.prompt import Prompt
    
    console = Console()
    
    console.print("\n[bold cyan]🎯 What would you like coaching on?[/bold cyan]\n")
    
    for i, intent in enumerate(CoachingIntent, 1):
        desc = INTENT_DESCRIPTIONS.get(intent, "")
        console.print(f"  [bold]{i}.[/bold] [yellow]{intent.value:18s}[/yellow] - {desc}")
    
    console.print()
    choice = Prompt.ask(
        "[bold]Choose an option[/bold]",
        default="8",
        choices=[str(i) for i in range(1, len(CoachingIntent) + 1)] + [i.value for i in CoachingIntent]
    )
    
    intent = parse_intent_choice(choice)
    
    if intent is None:
        console.print("[yellow]Defaulting to general analysis[/yellow]")
        intent = CoachingIntent.GENERAL
    
    # If champion-specific, ask for champion
    champion_focus = None
    if intent == CoachingIntent.CHAMPION_SPECIFIC:
        champion_focus = Prompt.ask("[bold]Which champion?[/bold]")
    
    # Optional: additional context
    additional = Prompt.ask(
        "[bold]Any additional context?[/bold] (press Enter to skip)",
        default=""
    )
    
    return PlayerIntent(
        intent=intent,
        champion_focus=champion_focus,
        additional_context=additional if additional else None
    )


if __name__ == "__main__":
    # Test the intent system
    intent = prompt_for_intent()
    print("\n" + "="*50)
    print(f"Selected intent: {intent.intent.value}")
    print(f"Description: {intent.description}")
    print("\nPrompt context for AI:")
    print(intent.to_prompt_context())
