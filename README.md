# LoL AI Coach

An AI-powered coaching system for League of Legends that analyzes your match history and provides personalized improvement recommendations.

## What Makes This Different

This is **NOT** another stats tracker. While apps like Blitz, Mobalytics, and Porofessor show you numbers and recommend builds, LoL AI Coach is a conversational AI that:

- **Understands your patterns** across multiple matches
- **Identifies your specific weaknesses** with concrete examples
- **Creates personalized drills** to address your issues
- **Focuses on what you want** with the intent system
- **Talks to you like a real coach** would
- **Voice-enabled Discord bot** with in-game overlay missions
- **Screenshot analysis** to verify your progress
- **Database-backed pattern tracking** that remembers across sessions
- **Socratic coaching method** that asks questions instead of lecturing
- **VOD review system** to analyze specific deaths with context

## Example Interaction

```
> python scripts/analyze_player.py "PlayerName#BR1" --platform br1

What would you like to focus on today?
1. Laning - CS, trading, wave management
2. Macro - Rotations, objectives, map awareness
3. Dying Less - Survivability and positioning
...

You: 1

Analyzing last 20 matches for PlayerName#BR1...

Found some patterns:

You died before 10 minutes in 14 of your last 20 games, averaging 2.1 early
deaths per game. Looking at the timeline data, most of these deaths happen
between 6-8 minutes when you're pushed up without vision.

Priority #1: Wave management for safety

When your wave is pushing toward enemy tower, you're vulnerable. Instead of
walking up for CS, let the wave push back to you.

Exercise: In your next 3 games, focus on one thing - don't walk past the
middle of the lane if you don't have a ward in river bush.

Want me to break down your teamfighting patterns, or focus more on laning?
```

## Quick Start

```bash
# Clone the repo
git clone https://github.com/yourusername/lol-ai-coach.git
cd lol-ai-coach

# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Run analysis
python scripts/analyze_player.py "YourName#TAG" --platform na1
```

## Getting API Keys

### Riot Games API (Free)
1. Go to https://developer.riotgames.com/
2. Sign in with your Riot account
3. Your development API key is on the dashboard
4. Note: Dev keys expire every 24 hours

### Anthropic Claude API
1. Go to https://console.anthropic.com/
2. Create an account and add credits
3. Generate an API key

### Discord Bot Token (for voice coaching)
1. Go to https://discord.com/developers/applications
2. Create a new application
3. Go to "Bot" section and create a bot
4. Copy the bot token
5. Enable these Privileged Gateway Intents:
   - Message Content Intent
   - Server Members Intent (optional)
6. Invite bot to your server with OAuth2 URL Generator:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Connect`, `Speak`, `Use Voice Activity`

## Discord Bot (Voice Coaching)

The Discord bot provides voice-enabled coaching with missions displayed via Discord's overlay.

### Setup

```bash
# Install Discord dependencies
pip install -e ".[discord]"

# Add to your .env
DISCORD_BOT_TOKEN=your-bot-token
DISCORD_GUILD_ID=your-server-id  # Optional, for faster command sync
WHISPER_MODEL=base  # tiny/base/small/medium/large

# Run the bot
python scripts/run_discord_bot.py
```

### Usage

1. **Enable Discord Overlay** in Discord settings (User Settings > Game Overlay)
2. **Join a voice channel** in your Discord server
3. Use slash commands:

| Command | Description |
|---------|-------------|
| `/coach PlayerName#TAG` | Start a coaching session |
| `/join` | Bot joins your voice channel |
| `/leave` | Bot leaves voice channel |
| `/mission` | Show current mission |
| `/check` | Upload screenshot to verify progress |
| `/complete` | Mark mission as complete |
| `/patterns` | View your detected patterns and status |
| `/review` | Start a Socratic VOD review session |

### Voice Commands

While in voice channel, you can say:
- "What's my mission?"
- "Check my progress"
- "Give me a new mission"
- "Mission complete"
- "How's my CS?"
- Any coaching question!

### How It Works

```
You speak → Whisper transcribes → Coach understands
                    ↓
         Claude generates mission
                    ↓
      Discord text (shows in overlay)
                    ↓
    You upload screenshot → Claude Vision analyzes
                    ↓
        Progress feedback in overlay
```

### Pattern Detection Flow

```
Match Timeline → Death Extraction → Pattern Detection → Mission Generation
       ↓                ↓                  ↓                    ↓
   Riot API      Position, wards,    Clustering by        "0 river deaths
                 gold diff, etc.     location/time         this game"
                        ↓                  ↓                    ↓
                   Database         Status Tracking      Auto-Verification
                   Storage       (active→improving→broken)
```

### Socratic VOD Review

The `/review` command walks you through deaths using the Socratic method:

```
Coach: "At 7:23, you died in river to their jungler. You were 300g ahead.
        What information did you have about where their jungler was?"

You:   "I didn't check the map..."

Coach: "Good awareness. What could you check before walking into river?"

You:   "I could look at which lanes have pressure, or if my jungler pinged"

Coach: "Exactly! When your lanes don't have pressure, the enemy jungler
        is more likely to be in your area. That's a great insight!"
```

## CLI Usage

```bash
# Basic analysis
python scripts/analyze_player.py "PlayerName#TAG" --platform br1

# Analyze more matches
python scripts/analyze_player.py "PlayerName#TAG" --platform na1 --matches 50

# Skip intent selection (direct focus)
python scripts/analyze_player.py "PlayerName#TAG" --intent laning

# Faster analysis (skip timeline data)
python scripts/analyze_player.py "PlayerName#TAG" --no-timeline

# Debug mode (verbose logging)
python scripts/analyze_player.py "PlayerName#TAG" --debug
```

### Available Intents

| Intent | Focus |
|--------|-------|
| `laning` | CS, trading, wave management |
| `macro` | Rotations, objectives, map awareness |
| `teamfighting` | Team engagement mechanics |
| `dying_less` | Survivability and positioning |
| `climbing` | General rank improvement |
| `champion_specific` | Master a specific champion |
| `mental` | Tilt management |
| `general` | Complete analysis |

## Docker Usage

```bash
# Build the image
docker build -t lol-ai-coach .

# Run analysis
docker run -it --env-file .env lol-ai-coach "PlayerName#TAG" --platform br1

# Run with docker-compose
docker-compose run coach "PlayerName#TAG" --platform br1
```

## Features

### Core Features
- Fetch player data by Riot ID
- Analyze up to 100 recent matches
- Timeline analysis for detailed death/event tracking
- AI-generated coaching with Claude
- Player intent system for focused coaching
- RAG knowledge base with coaching theory
- Interactive follow-up conversations

### Pattern Detection & Memory
- **Death extraction** with full context (position, ward state, gold diff)
- **7 pattern types** automatically detected:
  - `river_death_no_ward` - Dying in river without vision
  - `dies_when_ahead` - Throwing leads
  - `early_death_repeat` - Consistent early deaths
  - `caught_sidelane` - Getting caught while splitting
  - `tower_dive_death` - Failed tower dives
  - `teamfight_positioning` - Bad teamfight positioning
  - `objective_death` - Deaths during objective fights
- **Pattern status tracking**: Active → Improving → Broken
- **Session continuity**: "Last time you focused on X, you've improved!"
- **Pattern-linked missions**: Missions target YOUR failure patterns

### Socratic VOD Review
- **Reviews specific deaths** with full context
- **Asks questions instead of lecturing**: "What information did you have about their jungler?"
- **Detects breakthroughs**: Celebrates "aha" moments
- **Tracks player responses** for learning progress

### Production Infrastructure
- Structured logging (JSON for production, colored for dev)
- Comprehensive error handling with retry logic
- Input validation and sanitization
- Centralized configuration management
- Docker support with multi-stage builds
- GitHub Actions CI/CD pipeline
- Pre-commit hooks for code quality

## Project Structure

```
lol-ai-coach/
├── src/
│   ├── api/              # Riot API client
│   │   └── riot.py       # Rate-limited API calls
│   ├── analysis/         # Pattern detection
│   │   └── pattern_detector.py  # Death extraction & patterns
│   ├── coach/            # AI coaching logic
│   │   ├── claude_coach.py   # Claude integration (Socratic)
│   │   ├── intents.py        # Player intent system
│   │   ├── knowledge.py      # RAG knowledge loader
│   │   └── vod_review.py     # Socratic VOD review
│   ├── db/               # Database layer
│   │   ├── database.py       # Async SQLite connection
│   │   ├── repositories.py   # Data access layer
│   │   └── schema.sql        # Table definitions
│   ├── discord_bot/      # Discord integration
│   │   ├── bot.py            # Slash commands
│   │   ├── memory.py         # Player memory & context
│   │   └── missions.py       # Pattern-linked missions
│   ├── config.py         # Configuration management
│   ├── exceptions.py     # Custom exceptions
│   ├── logging_config.py # Structured logging
│   └── validation.py     # Input validation
├── knowledge/            # Coaching documents (RAG)
│   ├── core_theory.md
│   ├── fundamentals/
│   ├── macro/
│   └── mental/
├── scripts/
│   └── analyze_player.py # Main CLI entry point
├── tests/
│   ├── unit/
│   └── integration/
├── pyproject.toml        # Python packaging & tool config
├── Dockerfile
├── docker-compose.yml
└── .github/workflows/    # CI/CD
```

## Configuration

```bash
# .env
RIOT_API_KEY=RGAPI-xxxxx          # Your Riot API key
ANTHROPIC_API_KEY=sk-ant-xxxxx    # Your Claude API key

# Optional
APP_ENV=development               # development, staging, production
LOG_LEVEL=INFO                    # DEBUG, INFO, WARNING, ERROR
CLAUDE_MODEL=claude-sonnet-4-20250514  # Claude model to use
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/unit -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing

# Lint code
ruff check src/ tests/

# Format code
black src/ tests/

# Type check
mypy src/

# Install pre-commit hooks
pre-commit install
```

## Supported Regions

| Platform | Routing | Server |
|----------|---------|--------|
| na1 | americas | North America |
| br1 | americas | Brazil |
| la1 | americas | Latin America North |
| la2 | americas | Latin America South |
| euw1 | europe | EU West |
| eun1 | europe | EU Nordic & East |
| tr1 | europe | Turkey |
| ru | europe | Russia |
| kr | asia | Korea |
| jp1 | asia | Japan |
| oc1 | sea | Oceania |
| ph2 | sea | Philippines |
| sg2 | sea | Singapore |
| th2 | sea | Thailand |
| tw2 | sea | Taiwan |
| vn2 | sea | Vietnam |

## Contributing

Contributions welcome! Please:
1. Install pre-commit hooks: `pre-commit install`
2. Run tests before submitting: `pytest tests/`
3. See AGENT.md for technical details

## License

MIT

## Disclaimer

LoL AI Coach isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing League of Legends. League of Legends and Riot Games are trademarks or registered trademarks of Riot Games, Inc.
