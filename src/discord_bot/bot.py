"""
Discord Bot Core

Main bot class that handles:
- Slash commands for coaching
- Voice channel management
- Message routing to overlay
"""

import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..logging_config import get_logger
from ..config import get_config
from ..db import get_database, close_database
from ..db.repositories import PlayerRepository, PatternRepository
from .voice import VoiceHandler
from .missions import MissionTracker
from .memory import PlayerMemory

logger = get_logger(__name__)

# Rank choices for slash commands
RANK_CHOICES = [
    app_commands.Choice(name="Iron IV", value="Iron IV"),
    app_commands.Choice(name="Iron III", value="Iron III"),
    app_commands.Choice(name="Iron II", value="Iron II"),
    app_commands.Choice(name="Iron I", value="Iron I"),
    app_commands.Choice(name="Bronze IV", value="Bronze IV"),
    app_commands.Choice(name="Bronze III", value="Bronze III"),
    app_commands.Choice(name="Bronze II", value="Bronze II"),
    app_commands.Choice(name="Bronze I", value="Bronze I"),
    app_commands.Choice(name="Silver IV", value="Silver IV"),
    app_commands.Choice(name="Silver III", value="Silver III"),
    app_commands.Choice(name="Silver II", value="Silver II"),
    app_commands.Choice(name="Silver I", value="Silver I"),
    app_commands.Choice(name="Gold IV", value="Gold IV"),
    app_commands.Choice(name="Gold III", value="Gold III"),
    app_commands.Choice(name="Gold II", value="Gold II"),
    app_commands.Choice(name="Gold I", value="Gold I"),
    app_commands.Choice(name="Platinum IV", value="Platinum IV"),
    app_commands.Choice(name="Platinum III", value="Platinum III"),
    app_commands.Choice(name="Platinum II", value="Platinum II"),
    app_commands.Choice(name="Platinum I", value="Platinum I"),
    app_commands.Choice(name="Emerald IV", value="Emerald IV"),
    app_commands.Choice(name="Emerald III", value="Emerald III"),
    app_commands.Choice(name="Emerald II", value="Emerald II"),
    app_commands.Choice(name="Emerald I", value="Emerald I"),
    app_commands.Choice(name="Diamond+", value="Diamond IV"),
]


class CoachBot(commands.Bot):
    """
    LoL AI Coach Discord Bot

    Provides voice-based coaching through Discord with missions
    displayed via Discord's overlay feature.
    """

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True

        super().__init__(
            command_prefix="!",  # Fallback, we primarily use slash commands
            intents=intents,
        )

        self.config = get_config()
        self.voice_handler: Optional[VoiceHandler] = None
        self.mission_tracker: Optional[MissionTracker] = None
        self.memory: Optional[PlayerMemory] = None
        self.coaching_channel: Optional[discord.TextChannel] = None

    async def setup_hook(self):
        """Called when bot is starting up"""
        # Initialize components
        self.voice_handler = VoiceHandler(self)
        self.mission_tracker = MissionTracker(self)
        self.memory = PlayerMemory()

        # Register slash commands
        await self._register_commands()

        # Sync commands with Discord
        guild_id = os.getenv("DISCORD_GUILD_ID")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info(f"Synced commands to guild {guild_id}")
        else:
            await self.tree.sync()
            logger.info("Synced commands globally")

    async def _register_commands(self):
        """Register all slash commands"""

        @self.tree.command(name="coach", description="Start a coaching session")
        @app_commands.describe(
            riot_id="Your Riot ID (e.g., PlayerName#TAG)",
            platform="Your server region",
            focus="What you want to focus on"
        )
        @app_commands.choices(platform=[
            app_commands.Choice(name="Brazil", value="br1"),
            app_commands.Choice(name="North America", value="na1"),
            app_commands.Choice(name="EU West", value="euw1"),
            app_commands.Choice(name="EU Nordic & East", value="eun1"),
            app_commands.Choice(name="Korea", value="kr"),
            app_commands.Choice(name="Japan", value="jp1"),
            app_commands.Choice(name="Oceania", value="oc1"),
        ])
        @app_commands.choices(focus=[
            app_commands.Choice(name="Laning (CS, trading, wave management)", value="laning"),
            app_commands.Choice(name="Macro (rotations, objectives)", value="macro"),
            app_commands.Choice(name="Dying Less (positioning)", value="dying_less"),
            app_commands.Choice(name="Teamfighting", value="teamfighting"),
            app_commands.Choice(name="General Analysis", value="general"),
        ])
        async def coach_command(
            interaction: discord.Interaction,
            riot_id: str,
            platform: str = "br1",
            focus: str = "general"
        ):
            await self._handle_coach_command(interaction, riot_id, platform, focus)

        @self.tree.command(name="join", description="Join your voice channel for voice coaching")
        async def join_command(interaction: discord.Interaction):
            await self._handle_join_command(interaction)

        @self.tree.command(name="leave", description="Leave the voice channel")
        async def leave_command(interaction: discord.Interaction):
            await self._handle_leave_command(interaction)

        @self.tree.command(name="mission", description="Get your current mission")
        async def mission_command(interaction: discord.Interaction):
            await self._handle_mission_command(interaction)

        @self.tree.command(name="check", description="Check mission progress (takes a screenshot)")
        async def check_command(interaction: discord.Interaction):
            await self._handle_check_command(interaction)

        @self.tree.command(name="complete", description="Mark current mission as complete")
        async def complete_command(interaction: discord.Interaction):
            await self._handle_complete_command(interaction)

        @self.tree.command(name="setrank", description="Set your current rank")
        @app_commands.describe(rank="Your current rank")
        @app_commands.choices(rank=RANK_CHOICES)
        async def setrank_command(interaction: discord.Interaction, rank: str):
            await self._handle_setrank_command(interaction, rank)

        @self.tree.command(name="settarget", description="Set your target rank goal")
        @app_commands.describe(rank="The rank you want to reach")
        @app_commands.choices(rank=RANK_CHOICES)
        async def settarget_command(interaction: discord.Interaction, rank: str):
            await self._handle_settarget_command(interaction, rank)

        @self.tree.command(name="setgoal", description="Set your current coaching focus goal")
        @app_commands.describe(goal="What you want to focus on improving")
        async def setgoal_command(interaction: discord.Interaction, goal: str):
            await self._handle_setgoal_command(interaction, goal)

        @self.tree.command(name="profile", description="View your coaching profile")
        async def profile_command(interaction: discord.Interaction):
            await self._handle_profile_command(interaction)

        @self.tree.command(name="progress", description="View your progress and stats")
        async def progress_command(interaction: discord.Interaction):
            await self._handle_progress_command(interaction)

        @self.tree.command(name="review", description="Start a Socratic VOD review session")
        async def review_command(interaction: discord.Interaction):
            await self._handle_review_command(interaction)

        @self.tree.command(name="patterns", description="View your detected patterns")
        async def patterns_command(interaction: discord.Interaction):
            await self._handle_patterns_command(interaction)

    async def _handle_coach_command(
        self,
        interaction: discord.Interaction,
        riot_id: str,
        platform: str,
        focus: str
    ):
        """Handle /coach command - start a coaching session"""
        await interaction.response.defer(thinking=True)

        try:
            # Store the channel for overlay messages
            self.coaching_channel = interaction.channel

            # Import here to avoid circular imports
            from ..api.riot import RiotAPIClient
            from ..coach.claude_coach import CoachingClient, extract_match_summary
            from ..coach.intents import PlayerIntent, CoachingIntent

            # Fetch player data
            riot_client = RiotAPIClient()

            await interaction.followup.send(
                f"🔍 Looking up **{riot_id}** on **{platform}**..."
            )

            # Parse Riot ID
            if "#" not in riot_id:
                await interaction.followup.send(
                    "❌ Invalid Riot ID format. Use `Name#TAG` (e.g., `Player#BR1`)"
                )
                return

            game_name, tag_line = riot_id.rsplit("#", 1)

            # Get account and matches
            account = await riot_client.get_account_by_riot_id(game_name, tag_line, platform)
            matches = await riot_client.get_match_history(account["puuid"], platform, count=10)

            if not matches:
                await interaction.followup.send(
                    "❌ No recent matches found. Play some games first!"
                )
                return

            # Process matches
            summaries = []
            for match_id in matches[:10]:
                try:
                    match_data = await riot_client.get_match(match_id, platform)
                    summary = extract_match_summary(match_data, account["puuid"])
                    summaries.append(summary)
                except Exception as e:
                    logger.warning(f"Failed to process match {match_id}: {e}")

            if not summaries:
                await interaction.followup.send("❌ Couldn't process any matches.")
                return

            # Create intent
            intent = PlayerIntent(
                intent=CoachingIntent(focus),
                specific_champion=None,
                specific_question=None
            )

            # Get or create player profile
            profile = self.memory.get_or_create_profile(
                discord_id=interaction.user.id,
                discord_name=interaction.user.display_name,
                riot_id=riot_id,
                platform=platform
            )

            # Update focus goal
            self.memory.set_goal(interaction.user.id, focus, goal_type="current")

            # Get coaching analysis with player context
            coach = CoachingClient()

            # Include player memory context for personalized coaching
            player_context = self.memory.get_context_for_coach(interaction.user.id)

            analysis = coach.analyze_matches(
                matches=summaries,
                player_name=game_name,
                rank=profile.current_rank,
                intent=intent
            )

            # Generate first mission with user ID for tracking
            mission = await self.mission_tracker.generate_mission(
                analysis, focus, user_id=interaction.user.id
            )

            # Add coaching note
            self.memory.add_coaching_note(
                interaction.user.id,
                f"Started session focusing on {focus}. Analyzed {len(summaries)} matches."
            )

            # Send to channel (shows in overlay)
            embed = discord.Embed(
                title="🎮 Coaching Session Started",
                description=analysis[:1000] + "..." if len(analysis) > 1000 else analysis,
                color=discord.Color.blue()
            )

            # Add rank info
            embed.add_field(
                name="📊 Your Rank",
                value=f"**Current:** {profile.current_rank} → **Target:** {profile.target_rank}",
                inline=False
            )

            embed.add_field(
                name="📋 Your First Mission",
                value=mission[:1000] if len(mission) > 1000 else mission,
                inline=False
            )
            embed.set_footer(text="This message will appear in your Discord overlay! Use /profile to see your full stats.")

            await interaction.followup.send(embed=embed)

            logger.info(f"Started coaching session for {riot_id} (user {interaction.user.id})")

        except Exception as e:
            logger.exception(f"Error in coach command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    async def _handle_join_command(self, interaction: discord.Interaction):
        """Handle /join command - join voice channel"""
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ You need to be in a voice channel first!",
                ephemeral=True
            )
            return

        channel = interaction.user.voice.channel

        try:
            await self.voice_handler.join_channel(channel)
            self.coaching_channel = interaction.channel

            await interaction.response.send_message(
                f"🎤 Joined **{channel.name}**! I'm listening for voice commands.\n"
                f"Say things like:\n"
                f"• \"What should I focus on?\"\n"
                f"• \"Check my mission\"\n"
                f"• \"Give me a new mission\"\n"
                f"• \"How's my CS?\""
            )

            # Start listening
            await self.voice_handler.start_listening()

        except Exception as e:
            logger.exception(f"Error joining voice channel: {e}")
            await interaction.response.send_message(
                f"❌ Couldn't join voice channel: {e}",
                ephemeral=True
            )

    async def _handle_leave_command(self, interaction: discord.Interaction):
        """Handle /leave command - leave voice channel"""
        if self.voice_handler and self.voice_handler.is_connected():
            await self.voice_handler.disconnect()
            await interaction.response.send_message("👋 Left the voice channel!")
        else:
            await interaction.response.send_message(
                "❌ I'm not in a voice channel!",
                ephemeral=True
            )

    async def _handle_mission_command(self, interaction: discord.Interaction):
        """Handle /mission command - show current mission"""
        if not self.mission_tracker:
            await interaction.response.send_message(
                "❌ No active coaching session. Use `/coach` first!",
                ephemeral=True
            )
            return

        mission = self.mission_tracker.get_current_mission(interaction.user.id)

        if mission:
            embed = discord.Embed(
                title="📋 Current Mission",
                description=mission["description"],
                color=discord.Color.gold()
            )
            if mission.get("progress"):
                embed.add_field(name="Progress", value=mission["progress"])
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "No active mission. Start a session with `/coach`!",
                ephemeral=True
            )

    async def _handle_check_command(self, interaction: discord.Interaction):
        """Handle /check command - verify mission with screenshot"""
        await interaction.response.defer(thinking=True)

        await interaction.followup.send(
            "📸 To check your mission progress, please upload a screenshot of your game!\n"
            "I'll analyze it and let you know how you're doing."
        )

        # The actual screenshot analysis happens when user uploads an image
        # We'll handle that in on_message

    async def _handle_complete_command(self, interaction: discord.Interaction):
        """Handle /complete command - mark mission complete"""
        if not self.mission_tracker:
            await interaction.response.send_message(
                "❌ No active session!",
                ephemeral=True
            )
            return

        result = await self.mission_tracker.complete_mission(interaction.user.id)

        if result["success"]:
            embed = discord.Embed(
                title="✅ Mission Complete!",
                description=result["message"],
                color=discord.Color.green()
            )
            if result.get("next_mission"):
                embed.add_field(
                    name="📋 Next Mission",
                    value=result["next_mission"],
                    inline=False
                )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"❌ {result['message']}",
                ephemeral=True
            )

    async def on_ready(self):
        """Called when bot is ready"""
        logger.info(f"Bot is ready! Logged in as {self.user}")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

        # Set presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="your gameplay | /coach"
            )
        )

    async def on_message(self, message: discord.Message):
        """Handle incoming messages (for screenshot uploads)"""
        if message.author.bot:
            return

        # Check for screenshot attachments
        if message.attachments and self.mission_tracker:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith("image/"):
                    await self._analyze_screenshot(message, attachment)
                    return

        await self.process_commands(message)

    async def _analyze_screenshot(
        self,
        message: discord.Message,
        attachment: discord.Attachment
    ):
        """Analyze a screenshot for mission progress"""
        await message.add_reaction("🔍")

        try:
            # Download the image
            image_data = await attachment.read()

            # Analyze with vision
            result = await self.mission_tracker.analyze_screenshot(
                message.author.id,
                image_data
            )

            embed = discord.Embed(
                title="📊 Screenshot Analysis",
                description=result["analysis"],
                color=discord.Color.blue() if result["progress"] else discord.Color.orange()
            )

            if result.get("mission_status"):
                embed.add_field(
                    name="Mission Status",
                    value=result["mission_status"],
                    inline=False
                )

            if result.get("tips"):
                embed.add_field(
                    name="💡 Tips",
                    value=result["tips"],
                    inline=False
                )

            await message.reply(embed=embed)
            await message.remove_reaction("🔍", self.user)
            await message.add_reaction("✅")

        except Exception as e:
            logger.exception(f"Error analyzing screenshot: {e}")
            await message.remove_reaction("🔍", self.user)
            await message.add_reaction("❌")
            await message.reply(f"❌ Couldn't analyze screenshot: {e}")

    async def _handle_setrank_command(self, interaction: discord.Interaction, rank: str):
        """Handle /setrank command - set current rank"""
        if not self.memory:
            await interaction.response.send_message("❌ Memory system not initialized!", ephemeral=True)
            return

        profile = self.memory.load_profile(interaction.user.id)
        if not profile:
            await interaction.response.send_message(
                "❌ No profile found. Start a coaching session with `/coach` first!",
                ephemeral=True
            )
            return

        old_rank = profile.current_rank
        self.memory.update_rank(interaction.user.id, rank)

        embed = discord.Embed(
            title="📊 Rank Updated",
            color=discord.Color.blue()
        )
        embed.add_field(name="Previous", value=old_rank, inline=True)
        embed.add_field(name="Current", value=rank, inline=True)
        embed.add_field(name="Target", value=profile.target_rank, inline=True)

        # Calculate ranks to go
        profile = self.memory.load_profile(interaction.user.id)
        current_val = self.memory._rank_value(rank)
        target_val = self.memory._rank_value(profile.target_rank)
        diff = target_val - current_val

        if diff > 0:
            embed.add_field(
                name="🎯 Journey",
                value=f"{diff} divisions to reach {profile.target_rank}!",
                inline=False
            )
        elif diff == 0:
            embed.add_field(
                name="🎉 Congratulations!",
                value="You've reached your target rank!",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    async def _handle_settarget_command(self, interaction: discord.Interaction, rank: str):
        """Handle /settarget command - set target rank"""
        if not self.memory:
            await interaction.response.send_message("❌ Memory system not initialized!", ephemeral=True)
            return

        profile = self.memory.load_profile(interaction.user.id)
        if not profile:
            await interaction.response.send_message(
                "❌ No profile found. Start a coaching session with `/coach` first!",
                ephemeral=True
            )
            return

        self.memory.set_goal(interaction.user.id, rank, goal_type="target_rank")

        embed = discord.Embed(
            title="🎯 Target Rank Set",
            description=f"Your new goal is **{rank}**!",
            color=discord.Color.gold()
        )
        embed.add_field(name="Current Rank", value=profile.current_rank, inline=True)
        embed.add_field(name="Target Rank", value=rank, inline=True)

        # Motivational message based on gap
        current_val = self.memory._rank_value(profile.current_rank)
        target_val = self.memory._rank_value(rank)
        diff = target_val - current_val

        if diff <= 0:
            embed.add_field(
                name="💡",
                value="You're already at or above this rank! Set a higher goal?",
                inline=False
            )
        elif diff <= 4:
            embed.add_field(
                name="💪",
                value="That's a realistic goal! A few focused weeks of practice should get you there.",
                inline=False
            )
        elif diff <= 8:
            embed.add_field(
                name="🔥",
                value="Ambitious! This will take dedication, but it's totally achievable.",
                inline=False
            )
        else:
            embed.add_field(
                name="🚀",
                value="Big dreams! Let's break this into smaller milestones and climb together.",
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    async def _handle_setgoal_command(self, interaction: discord.Interaction, goal: str):
        """Handle /setgoal command - set current focus goal"""
        if not self.memory:
            await interaction.response.send_message("❌ Memory system not initialized!", ephemeral=True)
            return

        profile = self.memory.load_profile(interaction.user.id)
        if not profile:
            await interaction.response.send_message(
                "❌ No profile found. Start a coaching session with `/coach` first!",
                ephemeral=True
            )
            return

        self.memory.set_goal(interaction.user.id, goal, goal_type="current")
        self.memory.add_coaching_note(interaction.user.id, f"Set new focus goal: {goal}")

        embed = discord.Embed(
            title="🎯 Goal Updated",
            description=f"**New Focus:** {goal}",
            color=discord.Color.green()
        )
        embed.set_footer(text="Your missions will now focus on this goal!")

        await interaction.response.send_message(embed=embed)

    async def _handle_profile_command(self, interaction: discord.Interaction):
        """Handle /profile command - show player profile"""
        if not self.memory:
            await interaction.response.send_message("❌ Memory system not initialized!", ephemeral=True)
            return

        profile = self.memory.load_profile(interaction.user.id)
        if not profile:
            await interaction.response.send_message(
                "❌ No profile found. Start a coaching session with `/coach` first!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📋 {interaction.user.display_name}'s Coach Profile",
            color=discord.Color.blue()
        )

        # Rank section
        embed.add_field(
            name="📊 Rank",
            value=f"**Current:** {profile.current_rank}\n**Target:** {profile.target_rank}\n**Peak:** {profile.peak_rank}",
            inline=True
        )

        # Goals section
        embed.add_field(
            name="🎯 Current Focus",
            value=profile.current_goal[:100] or "Not set",
            inline=True
        )

        # Stats section
        success_rate = self.memory._calc_success_rate(profile)
        embed.add_field(
            name="📈 Stats",
            value=f"**Sessions:** {profile.sessions_count}\n**Missions:** {profile.missions_completed}✅ / {profile.missions_failed}❌\n**Success Rate:** {success_rate}%",
            inline=True
        )

        # Strengths & Weaknesses
        if profile.strengths:
            embed.add_field(
                name="💪 Strengths",
                value="\n".join(f"• {s}" for s in profile.strengths[:3]),
                inline=True
            )

        if profile.weaknesses:
            embed.add_field(
                name="⚠️ Weaknesses",
                value="\n".join(f"• {w}" for w in profile.weaknesses[:3]),
                inline=True
            )

        # Recent milestone
        if profile.milestones:
            embed.add_field(
                name="🏆 Latest Milestone",
                value=profile.milestones[-1],
                inline=False
            )

        embed.set_footer(text=f"Coaching since {profile.created_at[:10]} | Last session: {profile.last_session[:10]}")

        await interaction.response.send_message(embed=embed)

    async def _handle_progress_command(self, interaction: discord.Interaction):
        """Handle /progress command - show detailed progress"""
        if not self.memory:
            await interaction.response.send_message("❌ Memory system not initialized!", ephemeral=True)
            return

        profile = self.memory.load_profile(interaction.user.id)
        if not profile:
            await interaction.response.send_message(
                "❌ No profile found. Start a coaching session with `/coach` first!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📈 Progress Report",
            description=f"Journey from **{profile.current_rank}** to **{profile.target_rank}**",
            color=discord.Color.gold()
        )

        # Progress bar
        current_val = self.memory._rank_value(profile.current_rank)
        target_val = self.memory._rank_value(profile.target_rank)
        start_val = self.memory._rank_value("Iron IV")

        if target_val > start_val:
            progress = ((current_val - start_val) / (target_val - start_val)) * 100
            progress = min(100, max(0, progress))
            filled = int(progress / 10)
            bar = "█" * filled + "░" * (10 - filled)
            embed.add_field(
                name="🎯 Rank Progress",
                value=f"`{bar}` {progress:.0f}%",
                inline=False
            )

        # Mission stats
        total_missions = profile.missions_completed + profile.missions_failed
        if total_missions > 0:
            success_rate = (profile.missions_completed / total_missions) * 100
            embed.add_field(
                name="📋 Missions",
                value=f"**Completed:** {profile.missions_completed}\n**Failed:** {profile.missions_failed}\n**Success Rate:** {success_rate:.0f}%",
                inline=True
            )

        # Patterns identified
        if profile.patterns:
            embed.add_field(
                name="🔍 Patterns Identified",
                value="\n".join(f"• {p}" for p in profile.patterns[-5:]),
                inline=True
            )

        # Milestones
        if profile.milestones:
            embed.add_field(
                name="🏆 Milestones",
                value="\n".join(profile.milestones[-5:]),
                inline=False
            )

        # Recent notes
        if profile.coaching_notes:
            recent_notes = profile.coaching_notes[-3:]
            embed.add_field(
                name="📝 Recent Notes",
                value="\n".join(recent_notes),
                inline=False
            )

        await interaction.response.send_message(embed=embed)

    async def _handle_review_command(self, interaction: discord.Interaction):
        """Handle /review command - start Socratic VOD review"""
        await interaction.response.defer(thinking=True)

        try:
            from ..coach.vod_review import VODReviewManager

            vod_manager = VODReviewManager()

            # Get player ID from database
            db = await get_database()
            player_repo = PlayerRepository(db)
            player = await player_repo.get_by_discord_id(interaction.user.id)

            if not player:
                await interaction.followup.send(
                    "❌ No profile found. Start a coaching session with `/coach` first!",
                    ephemeral=True
                )
                return

            # Get reviewable deaths
            moments = await vod_manager.get_reviewable_deaths(player["id"], limit=3)

            if not moments:
                await interaction.followup.send(
                    "📭 No deaths to review yet!\n\n"
                    "Play some games first, then I'll find moments worth reviewing together.",
                    ephemeral=True
                )
                return

            # Show options
            embed = discord.Embed(
                title="🎬 VOD Review - Choose a Moment",
                description=(
                    "Select a death to review together. I'll ask questions to help you "
                    "discover what you could have done differently.\n\n"
                    "**How it works:**\n"
                    "1. Go to the timestamp in your replay\n"
                    "2. I'll ask you a question about what happened\n"
                    "3. Share your thoughts and we'll explore together"
                ),
                color=discord.Color.blue()
            )

            for i, moment in enumerate(moments):
                pattern_tag = f" [{moment.pattern_key.replace('_', ' ')}]" if moment.pattern_key else ""
                embed.add_field(
                    name=f"{i+1}. ⏱️ {moment.timestamp_formatted} - {moment.killer_champion}{pattern_tag}",
                    value=(
                        f"**Context:** {moment.context}\n"
                        f"**Question:** {moment.socratic_question}"
                    ),
                    inline=False
                )

            embed.set_footer(
                text="Reply with the number (1, 2, or 3) to start reviewing that moment"
            )

            await interaction.followup.send(embed=embed)

            # Store moments for follow-up (in a simple in-memory way for now)
            # In production, you'd use a proper session store
            if not hasattr(self, '_review_sessions'):
                self._review_sessions = {}
            self._review_sessions[interaction.user.id] = moments

        except Exception as e:
            logger.exception(f"Error in review command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    async def _handle_patterns_command(self, interaction: discord.Interaction):
        """Handle /patterns command - show detected patterns"""
        await interaction.response.defer(thinking=True)

        try:
            # Get pattern summary from memory
            pattern_summary = await self.memory.get_pattern_summary(interaction.user.id)

            embed = discord.Embed(
                title="🔍 Your Detected Patterns",
                description=(
                    "These are recurring behaviors I've noticed in your gameplay.\n"
                    "🔴 Active | 🟡 Improving | 🟢 Broken"
                ),
                color=discord.Color.purple()
            )

            embed.add_field(
                name="Patterns",
                value=pattern_summary,
                inline=False
            )

            embed.add_field(
                name="💡 What This Means",
                value=(
                    "**Active:** Still happening regularly\n"
                    "**Improving:** Getting better (3+ games without)\n"
                    "**Broken:** You've overcome this! (5+ games without)"
                ),
                inline=False
            )

            embed.set_footer(text="Use /review to work on these patterns with Socratic coaching")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.exception(f"Error in patterns command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    async def _handle_coach_command_with_context(
        self,
        interaction: discord.Interaction,
        riot_id: str,
        platform: str,
        focus: str
    ):
        """
        Enhanced /coach command that includes pattern context and session continuity.
        This replaces the original _handle_coach_command method.
        """
        await interaction.response.defer(thinking=True)

        try:
            self.coaching_channel = interaction.channel

            from ..api.riot import RiotAPIClient
            from ..coach.claude_coach import CoachingClient, extract_match_summary
            from ..coach.intents import PlayerIntent, CoachingIntent

            riot_client = RiotAPIClient()

            await interaction.followup.send(f"🔍 Looking up **{riot_id}** on **{platform}**...")

            if "#" not in riot_id:
                await interaction.followup.send(
                    "❌ Invalid Riot ID format. Use `Name#TAG` (e.g., `Player#BR1`)"
                )
                return

            game_name, tag_line = riot_id.rsplit("#", 1)

            account = await riot_client.get_account_by_riot_id(game_name, tag_line, platform)
            matches = await riot_client.get_match_history(account["puuid"], platform, count=10)

            if not matches:
                await interaction.followup.send("❌ No recent matches found. Play some games first!")
                return

            summaries = []
            for match_id in matches[:10]:
                try:
                    match_data = await riot_client.get_match(match_id, platform)
                    summary = extract_match_summary(match_data, account["puuid"])
                    summaries.append(summary)
                except Exception as e:
                    logger.warning(f"Failed to process match {match_id}: {e}")

            if not summaries:
                await interaction.followup.send("❌ Couldn't process any matches.")
                return

            intent = PlayerIntent(
                intent=CoachingIntent(focus),
                specific_champion=None,
                specific_question=None
            )

            profile = self.memory.get_or_create_profile(
                discord_id=interaction.user.id,
                discord_name=interaction.user.display_name,
                riot_id=riot_id,
                platform=platform
            )

            self.memory.set_goal(interaction.user.id, focus, goal_type="current")

            # Get coaching context with patterns and session opener
            coaching_context = await self.memory.get_coaching_context(interaction.user.id)

            coach = CoachingClient()

            # Pass coaching context for Socratic, pattern-aware coaching
            analysis = coach.analyze_matches(
                matches=summaries,
                player_name=game_name,
                rank=profile.current_rank,
                intent=intent,
                coaching_context=coaching_context  # NEW: includes patterns, opener
            )

            # Generate mission - from pattern if available
            db = await get_database()
            player_repo = PlayerRepository(db)
            pattern_repo = PatternRepository(db)

            player = await player_repo.get_or_create(
                interaction.user.id, riot_id, platform
            )

            priority_pattern = await pattern_repo.get_priority(player["id"])

            if priority_pattern:
                # Generate pattern-linked mission
                mission = await self.mission_tracker.generate_mission_from_pattern(
                    priority_pattern,
                    player["id"],
                    interaction.user.id
                )
            else:
                # Fallback to regular mission
                mission = await self.mission_tracker.generate_mission(
                    analysis, focus, user_id=interaction.user.id
                )

            # Record session
            await self.memory.record_session(
                discord_id=interaction.user.id,
                focus_area=focus,
                matches_analyzed=len(summaries)
            )

            self.memory.add_coaching_note(
                interaction.user.id,
                f"Started session focusing on {focus}. Analyzed {len(summaries)} matches."
            )

            embed = discord.Embed(
                title="🎮 Coaching Session Started",
                description=analysis[:1000] + "..." if len(analysis) > 1000 else analysis,
                color=discord.Color.blue()
            )

            # Add session opener if we have pattern progress
            if coaching_context.get("session_opener"):
                embed.insert_field_at(
                    0,
                    name="📊 Since Last Session",
                    value=coaching_context["session_opener"],
                    inline=False
                )

            # Show priority pattern if detected
            if priority_pattern:
                status_emoji = {
                    "active": "🔴",
                    "improving": "🟡",
                    "broken": "🟢",
                }.get(priority_pattern.get("status"), "⚪")

                embed.add_field(
                    name=f"{status_emoji} Focus Pattern",
                    value=f"**{priority_pattern.get('pattern_key', '').replace('_', ' ').title()}**\n{priority_pattern.get('description', '')[:100]}",
                    inline=False
                )

            embed.add_field(
                name="📊 Your Rank",
                value=f"**Current:** {profile.current_rank} → **Target:** {profile.target_rank}",
                inline=False
            )

            embed.add_field(
                name="📋 Your Mission",
                value=mission[:500] if len(mission) > 500 else mission,
                inline=False
            )

            embed.set_footer(text="Use /review to do Socratic VOD review | /patterns to see all patterns")

            await interaction.followup.send(embed=embed)
            logger.info(f"Started coaching session for {riot_id} (user {interaction.user.id})")

        except Exception as e:
            logger.exception(f"Error in coach command: {e}")
            await interaction.followup.send(f"❌ Error: {str(e)}")

    async def close(self):
        """Clean up when bot is shutting down"""
        await close_database()
        await super().close()


def run_bot():
    """Entry point to run the bot"""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError(
            "DISCORD_BOT_TOKEN not set! "
            "Get one at https://discord.com/developers/applications"
        )

    bot = CoachBot()
    bot.run(token)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_bot()
