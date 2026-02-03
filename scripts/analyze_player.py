#!/usr/bin/env python3
"""
LoL AI Coach - Player Analysis CLI

Usage:
    python analyze_player.py "GameName#TAG" --region americas --matches 20
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
    interactive_intent: bool = True
):
    """
    Full player analysis pipeline

    Args:
        riot_id: Player's Riot ID (Name#TAG)
        platform: Server platform (na1, br1, euw1, etc.)
        match_count: Number of matches to analyze
        include_timeline: Whether to fetch detailed timeline data
        intent: Optional pre-configured PlayerIntent
        interactive_intent: Whether to prompt for intent interactively
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

            # Step 4: Generate coaching analysis
            focus_msg = f"(focused on {intent.description})" if intent else ""
            task = progress.add_task(f"AI Coach analyzing your gameplay {focus_msg}...", total=None)

            logger.info("Generating coaching analysis", extra={"intent": intent.intent.value if intent else None})

            analysis = coach.analyze_matches(
                matches=summaries,
                player_name=f"{game_name}#{tag_line}",
                rank=rank,
                intent=intent
            )
            progress.update(task, completed=True)

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
