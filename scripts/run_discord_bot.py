#!/usr/bin/env python3
"""
Run the LoL AI Coach Discord Bot

Usage:
    python scripts/run_discord_bot.py

Required environment variables:
    DISCORD_BOT_TOKEN - Your Discord bot token
    ANTHROPIC_API_KEY - Your Claude API key
    RIOT_API_KEY - Your Riot Games API key

Optional:
    DISCORD_GUILD_ID - Server ID for faster command sync
    WHISPER_MODEL - Whisper model size (tiny/base/small/medium/large)
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))

from dotenv import load_dotenv


def check_dependencies():
    """Check that required dependencies are installed"""
    missing = []

    try:
        import discord
    except ImportError:
        missing.append("discord.py[voice]")

    try:
        import anthropic
    except ImportError:
        missing.append("anthropic")

    try:
        import nacl
    except ImportError:
        missing.append("pynacl")

    if missing:
        print("❌ Missing dependencies:")
        for dep in missing:
            print(f"   - {dep}")
        print("\nInstall with:")
        print('   pip install -e ".[discord]"')
        sys.exit(1)


def check_environment():
    """Check that required environment variables are set"""
    import os

    required = {
        "DISCORD_BOT_TOKEN": "Discord bot token (https://discord.com/developers/applications)",
        "ANTHROPIC_API_KEY": "Claude API key (https://console.anthropic.com)",
        "RIOT_API_KEY": "Riot API key (https://developer.riotgames.com)",
    }

    missing = []
    for var, description in required.items():
        if not os.getenv(var):
            missing.append(f"   {var} - {description}")

    if missing:
        print("❌ Missing environment variables:")
        for m in missing:
            print(m)
        print("\nCreate a .env file or set these variables.")
        sys.exit(1)


def main():
    """Run the Discord bot"""
    # Load environment
    load_dotenv()

    print("🎮 LoL AI Coach - Discord Bot")
    print("=" * 40)

    # Check dependencies
    print("Checking dependencies...")
    check_dependencies()
    print("✅ Dependencies OK")

    # Check environment
    print("Checking environment...")
    check_environment()
    print("✅ Environment OK")

    # Import and run bot
    print("\nStarting bot...")
    print("-" * 40)

    from src.discord_bot.bot import run_bot
    run_bot()


if __name__ == "__main__":
    main()
