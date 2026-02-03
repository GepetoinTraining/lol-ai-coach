# LoL AI Coach

An AI-powered coaching system for League of Legends that analyzes your match history and provides personalized improvement recommendations.

## What Makes This Different

This is **NOT** another stats tracker. While apps like Blitz, Mobalytics, and Porofessor show you numbers and recommend builds, LoL AI Coach is a conversational AI that:

- **Understands your patterns** across multiple matches
- **Identifies your specific weaknesses** with concrete examples
- **Creates personalized drills** to address your issues
- **Focuses on what you want** with the intent system
- **Talks to you like a real coach** would

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
│   ├── coach/            # AI coaching logic
│   │   ├── claude_coach.py   # Claude integration
│   │   ├── intents.py        # Player intent system
│   │   └── knowledge.py      # RAG knowledge loader
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
