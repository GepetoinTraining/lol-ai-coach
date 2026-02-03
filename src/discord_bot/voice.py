"""
Voice Handler for Discord Bot

Handles:
- Voice channel connection
- Audio capture from Discord
- Local Whisper transcription
- Voice command routing
"""

import os
import io
import asyncio
import tempfile
import wave
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass
from collections import defaultdict

import discord

from ..logging_config import get_logger

if TYPE_CHECKING:
    from .bot import CoachBot

logger = get_logger(__name__)

# Lazy load whisper to avoid import errors if not installed
whisper = None


def get_whisper():
    """Lazy load whisper model"""
    global whisper
    if whisper is None:
        try:
            import whisper as whisper_module
            whisper = whisper_module
        except ImportError:
            raise ImportError(
                "openai-whisper not installed. "
                "Install with: pip install openai-whisper"
            )
    return whisper


@dataclass
class VoiceSettings:
    """Voice processing settings"""
    model_name: str = "base"  # tiny, base, small, medium, large
    language: str = "en"
    silence_threshold: float = 0.01
    min_audio_length: float = 0.5  # seconds
    max_audio_length: float = 30.0  # seconds
    sample_rate: int = 48000  # Discord uses 48kHz


class AudioBuffer:
    """Buffer for collecting audio data from a user"""

    def __init__(self, user_id: int, sample_rate: int = 48000):
        self.user_id = user_id
        self.sample_rate = sample_rate
        self.frames: list[bytes] = []
        self.is_speaking = False
        self.silence_frames = 0
        self.max_silence_frames = int(sample_rate * 0.8 / 960)  # 0.8 seconds of silence

    def add_frame(self, data: bytes):
        """Add an audio frame to the buffer"""
        self.frames.append(data)

    def clear(self):
        """Clear the buffer"""
        self.frames.clear()
        self.silence_frames = 0

    def get_audio_data(self) -> bytes:
        """Get all audio data as bytes"""
        return b"".join(self.frames)

    def duration(self) -> float:
        """Get duration of buffered audio in seconds"""
        total_bytes = sum(len(f) for f in self.frames)
        # 16-bit stereo = 4 bytes per sample
        return total_bytes / (self.sample_rate * 4)


class VoiceSink(discord.sinks.Sink):
    """Custom sink to capture audio from voice channel"""

    def __init__(self, voice_handler: "VoiceHandler"):
        super().__init__()
        self.voice_handler = voice_handler
        self.buffers: dict[int, AudioBuffer] = defaultdict(
            lambda: AudioBuffer(0, VoiceSettings().sample_rate)
        )

    def write(self, data: bytes, user: int):
        """Called when audio data is received from a user"""
        if user not in self.buffers:
            self.buffers[user] = AudioBuffer(user)

        buffer = self.buffers[user]
        buffer.add_frame(data)

        # Check if we have enough audio to process
        if buffer.duration() >= VoiceSettings().max_audio_length:
            # Process what we have
            asyncio.create_task(
                self.voice_handler.process_audio(user, buffer.get_audio_data())
            )
            buffer.clear()

    def cleanup(self):
        """Called when recording stops"""
        self.buffers.clear()


class VoiceHandler:
    """
    Handles voice input from Discord

    Uses local Whisper model for speech-to-text transcription.
    """

    def __init__(self, bot: "CoachBot"):
        self.bot = bot
        self.settings = VoiceSettings()
        self.settings.model_name = os.getenv("WHISPER_MODEL", "base")

        self.voice_client: Optional[discord.VoiceClient] = None
        self.whisper_model = None
        self.is_listening = False
        self.sink: Optional[VoiceSink] = None

        # Track recent transcriptions to avoid duplicates
        self._recent_transcriptions: dict[int, str] = {}

        logger.info(f"VoiceHandler initialized with Whisper model: {self.settings.model_name}")

    def _load_whisper_model(self):
        """Load the Whisper model (lazy loading)"""
        if self.whisper_model is None:
            logger.info(f"Loading Whisper model: {self.settings.model_name}")
            whisper_module = get_whisper()
            self.whisper_model = whisper_module.load_model(self.settings.model_name)
            logger.info("Whisper model loaded successfully")

    async def join_channel(self, channel: discord.VoiceChannel):
        """Join a voice channel"""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect()

        logger.info(f"Joined voice channel: {channel.name}")

    async def disconnect(self):
        """Disconnect from voice channel"""
        if self.voice_client:
            await self.stop_listening()
            await self.voice_client.disconnect()
            self.voice_client = None
            logger.info("Disconnected from voice channel")

    def is_connected(self) -> bool:
        """Check if connected to a voice channel"""
        return self.voice_client is not None and self.voice_client.is_connected()

    async def start_listening(self):
        """Start listening for voice input"""
        if not self.is_connected():
            raise RuntimeError("Not connected to a voice channel")

        # Load Whisper model in background
        await asyncio.get_event_loop().run_in_executor(
            None, self._load_whisper_model
        )

        self.is_listening = True
        self.sink = VoiceSink(self)

        # Start recording
        self.voice_client.start_recording(
            self.sink,
            self._on_recording_finished,
            self.bot.coaching_channel
        )

        logger.info("Started listening for voice input")

    async def stop_listening(self):
        """Stop listening for voice input"""
        self.is_listening = False

        if self.voice_client and self.voice_client.recording:
            self.voice_client.stop_recording()

        if self.sink:
            self.sink.cleanup()
            self.sink = None

        logger.info("Stopped listening for voice input")

    async def _on_recording_finished(self, sink: VoiceSink, channel: discord.TextChannel):
        """Called when recording is stopped"""
        # Process any remaining audio
        for user_id, buffer in sink.buffers.items():
            if buffer.duration() >= self.settings.min_audio_length:
                await self.process_audio(user_id, buffer.get_audio_data())

    async def process_audio(self, user_id: int, audio_data: bytes):
        """Process audio data and transcribe it"""
        if not audio_data or len(audio_data) < 1000:
            return

        try:
            # Transcribe in executor to not block
            transcription = await asyncio.get_event_loop().run_in_executor(
                None,
                self._transcribe_audio,
                audio_data
            )

            if transcription and transcription.strip():
                # Check if this is a duplicate
                if self._recent_transcriptions.get(user_id) == transcription:
                    return

                self._recent_transcriptions[user_id] = transcription

                logger.info(f"Transcription from user {user_id}: {transcription}")

                # Handle the voice command
                await self._handle_voice_command(user_id, transcription)

        except Exception as e:
            logger.exception(f"Error processing audio: {e}")

    def _transcribe_audio(self, audio_data: bytes) -> str:
        """Transcribe audio using Whisper"""
        if not self.whisper_model:
            self._load_whisper_model()

        # Save audio to temp file (Whisper needs a file)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name

            # Write WAV header and data
            with wave.open(f, "wb") as wav:
                wav.setnchannels(2)  # Stereo
                wav.setsampwidth(2)  # 16-bit
                wav.setframerate(self.settings.sample_rate)
                wav.writeframes(audio_data)

        try:
            # Transcribe
            result = self.whisper_model.transcribe(
                temp_path,
                language=self.settings.language,
                fp16=False  # Disable FP16 for CPU
            )
            return result["text"].strip()
        finally:
            # Clean up temp file
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    async def _handle_voice_command(self, user_id: int, text: str):
        """Handle a transcribed voice command"""
        if not self.bot.coaching_channel:
            return

        text_lower = text.lower()

        # Get user
        user = self.bot.get_user(user_id)
        user_name = user.display_name if user else f"User {user_id}"

        # Log what we heard
        await self.bot.coaching_channel.send(
            f"🎤 **{user_name}**: {text}"
        )

        # Route to appropriate handler
        if any(word in text_lower for word in ["mission", "task", "objective"]):
            if any(word in text_lower for word in ["check", "status", "progress", "how"]):
                # Check mission progress
                await self._command_check_mission(user_id)
            elif any(word in text_lower for word in ["new", "next", "another"]):
                # Get new mission
                await self._command_new_mission(user_id)
            elif any(word in text_lower for word in ["complete", "done", "finished"]):
                # Mark mission complete
                await self._command_complete_mission(user_id)
            else:
                # Show current mission
                await self._command_show_mission(user_id)

        elif any(word in text_lower for word in ["help", "what can"]):
            await self._command_help()

        elif any(word in text_lower for word in ["tip", "advice", "suggest"]):
            await self._command_get_tip(user_id, text)

        else:
            # General question - pass to coach
            await self._command_ask_coach(user_id, text)

    async def _command_show_mission(self, user_id: int):
        """Show current mission"""
        if self.bot.mission_tracker:
            mission = self.bot.mission_tracker.get_current_mission(user_id)
            if mission:
                embed = discord.Embed(
                    title="📋 Current Mission",
                    description=mission["description"],
                    color=discord.Color.gold()
                )
                await self.bot.coaching_channel.send(embed=embed)
            else:
                await self.bot.coaching_channel.send(
                    "No active mission. Start a session with `/coach`!"
                )

    async def _command_check_mission(self, user_id: int):
        """Check mission progress"""
        await self.bot.coaching_channel.send(
            "📸 Upload a screenshot of your game and I'll check your progress!"
        )

    async def _command_new_mission(self, user_id: int):
        """Get a new mission"""
        if self.bot.mission_tracker:
            mission = await self.bot.mission_tracker.generate_new_mission(user_id)
            embed = discord.Embed(
                title="📋 New Mission",
                description=mission,
                color=discord.Color.blue()
            )
            await self.bot.coaching_channel.send(embed=embed)

    async def _command_complete_mission(self, user_id: int):
        """Mark mission as complete"""
        if self.bot.mission_tracker:
            result = await self.bot.mission_tracker.complete_mission(user_id)
            if result["success"]:
                embed = discord.Embed(
                    title="✅ Mission Complete!",
                    description=result["message"],
                    color=discord.Color.green()
                )
                if result.get("next_mission"):
                    embed.add_field(
                        name="📋 Next Mission",
                        value=result["next_mission"]
                    )
                await self.bot.coaching_channel.send(embed=embed)
            else:
                await self.bot.coaching_channel.send(f"❌ {result['message']}")

    async def _command_help(self):
        """Show help message"""
        embed = discord.Embed(
            title="🎤 Voice Commands",
            description="Here's what you can say:",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Mission Commands",
            value=(
                "• \"What's my mission?\"\n"
                "• \"Check my progress\"\n"
                "• \"Give me a new mission\"\n"
                "• \"Mission complete\""
            ),
            inline=False
        )
        embed.add_field(
            name="Coaching",
            value=(
                "• \"How's my CS?\"\n"
                "• \"Give me a tip\"\n"
                "• \"What should I focus on?\"\n"
                "• Any question about your gameplay!"
            ),
            inline=False
        )
        await self.bot.coaching_channel.send(embed=embed)

    async def _command_get_tip(self, user_id: int, context: str):
        """Get a coaching tip"""
        if self.bot.mission_tracker:
            tip = await self.bot.mission_tracker.get_contextual_tip(user_id, context)
            embed = discord.Embed(
                title="💡 Coaching Tip",
                description=tip,
                color=discord.Color.green()
            )
            await self.bot.coaching_channel.send(embed=embed)

    async def _command_ask_coach(self, user_id: int, question: str):
        """Pass a question to the coach"""
        if self.bot.mission_tracker:
            response = await self.bot.mission_tracker.ask_coach(user_id, question)
            embed = discord.Embed(
                title="🎓 Coach",
                description=response,
                color=discord.Color.blue()
            )
            await self.bot.coaching_channel.send(embed=embed)
