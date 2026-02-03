"""
Discord Bot for LoL AI Coach

Voice-enabled coaching through Discord with:
- Local Whisper STT for voice input
- Mission-based coaching displayed via Discord overlay
- Screenshot analysis for mission verification
- Persistent player memory (rank, goals, progress)
"""

from .bot import CoachBot
from .voice import VoiceHandler
from .missions import MissionTracker
from .memory import PlayerMemory, PlayerProfile

__all__ = ["CoachBot", "VoiceHandler", "MissionTracker", "PlayerMemory", "PlayerProfile"]
