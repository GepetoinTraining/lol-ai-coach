#!/usr/bin/env python3
"""
LoL AI Coach - Player Analysis CLI

Usage:
    python analyze_player.py "GameName#TAG" --region americas --matches 20

Enhanced with:
- Death extraction with full context
- Pattern detection across games
- Socratic coaching style
- Session continuity
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.table import Table

# Load environment before imports that use config
load_dotenv()

from api.riot import RiotAPI, RiotAPIError, ACCOUNT_ROUTING
from coach.claude_coach import CoachingClient, extract_match_summary
from coach.intents import CoachingIntent, PlayerIntent, prompt_for_intent
from logging_config import setup_logging, get_logger, generate_correlation_id
from validation import validate_riot_id, validate_platform, validate_match_count
from exceptions import (
    LoLCoachError,
    ClaudeAPIError,
    InvalidRiotIDError,
    InvalidPlatformError,
    InvalidMatchCountError,
)
from analysis.pattern_detector import (
    extract_deaths_from_match,
    detect_patterns,
    check_pattern_status,
    get_priority_pattern,
)
from db import get_database, close_database
from db.repositories import (
    PlayerRepository,
    MatchRepository,
    DeathRepository,
    PatternRepository,
    SessionRepository,
)


console = Console()
logger = get_logger(__name__)


def get_rank_string(league_entries: list[dict]) -> str:
    """Extract rank string from league entries"""
    for entry in league_entries:
        if entry.get("queueType") == "RANKED_SOLO_5x5":
            return f"{entry['tier']} {entry['rank']}"
    return "Unranked"


async def analyze_player(
    riot_id: str,
    platform: str = "br1",
    match_count: int = 20,
    include_timeline: bool = True,
    intent: PlayerIntent = None,
    interactive_intent: bool = True,
    discord_id: int = 0
):
    """
    Full player analysis pipeline with database spine

    NEW FLOW:
    1. Fetch matches with timeline (existing)
    2. Extract deaths with full context -> store in SQLite (NEW)
    3. Run pattern detection -> update patterns table (NEW)
    4. Check pattern status vs last session (NEW)
    5. Generate session opener with continuity (NEW)
    6. Analyze with Socratic prompts (UPDATED)
    7. Offer VOD review or mission based on priority pattern (NEW)

    Args:
        riot_id: Player's Riot ID (Name#TAG)
        platform: Server platform (na1, br1, euw1, etc.)
        match_count: Number of matches to analyze
        include_timeline: Whether to fetch detailed timeline data
        intent: Optional pre-configured PlayerIntent
        interactive_intent: Whether to prompt for intent interactively
        discord_id: Optional Discord user ID for database linking
    """
    # Generate correlation ID for this analysis session
    corr_id = generate_correlation_id()
    logger.info("Starting player analysis session", extra={"riot_id": riot_id[:10] + "..."})

    # Validate inputs
    try:
        game_name, tag_line = validate_riot_id(riot_id)
        platform = validate_platform(platform)
        match_count = validate_match_count(match_count)
    except (InvalidRiotIDError, InvalidPlatformError, InvalidMatchCountError) as e:
        console.print(f"\n[red]Validation Error: {e.message}[/red]")
        logger.warning(f"Validation failed: {e.message}")
        return

    region = ACCOUNT_ROUTING.get(platform.lower(), "americas")

    console.print(Panel.fit(
        f"[bold cyan]LoL AI Coach[/bold cyan]\n"
        f"Analyzing: {game_name}#{tag_line}\n"
        f"Region: {platform.upper()} ({region})",
        border_style="cyan"
    ))

    riot_api = RiotAPI()
    coach = CoachingClient()

    # Get player intent if not provided
    if intent is None and interactive_intent:
        intent = prompt_for_intent()
        console.print(f"\n[cyan]Coaching focus:[/cyan] {intent.description}\n")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # Step 1: Get player info
            task = progress.add_task("Looking up player...", total=None)
            logger.info("Fetching player info", extra={"game_name": game_name, "platform": platform})

            player = await riot_api.get_player_full_info(game_name, tag_line, platform)
            progress.update(task, completed=True)

            puuid = player["account"]["puuid"]
            rank = get_rank_string(player.get("league", []))

            console.print(f"\n[green]Found:[/green] {player['account']['gameName']}#{player['account']['tagLine']}")
            console.print(f"  Level: {player['summoner']['summonerLevel']}")
            console.print(f"  Rank: {rank}")

            logger.info("Player found", extra={"rank": rank, "level": player['summoner']['summonerLevel']})

            # Step 2: Fetch matches
            task = progress.add_task(f"Fetching last {match_count} matches...", total=None)
            logger.info(f"Fetching {match_count} matches", extra={"include_timeline": include_timeline})

            matches = await riot_api.get_recent_matches_with_details(
                puuid,
                region,
                count=match_count,
                include_timeline=include_timeline
            )
            progress.update(task, completed=True)

            console.print(f"[green]Retrieved {len(matches)} matches[/green]")
            logger.info(f"Fetched {len(matches)} matches")

            # Step 3: Extract summaries
            task = progress.add_task("Processing match data...", total=None)
            summaries = []
            skipped = 0

            for match in matches:
                try:
                    summary = extract_match_summary(match, puuid)
                    summaries.append(summary)
                except Exception as e:
                    skipped += 1
                    logger.warning(f"Skipped match: {e}")

            progress.update(task, completed=True)

            console.print(f"[green]Processed {len(summaries)} matches[/green]")
            if skipped > 0:
                console.print(f"[yellow]Skipped {skipped} matches[/yellow]")

            # Step 4: Initialize database and extract deaths
            task = progress.add_task("Connecting to database...", total=None)
            db = await get_database()
            player_repo = PlayerRepository(db)
            match_repo = MatchRepository(db)
            death_repo = DeathRepository(db)
            pattern_repo = PatternRepository(db)
            session_repo = SessionRepository(db)
            progress.update(task, completed=True)

            # Get or create player in database
            task = progress.add_task("Setting up player profile...", total=None)
            player = await player_repo.get_or_create(
                discord_id=discord_id,
                riot_id=riot_id,
                platform=platform
            )
            await player_repo.update_puuid(player["id"], puuid)
            progress.update(task, completed=True)

            # Step 5: Extract deaths with full context
            task = progress.add_task("Extracting death context from timeline...", total=None)
            all_deaths = []
            matches_with_timeline = 0

            for match in matches:
                match_info = match.get("info", {})
                match_id = match.get("metadata", {}).get("matchId", "unknown")

                # Store match in database
                db_match = await match_repo.get_or_create(
                    match_id=match_id,
                    player_id=player["id"],
                    champion=next(
                        (p["championName"] for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        "Unknown"
                    ),
                    role=next(
                        (p.get("teamPosition", "UNKNOWN") for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        "UNKNOWN"
                    ),
                    win=next(
                        (p.get("win", False) for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        False
                    ),
                    kills=next(
                        (p.get("kills", 0) for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        0
                    ),
                    deaths=next(
                        (p.get("deaths", 0) for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        0
                    ),
                    assists=next(
                        (p.get("assists", 0) for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        0
                    ),
                    cs=next(
                        (p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0)
                         for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        0
                    ),
                    vision_score=next(
                        (p.get("visionScore", 0) for p in match_info.get("participants", [])
                         if p.get("puuid") == puuid),
                        0
                    ),
                    game_duration_sec=match_info.get("gameDuration", 0),
                    played_at=None  # Could parse from gameStartTimestamp
                )

                # Extract deaths if timeline available
                if "timeline" in match:
                    matches_with_timeline += 1
                    deaths = extract_deaths_from_match(match, match["timeline"], puuid)

                    for death in deaths:
                        death_data = death.to_dict()
                        death_data["match_db_id"] = db_match["id"]
                        death_data["player_id"] = player["id"]
                        await death_repo.insert(death_data)
                        all_deaths.append(death)

            progress.update(task, completed=True)
            console.print(f"[green]Extracted {len(all_deaths)} deaths from {matches_with_timeline} matches[/green]")

            # Step 6: Detect patterns
            task = progress.add_task("Detecting patterns...", total=None)
            existing_patterns = await pattern_repo.get_all(player["id"])
            pattern_updates = detect_patterns(all_deaths, existing_patterns)

            for update in pattern_updates:
                await pattern_repo.upsert(player["id"], update["pattern_key"], update)

            # Update games_since_last for all patterns
            await pattern_repo.increment_games_since(player["id"])

            active_patterns = await pattern_repo.get_active(player["id"])
            priority_pattern = get_priority_pattern(active_patterns)
            progress.update(task, completed=True)

            # Display patterns
            if active_patterns:
                console.print(f"\n[bold yellow]Detected Patterns:[/bold yellow]")
                for p in active_patterns[:3]:
                    status_emoji = {"active": "🔴", "improving": "🟡", "broken": "🟢"}.get(p.get("status"), "⚪")
                    console.print(f"  {status_emoji} {p.get('pattern_key', '').replace('_', ' ').title()}: {p.get('description', '')[:60]}")

            # Step 7: Get session opener
            task = progress.add_task("Checking session history...", total=None)
            last_session = await session_repo.get_last(player["id"])

            session_opener = ""
            if last_session:
                focus = last_session.get("focus_area", "")
                if focus:
                    session_opener = f"Last time we talked about {focus}. "

            if priority_pattern and priority_pattern.get("improvement_streak", 0) > 0:
                session_opener += f"Your {priority_pattern.get('pattern_key', '').replace('_', ' ')} has been improving - {priority_pattern.get('improvement_streak')} games without triggering!"

            progress.update(task, completed=True)

            # Build coaching context
            coaching_context = {
                "active_patterns": active_patterns,
                "pattern_progress": {
                    p.get("pattern_key"): {
                        "occurrences": p.get("occurrences", 0),
                        "status": p.get("status"),
                        "improvement_streak": p.get("improvement_streak", 0),
                        "games_since_last": p.get("games_since_last", 0),
                    }
                    for p in active_patterns
                },
                "last_session": last_session,
                "session_opener": session_opener,
            }

            # Step 8: Generate coaching analysis with Socratic prompts
            focus_msg = f"(focused on {intent.description})" if intent else ""
            task = progress.add_task(f"AI Coach analyzing your gameplay {focus_msg}...", total=None)

            logger.info("Generating coaching analysis", extra={"intent": intent.intent.value if intent else None})

            analysis = coach.analyze_matches(
                matches=summaries,
                player_name=f"{game_name}#{tag_line}",
                rank=rank,
                intent=intent,
                coaching_context=coaching_context  # NEW: pattern-aware, Socratic
            )
            progress.update(task, completed=True)

            # Record session
            await session_repo.create(
                player_id=player["id"],
                focus_area=intent.intent.value if intent else "general",
                matches_analyzed=len(summaries)
            )

        # Display results
        console.print("\n")
        console.print(Panel(
            Markdown(analysis),
            title="[bold green]Coaching Analysis[/bold green]",
            border_style="green",
            padding=(1, 2)
        ))

        logger.info("Analysis complete, entering interactive mode")

        # Interactive follow-up
        console.print("\n[dim]Ask follow-up questions (or 'quit' to exit):[/dim]\n")

        conversation_history = []

        while True:
            try:
                user_input = console.input("[bold cyan]You:[/bold cyan] ")
            except (KeyboardInterrupt, EOFError):
                break

            if user_input.lower() in ["quit", "exit", "q"]:
                break

            if not user_input.strip():
                continue

            with Progress(
                SpinnerColumn(),
                TextColumn("Thinking..."),
                console=console,
                transient=True
            ) as progress:
                progress.add_task("", total=None)

                try:
                    response = coach.chat(
                        player_context=analysis,
                        user_message=user_input,
                        conversation_history=conversation_history
                    )
                except ClaudeAPIError as e:
                    console.print(f"\n[red]Coach Error: {e.message}[/red]")
                    logger.error(f"Chat error: {e.message}")
                    continue

            # Update history
            conversation_history.append({"role": "user", "content": user_input})
            conversation_history.append({"role": "assistant", "content": response})

            console.print(f"\n[bold green]Coach:[/bold green]")
            console.print(Markdown(response))
            console.print()

        console.print("\n[dim]Good luck on the Rift![/dim]\n")
        logger.info("Session ended")

    except RiotAPIError as e:
        logger.error(f"Riot API error: {e.status_code} - {e.message}")

        if e.status_code == 404:
            console.print(f"\n[red]Player not found: {riot_id}[/red]")
            console.print("[dim]Check the spelling and make sure you're using the correct region.[/dim]")
        elif e.status_code == 401:
            console.print(f"\n[red]Invalid API key[/red]")
            console.print("[dim]Check your RIOT_API_KEY in .env file.[/dim]")
        elif e.status_code == 403:
            console.print(f"\n[red]API key expired or forbidden[/red]")
            console.print("[dim]Development API keys expire every 24 hours. Get a new one at developer.riotgames.com[/dim]")
        elif e.status_code == 429:
            console.print(f"\n[red]Rate limited by Riot API[/red]")
            console.print("[dim]Wait a minute and try again.[/dim]")
        else:
            console.print(f"\n[red]API Error: {e.message}[/red]")

    except ClaudeAPIError as e:
        logger.error(f"Claude API error: {e.message}")
        console.print(f"\n[red]Coach Error: {e.message}[/red]")

        if e.status_code == 401:
            console.print("[dim]Check your ANTHROPIC_API_KEY in .env file.[/dim]")
        elif e.status_code == 429:
            console.print("[dim]AI is busy - wait a moment and try again.[/dim]")

    except LoLCoachError as e:
        logger.error(f"Application error: {e.message}")
        console.print(f"\n[red]Error: {e.message}[/red]")

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        console.print(f"\n[red]Unexpected Error: {e}[/red]")
        raise

    finally:
        await riot_api.close()
        await close_database()


def main():
    parser = argparse.ArgumentParser(
        description="LoL AI Coach - Analyze your gameplay and get personalized coaching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python analyze_player.py "Faker#KR1" --platform kr
    python analyze_player.py "PlayerName#BR1" --platform br1 --matches 30
    python analyze_player.py "SummonerName#NA1" --platform na1 --no-timeline

Platforms:
    na1     North America
    br1     Brazil
    euw1    EU West
    eun1    EU Nordic & East
    kr      Korea
    jp1     Japan
    oc1     Oceania
        """
    )

    parser.add_argument(
        "riot_id",
        help="Player's Riot ID in format 'GameName#TAG'"
    )

    parser.add_argument(
        "--platform", "-p",
        default="br1",
        help="Server platform (default: br1)"
    )

    parser.add_argument(
        "--matches", "-m",
        type=int,
        default=20,
        help="Number of matches to analyze (default: 20, max: 100)"
    )

    parser.add_argument(
        "--no-timeline",
        action="store_true",
        help="Skip fetching detailed timeline data (faster but less detailed)"
    )

    parser.add_argument(
        "--intent", "-i",
        choices=[i.value for i in CoachingIntent],
        help="Coaching focus area (skip interactive selection)"
    )

    parser.add_argument(
        "--champion",
        help="Champion to focus on (for champion_specific intent)"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Initialize logging
    log_level = "DEBUG" if args.debug else os.getenv("LOG_LEVEL", "INFO")
    setup_logging(level=log_level)

    logger.info("LoL AI Coach starting", extra={"version": "0.1.0"})

    # Validate environment
    if not os.getenv("RIOT_API_KEY"):
        console.print("[red]RIOT_API_KEY not set[/red]")
        console.print("[dim]Copy .env.example to .env and add your API key[/dim]")
        sys.exit(1)

    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY not set[/red]")
        console.print("[dim]Copy .env.example to .env and add your API key[/dim]")
        sys.exit(1)

    # Build intent if provided
    intent = None
    if args.intent:
        intent = PlayerIntent(
            intent=CoachingIntent(args.intent),
            champion_focus=args.champion if args.intent == "champion_specific" else None
        )

    # Run analysis
    asyncio.run(analyze_player(
        riot_id=args.riot_id,
        platform=args.platform,
        match_count=args.matches,
        include_timeline=not args.no_timeline,
        intent=intent,
        interactive_intent=args.intent is None  # Only prompt if not specified
    ))


if __name__ == "__main__":
    main()
