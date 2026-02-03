# LoL AI Coach - Coaching Module
from .claude_coach import CoachingClient, MatchSummary, extract_match_summary
from .intents import CoachingIntent, PlayerIntent, prompt_for_intent, INTENT_DESCRIPTIONS
from .knowledge import get_knowledge_context, load_for_intent, list_available_knowledge
